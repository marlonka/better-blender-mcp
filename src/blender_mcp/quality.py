"""Advisory model checks executed inside an isolated Blender worker.

This file deliberately has no package imports. Blender supplies bpy, bmesh and
NumPy; the MCP host does not need them. Checks are evidence, not an art score.
"""
from collections import Counter
from pathlib import Path
import time


def foreground_mask(pixels):
    """Single product on transparent or near-white background; fill row interiors."""
    import numpy as np
    alpha = pixels[..., 3]
    if np.any(alpha < .99):
        mask = alpha > .10
    else:
        mask = np.max(1 - pixels[..., :3], axis=2) > .06
    filled = np.zeros(mask.shape, dtype=bool)
    for y, row in enumerate(mask):
        xs = np.flatnonzero(row)
        if len(xs) >= 3:
            filled[y, xs[0]:xs[-1]+1] = True
    return filled


def compare_pixels(reference, rendered):
    """No resizing or alignment that could hide framing errors."""
    import numpy as np
    if reference.shape != rendered.shape:
        return {'comparable': False, 'reason': 'Image dimensions differ',
            'reference_size': list(reference.shape[1::-1]), 'render_size': list(rendered.shape[1::-1])}
    a, b = foreground_mask(reference), foreground_mask(rendered)
    if not a.any() or not b.any():
        return {'comparable': False, 'reason': 'No foreground under the stated background assumption'}
    def bounds(mask):
        y, x = np.where(mask)
        return [int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)]
    def white_composite(rgba):
        return rgba[..., :3] * rgba[..., 3:4] + 1 - rgba[..., 3:4]
    rgb_a, rgb_b = white_composite(reference), white_composite(rendered)
    delta = np.abs(rgb_a-rgb_b).mean(axis=2)
    union, intersection = a | b, a & b
    reference_box, render_box = bounds(a), bounds(b)
    bands = {}
    for name, rows in zip(('top', 'middle', 'bottom'), np.array_split(np.arange(a.shape[0]), 3)):
        selected = intersection[rows]
        if selected.any():
            bands[name] = round(float(delta[rows][selected].mean()), 5)
    return {'comparable': True,
        'assumption': 'Single product on transparent or near-white background; row-filled silhouette; no alignment',
        'silhouette_iou': round(float(intersection.sum()/union.sum()), 5),
        'reference_bbox_px': reference_box, 'render_bbox_px': render_box,
        'bbox_delta_px': [y-x for x, y in zip(reference_box, render_box)],
        'foreground_rgb_mae': round(float(delta[intersection].mean()), 5) if intersection.any() else None,
        'rgb_mae_by_image_third': bands,
        'channel_space': 'Normalized Blender image-buffer values; sRGB for the example PNGs',
        'clipped_white_foreground_fraction': round(float((rgb_b[b] >= .995).all(axis=1).mean()), 5)}


def _pixels(path):
    import bpy
    import numpy as np
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = image.size
        if not width or not height or width*height > 16_000_000:
            raise ValueError('Comparison images must contain 1-16,000,000 pixels')
        values = np.empty(width*height*image.channels, dtype=np.float32)
        image.pixels.foreach_get(values)
        values = values.reshape(height, width, image.channels)[::-1]
        if image.channels != 4:
            raise ValueError('Comparison needs RGBA images')
        return values
    finally:
        bpy.data.images.remove(image)


def _upstream_nodes(socket, seen=None):
    seen = set() if seen is None else seen
    result = []
    for link in socket.links:
        node = link.from_node
        if node.as_pointer() in seen:
            continue
        seen.add(node.as_pointer())
        result.append(node)
        for entry in node.inputs:
            result.extend(_upstream_nodes(entry, seen))
    return result


def audit_scene():
    import bpy
    import bmesh
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

    scene = bpy.context.scene
    subject = scene.get('better_mcp_subject')
    collection = bpy.data.collections.get(subject) if subject else None
    objects = sorted((o for o in (collection.all_objects if collection else scene.objects)
        if o.type == 'MESH' and not o.hide_render), key=lambda o: o.name)
    issues, rows = [], []
    def issue(code, target, detail, fix):
        issues.append(dict(code=code, target=str(target)[:128], detail=str(detail)[:256], fix=fix))
    if subject and not collection:
        issue('SUBJECT_MISSING', subject, 'Subject collection does not exist; checked the scene instead.', 'Set scene["better_mcp_subject"] to an existing collection.')
    materials = {slot.material for o in objects for slot in o.material_slots if slot.material}
    textured = set()
    for mat in sorted(materials, key=lambda m: m.name):
        if not mat.use_nodes or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                image = node.image
                if not image:
                    issue('MISSING_IMAGE', mat.name, 'Image texture has no image.', 'Assign the texture or remove the disconnected node.')
                elif image.source in {'FILE', 'TILED'} and not image.packed_file and not image.packed_files and not Path(bpy.path.abspath(image.filepath)).is_file():
                    issue('MISSING_IMAGE', mat.name, image.filepath, 'Restore the external image and pack the asset.')
            if node.type != 'BSDF_PRINCIPLED':
                continue
            for entry in node.inputs:
                if not entry.is_linked:
                    continue
                ancestors = _upstream_nodes(entry)
                if any(n.type == 'TEX_IMAGE' and not n.inputs['Vector'].is_linked for n in ancestors):
                    textured.add(mat.name)
                procedural = sorted({n.bl_idname for n in ancestors if n.type in {'TEX_NOISE', 'TEX_VORONOI', 'TEX_MUSGRAVE', 'TEX_WAVE', 'TEX_MAGIC', 'TEX_CHECKER', 'TEX_BRICK', 'BUMP', 'GROUP'}})
                if procedural:
                    issue('GLTF_BAKE_REQUIRED', mat.name, f'{entry.name}: {", ".join(procedural)}', 'Bake this shader input to an image before glTF export; compare the exported material.')
    for obj in objects[:200]:
        mesh = obj.data
        row = dict(name=obj.name, vertices=len(mesh.vertices), faces=len(mesh.polygons),
            triangles=sum(len(p.vertices)-2 for p in mesh.polygons), uv_layers=len(mesh.uv_layers))
        rows.append(row)
        if obj.matrix_world.determinant() < 0:
            issue('NEGATIVE_SCALE', obj.name, 'Negative world determinant.', 'Apply the mirror with correct winding before export.')
        if not obj.material_slots or any(s.material is None for s in obj.material_slots):
            issue('MATERIAL_UNASSIGNED', obj.name, 'Missing material slot.', 'Assign intentional materials to every visible surface.')
        if any(m.show_render for m in obj.modifiers):
            row['topology_scope'] = 'Base mesh; modifiers are not evaluated'
        if len(mesh.polygons) > 500_000:
            row['topology_skipped'] = 'Over 500,000 faces; bounded audit'
            continue
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            boundary = sum(e.is_boundary for e in bm.edges)
            non_manifold = sum(not e.is_manifold and not e.is_boundary for e in bm.edges)
            inconsistent = sum(e.is_manifold and not e.is_contiguous for e in bm.edges)
            # Face areas are local-space values; world scale must not change
            # whether the same authored face is considered degenerate.
            local_diagonal = sum((max(v[k] for v in obj.bound_box)-min(v[k] for v in obj.bound_box))**2 for k in range(3))
            tolerance = max(local_diagonal*1e-12, 1e-20)
            degenerate = sum(f.calc_area() <= tolerance for f in bm.faces)
            row.update(boundary_edges=boundary, non_manifold_edges=non_manifold,
                inconsistent_edges=inconsistent, degenerate_faces=degenerate)
            if boundary and not obj.get('better_mcp_open_surface', False):
                issue('OPEN_BOUNDARY', obj.name, f'{boundary} boundary edges.', 'Weld geometric seams and close the solid, or mark an intentional sheet with better_mcp_open_surface.')
            if non_manifold:
                issue('NON_MANIFOLD', obj.name, f'{non_manifold} wire or multiply shared edges.', 'Remove loose elements and repair edge connectivity.')
            if inconsistent:
                issue('NORMAL_WINDING', obj.name, f'{inconsistent} inconsistent adjacent edges.', 'Orient connected face winding consistently.')
            if degenerate:
                issue('DEGENERATE_FACES', obj.name, f'{degenerate} near-zero-area faces.', 'Collapse lathe poles to single vertices; remove zero-area faces.')
            if not boundary and not non_manifold and len(bm.faces) and bm.calc_volume(signed=True) < 0:
                issue('INVERTED_SOLID', obj.name, 'Closed mesh has negative signed volume.', 'Reverse face winding so solid normals point outward.')
        finally:
            bm.free()
        needs_uv = {i for i, s in enumerate(obj.material_slots) if s.material and s.material.name in textured}
        if needs_uv and not mesh.uv_layers:
            issue('UV_MISSING', obj.name, 'Image-driven material without a UV map.', 'Create UVs that preserve artwork scale and orientation.')
        elif needs_uv:
            uv = mesh.uv_layers.active.data
            collapsed = 0
            for face in mesh.polygons:
                if face.material_index not in needs_uv:
                    continue
                coords = [uv[i].uv for i in face.loop_indices]
                area = abs(sum(a.x*b.y-b.x*a.y for a, b in zip(coords, coords[1:]+coords[:1]))) / 2
                collapsed += area < 1e-12
            row['collapsed_textured_uv_faces'] = collapsed
            if collapsed:
                issue('UV_COLLAPSED', obj.name, f'{collapsed} textured faces have zero UV area.', 'Use planar UVs on caps and cylindrical UVs on walls.')
    if len(objects) > 200:
        issue('AUDIT_TRUNCATED', 'scene', f'{len(objects)-200} meshes omitted.', 'Audit smaller named subject collections.')
    camera = None
    if scene.camera and objects:
        projected = [world_to_camera_view(scene, scene.camera, o.matrix_world @ Vector(v)) for o in objects for v in o.bound_box]
        camera = dict(name=scene.camera.name, projection=scene.camera.data.type,
            subject_bbox_ndc=[round(min(p.x for p in projected), 4), round(min(p.y for p in projected), 4),
                round(max(p.x for p in projected), 4), round(max(p.y for p in projected), 4)],
            scope='Projected object bounding boxes; conservative, not visible silhouette')
        if any(p.z <= 0 for p in projected):
            issue('BEHIND_CAMERA', 'camera', 'Subject bounds intersect the camera plane.', 'Move the camera outside the subject.')
        if any(p.x < -.01 or p.x > 1.01 or p.y < -.01 or p.y > 1.01 for p in projected):
            issue('FRAMING_BOUNDS', 'camera', 'Subject bounding boxes extend beyond frame.', 'Check rendered pixels for unintended clipping.')
    elif not scene.camera:
        issue('CAMERA_MISSING', 'scene', 'No active render camera.', 'Set a reproducible camera before comparing reference pixels.')
    return dict(scope=subject if collection else 'render-enabled scene meshes',
        mesh_count=len(objects), checked_mesh_count=len(rows), material_count=len(materials),
        vertices=sum(len(o.data.vertices) for o in objects), triangles=sum(r['triangles'] for r in rows),
        issue_count=len(issues), issue_counts=dict(Counter(i['code'] for i in issues)),
        issues=issues, objects=rows, camera=camera,
        limits='Base mesh only; no self-intersection, UV overlap, shader equivalence or aesthetic-quality proof.')


def collect(config, outputs):
    import bpy
    started = time.perf_counter()
    outputs = dict(outputs) if isinstance(outputs, dict) else {}
    outputs.setdefault('blend', bpy.data.filepath)
    outputs.setdefault('render', bpy.path.abspath(bpy.context.scene.render.filepath))
    artifacts = {}
    for label, value in list(outputs.items())[:20]:
        if not isinstance(value, str) or not value or len(value) > 2048:
            continue
        path = Path(value).resolve()
        if path.is_file():
            artifacts[str(label)[:64]] = dict(path=str(path), bytes=path.stat().st_size,
                updated_this_run=path.stat().st_mtime >= config['started']-1)
    result = dict(version=1, blender=bpy.app.version_string, artifacts=artifacts)
    if config.get('audit', True):
        result['audit'] = audit_scene()
    if config.get('reference_path'):
        if 'render' not in artifacts:
            result['comparison'] = {'comparable': False, 'reason': 'No render artifact exists'}
        else:
            result['comparison'] = compare_pixels(_pixels(config['reference_path']), _pixels(artifacts['render']['path']))
            result['comparison']['render_updated_this_run'] = artifacts['render']['updated_this_run']
    result['audit_ms'] = round((time.perf_counter()-started)*1000, 2)
    return result

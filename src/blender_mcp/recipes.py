"""Reusable, deterministic geometry. Loaded as better_blender in workers."""
import math


def lathe_data(profile, segments=128, radial_scale=1.0, uv_radius=None, surfaces=None,
               uv_mode='cylinder', wall_uv_height=1.0):
    """Return welded vertices, faces, corner UVs and material indices.

    Profile is (radius, z), in scene units. Repeat the first point to close a
    hollow section; radius 0 creates one pole. Front is -Y, up is +Z. Per-segment
    surfaces map index to (material_index, projection). Projections: cylinder,
    planar, atlas_top, atlas_bottom. Atlas disks occupy the upper UV band;
    set wall_uv_height=.54 to keep wall artwork separate when baking.
    """
    if not isinstance(segments, int) or not 3 <= segments <= 512:
        raise ValueError('segments must be an integer from 3 to 512')
    if not 2 <= len(profile) <= 512:
        raise ValueError('profile must have 2-512 points')
    profile = [(float(r), float(z)) for r, z in profile]
    if any(not math.isfinite(r) or not math.isfinite(z) or r < 0 for r, z in profile):
        raise ValueError('Profile coordinates must be finite and radii nonnegative')
    if not math.isfinite(radial_scale) or radial_scale <= 0:
        raise ValueError('radial_scale must be finite and positive')
    if any(a == b for a, b in zip(profile, profile[1:])):
        raise ValueError('Consecutive duplicate profile points create degenerate faces')
    diameter = 2 * (uv_radius if uv_radius is not None else max(r for r, _ in profile)) * radial_scale
    if not math.isfinite(diameter) or diameter <= 0:
        raise ValueError('UV radius and at least one profile radius must be positive')
    if not math.isfinite(wall_uv_height) or not 0 < wall_uv_height <= 1:
        raise ValueError('wall_uv_height must be in (0, 1]')
    allowed = {'cylinder', 'planar', 'atlas_top', 'atlas_bottom'}
    if uv_mode not in allowed:
        raise ValueError('Unknown UV projection')
    surfaces = surfaces or {}
    for index, (material, mode) in surfaces.items():
        if not isinstance(index, int) or not 0 <= index < len(profile) or not isinstance(material, int) or material < 0 or mode not in allowed:
            raise ValueError('Invalid surface index, material index or UV projection')
    tolerance = max(1e-12, max(abs(v) for point in profile for v in point)*1e-8)
    closed = all(abs(a-b) <= tolerance for a,b in zip(profile[0], profile[-1]))
    if closed:
        profile = profile[:-1]
    verts, rings = [], []
    for r, z in profile:
        count = 1 if r == 0 else segments
        ring = []
        for j in range(count):
            theta = (j/segments-.5)*2*math.pi
            ring.append(len(verts))
            verts.append((0, 0, z) if count == 1 else (radial_scale*r*math.sin(theta), -radial_scale*r*math.cos(theta), z))
        rings.append(ring)
    faces, face_uvs, face_materials = [], [], []
    lo, hi = min(z for _, z in profile), max(z for _, z in profile)
    for i in range(len(profile) if closed else len(profile)-1):
        a, b = rings[i], rings[(i+1) % len(rings)]
        za, zb = profile[i][1], profile[(i+1) % len(profile)][1]
        if len(a) == len(b) == 1:
            continue
        material_id, projection = surfaces.get(i, (0, uv_mode))
        planar = projection != 'cylinder' or za == zb
        for j in range(segments):
            u0, u1 = j/segments, (j+1)/segments
            va, vb = (za-lo)/max(hi-lo, 1e-12), (zb-lo)/max(hi-lo, 1e-12)
            if len(a) == 1:
                face = (a[0], b[(j+1) % segments], b[j])
                coords = [((u0+u1)/2, va), (u1, vb), (u0, vb)]
            elif len(b) == 1:
                face = (a[j], a[(j+1) % segments], b[0])
                coords = [(u0, va), (u1, va), ((u0+u1)/2, vb)]
            else:
                face = (a[j], a[(j+1) % segments], b[(j+1) % segments], b[j])
                coords = [(u0, va), (u1, va), (u1, vb), (u0, vb)]
            if planar:
                coords = [(verts[v][0]/diameter+.5, .5+verts[v][1]/diameter) for v in face]
                if projection.startswith('atlas_'):
                    center = .25 if projection == 'atlas_top' else .75
                    coords = [(center+(x-.5)*.43, .775+(y-.5)*.43) for x, y in coords]
            else:
                coords = [(x, y*wall_uv_height) for x, y in coords]
            faces.append(face)
            face_uvs.append(coords)
            face_materials.append(material_id)
    if not faces:
        raise ValueError('Profile creates no surface')
    return verts, faces, face_uvs, face_materials


def lathe(name, profile, materials=None, collection=None, **options):
    """Create an editable Blender mesh from lathe_data; no context-sensitive operators."""
    import bpy
    data = lathe_data(profile, **options)
    verts, faces, corner_uvs, indices = data
    materials = [materials] if isinstance(materials, str) else (materials or [])
    slots = [bpy.data.materials[m] if isinstance(m, str) else m for m in materials]
    if slots and max(indices) >= len(slots):
        raise ValueError('Surface material index is outside provided materials')
    target = bpy.data.collections[collection] if isinstance(collection, str) else (collection or bpy.context.collection)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name='UVMap')
    for face, coords, material_id in zip(mesh.polygons, corner_uvs, indices):
        face.use_smooth = True
        face.material_index = material_id
        for loop, coord in zip(face.loop_indices, coords):
            layer.data[loop].uv = coord
    for material in slots:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    target.objects.link(obj)
    return obj


def pbr_material(name, color=(.5, .5, .5), roughness=.4, metallic=0):
    """Create Principled material. Color values are linear; returns (material, node)."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value = (*color, 1)
    node.inputs['Roughness'].default_value = roughness
    node.inputs['Metallic'].default_value = metallic
    mat.diffuse_color = (*color, 1)
    return mat, node


def point_at(obj, point):
    """Aim a camera or area light (-Z forward, Y up) at a world-space point."""
    from mathutils import Vector
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z', 'Y').to_euler()

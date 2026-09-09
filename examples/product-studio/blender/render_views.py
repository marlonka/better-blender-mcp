"""Three opaque white-background packshots from the existing, packed jar model.

Run in blender_worker with winternuesse.blend as blend_path. The live GUI and
the source model are untouched. WINTERNUESSE_PREVIEW=1 renders small proofs.
"""
from pathlib import Path
import json
import math
import os
import time

import bpy
from mathutils import Vector
from better_blender import point_at

PROJECT = Path(__file__).resolve().parents[1]
PREVIEW = os.environ.get('WINTERNUESSE_PREVIEW') == '1'
OUTPUT = PROJECT.parents[1] / '.local/product-view-previews' if PREVIEW else PROJECT / 'renders'
OUTPUT.mkdir(parents=True, exist_ok=True)
SCENE = bpy.context.scene
SCENE.name = 'Winternuesse | White studio views'
SCENE['better_mcp_subject'] = 'Product'
SCENE.render.engine = 'CYCLES'
SCENE.cycles.samples = 32 if PREVIEW else 128
SCENE.cycles.use_denoising = True
SCENE.cycles.use_adaptive_sampling = True
SCENE.cycles.adaptive_threshold = .025 if PREVIEW else .008
SCENE.cycles.max_bounces = 16
SCENE.cycles.transmission_bounces = 12
SCENE.render.resolution_x = 640 if PREVIEW else 1600
SCENE.render.resolution_y = 720 if PREVIEW else 1800
SCENE.render.resolution_percentage = 100
SCENE.render.film_transparent = True
SCENE.render.image_settings.file_format = 'PNG'
SCENE.render.image_settings.color_mode = 'RGB'
SCENE.render.image_settings.color_depth = '8'
SCENE.render.image_settings.compression = 30
SCENE.view_settings.view_transform = 'Standard'
SCENE.view_settings.look = 'None'
SCENE.view_settings.exposure = 0
SCENE.view_settings.gamma = 1

# The reference's near-tangent pixels contain its white backdrop. Fade that
# narrow, uncertain strip into the existing inferred back colors in the shader.
# This leaves all readable front artwork and the source model file intact.
label = bpy.data.materials['Label | original front artwork']
nodes, links = label.node_tree.nodes, label.node_tree.links
texture = next(n for n in nodes if n.type == 'TEX_IMAGE')
coordinates = nodes.new('ShaderNodeTexCoord')
separate = nodes.new('ShaderNodeSeparateXYZ')
links.new(coordinates.outputs['UV'], separate.inputs[0])
center = nodes.new('ShaderNodeMath'); center.operation = 'SUBTRACT'
center.inputs[1].default_value = .5
links.new(separate.outputs['X'], center.inputs[0])
distance = nodes.new('ShaderNodeMath'); distance.operation = 'ABSOLUTE'
links.new(center.outputs[0], distance.inputs[0])
fade = nodes.new('ShaderNodeMapRange')
fade.interpolation_type = 'SMOOTHERSTEP'
fade.inputs['From Min'].default_value = .195
fade.inputs['From Max'].default_value = .225
links.new(distance.outputs[0], fade.inputs['Value'])
back = nodes.new('ShaderNodeValToRGB')
def linear(color):
    return tuple((c/255/12.92 if c/255 <= .04045 else ((c/255+.055)/1.055)**2.4) for c in color) + (1,)
back.color_ramp.elements[0].position = .375
back.color_ramp.elements[0].color = linear((204,92,53))
back.color_ramp.elements[1].position = .43
back.color_ramp.elements[1].color = linear((158,35,29))
links.new(separate.outputs['Y'], back.inputs[0])
mix = nodes.new('ShaderNodeMixRGB')
links.new(fade.outputs['Result'], mix.inputs[0])
links.new(texture.outputs['Color'], mix.inputs[1])
links.new(back.outputs['Color'], mix.inputs[2])
links.new(mix.outputs['Color'], nodes['Principled BSDF'].inputs['Base Color'])

# Composite the actual Cycles image and contact shadow onto exact sRGB white.
tree = bpy.data.node_groups.new('Packshot | opaque white background', 'CompositorNodeTree')
tree.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
render_layer = tree.nodes.new('CompositorNodeRLayers')
over = tree.nodes.new('CompositorNodeAlphaOver')
over.inputs['Factor'].default_value = 1
over.inputs['Background'].default_value = (1, 1, 1, 1)
output_node = tree.nodes.new('NodeGroupOutput')
tree.links.new(render_layer.outputs['Image'], over.inputs['Foreground'])
tree.links.new(over.outputs['Image'], output_node.inputs['Image'])
SCENE.compositing_node_group = tree

studio = bpy.data.collections['Studio']
bottom = min((obj.matrix_world @ Vector(corner)).z
             for obj in bpy.data.collections['Product'].objects for corner in obj.bound_box)
ground_mesh = bpy.data.meshes.new('Contact shadow | plane')
ground_mesh.from_pydata([(-1,-1,bottom), (1,-1,bottom), (1,1,bottom), (-1,1,bottom)], [], [(0,1,2,3)])
ground = bpy.data.objects.new('Contact shadow | matte white floor', ground_mesh)
studio.objects.link(ground)
ground.is_shadow_catcher = True
ground_mat = bpy.data.materials.new('Contact shadow | white')
ground_mat.use_nodes = True
ground_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (1,1,1,1)
ground_mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .9
ground.data.materials.append(ground_mat)

views = [('frontal', 0, 7), ('links', -28, 14), ('rechts', 30, 21)]
manifest = {'source': 'public/assets/winternuesse.blend', 'engine': 'Cycles',
            'samples': SCENE.cycles.samples, 'background': '#FFFFFF',
            'material_adjustment': 'Render-only fade of contaminated tangent pixels into inferred back colors; front artwork unchanged.',
            'views': []}
BETTER_BLENDER_OUTPUTS = {}
cameras = {}
for name, azimuth, elevation in views:
    data = bpy.data.cameras.new('Packshot | ' + name)
    camera = bpy.data.objects.new(data.name, data)
    studio.objects.link(camera)
    a, e = math.radians(azimuth), math.radians(elevation)
    target = Vector((0, 0, .0465))
    camera.location = target + Vector((math.sin(a)*math.cos(e), -math.cos(a)*math.cos(e), math.sin(e))) * .65
    point_at(camera, target)
    data.type = 'ORTHO'
    data.ortho_scale = .134
    data.lens = 70
    data.clip_start = .001
    data.clip_end = 10
    cameras[name] = camera
    SCENE.camera = camera
    path = OUTPUT / ('winternuesse-' + name + '.png')
    SCENE.render.filepath = str(path)
    started = time.monotonic()
    bpy.ops.render.render(write_still=True)
    manifest['views'].append({'name': name, 'file': path.name, 'azimuth_degrees': azimuth,
                              'elevation_degrees': elevation, 'camera': camera.name,
                              'render_seconds': round(time.monotonic()-started, 2)})
    BETTER_BLENDER_OUTPUTS[name] = str(path)
    print(json.dumps(manifest['views'][-1]), flush=True)

SCENE.camera = cameras['frontal']
SCENE.render.filepath = str(OUTPUT / 'winternuesse-frontal.png')
manifest['resolution'] = [SCENE.render.resolution_x, SCENE.render.resolution_y]
manifest_path = OUTPUT / 'views.json'
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
BETTER_BLENDER_OUTPUTS['views'] = str(manifest_path)
if not PREVIEW:
    blend_path = OUTPUT / 'winternuesse-studio.blend'
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    BETTER_BLENDER_OUTPUTS['blend'] = str(blend_path)

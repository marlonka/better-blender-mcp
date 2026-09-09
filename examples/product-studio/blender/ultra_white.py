"""Apply the fictional Ultra White label to the packed jar and render three views.

Run with blender_worker, loading renders/winternuesse-studio.blend first.
The existing geometry, cameras and white studio are reused. Heavy
work stays in the disposable worker; original product files remain available.
"""
from pathlib import Path
import json
import math
import os
import time

import bpy

PROJECT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT / 'ultra-white'
PREVIEW = os.environ.get('ULTRA_WHITE_PREVIEW') == '1'
OUTPUT = PROJECT.parents[1] / '.local/ultra-white-previews' if PREVIEW else ASSETS
OUTPUT.mkdir(parents=True, exist_ok=True)
SCENE = bpy.context.scene
SCENE.name = 'enerBiO x Monster | Ultra White concept'
SCENE['better_mcp_subject'] = 'Product'
SCENE['design_note'] = 'Fictional Limited Edition packaging concept, not an official collaboration.'
SCENE.cycles.samples = 32 if PREVIEW else 128
SCENE.cycles.adaptive_threshold = .025 if PREVIEW else .008
SCENE.render.resolution_x = 640 if PREVIEW else 1600
SCENE.render.resolution_y = 720 if PREVIEW else 1800

# Select a supported GPU inside the disposable worker. Factory-startup workers
# do not inherit the user's Cycles device preferences. CPU remains an explicit
# fallback and no preferences are saved back to the interactive Blender app.
render_device = {'backend': 'CPU', 'devices': []}
SCENE.cycles.device = 'CPU'
if os.environ.get('ULTRA_WHITE_DEVICE', 'AUTO').upper() != 'CPU':
    preferences = bpy.context.preferences.addons['cycles'].preferences
    for backend in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
        try:
            preferences.compute_device_type = backend
            devices = preferences.get_devices_for_type(backend)
            selected = [device for device in devices if device.type == backend]
            if not selected:
                continue
            for device in preferences.devices:
                device.use = device.type == backend
            SCENE.cycles.device = 'GPU'
            render_device = {'backend': backend, 'devices': [device.name for device in selected]}
            break
        except (TypeError, ValueError, RuntimeError):
            continue
print(json.dumps({'render_device': render_device}), flush=True)

# Replace the photographed winter artwork with an actual flat label texture.
# Preserve the graphic's physical aspect ratio: the 3:1 printed segment covers
# the front and sides; the remaining rear arc is unprinted white paper.
label = bpy.data.objects['Label']
material = bpy.data.materials.new('Label | Ultra White limited edition')
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
nodes.clear()
shader = nodes.new('ShaderNodeBsdfPrincipled')
shader.inputs['Roughness'].default_value = .48
shader.inputs['Specular IOR Level'].default_value = .25
output = nodes.new('ShaderNodeOutputMaterial')
links.new(shader.outputs['BSDF'], output.inputs['Surface'])
coordinates = nodes.new('ShaderNodeTexCoord')
mapping = nodes.new('ShaderNodeVectorMath')
mapping.operation = 'MULTIPLY_ADD'
texture = nodes.new('ShaderNodeTexImage')
texture.name = 'Ultra White | generated flat artwork'
texture.image = bpy.data.images.load(str(ASSETS / 'label.png'), check_existing=True)
texture.image.colorspace_settings.name = 'sRGB'
texture.extension = 'EXTEND'
texture.interpolation = 'Linear'
height = float(label.dimensions.z)
radius = float(label.dimensions.x) / 2
image_aspect = texture.image.size[0] / texture.image.size[1]
u_scale = (2 * math.pi * radius / height) / image_aspect
mapping.inputs[1].default_value = (u_scale, 1, 1)
mapping.inputs[2].default_value = (.5 * (1 - u_scale), 0, 0)
links.new(coordinates.outputs['UV'], mapping.inputs[0])
links.new(mapping.outputs['Vector'], texture.inputs['Vector'])

# A smooth paper continuation prevents the generated outermost ornament
# pixels from stretching into long stripes on the unprinted back.
split = nodes.new('ShaderNodeSeparateXYZ')
links.new(mapping.outputs['Vector'], split.inputs[0])
center = nodes.new('ShaderNodeMath')
center.operation = 'SUBTRACT'
center.inputs[1].default_value = .5
links.new(split.outputs['X'], center.inputs[0])
absolute = nodes.new('ShaderNodeMath')
absolute.operation = 'ABSOLUTE'
links.new(center.outputs[0], absolute.inputs[0])
fade = nodes.new('ShaderNodeMapRange')
fade.interpolation_type = 'SMOOTHERSTEP'
fade.inputs['From Min'].default_value = .45
fade.inputs['From Max'].default_value = .49
links.new(absolute.outputs[0], fade.inputs['Value'])
paper = nodes.new('ShaderNodeMixRGB')
paper.inputs[2].default_value = (.93, .94, .935, 1)
links.new(fade.outputs['Result'], paper.inputs[0])
links.new(texture.outputs['Color'], paper.inputs[1])
links.new(paper.outputs['Color'], shader.inputs['Base Color'])
label.data.materials.clear()
label.data.materials.append(material)

# Remove the source photo's old tamper-sticker fragment from the lid top.
# White enamel with fine molded surface relief works from every camera angle.
cap_material = bpy.data.materials.new('Cap | Ultra White satin enamel')
cap_material.use_nodes = True
cap_nodes = cap_material.node_tree.nodes
cap_shader = cap_nodes['Principled BSDF']
cap_shader.inputs['Base Color'].default_value = (.84, .85, .84, 1)
cap_shader.inputs['Roughness'].default_value = .36
cap_shader.inputs['Metallic'].default_value = .06
micro = cap_nodes.new('ShaderNodeTexImage')
micro.image = bpy.data.images.load(str(PROJECT / 'public/assets/micro-normal.png'), check_existing=True)
micro.image.colorspace_settings.name = 'Non-Color'
normal = cap_nodes.new('ShaderNodeNormalMap')
normal.inputs['Strength'].default_value = .20
cap_material.node_tree.links.new(micro.outputs['Color'], normal.inputs['Color'])
cap_material.node_tree.links.new(normal.outputs['Normal'], cap_shader.inputs['Normal'])
cap = bpy.data.objects['Cap']
for slot in cap.material_slots:
    if slot.material and not slot.material.name.startswith('Seal |'):
        slot.material = cap_material

# The flavor concept has white cream rather than the original roasted filling.
# A weak, existing normal map retains fine surface variation without nut grains.
cream = bpy.data.materials.new('Contents | Ultra White cream')
cream.use_nodes = True
cream_nodes = cream.node_tree.nodes
cream_shader = cream_nodes['Principled BSDF']
cream_shader.inputs['Base Color'].default_value = (.92, .92, .90, 1)
cream_shader.inputs['Roughness'].default_value = .40
cream_shader.inputs['Specular IOR Level'].default_value = .28
cream_shader.inputs['Subsurface Weight'].default_value = .045
cream_shader.inputs['Subsurface Scale'].default_value = .0012
cream_shader.inputs['Subsurface Radius'].default_value = (.8, .65, .5)
cream_texture = cream_nodes.new('ShaderNodeTexImage')
cream_texture.image = bpy.data.images.load(str(PROJECT / 'public/assets/contents-normal.png'), check_existing=True)
cream_texture.image.colorspace_settings.name = 'Non-Color'
cream_normal = cream_nodes.new('ShaderNodeNormalMap')
cream_normal.inputs['Strength'].default_value = .12
cream.node_tree.links.new(cream_texture.outputs['Color'], cream_normal.inputs['Color'])
cream.node_tree.links.new(cream_normal.outputs['Normal'], cream_shader.inputs['Normal'])
contents = bpy.data.objects['Nut_Cream']
contents.data.materials.clear()
contents.data.materials.append(cream)

# Keep the white filling neutral through the thick glass wall.
original_glass = bpy.data.materials['Glass | clear soda lime']
clear_glass = original_glass.copy()
clear_glass.name = 'Glass | Ultra White clear'
clear_glass.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.985, .99, .985, 1)
for obj in bpy.data.collections['Product'].objects:
    for slot in obj.material_slots:
        if slot.material == original_glass:
            slot.material = clear_glass

views = [('frontal', 0, 7), ('links', -28, 14), ('rechts', 30, 21)]
manifest = {
    'concept': SCENE['design_note'],
    'source': 'renders/winternuesse-studio.blend',
    'texture': 'label.png',
    'texture_generation': 'Built-in image_gen; exact prompt in label-prompt.txt',
    'contents': 'White cream, fine surface normal, weak subsurface scattering',
    'label_uv_scale_u': round(u_scale, 6),
    'engine': 'Cycles', 'samples': SCENE.cycles.samples,
    'render_device': render_device,
    'resolution': [SCENE.render.resolution_x, SCENE.render.resolution_y],
    'background': '#FFFFFF', 'views': [],
}
BETTER_BLENDER_OUTPUTS = {}
for name, azimuth, elevation in views:
    SCENE.camera = bpy.data.objects['Packshot | ' + name]
    path = OUTPUT / ('ultra-white-' + name + '.png')
    SCENE.render.filepath = str(path)
    started = time.monotonic()
    bpy.ops.render.render(write_still=True)
    manifest['views'].append({
        'name': name, 'file': path.name, 'camera': SCENE.camera.name,
        'azimuth_degrees': azimuth, 'elevation_degrees': elevation,
        'render_seconds': round(time.monotonic() - started, 2),
    })
    BETTER_BLENDER_OUTPUTS[name] = str(path)
    print(json.dumps(manifest['views'][-1]), flush=True)

SCENE.camera = bpy.data.objects['Packshot | frontal']
SCENE.render.filepath = str(OUTPUT / 'ultra-white-frontal.png')
manifest_path = OUTPUT / 'views.json'
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
BETTER_BLENDER_OUTPUTS['views'] = str(manifest_path)
if not PREVIEW:
    blend_path = OUTPUT / 'ultra-white.blend'
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    BETTER_BLENDER_OUTPUTS['blend'] = str(blend_path)

"""Deterministic product recipe. Designed for a background Blender worker.

All product meshes use explicit topology + UVs; no operator-heavy modeling.
The saved .blend remains editable. The browser loads the same exported GLB.
"""
from pathlib import Path
import json
import math
import time
import bpy
from mathutils import Vector

# Archived initial geometry/material recipe; only asset paths are adapted.
import shutil
ROOT=Path(__file__).resolve().parents[2]/'examples'/'product-studio'
ASSETS=Path(__file__).resolve().parents[2]/'.local'/'baseline-product'
ASSETS.mkdir(parents=True,exist_ok=True)
for filename in ['reference.png','label.png','lid-top.png','micro-normal.png']:
    shutil.copy2(ROOT/'public'/'assets'/filename,ASSETS/filename)
SEGMENTS=256
RADIAL_SCALE=.965
TIMINGS={}

def timed(name, fn):
    t=time.perf_counter()
    fn()
    TIMINGS[name]=round((time.perf_counter()-t)*1000,2)
    print(json.dumps({'stage':name,'ms':TIMINGS[name]}),flush=True)

def setup():
    # In a worker this is a fresh scene, so user scenes are never removed.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.name='Winternuesse | Product study'
    scene.unit_settings.system='METRIC'
    product=bpy.data.collections.new('Product')
    scene.collection.children.link(product)
    studio=bpy.data.collections.new('Studio')
    scene.collection.children.link(studio)

def lathe(name,profile,material=None,segments=SEGMENTS,uv='cylinder',collection='Product'):
    verts=[]
    for r,z in profile:
        for j in range(segments+1):
            theta=(j/segments-.5)*2*math.pi
            verts.append((RADIAL_SCALE*r*math.sin(theta),-RADIAL_SCALE*r*math.cos(theta),z))
    faces=[]
    n=segments+1
    for i in range(len(profile)-1):
        for j in range(segments):
            a=i*n+j
            faces.append((a,a+1,a+1+n,a+n))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    layer=mesh.uv_layers.new(name='UVMap')
    lo=min(z for r,z in profile)
    hi=max(z for r,z in profile)
    for face in mesh.polygons:
        face.use_smooth=True
        for loop in face.loop_indices:
            vi=mesh.loops[loop].vertex_index
            if uv=='planar':
                x,y,_=verts[vi]
                layer.data[loop].uv=(x/(.0846*RADIAL_SCALE)+.5,.5+y/(.0846*RADIAL_SCALE))
            else:
                layer.data[loop].uv=((vi%n)/segments,(verts[vi][2]-lo)/max(hi-lo,1e-8))
    obj=bpy.data.objects.new(name,mesh)
    bpy.data.collections[collection].objects.link(obj)
    if material:
        mesh.materials.append(bpy.data.materials[material])
    return obj

def material(name,color,roughness=.4,metallic=0):
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    p=mat.node_tree.nodes.get('Principled BSDF')
    # Input values in linear space.
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=roughness
    p.inputs['Metallic'].default_value=metallic
    mat.diffuse_color=(*color,1)
    return mat,p

def image_texture(mat,filename):
    tex=mat.node_tree.nodes.new('ShaderNodeTexImage')
    tex.image=bpy.data.images.load(str(ASSETS/filename),check_existing=True)
    mat.node_tree.links.new(tex.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    return tex

def materials():
    m,p=material('Glass | clear soda lime',(.94,.97,.91),.075)
    p.inputs['Transmission Weight'].default_value=1
    p.inputs['IOR'].default_value=1.47
    m,p=material('Contents | roasted nut cream',(.245,.134,.053),.48)
    n=m.node_tree.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value=180
    n.inputs['Detail'].default_value=3
    ramp=m.node_tree.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.18
    ramp.color_ramp.elements[0].color=(.17,.081,.029,1)
    ramp.color_ramp.elements[1].position=.82
    ramp.color_ramp.elements[1].color=(.33,.204,.081,1)
    m.node_tree.links.new(n.outputs['Fac'],ramp.inputs['Fac'])
    m.node_tree.links.new(ramp.outputs['Color'],p.inputs['Base Color'])
    bump=m.node_tree.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value=.18
    bump.inputs['Distance'].default_value=.000045
    m.node_tree.links.new(n.outputs['Fac'],bump.inputs['Height'])
    m.node_tree.links.new(bump.outputs['Normal'],p.inputs['Normal'])
    m,p=material('Label | original front artwork',(.8,.8,.8),.6)
    image_texture(m,'label.png')
    p.inputs['Specular IOR Level'].default_value=0
    m,p=material('Cap | warm white enamel',(.79,.80,.76),.60,.04)
    tex=m.node_tree.nodes.new('ShaderNodeTexImage')
    tex.image=bpy.data.images.load(str(ASSETS/'micro-normal.png'),check_existing=True)
    tex.image.colorspace_settings.name='Non-Color'
    normal=m.node_tree.nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value=.25
    m.node_tree.links.new(tex.outputs['Color'],normal.inputs['Color'])
    m.node_tree.links.new(normal.outputs['Normal'],p.inputs['Normal'])
    m,p=material('Cap top | photographed detail',(.83,.83,.80),.55,.03)
    image_texture(m,'lid-top.png')
    material('Seal | ivory gasket',(.72,.70,.62),.7)
    material('Studio | warm ivory',(.81,.785,.72),.9)

def geometry():
    # Closed hollow cross-section; the bottom and inner wall are real geometry.
    glass=[(.00001,.0007),(.025,.0007),(.034,.0007),(.0378,.001),(.040,.0017),
        (.0413,.0029),(.0418,.0045),(.0419,.009),(.0419,.060),(.0419,.064),
        (.04175,.0668),(.0413,.0684),(.0404,.0695),(.0389,.0703),
        (.0371,.0708),(.0366,.072),(.0366,.0767),(.0369,.078),(.037,.079),
        (.0365,.0797),(.0351,.0797),(.0346,.079),(.0348,.076),(.0349,.073),
        (.0355,.071),(.0375,.0698),(.039,.068),(.0401,.0655),(.0403,.009),
        (.0398,.0062),(.0384,.0046),(.032,.004),(.00001,.004),(.00001,.0007)]
    lathe('Jar_Glass',glass,'Glass | clear soda lime')
    # Thin paper sleeve, with edge thickness and the exact label proportions.
    label=[(.04199,.00475),(.04205,.00480),(.04205,.06115),(.04199,.0612)]
    lathe('Label',label,'Label | original front artwork')
    fill=[(.00001,.0045),(.034,.0045),(.0385,.005),(.0397,.007),(.0398,.065),
          (.0393,.0674),(.037,.069),(.035,.0705),(.0346,.0745),(.033,.075),
          (.026,.0751),(.018,.0750),(.010,.0753),(.00001,.0752),(.00001,.0045)]
    lathe('Nut_Cream',fill,'Contents | roasted nut cream')
    cap=[(.0369,.07565),(.0396,.07565),(.04115,.076),(.0421,.0767),
         (.04228,.0776),(.04230,.081),(.04230,.0905),(.04225,.0922),
         (.0418,.09345),(.0407,.09415),(.0395,.0945)]
    lid=lathe('Cap',cap,'Cap | warm white enamel')
    # A gently domed recessed disk, shallow rim and rounded concentric lip.
    top=[(.0395,.0945),(.0388,.0947),(.0383,.0946),(.0375,.09445),
         (.033,.09475),(.025,.0955),(.015,.09605),(.00001,.0962)]
    top_obj=lathe('Cap_Top',top,'Cap top | photographed detail',uv='planar')
    top_obj.parent=lid
    gasket=lathe('Cap_Gasket',[(.0359,.0755),(.0364,.0753),(.0372,.0753),(.0376,.0756),(.0372,.0761),(.0359,.0761),(.0359,.0755)],'Seal | ivory gasket')
    gasket.parent=lid
    liner=lathe('Cap_Liner',[(.00001,.0933),(.025,.0933),(.0389,.0925),
        (.0398,.0916),(.0398,.079),(.0369,.07565)],'Seal | ivory gasket')
    liner.parent=lid
    # Real glass screw ridges, revealed when the lid is lifted.
    for i,z in enumerate([.0725,.075,.0775]):
        profile=[]
        for j in range(13):
            a=j/12*2*math.pi
            profile.append((.03675+.00062*math.cos(a),z+.0005*math.sin(a)))
        lathe(f'Glass_Thread_{i+1:02}',profile,'Glass | clear soda lime')
    # Distinct components permit mechanically meaningful lid motion in Three.js.
    for obj in bpy.data.collections['Product'].objects:
        obj['source']='Photograph reconstruction; hidden geometry inferred'

def point_at(obj,point):
    obj.rotation_euler=(Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

def light(name,location,power,size,target=(0,0,.045),color=(1,1,1),size_y=None):
    data=bpy.data.lights.new(name,'AREA')
    data.energy=power
    data.shape='RECTANGLE'
    data.size=size
    data.size_y=size_y or size
    data.color=color
    obj=bpy.data.objects.new(name,data)
    bpy.data.collections['Studio'].objects.link(obj)
    obj.location=location
    point_at(obj,target)

def studio():
    scene=bpy.context.scene
    cam_data=bpy.data.cameras.new('Camera')
    cam=bpy.data.objects.new('Camera',cam_data)
    bpy.data.collections['Studio'].objects.link(cam)
    cam.location=(0,-.65,.0481+.65*.0809)
    point_at(cam,(0,0,.0481))
    cam_data.type='ORTHO'
    cam_data.ortho_scale=.1096
    cam_data.shift_x=.030
    scene.camera=cam
    light('Key | tall softbox',(-.16,-.22,.25),.12,.18,size_y=.30)
    light('Fill | front',(0.16,-.26,.12),.05,.18,size_y=.25)
    light('Rim | rear',(0,.15,.22),.15,.14,size_y=.22)
    world=bpy.data.worlds.new('Studio ambient')
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(1,1,1,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.85
    scene.world=world
    scene.render.engine='CYCLES'
    scene.cycles.samples=48
    scene.cycles.use_denoising=True
    scene.cycles.max_bounces=12
    scene.cycles.transmission_bounces=8
    scene.render.resolution_x=870
    scene.render.resolution_y=903
    scene.render.resolution_percentage=100
    scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='Standard'
    scene.view_settings.look='None'
    # Keep saved GUI inexpensive; rendering happens only in the worker.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.shading.type='MATERIAL'
                area.spaces.active.region_3d.view_perspective='CAMERA'

def export():
    scene=bpy.context.scene
    scene.render.filepath=str(ASSETS/'blender-render.png')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSETS/'winternuesse.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.data.collections['Product'].objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(ASSETS/'winternuesse.glb'),export_format='GLB',
        use_selection=True,export_cameras=False,export_lights=False,export_animations=False,
        export_yup=True,export_extras=True,export_apply=False)
    meshes=[o for o in bpy.data.collections['Product'].objects if o.type=='MESH']
    stats=dict(meshes=len(meshes),vertices=sum(len(o.data.vertices) for o in meshes),
        triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes),
        materials=len({m.name for o in meshes for m in o.data.materials}),
        dimensions_m=[.0846*RADIAL_SCALE,.0846*RADIAL_SCALE,.0962],blender=bpy.app.version_string,
        glb_bytes=(ASSETS/'winternuesse.glb').stat().st_size,stages_ms=TIMINGS)
    (ASSETS/'model-info.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')

def render():
    bpy.ops.render.render(write_still=True)

if __name__=='__main__':
    for name,fn in [('setup',setup),('materials',materials),('geometry',geometry),('studio',studio),('export',export),('render',render)]:
        timed(name,fn)
    (ASSETS/'build-timings.json').write_text(json.dumps(TIMINGS,indent=2),encoding='utf-8')

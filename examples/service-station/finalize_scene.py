"""Render, inspect and save the completed furniture in the live MCP scene."""
from pathlib import Path
import json
import math
import bpy
from mathutils import Vector

OUT=Path(__file__).resolve().parent/'output'
s=bpy.context.scene
hero=s.camera
detail=next(o for o in s.objects if o.type=='CAMERA' and '04 Dispenser detail' in o.name)
detail.location=(-1.45,-2.65,1.90)
detail.rotation_euler=(Vector((.64,.35,1.19))-detail.location).to_track_quat('-Z','Y').to_euler()
detail.data.lens=81
for name,cam,w,h,samples in [
    ('service-station-front',next(o for o in s.objects if o.type=='CAMERA' and '02 Front elevation' in o.name),1600,1250,64),
    ('service-station-detail',detail,1600,1500,96),
    ('service-station-preview',hero,2400,1875,160),
]:
    s.camera=cam;s.render.resolution_x=w;s.render.resolution_y=h;s.cycles.samples=samples
    s.render.filepath=str(OUT/(name+'.png'))
    bpy.ops.render.render(write_still=True)

bpy.context.view_layer.update()
model=[o for o in s.objects if o.type in {'MESH','CURVE','FONT'}]
corners=[o.matrix_world@Vector(c) for o in model for c in o.bound_box]
mins=[min(p[i] for p in corners) for i in range(3)]
maxs=[max(p[i] for p in corners) for i in range(3)]
deps=bpy.context.evaluated_depsgraph_get()
vertices=0;triangles=0
for ob in model:
    ev=ob.evaluated_get(deps)
    me=ev.to_mesh()
    if me:
        vertices+=len(me.vertices);me.calc_loop_triangles();triangles+=len(me.loop_triangles)
        ev.to_mesh_clear()
images={n.image for o in model for m in getattr(o.data,'materials',[]) if m and m.use_nodes
        for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image}
fonts={o.data.font for o in model if o.type=='FONT'}
audit={
    'scene':s.name,'model_objects':len(model),'mesh_objects':sum(o.type=='MESH' for o in model),
    'evaluated_vertices':vertices,'evaluated_triangles':triangles,
    'bounds_m':{'minimum':mins,'maximum':maxs,'dimensions':[round(b-a,4) for a,b in zip(mins,maxs)]},
    'textures':[{'name':im.name,'packed':bool(im.packed_file),'size':list(im.size)} for im in images],
    'fonts':[{'name':f.name,'packed':bool(f.packed_file)} for f in fonts],
    'recycling_apertures':5,'furniture_only':True,'transparent_render':bool(s.render.film_transparent),
    'cameras':[o.name for o in s.objects if o.type=='CAMERA'],
    'limitations':['Physical size estimated from photographs; no measured dimensions provided.',
                   'Rear and internal construction inferred. A numeric likeness percentage is not established.'],
    'texture_source':'https://polyhaven.com/a/oak_veneer_01',
    'texture_license':'CC0',
}
assert len(images)==2 and all(im.packed_file for im in images),'Unpacked texture'
assert all(f.packed_file for f in fonts),'Unpacked font'
assert all(math.isfinite(v) for p in corners for v in p),'Nonfinite geometry'
(OUT/'quality-report.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
# Remove only orphaned resources created by this recipe's earlier iterations.
for kind in ('materials','meshes','curves','collections','cameras','lights','worlds','texts'):
    blocks=getattr(bpy.data,kind)
    for block in list(blocks):
        if block.name.startswith('SS | ') and block.users==0:
            blocks.remove(block)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'service-station.blend'))
result=audit

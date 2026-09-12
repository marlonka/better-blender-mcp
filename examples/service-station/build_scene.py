"""Editable Rossmann service-station reconstruction, executed in Blender via MCP.

No surrounding shop geometry. All measurements are estimates from two photographs.
Run with exec(compile(Path(...).read_text(), ..., 'exec')) in the connected Blender.
"""
from pathlib import Path
import math
import json
import random
import bpy
from mathutils import Vector, Matrix

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output'
OUT.mkdir(parents=True, exist_ok=True)
random.seed(52144)
PREFIX = 'SS | '

if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
old = bpy.data.scenes.get('Service station | isolated furniture')
if old:
    for obj in list(old.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.scenes.remove(old)
scene = bpy.data.scenes.new('Service station | isolated furniture')
bpy.context.window.scene = scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'METERS'

def collection(name):
    c = bpy.data.collections.new(PREFIX + name)
    scene.collection.children.link(c)
    return c

bench = collection('01 Bench · upholstery and curved oak slats')
cabinet = collection('02 Cabinet · joinery and divider')
openings = collection('03 Recycling apertures · liners and rims')
graphics = collection('04 German labels and pictograms')
dispenser = collection('05 Wrapping station · paper and hardware')
studio = collection('90 Cameras and studio lighting')
root = bpy.data.objects.new(PREFIX + 'SERVICE STATION', None)
cabinet.objects.link(root)
root['dimensions_estimated'] = True
root['source'] = '52144-detailp.jpeg; csm_CM_Bild_Servicestation_a25ebb1487 (1).jpg'
root['notes'] = 'Reconstructed from two photographs. Hidden construction is inferred.'
root.empty_display_size = .12

def link_obj(obj, coll, material=None, parent=True):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = root
    return obj

def simple_mat(name, color, roughness=.4, metal=0):
    m = bpy.data.materials.new(PREFIX + name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = roughness
    p.inputs['Metallic'].default_value = metal
    return m

def wood_mat(name, lighter=False):
    m = simple_mat(name, (.63,.49,.35), .41)
    n, l = m.node_tree.nodes, m.node_tree.links
    p = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord')
    scale = n.new('ShaderNodeVectorMath'); scale.operation = 'MULTIPLY'
    scale.inputs[1].default_value = (7.5,7.5,.72)
    l.new(tc.outputs['Object'],scale.inputs[0])
    noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 3.1
    noise.inputs['Detail'].default_value = 4.5; noise.inputs['Roughness'].default_value = .72
    l.new(scale.outputs[0],noise.inputs['Vector'])
    warp = n.new('ShaderNodeVectorMath'); warp.operation = 'SCALE'
    warp.inputs[3].default_value = .23; l.new(noise.outputs['Color'],warp.inputs[0])
    add = n.new('ShaderNodeVectorMath'); add.operation = 'ADD'
    l.new(scale.outputs[0],add.inputs[0]); l.new(warp.outputs[0],add.inputs[1])
    wave = n.new('ShaderNodeTexNoise')
    wave.inputs['Scale'].default_value = 7.8
    wave.inputs['Detail'].default_value = 4
    wave.inputs['Roughness'].default_value = .68
    l.new(add.outputs[0],wave.inputs['Vector'])
    mix = n.new('ShaderNodeMixRGB'); mix.blend_type='MULTIPLY'; mix.inputs[0].default_value=.50
    l.new(noise.outputs['Fac'],mix.inputs[1]); l.new(wave.outputs['Color'],mix.inputs[2])
    ramp = n.new('ShaderNodeValToRGB')
    colors = [(0,(.22,.145,.088,1)),(.20,(.43,.31,.205,1)),(.39,(.63,.49,.355,1)),(.57,(.76,.64,.49,1)),(1,(.84,.75,.61,1))]
    if lighter:
        colors=[(v,tuple(min(1,c*1.06+.022) if i<3 else c for i,c in enumerate(col))) for v,col in colors]
    cr=ramp.color_ramp; cr.elements.remove(cr.elements[1])
    for i,(v,col) in enumerate(colors):
        e=cr.elements[0] if i==0 else cr.elements.new(v)
        e.position=v;e.color=col
    l.new(mix.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],p.inputs['Base Color'])
    fine_scale=n.new('ShaderNodeVectorMath');fine_scale.operation='MULTIPLY'
    fine_scale.inputs[1].default_value=(145,145,1.8);l.new(tc.outputs['Object'],fine_scale.inputs[0])
    fine=n.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=3
    fine.inputs['Detail'].default_value=2;l.new(fine_scale.outputs[0],fine.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.19
    bump.inputs['Distance'].default_value=.00065
    l.new(fine.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],p.inputs['Normal'])
    # Scanned CC0 veneer supplies the distinctive oak cathedrals and fine pores.
    # The physical UV mapping is assigned after constructing the meshes.
    tex=n.new('ShaderNodeTexImage')
    tex.image=bpy.data.images.load(str(HERE/'assets/oak_veneer_01_diff_2k.jpg'),check_existing=True)
    hsv=n.new('ShaderNodeHueSaturation');hsv.inputs['Saturation'].default_value=.54
    hsv.inputs['Value'].default_value=1.52 if lighter else 1.37
    l.new(tex.outputs['Color'],hsv.inputs['Color'])
    wash=n.new('ShaderNodeMixRGB');wash.inputs[0].default_value=.22 if lighter else .14
    wash.inputs[2].default_value=(.81,.77,.70,1)
    l.new(hsv.outputs['Color'],wash.inputs[1]);l.new(wash.outputs[0],p.inputs['Base Color'])
    normal_tex=n.new('ShaderNodeTexImage')
    normal_tex.image=bpy.data.images.load(str(HERE/'assets/oak_veneer_01_nor_gl_2k.jpg'),check_existing=True)
    normal_tex.image.colorspace_settings.name='Non-Color'
    normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.25
    l.new(normal_tex.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs[0],p.inputs['Normal'])
    return m

oak=wood_mat('Pale oak · vertical crown grain')
slat_oak=wood_mat('Whitewashed oak · solid rounded slats',True)
edgewood=simple_mat('Birch plywood exposed edge',(.49,.34,.21),.46)
ivory=simple_mat('Warm white recessed plinth',(.77,.73,.65),.38)
red=simple_mat('Rossmann red powder coat',(.58,.003,.009),.34)
leather=simple_mat('Crimson upholstered vinyl',(.52,.003,.018),.49)
nodes=leather.node_tree.nodes; links=leather.node_tree.links;p=nodes.get('Principled BSDF')
p.inputs['Coat Weight'].default_value=.04;p.inputs['Coat Roughness'].default_value=.5
tc=nodes.new('ShaderNodeTexCoord');noise=nodes.new('ShaderNodeTexNoise')
noise.inputs['Scale'].default_value=760;noise.inputs['Detail'].default_value=2
links.new(tc.outputs['Object'],noise.inputs['Vector'])
bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16;bump.inputs['Distance'].default_value=.00033
links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],p.inputs['Normal'])
seamred=simple_mat('Upholstery seam thread',(.37,.004,.014),.62)
black=simple_mat('Black hardware satin',(.009,.010,.009),.3)
interior=simple_mat('Recycling chute interior',(.014,.012,.009),.77)
ink=simple_mat('Warm charcoal printed lettering',(.068,.039,.019),.58)
chrome=simple_mat('Brushed stainless steel',(.50,.53,.53),.24,.82)
paper=simple_mat('Unbleached cream wrapping paper',(.64,.53,.37),.76)
paperedge=simple_mat('Paper roll edge',(.76,.67,.51),.71)
yellow=simple_mat('Yellow plastics identification',(.94,.60,.012),.4)
blue=simple_mat('Pale blue paper identification',(.34,.52,.58),.42)
gray=simple_mat('Gray residual waste identification',(.24,.22,.19),.4)
green=simple_mat('Green battery identification',(.12,.40,.26),.4)
orange=simple_mat('Warm white lamp identification',(.78,.64,.43),.42)

def mesh_obj(name, verts, faces, coll, mat, smooth=False):
    me=bpy.data.meshes.new(PREFIX+name);me.from_pydata(verts,[],faces);me.update()
    ob=bpy.data.objects.new(PREFIX+name,me);coll.objects.link(ob);ob.parent=root
    if mat:me.materials.append(mat)
    for poly in me.polygons:poly.use_smooth=smooth
    return ob

def bevel(ob,width=.003,segments=3):
    m=ob.modifiers.new('Soft manufactured edges','BEVEL');m.width=width;m.segments=segments
    return m

def box(name,loc,dims,mat,coll=cabinet,r=.002):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob=link_obj(bpy.context.object,coll,mat);ob.name=PREFIX+name
    ob.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if r:bevel(ob,r,4)
    return ob

def cylinder(name,loc,radius,depth,mat,coll=dispenser,axis='Z',vertices=64,bevel_width=.001):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    ob=link_obj(bpy.context.object,coll,mat);ob.name=PREFIX+name
    if axis=='X':ob.rotation_euler[1]=math.pi/2
    if axis=='Y':ob.rotation_euler[0]=math.pi/2
    if bevel_width:bevel(ob,bevel_width,3)
    for p in ob.data.polygons:p.use_smooth=len(p.vertices)==4
    return ob

def curve(name,coords,radius,mat,coll=graphics,closed=False):
    cu=bpy.data.curves.new(PREFIX+name,'CURVE');cu.dimensions='3D';cu.resolution_u=12
    cu.bevel_depth=radius;cu.bevel_resolution=3
    sp=cu.splines.new('POLY');sp.points.add(len(coords)-1)
    for p,co in zip(sp.points,coords):p.co=(*co,1)
    sp.use_cyclic_u=closed
    ob=bpy.data.objects.new(PREFIX+name,cu);coll.objects.link(ob);ob.parent=root
    cu.materials.append(mat)
    return ob

def extrude_profile(name,coords,low,high,axis,mat,coll,r=.002):
    def point(p,a):
        return (p[0],p[1],a) if axis=='Z' else ((p[0],a,p[1]) if axis=='Y' else (a,p[0],p[1]))
    verts=[point(p,v) for v in (low,high) for p in coords];n=len(coords)
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    ob=mesh_obj(name,verts,faces,coll,mat)
    if r:bevel(ob,r,4)
    return ob

def round_rect(x0,x1,y0,y1,r,steps=12):
    pts=[]
    for cx,cy,st in [(x1-r,y1-r,0),(x0+r,y1-r,90),(x0+r,y0+r,180),(x1-r,y0+r,270)]:
        pts += [(cx+r*math.cos(math.radians(st+i*90/steps)),cy+r*math.sin(math.radians(st+i*90/steps))) for i in range(steps+1)]
    return pts

def face_ring(name,x,z,outer,inner,yfront,yback,mat):
    n=96;verts=[]
    for y,r in [(yfront,outer),(yfront,inner),(yback,outer),(yback,inner)]:
        verts += [(x+r*math.cos(i*math.tau/n),y,z+r*math.sin(i*math.tau/n)) for i in range(n)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [(i,j,n+j,n+i),(i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i),(2*n+i,3*n+i,3*n+j,2*n+j)]
    ob=mesh_obj(name,verts,faces,openings,mat,True);bevel(ob,.0007,2)
    return ob

# Coordinates: length on X; front Y=0; rear Y=.58; floor Z=0.
CW=.94; D=.57; CH=1.13; DH=1.30; H=.493; LEFT=-1.48
R=.285; CX=LEFT+R

def capsule_profile(xright=0,inset=0):
    rr=R-inset
    return [(xright,inset),(xright,D-inset),(CX,D-inset)] + [(CX+rr*math.cos(math.pi/2+i*math.pi/48),D/2+rr*math.sin(math.pi/2+i*math.pi/48)) for i in range(49)]

# Capsule-ended white base, shadow toe and concealed slat support.
extrude_profile('Bench recessed shadow foot',capsule_profile(-.012,.025),.016,.042,'Z',black,bench,.007)
extrude_profile('Bench continuous white plinth',capsule_profile(-.008,.010),.035,.119,'Z',ivory,bench,.006)
extrude_profile('Bench inner oak carcass',capsule_profile(-.006,.033),.100,.422,'Z',oak,bench,.005)

# Round oak dowels wrap around the visible semicircular nose and both long sides.
path=[];pitch=.061
count=round((-.015-CX)/pitch)
for i in range(count+1):
    x=CX+(-.018-CX)*i/count
    path.extend([(x,.010),(x,D-.010)])
arc_count=round(math.pi*(R-.011)/pitch)
for i in range(1,arc_count):
    a=math.pi/2+math.pi*i/arc_count
    path.append((CX+(R-.011)*math.cos(a),D/2+(R-.011)*math.sin(a)))
for i,(x,y) in enumerate(path):
    ob=cylinder(f'Oak round slat {i+1:02d}',(x,y,.263),.0285,.321,slat_oak,bench,vertices=32,bevel_width=.0025)
    # Shift local texture origin for natural variation without altering geometry.
    ob.rotation_euler[2]=random.uniform(-math.pi,math.pi)

# Two shaped, subtly crowned vinyl seat pads, with an actual narrow join.
def cushion(name,outline,z0,z1):
    center=Vector((sum(p[0] for p in outline)/len(outline),sum(p[1] for p in outline)/len(outline)))
    layers=[(.985,z0),(1,z0+.014),(1,z1-.022),(.993,z1-.007),(.978,z1)]
    verts=[];n=len(outline)
    for scale,z in layers:
        verts += [(center.x+(x-center.x)*scale,center.y+(y-center.y)*scale,z) for x,y in outline]
    faces=[tuple(range(n-1,-1,-1))]
    for k in range(len(layers)-1):
        faces += [(k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i) for i in range(n)]
    # A concentric inner surface keeps the top flat with a very gentle crown.
    inner=len(verts)
    verts += [(center.x+(x-center.x)*.70,center.y+(y-center.y)*.70,z1+.001) for x,y in outline]
    faces += [((len(layers)-1)*n+i,(len(layers)-1)*n+(i+1)%n,inner+(i+1)%n,inner+i) for i in range(n)]
    faces.append(tuple(range(inner,inner+n)))
    ob=mesh_obj(name,verts,faces,bench,leather,True)
    curve(name+' bottom stitched welt',[(center.x+(x-center.x)*.989,center.y+(y-center.y)*.989,z0+.010) for x,y in outline],.0010,seamred,bench,True)
    return ob

split=-.70
left_outline=[(split-.001,-.013),(split-.001,D+.013),(CX,D+.013)]
left_outline += [(CX+(R+.013)*math.cos(math.pi/2+i*math.pi/64),D/2+(R+.013)*math.sin(math.pi/2+i*math.pi/64)) for i in range(65)]
cushion('Outer rounded seat cushion',left_outline,.420,H)
inner_outline=round_rect(split+.001,-.009,-.012,D+.012,.016,16)
cushion('Inner rectangular seat cushion',inner_outline,.420,H)

# Tall divider / back rest, radius only on the upper front corner.
profile=[(0,.105),(D,.105),(D,DH),(.070,DH)]
profile += [(.070+.070*math.cos(math.pi/2+i*math.pi/2/16),DH-.070+.070*math.sin(math.pi/2+i*math.pi/2/16)) for i in range(17)]
divider=extrude_profile('High oak divider · radiused front corner',profile,-.029,-.009,'X',oak,cabinet,.002)

bolster=cylinder('Round red bolster',(-.124,D/2,.594),.097,.522,leather,bench,'Y',96,.018)
for y in (.019,.551):
    coords=[(-.124+.083*math.cos(i*math.tau/96),y,.594+.083*math.sin(i*math.tau/96)) for i in range(96)]
    curve('Bolster end-cap stitched welt',coords,.00115,seamred,bench,True)

# Cabinet: real separable joinery and recessed lower plinth.
box('Cabinet white kickboard',(CW/2,.021,.077),(CW,.04,.13),ivory,r=.002)
box('Cabinet underside',(CW/2,D/2,.137),(CW,.55,.035),oak)
box('Cabinet rear panel',(CW/2,D-.013,.630),(CW,.026,.988),oak)
box('Cabinet right side',(CW-.013,D/2,.630),(.026,D,.988),oak)
box('Cabinet left interior wall',(.015,D/2,.626),(.026,D,.98),oak)
for x in (.233,.466,.699):
    box(f'Inner compartment divider {x:.3f}',(x,D/2,.613),(.014,D-.036,.937),oak)
box('Top shadow joint',(CW/2,D/2,CH-.019),(CW,D,.006),black,r=.001)
top=box('Oak work surface',(CW/2,D/2,CH),(CW+.008,D+.012,.025),oak,r=.003)

centers=[.115,.350,.583,.815]
hole_z=.950
panels=[]
for i,(xa,xb) in enumerate([(0,.231),(.235,.464),(.468,.697),(.701,.929)]):
    panel=box(f'Recycling door {i+1} · bored oak panel',((xa+xb)/2,.002,.627),(xb-xa,.026,.970),oak,r=0)
    holes=[(centers[i],hole_z,.086)]
    if i==3:holes.append((centers[i],.585,.080))
    for j,(x,z,r) in enumerate(holes):
        cutter=cylinder('Temporary bore',(x,.002,z),r,.14,None,openings,'Y',96,0)
        mod=panel.modifiers.new('Through-bore','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        bpy.ops.object.select_all(action='DESELECT');panel.select_set(True);bpy.context.view_layer.objects.active=panel
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
        rim_mat=[yellow,blue,gray,green][i] if j==0 else orange
        face_ring(f'{i+1}.{j+1} exposed plywood bore',x,z,r+.002,r-.007,-.012,.012,edgewood)
        face_ring(f'{i+1}.{j+1} colored identification bezel',x,z,r+.010,r+.001,-.016,-.012,rim_mat)
        face_ring(f'{i+1}.{j+1} narrow metal inner rim',x,z,r-.005,r-.008,-.014,-.011,chrome)
        face_ring(f'{i+1}.{j+1} dark recessed throat',x,z,r-.008,r-.010,.024,.153,interior)
        cylinder(f'{i+1}.{j+1} dark bin recess',(x,.205,z-.010),r-.011,.009,interior,openings,'Y',64,0)
        box(f'{i+1}.{j+1} interior chute lower lip',(x,.105,z-r+.014),(r*1.38,.080,.005),black,openings,.001)
    bevel(panel,.0015,3);panels.append(panel)

# Front surface labels use packed condensed type, not photograph projections.
font_path=Path('C:/Windows/Fonts/ARIALN.TTF')
font=bpy.data.fonts.load(str(font_path)) if font_path.exists() else None
def text_obj(name,body,x,y,z,size,mat=ink,align='CENTER',coll=graphics):
    cu=bpy.data.curves.new(PREFIX+name,'FONT');cu.body=body;cu.size=size;cu.align_x=align
    cu.space_character=1.03;cu.space_line=.94;cu.extrude=.000035;cu.resolution_u=8
    if font:cu.font=font
    ob=bpy.data.objects.new(PREFIX+name,cu);coll.objects.link(ob);ob.parent=root
    ob.location=(x,y,z);ob.rotation_euler=(math.pi/2,0,0);cu.materials.append(mat)
    return ob

for x,label in zip(centers,['Plastik','Papier','Restmüll','Batterien']):
    text_obj(label+' label',label,x,-.0125,.800,.046)
text_obj('Lamp recycling label','Energie-\nsparlampen',centers[3],-.0125,.450,.029)

def icon_line(name,x,z,pts,mat=ink,w=.0009):
    return curve(name,[(x+px,-.01135,z+pz) for px,pz in pts],w*.42,mat,graphics)

for j in range(3):
    x=centers[0]-.032+j*.031;z=.700
    pts=[(-.009,0),(-.010,.045),(-.006,.052),(-.006,.063),(.004,.063),(.004,.052),(.009,.045),(.010,0),(-.009,0)]
    icon_line('Plastic bottle outline',x,z,pts,yellow,.00125)
    for zz in (.018,.027,.047):icon_line('Bottle embossing',x,z,[(-.008,zz),(.008,zz)],yellow,.0008)
for j in range(3):
    x=centers[1]-.030+j*.021;z=.718+j*.006
    icon_line('Folded paper outline',x,z,[(-.020,-.011),(-.027,.032),(.009,.042),(.023,.019),(.012,-.015),(-.020,-.011)],blue,.00105)
    for zz in (.008,.017,.026):icon_line('Printed paper lines',x,z,[(-.017,zz),(.006,zz+.007)],blue,.0008)
icon_line('Waste bag outline',centers[2]-.021,.719,[(-.021,0),(-.025,.020),(-.006,.044),(-.009,.053),(.010,.053),(.006,.043),(.027,.019),(.020,-.004),(-.021,0)],gray,.0012)
icon_line('Crumpled waste outline',centers[2]+.031,.732,[(-.018,-.016),(-.018,.020),(.012,.025),(.023,.010),(.015,-.019),(-.018,-.016)],gray,.0011)
for i in range(2):icon_line('Waste folds',centers[2]-.023+i*.018,.719,[(0,.004),(.005,.023),(.010,.036)],gray,.0008)

# Red freestanding rear board with two large upper corner radii.
dispenser_start=set(dispenser.objects)
BH=1.580;BR=.125
backprofile=[(-.005,.078),(CW+.014,.078),(CW+.014,BH-BR)]
backprofile += [(CW+.014-BR+BR*math.cos(i*math.pi/2/24),BH-BR+BR*math.sin(i*math.pi/2/24)) for i in range(25)]
backprofile += [(.120,BH)]
backprofile += [(.120+BR*math.cos(math.pi/2+i*math.pi/2/24),BH-BR+BR*math.sin(math.pi/2+i*math.pi/2/24)) for i in range(25)]
extrude_profile('Red rounded dispenser backboard',backprofile,D-.008,D+.014,'Y',red,dispenser,.0035)
box('Red right exposed upright',(CW+.009,D/2,.588),(.022,D+.028,1.022),red,dispenser,.003)

# Main corrugated wrapping roll. Actual fine rings on the surface, hollow core.
paper_assembly_start=set(dispenser.objects)
roll_x=.477;roll_y=.430;roll_z=1.499;roll_w=.761;roll_r=.112
cylinder('Large paper roll core',(roll_x,roll_y,roll_z),roll_r-.001,roll_w,paper,dispenser,'X',128,.0008)
N=128;bands=560;verts=[];faces=[]
for j in range(bands+1):
    x=roll_x-roll_w/2+roll_w*j/bands
    rr=roll_r+.0008*math.sin(j*math.pi/2)
    verts += [(x,roll_y+rr*math.cos(i*math.tau/N),roll_z+rr*math.sin(i*math.tau/N)) for i in range(N)]
for j in range(bands):
    faces += [(j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i) for i in range(N)]
mesh_obj('Fine corrugated wrapping-paper surface',verts,faces,dispenser,paper,True)
for side in (-1,1):
    x=roll_x+side*(roll_w/2+.0003)
    cylinder('Cream paper roll circular end',(x,roll_y,roll_z),roll_r,.0012,paperedge,dispenser,'X',128,0)
    for k in range(13):
        rr=.018+k*.0070
        curve('Concentric wound-paper end grain',[(x+side*.0008,roll_y+rr*math.cos(i*math.tau/96),roll_z+rr*math.sin(i*math.tau/96)) for i in range(96)],.00021,paper,dispenser,True)
    cylinder('Cardboard center socket',(x+side*.002,roll_y,roll_z),.013,.008,black,dispenser,'X',48,.0005)
cylinder('Paper roll axle',(roll_x,roll_y,roll_z),.0055,.848,chrome,dispenser,'X',48,.0005)

# Cream metal end brackets, fixing screws and front tear bar.
for x in (.064,.888):
    pr=[(.553,1.436),(.331,1.436),(.313,1.451),(.313,1.482),(.334,1.503),(.345,1.531),(.367,1.538),(.389,1.530),(.389,1.511),(.553,1.511)]
    extrude_profile('Paper holder formed end bracket',pr,x-.004,x+.004,'X',ivory,dispenser,.002)
    for y,z in [(.353,1.492),(.526,1.469)]:
        cylinder('Bracket black mounting screw',(x+(.005 if x>.5 else -.005),y,z),.006,.003,black,dispenser,'X',32,.0006)
cylinder('Chrome paper tear bar',(roll_x,.313,1.495),.0038,.861,chrome,dispenser,'X',48,.0005)
box('Flat metal tear rail',(roll_x,.310,1.491),(.842,.009,.004),chrome,dispenser,.0008)
for x in (.046,.907):cylinder('Tear rail end stop',(x,.313,1.495),.006,.013,black,dispenser,'X',32,.001)
for ob in set(dispenser.objects)-paper_assembly_start:ob.location.z-=.065

# Lower gift-ribbon/tape dispenser rail, with three separate rolls and brackets.
box('Lower dispenser rear fixing plate',(.668,.539,1.286),(.449,.020,.060),black,dispenser,.003)
cylinder('Lower common spindle',(.672,.470,1.282),.007,.447,chrome,dispenser,'X',48,.001)
for j,(x,w,mat) in enumerate([(.500,.091,red),(.624,.071,paperedge),(.757,.082,paperedge)]):
    cylinder(f'Ribbon roll {j+1}',(x,.470,1.283),.038,w,mat,dispenser,'X',64,.002)
    for side in (-1,1):
        cylinder('Black dispenser flange',(x+side*(w/2+.006),.470,1.283),.039,.009,black,dispenser,'X',64,.001)
        cylinder('Chrome hub bolt',(x+side*(w/2+.012),.470,1.283),.013,.007,chrome,dispenser,'X',40,.0007)
        box('Dispenser mounting arm',(x+side*(w/2+.006),.511,1.282),(.014,.105,.023),black,dispenser,.003)
    if j==0:
        tab=box('Lower cutter black pull tab',(x+.026,.437,1.232),(.024,.031,.014),black,dispenser,.002)
        tab.rotation_euler[0]=-.5
# A loose cream ribbon hangs from the right roll.
curve('Hanging cream ribbon',[(.751,.446,1.267),(.750,.432,1.239),(.752,.429,1.204),(.761,.430,1.169),(.770,.432,1.154),(.763,.434,1.150),(.755,.435,1.158)],.0031,paperedge,dispenser)

# The dispenser is mounted across the RIGHT END of the cabinet, facing the bench.
# Its roll axis follows the cabinet depth, as confirmed by the visible right cap.
end_mount=Matrix(((0,1,0,CW-D),(-D/CW,0,0,D),(0,0,1,0),(0,0,0,1)))
bpy.context.view_layer.update()
for ob in set(dispenser.objects)-dispenser_start:
    if 'Red right exposed upright' not in ob.name:ob.matrix_world=end_mount@ob.matrix_world

# Counter wrapping guide, small paper stack and rear instruction plaque.
box('Wrapping counter shallow tray',(.170,.214,CH+.020),(.315,.285,.010),edgewood,dispenser,.002)
for j in range(7):
    box('Loose wrapping sheet '+str(j+1),(.175+j*.001,.214,CH+.027+j*.0006),(.289,.235,.0005),paperedge,dispenser,.00015)
for yy in (.083,.344):box('Tray silver guide',(.172,yy,CH+.034),(.332,.009,.008),chrome,dispenser,.001)
box('Tray blade carrier',(.335,.216,CH+.037),(.012,.278,.013),ivory,dispenser,.002)
box('Tray black slider',(.333,.333,CH+.048),(.023,.024,.018),black,dispenser,.003)
box('Oak counter sign board',(.285,D-.019,1.241),(.490,.017,.200),oak,dispenser,.0015)
text_obj('Wrapping sign','Gut verpackt',.310,D-.029,1.240,.048,paperedge,coll=dispenser)
box('Small instruction decal',(.817,-.0139,1.076),(.113,.0004,.060),paperedge,graphics,.0004)
text_obj('Sticker red title','BITTE BEACHTEN',.817,-.0145,1.091,.0105,red)
text_obj('Sticker instruction','Nur leere Batterien\nund Energiesparlampen',.817,-.0145,1.075,.009,ink)

# Model-only cameras. World is transparent; there is deliberately no floor plane.
def camera(name,loc,target,lens):
    data=bpy.data.cameras.new(PREFIX+name);ob=bpy.data.objects.new(PREFIX+name,data);studio.objects.link(ob)
    ob.location=loc;ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
    data.lens=lens;data.clip_start=.01;data.clip_end=200
    return ob

hero=camera('01 Reference angle',(-2.013,-2.231,1.478),(-.24,.245,.85),36.65)
hero.rotation_euler=(1.34432,.051354,-.582178)
hero.data.shift_y=-.035
front=camera('02 Front elevation',(-.265,-6,1.0),(-.265,.1,.82),55)
front.data.type='ORTHO';front.data.ortho_scale=2.85
back=camera('03 Rear construction',(3.1,4.5,2.9),(-.25,.25,.82),53)
detail=camera('04 Dispenser detail',(1.95,-2.45,2.02),(.48,.30,1.22),72)
scene.camera=hero

world=bpy.data.worlds.new(PREFIX+'Neutral photographic world');world.use_nodes=True
world.node_tree.nodes.get('Background').inputs[0].default_value=(.74,.77,.82,1)
world.node_tree.nodes.get('Background').inputs[1].default_value=.32
scene.world=world
def area(name,loc,energy,size,color,target):
    data=bpy.data.lights.new(PREFIX+name,'AREA');data.energy=energy;data.shape='DISK';data.size=size;data.color=color
    ob=bpy.data.objects.new(PREFIX+name,data);studio.objects.link(ob);ob.location=loc
    ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
    return ob
area('Large window key',(-3.0,-2.4,4.0),420,3.0,(1,.93,.83),(-.5,0,.65))
area('Soft front fill',(2.8,-3.3,2.6),200,3.2,(.84,.91,1),(.3,.2,.9))
area('Top rim',(1.2,2.4,3.9),300,2.5,(1,.89,.74),(0,.2,.8))

scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True
prefs=bpy.context.preferences.addons['cycles'].preferences
try:
    prefs.compute_device_type='OPTIX';prefs.get_devices()
    for d in prefs.devices:d.use=d.type=='OPTIX'
    scene.cycles.device='GPU'
except Exception:
    scene.cycles.device='CPU'
scene.render.resolution_x=1600;scene.render.resolution_y=1250;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
scene.render.film_transparent=True
scene.view_settings.view_transform='Standard'
scene.view_settings.exposure=-.65
scene.render.filepath=str(OUT/'service-station-preview.png')

# Photo-calibrated depth and seat height, with an estimated overall scale.
root.scale.y=.76355/.57
for ob in bench.objects:
    if ob.type=='MESH':
        for v in ob.data.vertices:
            world_z=(ob.matrix_world@v.co).z
            if world_z>.1:
                new_z=.1+(world_z-.1)*1.076
                delta=new_z-world_z
                # Bench meshes have local vertical Z except the Y-axis bolster.
                v.co += ob.matrix_world.inverted().to_3x3()@Vector((0,0,delta))
    elif ob.type=='CURVE':
        for sp in ob.data.splines:
            for pt in sp.points:
                world_z=(ob.matrix_world@Vector(pt.co[:3])).z
                if world_z>.1:pt.co.z += (world_z-.1)*.076
bpy.context.view_layer.update()
for ob in list(bench.objects)+list(cabinet.objects)+list(dispenser.objects):
    if ob.type!='MESH' or not any(m in (oak,slat_oak) for m in ob.data.materials):continue
    uv=ob.data.uv_layers.get('Veneer grain · 1.8 metre tile') or ob.data.uv_layers.new(name='Veneer grain · 1.8 metre tile')
    ob.data.uv_layers.active=uv
    uv.active_render=True
    is_slat='Oak round slat' in ob.name
    offset=random.random() if is_slat else 0
    for poly in ob.data.polygons:
        for li in poly.loop_indices:
            v=ob.data.vertices[ob.data.loops[li].vertex_index].co
            if is_slat and abs(poly.normal.z)<.6:
                u=math.atan2(v.y,v.x)*.0285/1.8+offset
                vv=v.z/1.8+offset*.71
            else:
                w=ob.matrix_world@v
                if abs(poly.normal.z)>.6:u,vv=w.x/1.8+.31,w.y/1.8+.2
                elif abs(poly.normal.y)>.6:u,vv=w.x/1.8+.34,w.z/1.8
                else:u,vv=w.y/1.8+.15,w.z/1.8
            uv.data[li].uv=(u,vv)
bpy.ops.object.select_all(action='DESELECT')
divider.select_set(True);bpy.context.view_layer.objects.active=divider
for screen in bpy.data.screens:
    for a in screen.areas:
        if a.type=='VIEW_3D':
            a.spaces.active.region_3d.view_perspective='CAMERA'
            a.spaces.active.shading.type='MATERIAL'
            a.spaces.active.overlay.show_overlays=False
            a.spaces.active.region_3d.view_camera_zoom=5
text=bpy.data.texts.new(PREFIX+'READ ME')
text.write('SERVICE STATION — REFERENCE RECONSTRUCTION\n\n'
           'Furniture only, built from both supplied photographs through Blender MCP.\n'
           'Separate editable collections: bench, cabinet, bores, labels, dispenser.\n'
           'Estimated size: 2.45 m long x 0.83 m deep x 1.58 m high.\n'
           'No measured dimensions supplied; hidden structure is inferred.\n'
           'Five actual through-holes, modeled rims and dark chutes.\n'
           'CC0 scanned oak veneer, procedural vinyl; textures and font packed.\n'
           'Four cameras. Active camera shows the complete reference-side view.\n'
           'Transparent render; no floor, people, walls, basket or shop surroundings.\n'
           'Numpad 0 exits camera. Middle mouse orbits.\n')
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'service-station.blend'))
result={'file':str(OUT/'service-station.blend'),'objects':len(scene.objects),'mesh_objects':sum(o.type=='MESH' for o in scene.objects),'scene':scene.name}

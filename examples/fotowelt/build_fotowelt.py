"""Editable Fotowelt reconstruction, executed in a Better Blender MCP worker.

Coordinates: metres, X across the cabinetry, -Y towards customers, Z up.
The reference supports visible layout/artwork; physical dimensions are estimates.
"""
from pathlib import Path
import json
import math
import time
import bpy
import bmesh
from mathutils import Vector
from better_blender import lathe, pbr_material, point_at

START=time.perf_counter()
HERE=Path(__file__).resolve().parent
ASSETS=HERE/'assets'
OUT=HERE/'output';OUT.mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
for c in list(bpy.data.collections):
    if c.name!='Collection':bpy.data.collections.remove(c)
scene=bpy.context.scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1

def collection(name,parent=None):
    c=bpy.data.collections.new(name);(parent.children if parent else scene.collection.children).link(c);return c
subject=collection('Fotowelt')
frame=collection('01 | Maple architecture',subject)
pickup=collection('02 | Abholstation',subject)
counter=collection('03 | Counter and floor printers',subject)
kiosks=collection('04 | Three photo kiosks',subject)
seating=collection('05 | Bent plywood stools',subject)
graphics=collection('06 | Signage and printed artwork',subject)
props=collection('07 | Counter accessories',subject)
setting=collection('Shop | Context')
studio=collection('Studio | Cameras and lighting')
scene['better_mcp_subject']='Fotowelt'
scene['reference_note']='Single photograph reconstruction. Inferred size: 4.24 m wide, 2.73 m high, 0.80 m cabinet depth.'

def material(name,color,roughness=.45,metallic=0):
    return pbr_material(name,color,roughness,metallic)[0]
ivory=material('Warm white | powder-coated cabinetry',(.82,.785,.705),.32)
laminate=material('White laminate | counters and doors',(.875,.837,.75),.29)
wall=material('Warm plaster',(.72,.64,.52),.82)
floor=material('Large cream porcelain tiles',(.61,.49,.355),.34)
grout=material('Fine sand-coloured grout',(.37,.32,.25),.8)
dark=material('Moulded black ABS',(.012,.014,.012),.28)
rubber=material('Black rubber and cable jackets',(.008,.01,.009),.66)
inset=material('Recess shadow',(.004,.004,.003),.86)
chrome=material('Polished chrome',(.72,.75,.76),.16,1)
brushed=material('Brushed aluminium',(.55,.56,.54),.3,1)
gold=material('Kodak yellow | front fascia',(.94,.58,.015),.28)
red=material('Rossmann red',(.64,.025,.012),.42)
letters=material('Raised dark brown lettering',(.012,.009,.004),.60,0)
letters.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value=.07
ink=material('Printed warm grey',(.085,.075,.056),.8)
paper=material('Brochure paper',(.9,.88,.80),.72)
maple=material('Natural maple veneer',(.68,.48,.29),.42)
image=bpy.data.images.load(str(ASSETS/'maple.png'));image.pack()
node=maple.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
maple.node_tree.links.new(node.outputs['Color'],maple.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
maple_seat=material('Honey maple | stool plywood',(.53,.27,.10),.34)
seat_image=bpy.data.images.load(str(ASSETS/'maple-seat.png'));seat_image.pack()
node=maple_seat.node_tree.nodes.new('ShaderNodeTexImage');node.image=seat_image
maple_seat.node_tree.links.new(node.outputs['Color'],maple_seat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
maple_seat.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.18
glass,glass_node=pbr_material('Clear polished glass',(.86,.96,.89),.055)
glass_node.inputs['Transmission Weight'].default_value=1;glass_node.inputs['IOR'].default_value=1.46
led,led_node=pbr_material('Warm under-header light',(.95,.70,.36),.25)
led_node.inputs['Emission Color'].default_value=(1,.71,.39,1);led_node.inputs['Emission Strength'].default_value=4

def mesh_object(name,verts,faces,mat,group,uvs=None):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);group.objects.link(obj)
    mesh.materials.append(mat)
    if uvs:
        layer=mesh.uv_layers.new(name='UVMap')
        for face,coords in zip(mesh.polygons,uvs):
            for idx,uv in zip(face.loop_indices,coords):layer.data[idx].uv=uv
    return obj

def box(name,loc,size,mat,group=frame,bevel=.002):
    x,y,z=[v/2 for v in size]
    verts=[(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
    faces=[(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]
    uv=[[(0,0),(1,0),(1,1),(0,1)] for _ in faces]
    obj=mesh_object(name,verts,faces,mat,group,uv);obj.location=loc
    if bevel:
        mod=obj.modifiers.new('Soft manufactured edges','BEVEL');mod.width=bevel;mod.segments=3
        mod=obj.modifiers.new('Face weighted normals','WEIGHTED_NORMAL');mod.keep_sharp=True
    return obj

def join(items,name):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in items:obj.select_set(True)
    bpy.context.view_layer.objects.active=items[0];bpy.ops.object.join()
    items[0].name=name;return items[0]

def tube(name,points,radius,mat,group=props):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=2
    curve.bevel_depth=radius;curve.bevel_resolution=4;curve.use_fill_caps=True
    spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
    for p,co in zip(spline.points,points):p.co=(*co,1)
    obj=bpy.data.objects.new(name,curve);group.objects.link(obj);curve.materials.append(mat);return obj

def cylinder(name,loc,radius,depth,mat,group=props,rotation=None):
    edge=min(.001,depth*.15,radius*.06)
    obj=lathe(name,[(0,-depth/2),(radius*.94,-depth/2),(radius,-depth/2+edge),(radius,depth/2-edge),(radius*.94,depth/2),(0,depth/2)],materials=[mat],collection=group,segments=48)
    obj.location=loc
    if rotation:obj.rotation_euler=rotation
    return obj

fonts={}
font_folder=Path('C:/Windows/Fonts')
for key,filename in [('bold','ARIALNB.TTF'),('regular','ARIALN.TTF')]:
    path=font_folder/filename
    if path.exists():fonts[key]=bpy.data.fonts.load(str(path))

def text(name,body,loc,size,mat=ink,group=graphics,align='LEFT',bold=False,depth=.0001):
    data=bpy.data.curves.new(name,'FONT');data.body=body;data.size=size;data.align_x=align;data.align_y='BOTTOM_BASELINE'
    data.extrude=depth;data.bevel_depth=min(depth*.22,.001);data.bevel_resolution=2;data.resolution_u=10
    if fonts:data.font=fonts['bold' if bold else 'regular']
    obj=bpy.data.objects.new(name,data);group.objects.link(obj);obj.location=loc;obj.rotation_euler=(math.pi/2,0,0);data.materials.append(mat)
    return obj

image_materials={}
def photo_material(filename,emission=0):
    if filename in image_materials:return image_materials[filename]
    mat=material('Source pixels | '+filename,(1,1,1),.52)
    p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Specular IOR Level'].default_value=.18
    img=bpy.data.images.load(str(ASSETS/filename));img.pack()
    node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=img
    mat.node_tree.links.new(node.outputs['Color'],p.inputs['Base Color'])
    if emission:
        mat.node_tree.links.new(node.outputs['Color'],p.inputs['Emission Color']);p.inputs['Emission Strength'].default_value=emission
    image_materials[filename]=mat;return mat

def picture(name,filename,loc,size,group=graphics,emission=.08):
    # Closed backing; only its front face uses the photograph.
    obj=box(name,loc,(size[0],.0015,size[1]),paper,group,0)
    obj.data.materials.append(photo_material(filename,emission));obj.data.polygons[1].material_index=1
    return obj

# Cabinet architecture: maple end panels, continuous cornice, rounded slat rhythm.
for x in [-2.105,2.105]:box('Full-height maple end panel', (x,-.05,1.24),(.03,.80,2.48),maple)
box('Maple plinth',(0,-.035,.045),(4.22,.73,.075),maple)
box('Photo bay backing',(.57,.333,1.50),(3.03,.038,1.24),laminate)
box('Pickup bay backing',(-1.525,.333,1.1),(1.1,.038,2.18),laminate)
box('Deep vertical maple divider',(-.948,-.038,1.095),(.078,.78,2.12),maple)
box('Cornice | lower maple beam',(0,-.047,2.108),(4.24,.804,.095),maple,bevel=.004)
box('Cornice | upper border',(0,-.047,2.473),(4.24,.804,.035),maple,bevel=.003)
box('Cornice | slat backing',(0,-.218,2.298),(4.18,.20,.32),maple)
slats=[]
for i in range(53):
    x=-2.052+i*4.104/52
    r=.025
    cross=[(r*math.sin(t),-r*math.cos(t)) for t in [(-math.pi/2+j*math.pi/12) for j in range(13)]]
    n=len(cross);v=[(a,b,z) for z in [-.156,.156] for a,b in cross]
    f=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)]
    uv=[[(v[k][0]/(.05)+.5,v[k][1]/(.05)+.5) for k in face] if idx<2 else [(0,0),(1,0),(1,1),(0,1)] for idx,face in enumerate(f)]
    obj=mesh_object('Maple reed %02d'%i,v,f,maple,frame,uv);obj.location=(x,-.328,2.296)
    for face in obj.data.polygons:face.use_smooth=len(face.vertices)==4
    slats.append(obj)
join(slats,'53 rounded maple slats | welded individual solids')
box('Warm linear light diffuser',(.59,-.237,2.052),(2.94,.025,.006),led,bevel=.001)
box('Ceiling fascia',(0,.535,2.735),(4.32,.02,.48),wall,bevel=0)
text('Abholstation | raised lettering','Abholstation',(-2.05,-.335,2.52),.30,letters,bold=True,depth=.007)
text('Fotowelt | raised lettering','Fotowelt',(.02,-.335,2.505),.44,letters,bold=True,depth=.010)

# Pickup locker: physical door seams, screen and lower photo drawers.
box('Pickup cabinet carcass',(-1.535,-.01,1.085),(1.085,.70,2.05),ivory,pickup)
box('Pickup instruction panel',(-1.535,-.375,1.492),(1.061,.024,1.14),laminate,pickup)
picture('Original pickup instructions','pickup-artwork.png',(-1.535,-.389,1.502),(1.045,1.115),pickup,.025)
for x in [-2.055,-1.64,-1.015]:box('Vertical locker reveal',(x,-.393,1.497),(.003,.005,1.14),ivory,pickup,0)
box('Locker seam | horizontal',(-1.535,-.393,1.195),(1.06,.006,.003),ivory,pickup,0)
for z in [.767,.403]:
    box('Photo order drawer',(-1.535,-.378,z),(1.057,.025,.349),laminate,pickup,.002)
    box('Recessed drawer pull',(-1.535,-.396,z+.11),(.94,.012,.031),brushed,pickup,.001)
    text('Fotowelt drawer branding','FOTOWELT',(-1.68,-.394,z-.056),.058,ink,pickup,bold=True)
    text('Drawer red icon','+',(-1.376,-.396,z-.05),.055,red,pickup,bold=True)
box('Pickup portrait touch terminal',(-1.514,-.406,1.49),(.158,.025,.333),dark,pickup,.008)
picture('Pickup touchscreen pixels','pickup-screen.png',(-1.514,-.420,1.498),(.132,.290),pickup,.25)
cylinder('Pickup terminal status light',(-1.514,-.424,1.336),.003,.002,led,pickup,(math.pi/2,0,0))

# Counter, white floor printers, slots, caster wheels and vents.
box('Counter | laminated substrate',(.59,-.097,1.013),(2.98,.846,.036),laminate,counter,.003)
box('Counter | polished glass surface',(.59,-.096,1.038),(2.99,.854,.013),glass,counter,.002)
box('Counter | reflective front edge',(.59,-.524,1.026),(2.99,.009,.017),brushed,counter,.001)
for i,x in enumerate([-.505,.47,1.455],1):
    w=.87 if i<3 else .91
    box(f'Printer {i} | cabinet',(x,-.062,.523),(w,.714,.924),ivory,counter,.012)
    box(f'Printer {i} | separate front panel',(x,-.426,.537),(w-.027,.018,.874),laminate,counter,.006)
    box(f'Printer {i} | kick recess',(x,-.404,.07),(w-.06,.025,.055),inset,counter,.002)
    for dx in [-w*.36,w*.36]:
        for y in [-.31,.21]:cylinder(f'Printer {i} | recessed caster',(x+dx,y,.047),.035,.043,rubber,counter,(math.pi/2,0,0))
    # Kodak self-service output apertures and raised surrounds.
    slotz=.30 if i==2 else .61
    box(f'Printer {i} | output recess',(x,-.440,slotz),(.295,.024,.095),inset,counter,.008)
    box(f'Printer {i} | output lip',(x,-.458,slotz-.035),(.282,.042,.018),dark,counter,.004)
    box(f'Printer {i} | paper guide',(x,-.452,slotz-.019),(.259,.006,.006),brushed,counter,.001)
    text(f'Printer {i} | Kodak mark','Kodak Moments',(x-.149,-.44,slotz+.135),.027,red,counter,bold=True)
    if i==2:
        text('Enlargement formats','Ausdrucke\n20 x 20\nund\n20 x 30',(x,-.441,.654),.031,ink,counter,'CENTER')
    else:
        box(f'Printer {i} | lower access hatch',(x,-.439,.187),(.48,.013,.26),ivory,counter,.008)
    # Fine side ventilation; small mesh bars joined to one editable part.
    bars=[box('Vent slat',(x+w/2+.001,-.15,.30+j*.012),(.003,.25,.004),ink,counter,0) for j in range(9)]
    join(bars,f'Printer {i} | nine ventilation slats')

# Three independent Kodak photo kiosks. Screens tilt back; cables and ports are real geometry.
for i,x in enumerate([-.52,.47,1.465],1):
    box(f'Kiosk {i} | lower ABS base',(x,-.095,1.115),(.616,.445,.113),dark,kiosks,.013)
    box(f'Kiosk {i} | yellow media fascia',(x,-.324,1.104),(.589,.013,.048),gold,kiosks,.003)
    box(f'Kiosk {i} | output aperture',(x+.064,-.335,1.112),(.34,.012,.018),inset,kiosks,.002)
    box(f'Kiosk {i} | card reader strip',(x-.201,-.335,1.112),(.10,.012,.027),dark,kiosks,.002)
    for j in range(3):box('Memory card socket',(x-.222+j*.024,-.343,1.112),(.017,.008,.004),inset,kiosks,0)
    text(f'Kiosk {i} | reader legend','USB  SD',(x-.247,-.344,1.086),.010,ink,kiosks,bold=True)
    box(f'Kiosk {i} | pedestal',(x,.052,1.235),(.30,.185,.14),dark,kiosks,.011)
    box(f'Kiosk {i} | pedestal seam',(x,-.044,1.251),(.21,.008,.035),rubber,kiosks,.002)
    cylinder(f'Kiosk {i} | display hinge',(x,.045,1.338),.045,.21,dark,kiosks,(0,math.pi/2,0))
    monitor=bpy.data.objects.new(f'Kiosk {i} | adjustable display',None);kiosks.objects.link(monitor)
    monitor.location=(x,-.01,1.53);monitor.rotation_euler.x=math.radians(-11)
    elements=[box(f'Kiosk {i} | black monitor housing',(0,0,0),(.644,.047,.394),dark,kiosks,.008),
        box(f'Kiosk {i} | fine yellow bezel',(0,-.025,0),(.622,.007,.374),gold,kiosks,.002),
        box(f'Kiosk {i} | inner black bezel',(0,-.030,0),(.611,.005,.363),dark,kiosks,.002),
        picture(f'Kiosk {i} | original screen UI','kiosk-screen.png',(0,-.034,.003),(.590,.334),kiosks,.4)]
    for obj in elements:obj.parent=monitor
    cable=[(x+.20,.06,1.42),(x+.29,.07,1.29),(x+.32,-.03,1.15),(x+.29,-.26,1.053),(x+.13,-.37,1.054),(x-.07,-.31,1.058)]
    tube(f'Kiosk {i} | coiled USB lead',cable,.004,rubber,kiosks)
    # Transparent photograph receiving tray in front of each kiosk.
    box(f'Kiosk {i} | clear receiving tray',(x,-.369,1.063),(.59,.195,.009),glass,kiosks,.002)
    for dx in [-.291,.291]:box('Acrylic tray side',(x+dx,-.368,1.085),(.005,.194,.042),glass,kiosks,.001)
    box('Tray front wall',(x,-.466,1.079),(.59,.005,.035),glass,kiosks,.001)

# Plywood stool shells: one continuous bent, closed solid per stool.
def stool_shell(name,cx):
    section=[(-1.218,1.12),(-1.206,1.02),(-1.197,.92),(-1.190,.864)]
    for j in range(1,10):
        t=(math.pi/2)*j/9
        section.append((-1.110-.080*math.cos(t),.864-.080*math.sin(t)))
    section.extend([(-1.04,.784),(-.96,.788),(-.87,.798),(-.80,.814)])
    cols=13;verts=[]
    for side in [-1,1]:
        for k,(y,z) in enumerate(section):
            before=section[max(0,k-1)];after=section[min(len(section)-1,k+1)]
            dy,dz=after[0]-before[0],after[1]-before[1]
            length=math.hypot(dy,dz);ny,nz=-dz/length,dy/length
            for j in range(cols):
                u=j/(cols-1)*2-1
                width=.235-.008*math.cos(k/(len(section)-1)*math.pi)
                # A shallow crosswise dish catches a broad highlight on the maple back.
                verts.append((cx+u*width,y+.013*u*u+side*.0065*ny,z+.003*u*u+side*.0065*nz))
    rows=len(section);size=rows*cols;faces=[];uvs=[]
    for side in [0,1]:
        for k in range(rows-1):
            for j in range(cols-1):
                q=[side*size+k*cols+j,side*size+k*cols+j+1,side*size+(k+1)*cols+j+1,side*size+(k+1)*cols+j]
                if side==1:q.reverse()
                faces.append(q);uvs.append([((v%cols)/(cols-1),1-((v%size)//cols)/(rows-1)) for v in q])
    boundary=list(range(cols))+[k*cols+cols-1 for k in range(1,rows)]+[(rows-1)*cols+j for j in range(cols-2,-1,-1)]+[k*cols for k in range(rows-2,0,-1)]
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):
        faces.append((a,a+size,b+size,b));uvs.append([(0,0),(0,.03),(1,.03),(1,0)])
    obj=mesh_object(name,verts,faces,maple_seat,seating,uvs)
    bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(obj.data);bm.free()
    for face in obj.data.polygons:face.use_smooth=True
    mod=obj.modifiers.new('Plywood edge radius','BEVEL');mod.width=.004;mod.segments=3
    return obj

for i,x in enumerate([-.52,.83],1):
    stool_shell(f'Stool {i} | continuous bent maple shell',x)
    base=lathe(f'Stool {i} | domed chrome base',[(0,.017),(.25,.017),(.263,.025),(.26,.038),(.21,.054),(.115,.063),(.037,.072),(.027,.075),(0,.075)],materials=[chrome],collection=seating,segments=96);base.location=(x,-.995,0)
    cylinder(f'Stool {i} | rubber floor ring',(x,-.995,.014),.249,.018,rubber,seating)
    cylinder(f'Stool {i} | pedestal',(x,-.995,.359),.027,.58,chrome,seating)
    cylinder(f'Stool {i} | hydraulic sleeve',(x,-.995,.616),.039,.19,brushed,seating)
    box(f'Stool {i} | seat bracket',(x,-.983,.756),(.27,.265,.025),chrome,seating,.006)
    pts=[(x-.05,-.995,.34),(x-.05,-1.16,.34),(x-.035,-1.24,.34),(x+.29,-1.24,.34),(x+.33,-1.20,.34),(x+.33,-1.00,.34),(x+.29,-.97,.34),(x+.03,-.97,.34)]
    tube(f'Stool {i} | rectangular chrome footrest',pts,.012,chrome,seating)
    tube(f'Stool {i} | height lever',[(x+.015,-.99,.70),(x+.22,-.99,.70),(x+.255,-1.07,.72)],.006,chrome,seating)
    box(f'Stool {i} | lever grip',(x+.255,-1.09,.72),(.032,.09,.018),dark,seating,.006)

# Photo wall: real source collage and companion poster, in slim black frames.
box('Memories collage | black frame',(.238,.280,1.755),(1.91,.025,.68),dark,graphics,.002)
picture('Memories collage | reference artwork','memories-poster.png',(.238,.265,1.855),(1.884,.446),graphics,.025)
box('Right photo offer | frame',(1.66,.280,1.796),(.545,.023,.635),ivory,graphics,.001)
picture('Right photo offer | reference artwork','right-poster.png',(1.66,.267,1.796),(.52,.61),graphics)

# Small counter objects, acrylic leaflet holder, sample print stack.
box('Acrylic leaflet stand | base',(-.027,-.108,1.064),(.26,.20,.008),glass,props,.001)
stand=box('Acrylic leaflet stand | sloped back',(-.027,-.010,1.236),(.255,.009,.32),glass,props,.001);stand.rotation_euler.x=math.radians(-12)
card=box('Red promotional leaflet',(-.027,-.026,1.233),(.18,.002,.255),red,props,.001);card.rotation_euler.x=math.radians(-12)
text('Leaflet caption','Deine Bilder.\nDeine Momente.',(-.027,-.063,1.265),.019,paper,props,'CENTER',True)
for i in range(5):box('Sample print stack',(.007,-.305,1.058+i*.0017),(.205,.138,.0015),paper,props,.0003)
for x in [-.155,.12]:box('Brochure display upright',(x,-.010,1.249),(.004,.2,.374),glass,props,.001)

# Restrained retail context: tiled floor, wall and right-hand photo accessory shelf.
box('Tile grout substrate',(0,-1.1,-.04),(9,8,.08),grout,setting,0)
tiles=[]
for ix in range(-5,6):
    for iy in range(-5,4):tiles.append(box('Porcelain floor tile',(ix*.60,iy*.60,-.002),(.597,.597,.012),floor,setting,.0008))
join(tiles,'60 cm porcelain tile grid')
box('Shop rear wall',(0,.62,1.65),(9,.16,3.3),wall,setting,0)
box('Shop ceiling',(0,-1.0,3.22),(10,8,.09),laminate,setting,0)
box('Accessories | back panel',(2.58,.267,1.23),(.84,.038,2.46),ivory,setting,.002)
for x in [2.17,2.99]:box('Accessories | perforated upright',(x,.03,1.23),(.026,.49,2.46),brushed,setting,.001)
for z in [.18,.68,1.17,1.65,2.15]:
    box('Accessories | shallow shelf',(2.58,-.017,z),(.82,.52,.018),laminate,setting,.002)
    box('Accessories | price rail',(2.58,-.285,z+.02),(.82,.016,.035),brushed,setting,.001)
    for k in range(5):
        box('Accessories | price ticket',(2.24+k*.147,-.296,z+.02),(.093,.002,.025),paper,setting,0)
album_colors=[(.46,.50,.42),(.62,.51,.39),(.48,.37,.26),(.72,.58,.51),(.72,.70,.62)]
for i in range(8):
    mat=material('Photo album cloth %d'%i,album_colors[i%5],.85)
    box('Photo album | standing spine',(2.235+i*.097,.015,2.318),(.081,.28,.30),mat,setting,.003)
    box('Photo album | pale spine band',(2.235+i*.097,-.130,2.235),(.079,.003,.025),paper,setting,.0003)
for z in [1.22,1.70]:
    for i in range(6):
        x=2.23+i*.137
        box('Photo accessories | card pack',(x,-.005,z+.115),(.104,.015,.19),paper,setting,.002)
        box('Photo accessories | red brand strip',(x,-.015,z+.17),(.104,.004,.045),red,setting,0)
        cylinder('Photo accessories | memory card motif',(x,-.018,z+.092),.023,.003,dark,setting,(math.pi/2,0,0))

# Lighting kept outside the subject collection. Broad warm retail illumination.
world=bpy.data.worlds.new('Warm shop ambience');world.use_nodes=True
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.73,.79,.88,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.40;scene.world=world
def area(name,loc,target,power,color,size,size_y=None):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color;data.shape='RECTANGLE';data.size=size;data.size_y=size if size_y is None else size_y
    obj=bpy.data.objects.new(name,data);studio.objects.link(obj);obj.location=loc;point_at(obj,target);return obj
area('Ceiling | broad warm source',(-1,-1.2,3.05),(0,-.1,1),620,(1,.83,.65),4.5,2.2)
area('Aisle | soft front fill',(1.8,-4,2.7),(0,0,1.4),360,(1,.91,.79),4,3)
area('Right | cool bounce',(4.0,-1.5,2.8),(.8,.0,1.2),210,(.83,.90,1),2.5,2)
area('Counter | concealed strip',(.58,-.1,2.04),(.58,-.03,1.25),28,(1,.77,.48),2.8,.025)

def camera(name,loc,target,lens):
    data=bpy.data.cameras.new(name);data.lens=lens;data.sensor_width=36;data.clip_end=100
    obj=bpy.data.objects.new(name,data);studio.objects.link(obj);obj.location=loc;point_at(obj,target);return obj
hero=camera('Camera | complete station',(3.5,-7.5,1.92),(.12,-.03,1.38),48)
camera('Camera | front elevation',(.12,-8.8,1.42),(.12,0,1.42),48)
camera('Camera | kiosk and stool detail',(2.8,-4.0,2.25),(.51,-.22,1.10),54)
scene.camera=hero
scene.render.engine='CYCLES';scene.cycles.samples=96;scene.cycles.use_denoising=True
scene.cycles.max_bounces=8;scene.cycles.transmission_bounces=6
scene.render.resolution_x=1600;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.render.filepath=str(OUT/'fotowelt-render.png')
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-.40
scene.render.threads_mode='FIXED';scene.render.threads=6

# Material preview exposes the actual photo surfaces without a live Cycles render.
for screen in bpy.data.screens:
    for a in screen.areas:
        if a.type=='VIEW_3D':
            a.spaces.active.shading.type='MATERIAL';a.spaces.active.shading.color_type='MATERIAL'
            a.spaces.active.shading.use_scene_world=False;a.spaces.active.shading.use_scene_lights=False
            a.spaces.active.overlay.show_overlays=False;a.spaces.active.region_3d.view_perspective='CAMERA'
bpy.ops.object.select_all(action='DESELECT')
for img in bpy.data.images:
    if img.source=='FILE' and not img.packed_file:img.pack()
bpy.ops.file.pack_all()
notes=bpy.data.texts.new('READ ME | Fotowelt')
notes.write('FOTOWELT — reference reconstruction\n\nBuilt through Better Blender MCP isolated workers.\nAll image textures and fonts are packed. Units: metres.\n\nCollections 01–07 contain editable station components.\nShop contains the optional surrounding retail context.\nStudio contains the complete, front and detail cameras.\nNumpad 0 enters/exits the active camera. Middle mouse orbits.\nMaterial Preview shows the photo surfaces without running Cycles.\n\nWidth, depth and hidden surfaces are estimated from one photograph.\nOriginal poster and screen pixels come from 52143-detailp.jpeg.\nSoftware licence does not grant rights to the source artwork or marks.\n')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'fotowelt.blend'))
bpy.ops.render.render(write_still=True)
stats={'elapsed_seconds':round(time.perf_counter()-START,2),'objects':len(subject.all_objects),'mesh_objects':sum(o.type=='MESH' for o in subject.all_objects),'dimensions_estimated_m':[4.24,.80,2.73],
    'geometry':'Three complete kiosks, pickup lockers, three floor printers, two chrome/plywood stools, 53 rounded slats, extruded lettering, glass trays, posters and accessories.',
    'reference':'../assets/reference.jpeg','recipe':'../build_fotowelt.py'}
(OUT/'model-info.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
BETTER_BLENDER_OUTPUTS={'blend':str(OUT/'fotowelt.blend'),'render':str(OUT/'fotowelt-render.png'),'model_info':str(OUT/'model-info.json')}
print(json.dumps(stats))

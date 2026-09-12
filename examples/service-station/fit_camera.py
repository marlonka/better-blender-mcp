"""Least-squares reference camera calibration from manually identified landmarks."""
import bpy
import numpy as np
from mathutils import Vector, Euler
from bpy_extras.object_utils import world_to_camera_view
from pathlib import Path
import json

scene=bpy.context.scene
cam=scene.camera
landmarks=[
    ((-.029,.57,1.315),(478,96)),
    ((-.029,.070,1.315),(598,99)),
    ((-.029,0,1.245),(616,118)),
    ((-.029,0,.493),(614,341)),
    ((0,-.012,1.13),(622,155)),
    ((.94,-.012,1.13),(816,134)),
    ((0,-.012,.142),(622,455)),
    ((.929,-.012,.142),(814,374)),
    ((.115,-.016,.950),(658,201)),
    ((.350,-.016,.950),(708,193)),
    ((.583,-.016,.950),(754,185)),
    ((.815,-.016,.950),(798,178)),
    ((.815,-.016,.585),(798,278)),
    ((-.7,.582,.493),(326,332)),
    ((-.7,-.012,.493),(450,388)),
]

target=np.array([p for _,p in landmarks]).reshape(-1)
scene.render.resolution_x=940;scene.render.resolution_y=530
def predict(p):
    x,y,z,rx,ry,rz,lens,depth,divider_h,split,seat_h=p
    cam.location=(x,y,z);cam.rotation_euler=(rx,ry,rz)
    cam.data.lens=lens;cam.data.shift_x=0;cam.data.shift_y=0
    bpy.context.view_layer.update()
    out=[]
    for idx,(co,_) in enumerate(landmarks):
        co=list(co)
        if idx in (0,13):co[1]=depth
        if idx in (0,1):co[2]=divider_h
        if idx==2:co[2]=divider_h-.070
        if idx in (3,13,14):co[2]=seat_h
        if idx in (13,14):co[0]=split
        v=world_to_camera_view(scene,cam,Vector(co))
        out.extend([v.x*940,(1-v.y)*530])
    return np.array(out)

p=np.array([-1.8,-1.6,1.4,1.5,0,-.73,28,.65,1.315,-.70,.493],dtype=float)
damp=1
for iteration in range(100):
    pred=predict(p);res=pred-target
    jac=np.empty((len(res),len(p)))
    for i in range(len(p)):
        h=.0002 if i<6 else (.01 if i==6 else .00005)
        q=p.copy();q[i]+=h;jac[:,i]=(predict(q)-pred)/h
    scale=np.sqrt(np.maximum(np.sum(jac*jac,axis=0),1e-8))
    j=jac/scale
    delta=np.linalg.solve(j.T@j+np.eye(len(p))*damp,j.T@res)/scale
    trial=p-delta
    if trial[6]>10 and trial[6]<200 and np.linalg.norm(predict(trial)-target)<np.linalg.norm(res):
        p=trial;damp=max(1e-7,damp*.5)
    else:damp=min(1e6,damp*4)
pred=predict(p)
report={'parameters':p.tolist(),'landmark_rmse_px':float(np.sqrt(np.mean((pred-target)**2))),
        'landmarks':[{'reference':t,'projected':v.tolist()} for (_,t),v in zip(landmarks,pred.reshape(-1,2))]}
path=Path(__file__).resolve().parent/'output/reference-camera-fit.json'
path.write_text(json.dumps(report,indent=2))
result=report

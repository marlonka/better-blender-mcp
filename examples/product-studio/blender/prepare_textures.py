"""Recover cylindrical UV artwork from the supplied photograph, without retyping it.

This is a geometric resampling, not recovered original packaging artwork. Only
the visible hemisphere is evidenced; the back is a neutral colour continuation.
Run with the repository's Python environment (numpy + Pillow).
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / 'public' / 'assets'
source = np.asarray(Image.open(ASSETS/'reference.png').convert('RGB'), dtype=np.float32)

def sample(x, y):
    x, y = np.broadcast_arrays(np.clip(x, 0, source.shape[1]-1.001), np.clip(y, 0, source.shape[0]-1.001))
    xi, yi = x.astype(int), y.astype(int)
    dx, dy = (x-xi)[...,None], (y-yi)[...,None]
    return ((source[yi,xi]*(1-dx)+source[yi,xi+1]*dx)*(1-dy)
        +(source[yi+1,xi]*(1-dx)+source[yi+1,xi+1]*dx)*dy)

w,h=4096,1024
theta=(np.arange(w)[None,:]/(w-1)-.5)*2*np.pi
v=np.arange(h)[:,None]/(h-1)
sx=407.5+334.5*np.sin(theta)
sy=348+27*np.cos(theta)+v*451
artwork=sample(sx,sy)
top=np.array([158,35,29],dtype=float)
bottom=np.array([204,92,53],dtype=float)
blend=np.clip((v-.57)*18,0,1)
back=top[None,None,:]*(1-blend[...,None])+bottom[None,None,:]*blend[...,None]
weight=np.clip((np.pi/2-np.abs(theta))/.05,0,1)[...,None]
label=artwork*weight+back*(1-weight)
Image.fromarray(np.uint8(np.clip(label,0,255))).save(ASSETS/'label.png',optimize=True)

# The shallow top ellipse contains only ~56 pixels of vertical evidence.
u=np.linspace(-1,1,1024)[None,:]
t=np.linspace(-1,1,1024)[:,None]
lid=sample(407+333*u,69+27*t)
Image.fromarray(np.uint8(lid)).save(ASSETS/'lid-top.png',optimize=True)

# Deterministic microstructure for real-time PBR. Values are data, not sRGB.
rng=np.random.default_rng(42)
noise=rng.normal(0,1,(512,512))
for _ in range(3):
    noise=(noise+np.roll(noise,1,0)+np.roll(noise,-1,0)+np.roll(noise,1,1)+np.roll(noise,-1,1))/5
dx=np.roll(noise,1,1)-np.roll(noise,-1,1)
dy=np.roll(noise,1,0)-np.roll(noise,-1,0)
normal=np.stack((.5+dx*.13,.5+dy*.13,np.ones_like(dx)),axis=-1)
Image.fromarray(np.uint8(np.clip(normal,0,1)*255)).save(ASSETS/'micro-normal.png')
(ASSETS/'provenance.json').write_text(json.dumps({
    'source':'User-supplied front photograph of enerBiO Topping Gebrannte Winternuesse 250 g',
    'method':'Inverse cylindrical projection, 4096 x 1024, plus sampled cap top',
    'evidenced':'Visible front label, silhouette, colours and cap top',
    'inferred':'Back, glass wall thickness, thread geometry and absolute dimensions',
    'dimensions_m':{'diameter':.0846*.965,'height':.0962},
    'scale':'Estimated from image proportions; no physical measurement provided',
    'trademark':'enerBiO and ROSSMANN belong to their respective owners; independent reconstruction study'
},indent=2),encoding='utf-8')
print('Prepared label, cap and microstructure textures')

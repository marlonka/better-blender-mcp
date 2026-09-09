"""Rectify source artwork for the modeled surfaces; generate a maple material tile."""
from pathlib import Path
import json
import shutil
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
source_path = ASSETS / 'reference.jpeg'
if not source_path.exists():
    shutil.copyfile(Path.home() / 'Downloads' / '52143-detailp.jpeg', source_path)
source = Image.open(source_path).convert('RGB')

def rectify(name, quad, size):
    """Output rectangle -> source quadrilateral, TL/TR/BR/BL pixel coordinates."""
    w,h=size
    matrix,values=[],[]
    for (x,y),(u,v) in zip([(0,0),(w,0),(w,h),(0,h)],quad):
        matrix.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]])
        values.extend([u,v])
    coefficients=np.linalg.solve(np.array(matrix),np.array(values))
    source.transform(size,Image.Transform.PERSPECTIVE,coefficients,Image.Resampling.BICUBIC).save(ASSETS/name)

# The unobstructed upper artwork. The modeled black poster backing continues
# below it; monitor pixels from the foreground must not become printed artwork.
rectify('memories-poster.png',[(396,168),(696,146),(696,214),(394,228)],(1536,370))
rectify('right-poster.png',[(735,144),(795,141),(797,211),(735,216)],(480,600))
rectify('kiosk-screen.png',[(704,226),(806,225),(803,280),(699,278)],(768,420))
rectify('pickup-artwork.png',[(165,178),(328,158),(326,331),(164,333)],(900,1080))
rectify('pickup-screen.png',[(238,234),(252,233),(252,264),(238,264)],(150,300))

# A deterministic, non-photographic material tile. Fine fibres run vertically.
rng=np.random.default_rng(52143)
n=1024
x=np.linspace(0,1,n)[None,:]; y=np.linspace(0,1,n)[:,None]
warp=x+.011*np.sin(y*8+x*5)+.004*np.sin(y*19+x*16)
grain=np.sin(warp*280)+.42*np.sin(warp*1040)+.14*np.sin(warp*3100)
fibres=rng.normal(0,1,(1,n))*.7+rng.normal(0,.38,(n,n))
tone=grain*3.6+fibres
wood=np.clip(np.array([216,179,139])[None,None,:]+tone[:,:,None]*np.array([1,.86,.65]),0,255).astype('uint8')
Image.fromarray(wood).save(ASSETS/'maple.png')
seat=np.clip(np.array([193,140,86])[None,None,:]+tone[:,:,None]*np.array([1,.86,.65]),0,255).astype('uint8')
Image.fromarray(seat).save(ASSETS/'maple-seat.png')
(ASSETS/'provenance.json').write_text(json.dumps({
    'reference':'User-supplied 52143-detailp.jpeg, 940 x 530 pixels',
    'artwork':'Perspective-rectified poster, screen and pickup panel crops from the reference; source pixels, no invented portraits.',
    'geometry':'Editable reconstruction. Width, height, depth and hidden details estimated from a single photo.',
    'wood':'Deterministic synthetic maple-grain material tile.',
    'rights':'Reference photograph, printed artwork and marks retain their owners\u2019 rights.'
},indent=2),encoding='utf-8')
print('Prepared photo artwork and maple material')

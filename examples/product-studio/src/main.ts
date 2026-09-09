import './style.css';
import { createIcons, ArrowUpRight, Scan, Leaf, Sprout, Sparkles, RotateCcw, Maximize, Minimize, MoveUpRight, ArrowUp, X, Download, ArrowDown } from 'lucide';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const icons = { ArrowUpRight, Scan, Leaf, Sprout, Sparkles, RotateCcw, Maximize, Minimize, MoveUpRight, ArrowUp, X, Download, ArrowDown };
createIcons({ icons });
const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const canvas = $<HTMLCanvasElement>('#canvas');
const stage = $('#studio');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const announce = (message: string) => { $('#announcement').textContent = message; };

class Spring {
  velocity = 0;
  constructor(public value: number, public target = value) {}
  update(dt: number, snap = false) {
    if (snap) { this.value = this.target; this.velocity = 0; return this.value; }
    // Critically damped spring, integrated at a fixed maximum substep.
    const count = Math.max(1, Math.ceil(dt / (1 / 120)));
    for (let i = 0; i < count; i++) {
      const h = dt / count;
      this.velocity += (140 * (this.target - this.value) - 24 * this.velocity) * h;
      this.value += this.velocity * h;
    }
    return this.value;
  }
  get settled() { return Math.abs(this.target-this.value) < .00005 && Math.abs(this.velocity) < .00005; }
}

let renderer: THREE.WebGLRenderer;
let controls: OrbitControls;
let camera: THREE.OrthographicCamera;
let scene: THREE.Scene;
let product: THREE.Group | null = null;
let cap: THREE.Object3D | undefined;
let capBase = 0;
let envTarget: THREE.WebGLRenderTarget;
let shadow: THREE.Mesh;
let currentView = 'object';
let currentLight = 'daylight';
let autoRotate = false;
let userInteracting = false;
let loaded = false;
let needsRender = true;
let idleFrames = 0;
let raf = 0;
let inFrame = false;
let previousTime = 0;
const lift = new Spring(0);
const zoom = new Spring(1);
const targetY = new Spring(0);
const yaw = new Spring(0);
const exposure = new Spring(.76);
const key = new THREE.DirectionalLight(0xfff8ed, 1.4);
const fill = new THREE.DirectionalLight(0xffffff, .45);
const rim = new THREE.DirectionalLight(0xffffff, 2.0);
const home = new THREE.Vector3(0, .42, 5);

function wake() {
  needsRender = true;
  idleFrames = 0;
  stage.dataset.rendering = 'active';
  if (!raf && !inFrame && !document.hidden) { previousTime = performance.now(); raf = requestAnimationFrame(frame); }
}

function setMotion(value: boolean) {
  autoRotate = value;
  $('#motion').setAttribute('aria-pressed', String(value));
  announce(value ? 'Auto rotate on' : 'Auto rotate off');
  wake();
}

function setView(view: string) {
  if (!loaded) return;
  currentView = view;
  setMotion(false);
  document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === view)));
  controls.target.set(0, 0, 0);
  camera.position.copy(home);
  controls.update();
  yaw.target = view === 'layers' ? -.22 : 0;
  lift.target = view === 'layers' ? .023 : 0;
  zoom.target = view === 'detail' ? 1.66 : view === 'layers' ? .90 : 1;
  targetY.target = view === 'detail' ? -.13 : view === 'layers' ? .12 : 0;
  $('#view-label').textContent = view === 'detail' ? '02 / UP CLOSE' : view === 'layers' ? '03 / LIFT THE LID' : '01 / THE OBJECT';
  $('#stage-caption').textContent = view === 'detail' ? 'The artwork, wrapped around every curve.' : view === 'layers' ? 'A gentle twist. A glimpse inside.' : 'Glass, paper, and a little winter magic.';
  announce(view === 'layers' ? 'Lid lifted; glass threads and contents revealed' : view === 'detail' ? 'Close view of the printed label' : 'Front product view');
  wake();
}

function setLighting(mood: string) {
  currentLight = mood;
  stage.dataset.mood = mood;
  document.querySelectorAll<HTMLButtonElement>('[data-light]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.light === mood));
    button.classList.toggle('active', button.dataset.light === mood);
  });
  if (mood === 'warm') {
    key.color.set(0xffddaa); fill.color.set(0xffecd5); rim.color.set(0xffe5c5);
    exposure.target = .78;
    scene.environmentIntensity = .65;
  } else if (mood === 'dark') {
    key.color.set(0xffe9d2); fill.color.set(0xc9ddff); rim.color.set(0xffe4bc);
    exposure.target = .56;
    scene.environmentIntensity = .50;
  } else {
    key.color.set(0xfff8ed); fill.color.set(0xffffff); rim.color.set(0xffffff);
    exposure.target = .76;
    scene.environmentIntensity = .7;
  }
  announce(`${mood === 'dark' ? 'Midnight' : mood === 'warm' ? 'Warm' : 'Daylight'} studio lighting`);
  wake();
}

function makeShadow() {
  const element = document.createElement('canvas');
  element.width = element.height = 256;
  const context = element.getContext('2d')!;
  const gradient = context.createRadialGradient(128,128,12,128,128,128);
  gradient.addColorStop(0, 'rgba(72,53,25,.26)');
  gradient.addColorStop(.40, 'rgba(72,53,25,.16)');
  gradient.addColorStop(.73, 'rgba(72,53,25,.035)');
  gradient.addColorStop(1, 'rgba(72,53,25,0)');
  context.fillStyle = gradient;
  context.fillRect(0,0,256,256);
  const texture = new THREE.CanvasTexture(element);
  texture.colorSpace = THREE.SRGBColorSpace;
  shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.9,2.9), new THREE.MeshBasicMaterial({map:texture, transparent:true, depthWrite:false}));
  shadow.rotation.x = -Math.PI/2;
  shadow.position.set(0,-.894,0);
  scene.add(shadow);
}

async function init() {
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha:true, antialias:true, powerPreference:'high-performance' });
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    renderer.setClearColor(0x000000,0);
    renderer.toneMapping = THREE.LinearToneMapping;
    renderer.toneMappingExposure = exposure.value;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    scene = new THREE.Scene();
    camera = new THREE.OrthographicCamera(-1.5,1.5,1.22,-1.22,.01,50);
    camera.position.copy(home);
    controls = new OrbitControls(camera, canvas);
    controls.enableDamping = !reducedMotion.matches;
    controls.dampingFactor = .075;
    controls.enablePan = false;
    controls.minZoom = .65;
    controls.maxZoom = 2.7;
    controls.minPolarAngle = .23;
    controls.maxPolarAngle = Math.PI*.57;
    controls.rotateSpeed = .65;
    controls.zoomSpeed = .7;
    controls.addEventListener('change', wake);
    controls.addEventListener('start', () => { userInteracting = true; setMotion(false); zoom.value = zoom.target = camera.zoom; });
    controls.addEventListener('end', () => { userInteracting = false; zoom.value = zoom.target = camera.zoom; wake(); });
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    envTarget = pmrem.fromScene(room,.04);
    scene.environment = envTarget.texture;
    scene.environmentIntensity = .7;
    room.dispose();
    pmrem.dispose();
    key.position.set(-3,4,5);fill.position.set(4,1.5,3);rim.position.set(1,3,-3);
    scene.add(key,fill,rim);
    makeShadow();
    new ResizeObserver(resize).observe(stage);
    resize();
    const gltf = await new GLTFLoader().loadAsync('/assets/winternuesse.glb');
    product = gltf.scene;
    product.scale.setScalar(18.4);
    product.position.y = -.885;
    cap = product.getObjectByName('Cap');
    capBase = cap?.position.y ?? 0;
    product.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      for (const mat of materials) {
        if (!(mat instanceof THREE.MeshStandardMaterial)) continue;
        if (mat.map) mat.map.anisotropy = Math.min(8,renderer.capabilities.getMaxAnisotropy());
        if (mat.name.startsWith('Glass') && mat instanceof THREE.MeshPhysicalMaterial) {
          mat.roughness = .16;
          mat.ior = 1.47;
          mat.thickness = .035;
          mat.attenuationColor.set('#e5ebcd');
          mat.attenuationDistance = 1.4;
        }
        if (mat.name.startsWith('Label')) { mat.roughness = .85; mat.envMapIntensity = .85; }
        if (mat.name.startsWith('Cap |')) { mat.roughness = .58; mat.metalness = .06; }
      }
    });
    scene.add(product);
    await renderer.compileAsync(scene,camera);
    loaded = true;
    $('#loader').classList.add('done');
    $('#loader').setAttribute('aria-hidden','true');
    stage.dataset.ready = 'true';
    announce('3D product loaded. Drag to rotate or choose a view below.');
    wake();
    fetch('/assets/model-info.json').then(r => r.json()).then(info => { $('#mesh-count').textContent = `${info.meshes} meshes · ${(info.triangles/1000).toFixed(1)}k triangles`; }).catch(() => {});
  } catch (error) {
    console.error('Product studio failed to load',error);
    $('#loader').classList.add('done');
    $('#render-error').hidden = false;
    stage.dataset.ready = 'error';
    announce('3D could not load. Showing the reference image.');
  }
}

function resize() {
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  const aspect = width/height;
  const vertical = width < 420 ? 1.37 : 1.22;
  camera.left = -vertical*aspect;
  camera.right = vertical*aspect;
  camera.top = vertical;
  camera.bottom = -vertical;
  camera.updateProjectionMatrix();
  renderer.setSize(width,height,false);
  wake();
}

function frame(time: number) {
  raf = 0;
  inFrame = true;
  const dt = Math.min((time-previousTime)/1000,.05);
  previousTime = time;
  const snap = reducedMotion.matches;
  lift.update(dt,snap);yaw.update(dt,snap);targetY.update(dt,snap);exposure.update(dt,snap);
  if (product) {
    if (autoRotate && !userInteracting) {
      yaw.target += dt*.19;
      yaw.value = yaw.target;
    }
    product.rotation.y = yaw.value;
  }
  if (cap) {
    cap.position.y = capBase+lift.value;
    cap.rotation.y = -lift.value*25;
  }
  if (!userInteracting) {
    zoom.update(dt,snap);
    camera.zoom = zoom.value;
    controls.target.y = targetY.value;
    camera.updateProjectionMatrix();
  }
  const changed = controls.update();
  renderer.toneMappingExposure = exposure.value;
  renderer.render(scene,camera);
  const animating = !lift.settled || !yaw.settled || !zoom.settled || !targetY.settled || !exposure.settled;
  if (needsRender || animating || autoRotate || changed) idleFrames = 0;
  else idleFrames++;
  needsRender = false;
  inFrame = false;
  if (idleFrames < 3 && !document.hidden) raf = requestAnimationFrame(frame);
  else {
    stage.dataset.rendering = 'idle';
    stage.dataset.state = JSON.stringify({revision:THREE.REVISION,loaded,view:currentView,lighting:currentLight,autoRotate,capLift:lift.value,zoom:camera.zoom,triangles:renderer.info.render.triangles});
  }
}

document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(b => b.addEventListener('click',() => setView(b.dataset.view!)));
document.querySelectorAll<HTMLButtonElement>('[data-light]').forEach(b => b.addEventListener('click',() => { if (loaded) setLighting(b.dataset.light!); }));
$('#motion').addEventListener('click',() => { if (loaded) setMotion(!autoRotate); });
$('#reset').addEventListener('click',() => setView('object'));
$('#explore').addEventListener('click',() => {
  if (loaded) setView('layers');
  stage.scrollIntoView({behavior:reducedMotion.matches?'instant':'smooth',block:'center'});
  canvas.focus({preventScroll:true});
});
$('#fullscreen').addEventListener('click',async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await stage.requestFullscreen();
  } catch { announce('Fullscreen is unavailable in this browser.'); }
});
document.addEventListener('fullscreenchange',() => {
  const full = !!document.fullscreenElement;
  $('#fullscreen').setAttribute('aria-label',full?'Exit fullscreen':'Enter fullscreen');
  $('#fullscreen').innerHTML = `<i data-lucide="${full?'minimize':'maximize'}"></i>`;
  createIcons({icons});
  resize();
});
$('#retry').addEventListener('click',() => location.reload());
canvas.addEventListener('keydown',event => {
  if (!loaded) return;
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();setMotion(false);yaw.target += event.key==='ArrowLeft'?-.25:.25;wake();
  } else if (event.key === '+' || event.key === '=') { event.preventDefault();zoom.target=Math.min(2.7,zoom.target+.2);wake(); }
  else if (event.key === '-') { event.preventDefault();zoom.target=Math.max(.65,zoom.target-.2);wake(); }
  else if (event.key === 'Home') { event.preventDefault();setView('object'); }
});
for (const name of ['reference','about']) {
  const dialog = $<HTMLDialogElement>(`#${name}-dialog`);
  $(`#${name}-open`).addEventListener('click',() => dialog.showModal());
  dialog.querySelector('.close-dialog')!.addEventListener('click',() => dialog.close());
  dialog.addEventListener('click',event => { if (event.target===dialog) { const rect=dialog.getBoundingClientRect(); if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) dialog.close(); } });
}
document.addEventListener('visibilitychange',() => { if(document.hidden) { cancelAnimationFrame(raf);raf=0; } else wake(); });
reducedMotion.addEventListener('change',() => { controls.enableDamping=!reducedMotion.matches;if(reducedMotion.matches)setMotion(false);wake(); });
canvas.addEventListener('webglcontextlost',event => { event.preventDefault();cancelAnimationFrame(raf);raf=0;$('#render-error').hidden=false;announce('Graphics context lost. Reload the studio to continue.'); });

// Read-only instrumentation for reproducible browser QA.
Object.defineProperty(window,'productStudio',{get:() => ({
  revision:THREE.REVISION,loaded,view:currentView,lighting:currentLight,autoRotate,
  capLift:lift.value,zoom:camera?.zoom,meshes:renderer?.info.render.calls,
  triangles:renderer?.info.render.triangles,rendering:!!raf,
})});
void init();

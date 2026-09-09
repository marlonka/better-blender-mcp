# Object Studio — Winternüsse

An editable Blender reconstruction of the supplied enerBiO product photograph,
presented in a responsive Three.js **r186** material studio.

```sh
npm ci
npm run dev -- --port 5173
```

Open http://127.0.0.1:5173. `npm run build` produces a static site in `dist`;
`npm run preview -- --port 4173` serves that production build locally.

## Explore

- Drag/orbit, wheel/pinch zoom; keyboard arrows rotate, `+`/`-` zoom, `Home` resets.
- Front, close-up and spring-driven lid lift; daylight, warm and midnight lighting.
- Explicit auto-rotation, fullscreen, source photograph and model downloads.
- Rendering stops when settled and when hidden. Reduced-motion preferences disable
  spring transitions; automatic rotation starts off.
- WebGL/load errors retain the reference and offer a reload.

## Rebuild the assets

From the repository root, with Blender open and the enhanced addon connected:

```sh
uv sync --extra dev
uv run --extra dev python examples/product-studio/blender/prepare_textures.py
uv run --extra dev python tools/render_product.py
```

The second command derives texture maps from the supplied photograph. The third
uses the actual compact MCP stdio server to build, bake, render, export and audit
an isolated Blender worker, usually returning completion in one tool call. It writes:

- `public/assets/winternuesse.blend`: packed, editable scene, camera and Cycles lights.
- `public/assets/winternuesse.glb`: the geometry, UVs and PBR materials used by the browser.
- `public/assets/blender-render.png`: calibrated front render with transparency.
- `model-info.json`, `build-timings.json`, `provenance.json`: dimensions, costs and source limits.

The deterministic recipe uses explicit lathed mesh topology: hollow glass wall,
rolled base and shoulder, paper sleeve, nut cream, enamel cap, top, gasket, liner
and glass ridges. Eight meshes, 56,320 triangles, a 4.47 MB GLB. Absolute dimensions
are estimated (81.64 mm diameter, 96.2 mm height).

The 4096 × 1024 label is an inverse cylindrical projection of the photograph;
the visible artwork is preserved instead of retyped. The unseen half continues
the red/orange background without inventing claims or a barcode. The cap map
contains only the shallow ellipse visible in the photo. Hidden construction is
inferred. This cannot be a pixel-perfect account of a real jar's unseen surfaces.

Blender retains the editable procedural cream shader and bakes its color and
tangent normal into textures for glTF. The browser uses those baked maps and
tunes glass transmission for real-time rendering.
Three.js room reflections and lights are designed for interactive viewing; they
do not reproduce Cycles ray tracing exactly. The photograph already contains
lighting, so the label is not a measured diffuse-albedo texture.

## Dependencies and verification

`three` is pinned to **0.186.0**; TypeScript's separately published `@types/three`
was available at **0.185.4**. `npm run build` checks the used API surface and builds
the viewer. The initial JavaScript bundle is ~168 kB gzip; the PBR engine accounts
for most of it. Vite's default 500 kB uncompressed chunk warning is expected.

Browser QA covers the loaded r186 geometry, three views, lighting, lid motion,
rotation, reference dialog, mobile overflow and idle rendering. See
[`../../docs/verification.md`](../../docs/verification.md).

The photograph and packaging marks were supplied as reference. enerBiO and
ROSSMANN belong to their respective owners; this independent reconstruction is
not affiliated with either. The repository's MIT software licence does not grant
trademark or product-photography rights.

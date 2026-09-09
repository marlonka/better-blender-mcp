# Verification

Recorded on 9 September 2026 using Windows, Python 3.11.15 and Blender 5.2.1 LTS.
The upstream baseline is commit
[`5f8ddaf6e987c4aa0c3467fcc548838b28f64477`](https://github.com/ahujasid/blender-mcp/commit/5f8ddaf6e987c4aa0c3467fcc548838b28f64477).
It was the upstream main revision when checked. The fork retains its protocol 5 interface.

## Local checks

- **156 tests passed**, including a real Blender worker integration test.
- Real MCP stdio initialization, tool discovery, product construction and completion
  feedback passed through `tools/render_product.py`.
- The enhanced addon was installed and reloaded in the running Blender GUI. The
  final product opens as an editable scene with eight product meshes and a studio.
- A real Windows test terminated the worker manager with `os._exit` and verified
  cleanup of its owned worker and grandchild process.
- The `blender_mcp-1.9.1.post1` wheel built successfully; its contents include the
  bundled addon, worker bootstrap, process guard, recipes and quality checker.
- The Three.js **0.186.0** example passed TypeScript and Vite production builds.
  Desktop and mobile interaction checks covered orbit, view presets, lid motion,
  lighting, dialogs and reset. The build reports a 656 kB JavaScript chunk
  (168 kB gzip); further viewer optimization is outside this MCP-focused iteration.

Tests cover queue expiry, cancellation, idempotency, output bounds, immutable
status snapshots, disconnected sockets without replay, streaming Unicode,
absolute deadlines, worker source snapshots, bounded logs, process cleanup,
render/bake scheduling guards, lathe topology and UVs, and reference comparison.
The real Blender fixture verifies detection of an intentionally defective mesh
alongside a valid closed solid. These checks do not prove arbitrary scripts safe
or native Blender operations preemptible.

The included CI workflow runs Python tests on Windows and Ubuntu and builds the
viewer on Ubuntu. Hosted CI does not install Blender; that integration test skips
unless `BLENDER_BINARY` is supplied. Platform-specific tests also skip where
inapplicable. Local results above do not claim hosted CI has already passed.

## Bridge measurements

Raw observations, samples and measurement boundaries are in
[`product-study.json`](../benchmarks/product-study.json).

| Measurement | Baseline | Enhanced | Meaning |
| --- | ---: | ---: | --- |
| Tool definitions | 28 tools / 30,062 bytes | 5 tools / 3,179 bytes | 89.4% fewer UTF-8 bytes in `tools/list` |
| Unchanged scene reply | 2,389-byte full digest | 145-byte delta | 93.9% smaller reply for the same digest fields |
| 910,043-byte JSON framing | 741.9 ms median | 33.7 ms median | Five in-memory runs; about 22 times faster framing |
| Five separate small edits | 5 calls / 993 bytes | 2 calls / 1,324 bytes | Fewer calls, but more bytes for stage evidence |

The compact server additionally advertises 1,186 bytes of instructions and 172
bytes of resource definitions. The optional recipe reference is 2,069 bytes and
loads on request. Its reduced tool set omits upstream asset-service integrations;
the legacy entry point retains them. Schema bytes are **not billed LLM tokens**.
No controlled model sampling, token billing or end-to-end generation-speed trial
was performed. The upstream API can also combine edits into one blocking Python
call; the staged example is a workflow comparison, not a minimum-call claim.

During an **18.1-second** separate-process product rebuild, bake, export, render
and audit, the running GUI addon answered **42 probes**, with **26.2 ms median**
and **37.9 ms maximum** latency. This demonstrates concurrent inspection during
this workload. It does not measure GUI frame rate or a reduction in freeze
frequency across other Blender workloads. A single live Python/native call can
still block the GUI; use workers for heavy work.

## Product quality iteration

The supplied jar photograph is the reference. The baseline and final result are
successive iterations of this reconstruction, **not** an upstream-versus-enhanced
LLM quality benchmark. Both audit reports use the enhanced checker.

| Diagnostic | Initial reconstruction | Final reconstruction |
| --- | ---: | ---: |
| Automated findings | 13 | 0 |
| Product meshes | 10 | 8 |
| Vertices | 31,868 | 28,166 |
| Triangles | 58,368 | 56,320 |
| Foreground RGB mean absolute error | 0.07686 | 0.07230 |

The repairs close unintended mesh boundaries, remove collapsed cap UVs, join the
cap into a closed solid and bake the procedural nut material into portable colour
and normal textures. The actual product imports the shared `better_blender`
helpers, so these geometry improvements are reusable beyond the example.

The final silhouette IoU is **0.98415** without automatic alignment. Relative to
the reference, its bounding box differs by **[+1, +2, 0, -3] pixels** at 870 × 903.
RGB error uses normalized image-buffer channels (sRGB for these PNGs), not linear
radiance or a perceptual-quality score. White clipping remains visible in the
diagnostics. A trial that lowered RGB error but introduced an objectionable
reflection was rejected after inspecting the rendered image.

Zero findings means the bounded base-mesh, UV and common export checks passed.
It does not prove pixel-perfect materials, hidden geometry, self-intersection
absence or aesthetic quality. Back artwork, hidden details and physical size are
inferred from one photograph. The GLB is **4,473,960 bytes**; baking improves material
portability but increases asset size from the initial approximately 3.02 MB.

- [Initial audit](../benchmarks/quality-before.json) and
  [archived initial render](../benchmarks/renders/before.png).
- [Final audit](../benchmarks/quality-after.json) and
  [final render](../examples/product-studio/public/assets/blender-render.png).
- [Initial recipe](../benchmarks/fixtures/product-before.py) preserves the initial
  modeling code with paths redirected to `.local/baseline-product`. The original
  initial `.blend` was not archived; regenerate it with this recipe.
- [Final editable Blender file](../examples/product-studio/public/assets/winternuesse.blend),
  [GLB](../examples/product-studio/public/assets/winternuesse.glb) and
  [recipe](../examples/product-studio/blender/build_product.py).

## Reproduce

Install the fork, enable the enhanced addon and open the included product scene
in Blender. Run from the repository root:

```sh
uv sync --extra dev
uv run python tools/render_product.py
uv run python tools/benchmark.py
uv run python -m pytest -q
```

Set `BLENDER_BINARY` to the Blender executable before pytest to include the real
Blender integration test. Regenerate the initial model independently with:

```sh
uv run python tools/render_product.py benchmarks/fixtures/product-before.py
```

The benchmark loads upstream schema and parser code from the pinned Git commit,
temporarily creates/removes its own small collection in the GUI, and rebuilds the
final product assets in a worker. Bake caches, hardware and background activity
affect timing. JSON timestamps and absolute paths in fresh reports may differ;
the committed reports normalize artifact paths to the repository.

Software is MIT-licensed. The supplied photograph, packaging artwork and marks
retain their owners' rights; they are reference evidence for this reconstruction.

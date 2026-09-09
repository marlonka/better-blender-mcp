# How Better Blender MCP works

The compact entry point exposes five tools and a short quality workflow. The
upstream entry point remains available for Poly Haven, Sketchfab, Poly Pizza and
generation integrations. Both use the enhanced socket transport and addon.

## Choose the execution path

| Work | Path | Why |
| --- | --- | --- |
| Inspect transforms, dimensions, counts and assignments | `blender_scene` | Named selection, explicit pagination, revision deltas |
| Short edits in the open scene | `blender_batch`, then `blender_job` | Shared namespace, compile-all validation, progress and yielding |
| Render, bake, export, expensive construction | `blender_worker` | Separate background Blender process; leaves the interactive scene available |
| Verify visible output | `blender_snapshot` | Explicit viewport evidence; no automatic image on every call |

Supply a caller-chosen `job_id` when submitting a live batch. The same ID and
identical stages return the existing job; changed content is rejected. On a
timeout inspect that ID before resubmitting. Idempotency lasts for the last 128
jobs in this Blender session, not across addon restarts or cache eviction.

Every stage is compiled before any stage executes. One stage runs per timer tick.
The staged path also rejects known render, object-bake and simulation-bake
operators, including straightforward aliases across stages. Use a background
worker for these. This scheduling guard cannot recognize all dynamic Python;
the legacy arbitrary-code endpoint retains upstream behavior.
A failed stage stops the job; earlier mutations persist. Cancellation occurs
between stages. A Python or native `bpy` call already running cannot be preempted
by this queue. Stages over 100 ms report a warning; rendering belongs in a worker.
Stopping the addon cancels pending stages, so a restart cannot resume them.

## Bounds and transport

- Request: 2 MB; response: 16 MB; command queue: 64; active live jobs: 8.
- UI queue servicing budget: 8 ms **between commands**, measured with the
  high-resolution performance counter. Python 3.11's Windows monotonic clock
  can tick at approximately 16 ms. A command may still exceed the budget.
- Stage stdout: first 2,048 characters, with an explicit discarded-character count.
- Socket serialization and sends run on client threads, not Blender's UI thread.
  Job status responses copy their result lists before crossing that boundary.
- Responses are framed in one byte scan. UTF-8 is decoded after the entire object
  arrives, including when a multibyte character crosses a socket chunk boundary.
- Absolute request deadlines, bounded receive buffers, serialized requests, actual
  socket closure on failure. Mutations are never automatically replayed.
- The addon retains the upstream protocol 5 commands and advertises new capabilities
  and `enhanced_version: 0.1.0`. Compact mode requires the enhanced addon.

`blender_scene` defaults to 40 objects and permits at most 200 per page. Revisions
cover reported transforms, dimensions, mesh counts and material **assignments**.
They are not hashes of every vertex coordinate, shader node, texture pixel,
visibility setting or animation channel. Inspect those explicitly in a short
stage and verify pixels after a material or topology change. A query or scene
change, or an evicted revision, returns a full page instead of an invalid delta.
Sixteen page revisions are cached. Removal from a page may reflect pagination,
not deletion from the entire scene.

## Workers

Workers use `--background --factory-startup --disable-autoexec --threads 6`, an
optional `.blend`, and a validated snapshot of a local Python file. They inherit no unsaved GUI
scene state. Scripts must explicitly save/export their outputs. File paths with
spaces are passed as arguments; no shell is used. Windows workers have no console
window. Two workers may run at once; 64 records remain in memory.

Each worker has a 1–3,600 second deadline. The manager kills its own process tree on
timeout or cancellation and never targets an arbitrary stored PID. Logs retain
the last 8,192 characters; successful/running status omits logs by default. Failed
jobs include the last 1,500 characters even when logs were not requested. Terminal status
waits for final output. Records are written atomically under
`~/.better-blender-mcp/jobs` (override with `BETTER_BLENDER_JOBS`).

Normal MCP shutdown cancels owned workers. On Windows, a non-inheritable Job Object
uses `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; OS handle cleanup terminates the attached
process tree even when the manager crashes. This is verified with an abruptly
exiting manager and a real grandchild process. Assignment happens immediately
after process creation; descendants created before assignment are not guaranteed
to be contained. This is process cleanup, not a security boundary. See Microsoft's
[Job Objects documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

On POSIX, workers start a new process group; cancellation, timeout and normal
shutdown kill that group. Abrupt manager death does not guarantee cleanup there.
Persisted running records return `unknown_after_restart`, including on Windows:
the new server never assumes that an old PID is still owned. Do not replay an
unknown job blindly; inspect its files and state.

A supplied 32-hex worker ID is durable while its local record exists. The
fingerprint covers source, paths, initial blend size/mtime and execution options.
It does not hash arbitrary imported modules or every file read by the recipe.
Identical inputs return the existing job; changed inputs are rejected. The
validated source snapshot preserves the original `__file__` and working directory.
Imported modules and other inputs remain live filesystem dependencies.

`wait_seconds` (0–30) waits on a completion event in a host thread, keeping the MCP
event loop and GUI connection available. A short build/render/audit can complete
in one tool call. Longer work returns its ID for a later bounded wait.

Set `BLENDER_BINARY` to run workers without asking the connected addon for its
executable. `BLENDER_HOST` and `BLENDER_PORT` select the socket endpoint. Keep the
unauthenticated addon bound to loopback. These tools intentionally execute local
Python with the user's permissions; worker isolation protects the GUI, not the OS.
Upstream's optional `BLENDER_MCP_SAFE_MODE=1` AST validation is applied to batches
and worker source; it remains a guard, not a security sandbox.

Compact mode does not create telemetry events or capture before/after snapshots
automatically. The legacy mode retains upstream telemetry behavior and controls.

## Model checks and reusable recipes

Workers automatically run a bounded base-mesh audit after a successful script,
or audit a saved `.blend` without needing a script. Disable it with `audit: false`
when inappropriate. Completion returns artifact paths, counts, at most eight
findings and a path to the full JSON report. `BETTER_BLENDER_OUTPUTS` can identify
up to 20 explicitly produced files; the saved blend and render path are detected.
Each file reports whether its modification time indicates it was updated this run.

Checks include boundary/non-manifold edges, winding, near-zero-area faces,
collapsed image-driven UVs, missing materials/images, negative world transforms,
common unsupported procedural glTF inputs and conservative camera bounds. They
inspect at most 200 meshes and skip topology work above 500,000 faces per mesh.
Modifiers are not evaluated. Self-intersections, UV overlap, all shader semantics,
collection visibility and aesthetic quality are not proven by this audit.

Set `scene['better_mcp_subject']` to an existing collection name to scope checks.
Mark intentional sheets with `obj['better_mcp_open_surface'] = True`; do not use
that flag to conceal unintended holes. Complete findings remain in the report.

`reference_path` compares an existing render with a single product on white or
transparent background. Both images must have identical dimensions and no more
than 16 million pixels. The algorithm fills foreground row interiors, computes
silhouette IoU, bounding-box offsets, foreground RGB error and white clipping.
It does not automatically resize, align or rerender. Narrow diagnostics can
improve while reflections or other visible details get worse; inspect the pixels.

The `blender://recipes` resource is loaded on demand. Workers provide
`better_blender.lathe`, `pbr_material` and `point_at`. Lathes share vertices at
geometric seams, collapse zero-radius poles, and retain UV discontinuities at
face corners. Profile validation rejects invalid bounds/coordinates before any
Blender mesh is created. The product recipe uses this same reusable library.

## Quality loop

1. Establish source evidence, silhouette, component proportions and camera.
2. Build deterministic named geometry and UVs. Keep files editable.
3. Preserve original artwork where available; mark hidden details as inferred.
4. Render in a worker. Check actual pixels for framing, colour clipping, label
   legibility, material response and missing geometry.
5. Change the specific cause of the discrepancy, then re-render.
6. Export and inspect the actual browser asset. Test motion and failure handling.

Fewer calls alone do not produce better art. The reference projection, topology,
material choices, rendering and visual iteration in the product example are the
quality work; the bridge makes that work cheaper to inspect and easier to recover.

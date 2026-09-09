"""Five focused tools for measured, iterative Blender work. No telemetry."""
from __future__ import annotations

import asyncio
import atexit
from contextlib import asynccontextmanager
import os
from pathlib import Path
import tempfile
import uuid

from mcp.server.fastmcp import FastMCP, Image
from pydantic import BaseModel, Field

from .connection import BlenderConnection
from .safe_mode import safe_mode_enabled, validate_code
from .workers import WorkerManager

connection = BlenderConnection(os.getenv('BLENDER_HOST', '127.0.0.1'), int(os.getenv('BLENDER_PORT', '9876')), timeout=30)
workers = None

def get_workers():
    global workers
    if workers is None:
        directory = Path(os.getenv('BETTER_BLENDER_JOBS', str(Path.home()/'.better-blender-mcp'/'jobs')))
        workers = WorkerManager(directory)
        atexit.register(workers.close)
    return workers

@asynccontextmanager
async def lifespan(_):
    try:
        yield {}
    finally:
        connection.disconnect()
        if workers:
            workers.close()

mcp = FastMCP('Better Blender MCP', lifespan=lifespan, instructions=(
    'For reference modeling, first inspect the reference and current scene. '
    'Match silhouette, component proportions, camera and readable artwork before decorative detail. '
    'Preserve source artwork with appropriate UV projection; identify inferred hidden surfaces. '
    'Prefer deterministic, editable meshes with explicit UVs and named physical materials. '
    'Save reusable Python recipes locally; render, bake and export in blender_worker. '
    'For live edits, submit short named stages with a caller-chosen job_id; on timeout query that ID before retrying. '
    'Worker completion includes mesh/UV/material checks, artifact paths and optional reference comparison. '
    'Fix its actionable findings, then inspect a compact scene delta and actual pixels after meaningful changes. '
    'Use wait_seconds up to 30 to get a completed worker result in one call; avoid rapid polling. '
    'Read blender://recipes for reusable welded lathe/UV helpers instead of rewriting mesh boilerplate. '
    'Compare geometry, texture legibility, reflections and framing before declaring completion. '
    'A batch is not a transaction; completed stages persist after failure. '
    'Do not infer billed-token savings or general modeling quality from payload size alone.'
))

async def command(name, params=None):
    return await asyncio.to_thread(connection.send_command, name, params)

class Stage(BaseModel):
    name: str = Field(max_length=100)
    code: str = Field(max_length=500_000)


@mcp.resource('blender://recipes')
def recipe_reference() -> str:
    """Deterministic worker helpers and quality-loop conventions, loaded on demand."""
    return '''Worker recipes can import from better_blender (provided by the bootstrap):
from better_blender import lathe, pbr_material, point_at
mat, shader = pbr_material('Ceramic', color=(.7,.65,.55), roughness=.3)
jar = lathe('Jar', [(0,0),(.04,0),(.04,.08),(.037,.08),(.037,.003),(0,.003),(0,0)],
            materials=[mat], segments=128)

lathe(name, profile, materials=None, collection=None, segments=128,
      radial_scale=1, uv_radius=None, surfaces=None, uv_mode='cylinder', wall_uv_height=1)
Profile: (radius,z) in scene units; front -Y, up +Z. Use radius 0 for single poles.
Repeat first point to close a hollow section. Geometry seams are welded; UV seams use face corners.
materials: material objects or existing names. collection: existing name/object, or active.
surfaces: {profile_segment_index: (material_index, projection)}.
Projections: cylinder, planar, atlas_top, atlas_bottom. For baking, assign caps to atlas disks
and wall_uv_height=.54; inspect UVs for unusual profiles. Defaults map horizontal faces planar.
128 segments usually suffice; 256 for tight product closeups. Max 512 segments/512 profile points.
point_at(camera_or_light, world_point) aims local -Z with Y up.
pbr_material returns (material, Principled node); color is linear RGB.

Set scene['better_mcp_subject']='Product' to audit one collection.
Set obj['better_mcp_open_surface']=True only for intentional sheets.
Set BETTER_BLENDER_OUTPUTS={'glb':'/absolute/model.glb', 'render':'/absolute/render.png'}
to return artifact paths in job completion. Saved blend and scene render path are detected.
Worker audits base meshes/UVs and common procedural glTF risks; read full result_path for all findings.
Reference comparison assumes one product on white/transparent background with identical pixel dimensions.
Silhouette IoU and color error are narrow diagnostics, not an aesthetic or pixel-perfect score.
No implicit save, export, render, overwrite, or GUI-scene import is performed by these helpers.
Optional upstream safe mode restricts imports; use its allowed bpy operations in that mode.'''

@mcp.tool()
async def blender_scene(names: list[str] | None = None, since: str | None = None, offset: int = 0, limit: int = 40) -> dict:
    """Inspect transforms, dimensions, mesh counts and material assignments. Reuse revision as since for compact deltas. Pagination is explicit; not a vertex/shader-content hash."""
    return await command('scene_digest', dict(names=names, since=since, offset=offset, limit=limit))

@mcp.tool()
async def blender_batch(steps: list[Stage], job_id: str | None = None) -> dict:
    """Queue named Python stages, sharing a namespace. Validates every stage first. Reuse job_id to avoid replay. Keep stages <100 ms; render/bake in blender_worker. No rollback; inspect failures."""
    for step in steps:
        compile(step.code, '<blender-job>', 'exec')
        if safe_mode_enabled():
            validate_code(step.code)
    return await command('submit_job', dict(steps=[s.model_dump() for s in steps], job_id=job_id))

@mcp.tool()
async def blender_job(job_id: str, cancel: bool = False) -> dict:
    """Get bounded progress/output or cancel between stages. Cannot preempt a running bpy operation. Completed jobs retain 128 IDs per Blender session."""
    return await command('cancel_job' if cancel else 'get_job_status', dict(job_id=job_id))

@mcp.tool()
async def blender_worker(script_path: str | None = None, blend_path: str | None = None, job_id: str | None = None, cancel: bool = False, timeout_seconds: int = 120, log_chars: int = 0, wait_seconds: int = 0, audit: bool = True, reference_path: str | None = None) -> dict:
    """Run a local recipe or audit a saved blend in background Blender. Returns bounded model checks/artifacts; optional white-background reference comparison. wait_seconds 0-30 avoids polls. Caller-chosen 32-hex job_id prevents replay; with no input files, inspect/cancel that ID. Snapshot source; hard deadline; no implicit save/render. Logs opt-in, errors automatic."""
    manager = get_workers()
    if not 0 <= wait_seconds <= 30 or not 0 <= log_chars <= 8192:
        raise ValueError('wait_seconds must be 0-30; log_chars must be 0-8192')
    if cancel:
        if not job_id or script_path or blend_path:
            raise ValueError('Cancel requires job_id and no input files')
        return manager.cancel(job_id)
    if job_id and not script_path and not blend_path:
        return await asyncio.to_thread(manager.wait, job_id, wait_seconds, log_chars)
    if not script_path and not blend_path:
        raise ValueError('Provide script_path or blend_path to start, or job_id to inspect')
    if script_path and safe_mode_enabled():
        validate_code(Path(script_path).read_text(encoding='utf-8'))
    binary = os.getenv('BLENDER_BINARY')
    if not binary:
        binary = (await command('get_addon_info'))['blender_binary']
    result = await asyncio.to_thread(manager.start, binary, script_path, blend_path, timeout_seconds,
        job_id=job_id, audit=audit, reference_path=reference_path,
        validator=validate_code if safe_mode_enabled() else None)
    return await asyncio.to_thread(manager.wait, result['id'], wait_seconds, log_chars)

@mcp.tool()
async def blender_snapshot(max_size: int = 1000) -> Image:
    """Inspect actual viewport pixels after a meaningful change. No automatic screenshots or scene dumps."""
    if not 128 <= max_size <= 2048:
        raise ValueError('max_size must be 128-2048')
    path = Path(tempfile.gettempdir()) / f'better-blender-{uuid.uuid4().hex}.png'
    try:
        result = await command('get_viewport_screenshot', dict(max_size=max_size, filepath=str(path), format='png'))
        if 'error' in result:
            raise RuntimeError(result['error'])
        return Image(data=path.read_bytes(), format='png')
    finally:
        path.unlink(missing_ok=True)

def main():
    from .addon_manager import run_cli
    import sys
    code = run_cli(sys.argv[1:])
    if code >= 0:
        raise SystemExit(code)
    mcp.run()

if __name__ == '__main__':
    main()

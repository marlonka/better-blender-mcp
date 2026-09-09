"""Reproducible measurements; requires a connected enhanced addon + product scene.

No LLM is sampled, and no billed-token or general modeling-quality score is
inferred. Upstream schemas/parser come from the exact pinned git revision.
Both live inspection routes use the same enhanced addon and current scene.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types

os.environ['DISABLE_TELEMETRY'] = 'true'
from blender_mcp.connection import BlenderConnection
from blender_mcp.compact_server import mcp, recipe_reference
from blender_mcp.workers import WorkerManager

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = '5f8ddaf6e987c4aa0c3467fcc548838b28f64477'


def canonical(value):
    return json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()


def pinned_module():
    source = subprocess.check_output(['git','show',f'{UPSTREAM}:src/blender_mcp/server.py'],cwd=ROOT).decode()
    module = types.ModuleType('benchmark_upstream')
    module.__package__ = 'blender_mcp'
    module.__file__ = str(ROOT/'src'/'blender_mcp'/'server.py')
    sys.modules[module.__name__] = module
    exec(compile(source,'<pinned-upstream>','exec'),module.__dict__)
    return module


class Chunks:
    def __init__(self,payload,size):
        self.chunks = iter(payload[i:i+size] for i in range(0,len(payload),size))
    def recv(self,_):
        return next(self.chunks,b'')
    def settimeout(self,_):
        pass


def parser_benchmark(upstream):
    payload = canonical({'status':'success','result':{'objects':[
        {'name':f'Object-{i:05}','location':[1.234,2.345,3.456],'vertices':1024,'material':'enamel'}
        for i in range(10000)]}})
    runs = {}
    for name,cls in [('upstream',upstream.BlenderConnection),('enhanced',BlenderConnection)]:
        times = []
        for _ in range(5):
            conn = cls('unused',0)
            start = time.perf_counter()
            received = conn.receive_full_response(Chunks(payload,4096))
            # Both paths include final JSON validation (new framing defers it).
            assert json.loads(received)['status'] == 'success'
            times.append(round((time.perf_counter()-start)*1000,3))
        runs[name] = {'median_ms':statistics.median(times),'samples_ms':times}
    return {'payload_bytes':len(payload),'chunk_bytes':4096,'runs':runs,
        'scope':'In-memory framing microbenchmark; excludes network, Blender and LLM time.'}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='benchmarks/product-study.json')
    args = parser.parse_args()
    upstream = pinned_module()
    logging.disable(logging.CRITICAL)
    report = {'recorded_at':datetime.now(timezone.utc).isoformat(),'upstream_commit':UPSTREAM,
        'platform':sys.platform,'python':sys.version.split()[0],
        'measurement':'UTF-8 bytes and wall-clock latency; not billed tokens or quality scores'}
    schemas = {}
    for name,server in [('upstream',upstream.mcp),('enhanced',mcp)]:
        tools = await server.list_tools()
        data = [tool.model_dump(exclude_none=True) for tool in tools]
        schemas[name] = {'tools':len(tools),'bytes':len(canonical(data))}
        schemas[name]['instructions_bytes'] = len((server.instructions or '').encode())
        resources = await server.list_resources()
        schemas[name]['resource_definitions_bytes'] = len(canonical([r.model_dump(mode='json',exclude_none=True) for r in resources]))
    schemas['enhanced']['optional_recipe_reference_bytes'] = len(recipe_reference().encode())
    schemas['scope'] = 'Full tools/list definitions. Compact mode omits upstream asset-service tools; legacy entry point remains available.'
    report['tool_schemas'] = schemas
    report['parser'] = parser_benchmark(upstream)

    conn = BlenderConnection('127.0.0.1',9876,timeout=10)
    try:
        info = conn.send_command('get_addon_info')
        report['blender'] = info['blender_version']
        report['enhanced_version'] = info['enhanced_version']
        digest = conn.send_command('scene_digest',{'limit':200})
        if 'Jar_Glass' not in digest['objects']:
            raise RuntimeError('Open the product .blend in Blender before benchmarking')
        initial = conn.metrics.copy()
        full = conn.send_command('get_world_state_snapshot')
        upstream_full = conn.metrics.copy()
        unchanged = conn.send_command('scene_digest',{'limit':200,'since':digest['revision']})
        assert unchanged['delta'] and not unchanged['objects']
        report['inspection'] = {'objects':digest['total'],'full_digest':initial,
            'legacy_full_snapshot':upstream_full,'unchanged_delta':conn.metrics.copy(),
            'scope':'Same enhanced addon and unchanged scene. Snapshot and digest have different fields; delta reports changes only to digest fields.'}

        # Equal scoped edits: identical code, individual calls vs staged job.
        # Uses a private temporary collection; existing scene objects untouched.
        steps = [
            {'name':'create','code':"c=bpy.data.collections.new('__BetterBenchmark'); bpy.context.scene.collection.children.link(c)"},
            {'name':'object','code':"c=bpy.data.collections['__BetterBenchmark']; o=bpy.data.objects.new('__BetterBenchmark',None); c.objects.link(o)"},
            {'name':'transform','code':"bpy.data.objects['__BetterBenchmark'].location.x=0.01"},
            {'name':'assert','code':"assert abs(bpy.data.objects['__BetterBenchmark'].location.x-0.01)<1e-6"},
            {'name':'cleanup','code':"bpy.data.objects.remove(bpy.data.objects['__BetterBenchmark'],do_unlink=True); bpy.data.collections.remove(bpy.data.collections['__BetterBenchmark'])"},
        ]
        legacy_calls = []
        for step in steps:
            result = conn.send_command('execute_code',{'code':step['code']})
            if result.get('error'):
                raise RuntimeError(result['error'])
            legacy_calls.append(conn.metrics.copy())
        job = conn.send_command('submit_job',{'steps':steps})
        enhanced_calls = [conn.metrics.copy()]
        # Five short stages finish well within this coarse wait on the test scene.
        await asyncio.sleep(.6)
        status = conn.send_command('get_job_status',{'job_id':job['id']})
        enhanced_calls.append(conn.metrics.copy())
        assert status['state'] == 'succeeded', status
        report['staged_edits'] = {'stages':5,'legacy_calls':legacy_calls,'enhanced_calls':enhanced_calls,
            'scope':'Five separate execute_code calls versus submit + one status call. Upstream can also combine Python in one blocking call; this is a workflow comparison, not a minimum-call lower bound.'}

        workers = WorkerManager(ROOT/'.local'/'benchmark-workers')
        try:
            job = workers.start(info['blender_binary'],ROOT/'examples/product-studio/blender/build_product.py',timeout_seconds=120,
                reference_path=ROOT/'examples/product-studio/public/assets/reference.png')
            probes = []
            deadline = time.monotonic()+125
            while workers.status(job['id'],0)['returncode'] is None:
                if time.monotonic() > deadline:
                    raise TimeoutError('Benchmark worker exceeded test deadline')
                conn.send_command('scene_digest',{'limit':200,'since':digest['revision']})
                probes.append(conn.metrics['elapsed_ms'])
                await asyncio.sleep(.4)
            done = workers.status(job['id'],0)
            assert done['state'] == 'succeeded', done
            report['product_quality'] = {k:v for k,v in done['result'].items() if k != 'artifacts'}
            # Full diagnostic rows are a file artifact, not repeated tool output.
            quality = json.loads(Path(done['result_path']).read_text(encoding='utf-8'))
            quality['artifacts'] = {k:{**v,'path':str(Path(v['path']).relative_to(ROOT)).replace('\\','/')} for k,v in quality['artifacts'].items()}
            (ROOT/'benchmarks/quality-after.json').write_text(json.dumps(quality,indent=2)+'\n',encoding='utf-8')
            report['worker_responsiveness'] = {'render_worker_elapsed_ms':done['elapsed_ms'],
                'successful_gui_probes':len(probes),'gui_probe_median_ms':statistics.median(probes),
                'gui_probe_max_ms':max(probes),'gui_probe_samples_ms':probes,
                'scope':'Live GUI addon served inspection requests while a separate six-thread Blender process rebuilt/exported/rendered the product. Not a measurement of UI frame rate or freeze frequency.'}
        finally:
            workers.close()
    finally:
        conn.disconnect()
    path = ROOT/args.output
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    asyncio.run(main())

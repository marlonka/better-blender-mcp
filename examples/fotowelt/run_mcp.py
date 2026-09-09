"""Run the scene recipe through the configured enhanced MCP, not a direct Blender CLI."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import time
import tomllib
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

async def main():
    cfg=tomllib.loads((Path.home()/'.codex/config.toml').read_text(encoding='utf-8'))['mcp_servers']['blender']
    env=os.environ.copy();env.update(cfg.get('env',{}));env.update(PYTHONUTF8='1',DISABLE_TELEMETRY='true')
    env['BETTER_BLENDER_JOBS']=str(ROOT/'.local/fotowelt-workers')
    mode=sys.argv[1] if len(sys.argv)>1 else 'build'
    async with stdio_client(StdioServerParameters(command=cfg['command'],args=cfg['args'],env=env,cwd=str(ROOT))) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            async def call(name,args):
                result=await session.call_tool(name,args)
                if result.isError:raise RuntimeError(result.content)
                return json.loads(result.content[0].text)
            schemas=[t.name for t in (await session.list_tools()).tools]
            if 'blender_worker' not in schemas:raise RuntimeError('Configure the enhanced MCP entry point first')
            print(json.dumps({'mcp_tools':schemas}),flush=True)
            if mode=='snapshot':
                result=await session.call_tool('blender_snapshot',{'max_size':1400})
                if result.isError:raise RuntimeError(result.content)
                for item in result.content:
                    if item.type=='image':
                        destination=ROOT/'.local/fotowelt-viewport.png'
                        destination.write_bytes(base64.b64decode(item.data));print(str(destination))
                return
            if mode=='open':
                scene=str(HERE/'output/fotowelt.blend')
                job_id='fotowelt-open-'+uuid.uuid4().hex
                backup=str(ROOT/'.local'/('before-'+job_id+'.blend'))
                code=f'import bpy\nif bpy.data.is_dirty:\n bpy.ops.wm.save_as_mainfile(filepath={backup!r},copy=True)\nbpy.ops.wm.open_mainfile(filepath={scene!r})\nprint("Fotowelt opened")'
                result=await call('blender_batch',{'job_id':job_id,'steps':[{'name':'Preserve changes and open completed Fotowelt scene','code':code}]})
                while result['state'] in {'queued','running'}:
                    await asyncio.sleep(.5)
                    result=await call('blender_job',{'job_id':job_id})
                print(json.dumps(result),flush=True)
                if result['state']!='succeeded':raise RuntimeError(result)
                print(json.dumps(await call('blender_scene',{'limit':12})),flush=True)
                return
            recipe=str(HERE/('build_fotowelt.py' if mode=='build' else mode))
            started=time.monotonic(); calls=1
            result=await call('blender_worker',{'script_path':recipe,'job_id':uuid.uuid4().hex,'timeout_seconds':480,'wait_seconds':25})
            while result['state']=='running':
                print(json.dumps({'state':result['state'],'elapsed_seconds':round(time.monotonic()-started),'job_id':result['id']}),flush=True)
                result=await call('blender_worker',{'job_id':result['id'],'wait_seconds':25});calls+=1
            evidence={'mcp_entry_point':cfg['args'],'worker_tool_calls':calls,'elapsed_seconds':round(time.monotonic()-started,2),'worker':result}
            local_result=ROOT/'.local/fotowelt-latest-result.json'
            local_result.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
            # Keep a portable full audit and compact, path-normalized build record.
            if result.get('result_path') and Path(result['result_path']).is_file():
                full=json.loads(Path(result['result_path']).read_text(encoding='utf-8'))
                for artifact in full.get('artifacts',{}).values():
                    artifact['path']=Path(artifact['path']).relative_to(ROOT).as_posix()
                (HERE/'output/quality-report.json').write_text(json.dumps(full,indent=2),encoding='utf-8')
            portable={k:evidence[k] for k in ['mcp_entry_point','worker_tool_calls','elapsed_seconds']}
            portable['worker']={k:result[k] for k in ['state','elapsed_ms','returncode','tree_cleanup']}
            portable['audit']=result.get('result',{}).get('audit')
            (HERE/'output/mcp-result.json').write_text(json.dumps(portable,indent=2),encoding='utf-8')
            print(json.dumps(evidence),flush=True)
            if result['state']!='succeeded':raise RuntimeError(result.get('failure_tail',result['state']))

if __name__=='__main__':asyncio.run(main())

"""Exercise the real compact MCP stdio server and its isolated render worker."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]

async def main():
    env=os.environ.copy()
    env.update(DISABLE_TELEMETRY='true', PYTHONUTF8='1',
        BETTER_BLENDER_JOBS=str(ROOT/'.local'/'workers'))
    args=StdioServerParameters(command=sys.executable,args=['-m','blender_mcp.compact_server'],cwd=str(ROOT),env=env)
    async with stdio_client(args) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            schemas=await session.list_tools()
            print(json.dumps({'tools':[t.name for t in schemas.tools]}),flush=True)
            def data(result):
                if result.isError:
                    raise RuntimeError(result.content)
                return json.loads(result.content[0].text)
            started=time.monotonic()
            script=sys.argv[1] if len(sys.argv)>1 else 'examples/product-studio/blender/build_product.py'
            result=data(await session.call_tool('blender_worker',dict(script_path=str(ROOT/script),timeout_seconds=300,
                wait_seconds=25, reference_path=str(ROOT/'examples/product-studio/public/assets/reference.png'))))
            job_id=result['id']
            print(json.dumps({'worker':job_id,'state':result['state']}),flush=True)
            (ROOT/'.local'/'active-worker.json').write_text(json.dumps(result),encoding='utf-8')
            while result['state']=='running':
                result=data(await session.call_tool('blender_worker',dict(job_id=job_id,wait_seconds=25)))
                (ROOT/'.local'/'active-worker.json').write_text(json.dumps(result),encoding='utf-8')
                print(json.dumps({'state':result['state'],'seconds':round(time.monotonic()-started),'tail':result['log_tail'][-700:]}),flush=True)
            print(json.dumps(result),flush=True)
            if result['state']!='succeeded':
                raise RuntimeError('Worker '+result['state'])

if __name__=='__main__':
    asyncio.run(main())

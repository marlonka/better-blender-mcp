"""Render three jar packshots through the configured, five-tool Blender MCP."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
import tomllib
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / 'examples/product-studio'

VARIANTS = {
    'winternuesse': ('blender/render_views.py', 'public/assets/winternuesse.blend', 'renders'),
    'ultra-white': ('blender/ultra_white.py', 'renders/winternuesse-studio.blend', 'ultra-white'),
}

async def main(preview=False, variant='winternuesse'):
    recipe, source, output = VARIANTS[variant]
    cfg = tomllib.loads((Path.home()/'.codex/config.toml').read_text(encoding='utf-8'))['mcp_servers']['blender']
    env = os.environ.copy()
    env.update(cfg.get('env', {}))
    env.update(DISABLE_TELEMETRY='true', PYTHONUTF8='1', WINTERNUESSE_PREVIEW='1' if preview else '0',
               ULTRA_WHITE_PREVIEW='1' if preview else '0',
               BETTER_BLENDER_JOBS=str(ROOT/'.local/product-view-workers'))
    async with stdio_client(StdioServerParameters(command=cfg['command'], args=cfg['args'], env=env, cwd=str(ROOT))) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(args):
                response = await session.call_tool('blender_worker', args)
                if response.isError:
                    raise RuntimeError(response.content)
                return json.loads(response.content[0].text)
            started = time.monotonic()
            result = await call({'script_path': str(PRODUCT/recipe),
                                 'blend_path': str(PRODUCT/source),
                                 'job_id': uuid.uuid4().hex, 'timeout_seconds': 1200, 'wait_seconds': 25})
            calls = 1
            while result['state'] == 'running':
                print(json.dumps({'job_id': result['id'], 'state': result['state'],
                                  'elapsed_seconds': round(time.monotonic()-started)}), flush=True)
                result = await call({'job_id': result['id'], 'wait_seconds': 25})
                calls += 1
            evidence = {'variant': variant, 'entry_point': cfg['args'], 'worker_calls': calls,
                        'elapsed_seconds': round(time.monotonic()-started, 2), 'worker': result}
            evidence_name = 'product-views-latest.json' if variant == 'winternuesse' else f'{variant}-views-latest.json'
            evidence_path = ROOT/'.local'/evidence_name
            evidence_path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print(json.dumps(evidence), flush=True)
            if result['state'] != 'succeeded':
                raise RuntimeError(result.get('failure_tail', result['state']))
            if not preview:
                full = json.loads(Path(result['result_path']).read_text(encoding='utf-8'))
                for artifact in full.get('artifacts', {}).values():
                    artifact['path'] = Path(artifact['path']).relative_to(ROOT).as_posix()
                (PRODUCT/output/'quality-report.json').write_text(json.dumps(full, indent=2), encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--variant', choices=VARIANTS, default='winternuesse')
    args = parser.parse_args()
    asyncio.run(main(args.preview, args.variant))

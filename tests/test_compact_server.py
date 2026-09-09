import asyncio
import io
from types import SimpleNamespace

import pytest
from blender_mcp import compact_server as server
from blender_mcp.safe_mode import SandboxViolation


def test_all_stages_validated_before_transport(monkeypatch):
    sent = []
    async def command(*args):
        sent.append(args)
    monkeypatch.setattr(server,'command',command)
    stages = [server.Stage(name='valid',code='x = 1'),server.Stage(name='invalid',code='x = (')]
    with pytest.raises(SyntaxError):
        asyncio.run(server.blender_batch(stages))
    assert sent == []


def test_safe_mode_rejects_batch_and_worker_before_execution(monkeypatch,tmp_path):
    monkeypatch.setenv('BLENDER_MCP_SAFE_MODE','1')
    sent = []
    async def command(*args):
        sent.append(args)
    monkeypatch.setattr(server,'command',command)
    monkeypatch.setattr(server,'get_workers',lambda:SimpleNamespace())
    with pytest.raises(SandboxViolation):
        asyncio.run(server.blender_batch([server.Stage(name='bad',code='import subprocess')]))
    script = tmp_path/'bad.py'
    script.write_text('import subprocess')
    with pytest.raises(SandboxViolation):
        asyncio.run(server.blender_worker(script_path=str(script)))
    assert sent == []


def test_windows_install_cli_survives_cp1252(monkeypatch):
    from blender_mcp import addon_manager as manager
    output = io.BytesIO()
    stdout = io.TextIOWrapper(output,encoding='cp1252')
    monkeypatch.setattr(manager.sys,'stdout',stdout)
    monkeypatch.setattr(manager,'install_addon',lambda *_:SimpleNamespace(success=True,message='Updated old → new'))
    assert manager.run_cli(['install-addon']) == 0
    stdout.flush()
    assert b'Updated old ? new' in output.getvalue()

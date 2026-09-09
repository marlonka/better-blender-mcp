import sys
import time
import json
import os
from pathlib import Path
import subprocess

import pytest
from blender_mcp.workers import WorkerManager


def wait(manager, job):
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        status = manager.status(job['id'],8192)
        if status['returncode'] is not None:
            return status
        time.sleep(.02)
    pytest.fail('Worker failed to terminate')


def test_real_process_exit_and_bounded_logs(tmp_path):
    manager = WorkerManager(tmp_path)
    job = manager._spawn([sys.executable,'-c','print("x"*100000); raise SystemExit(7)'],tmp_path,5)
    result = wait(manager,job)
    assert result['state'] == 'failed' and result['returncode'] == 7
    assert len(result['log_tail']) <= 8192
    assert result['log_chars'] >= 100000
    assert manager.status(job['id'],0)['log_tail'] == ''
    assert WorkerManager(tmp_path).status(job['id'])['state'] == 'failed'


def test_timeout_kills_only_owned_worker(tmp_path):
    manager = WorkerManager(tmp_path)
    job = manager._spawn([sys.executable,'-c','import time; time.sleep(60)'],tmp_path,.15)
    result = wait(manager,job)
    assert result['state'] == 'timed_out'
    assert result['elapsed_ms'] < 5000


def test_capacity_cancel_and_close(tmp_path):
    manager = WorkerManager(tmp_path,max_active=1)
    job = manager._spawn([sys.executable,'-c','import time; time.sleep(60)'],tmp_path,10)
    try:
        with pytest.raises(ValueError,match='capacity'):
            manager._spawn([sys.executable,'-c','pass'],tmp_path,10)
        assert manager.cancel(job['id'])['state'] == 'cancelled'
        assert wait(manager,job)['returncode'] is not None
    finally:
        manager.close()


def test_invalid_script_and_identifiers_never_start_process(tmp_path):
    manager = WorkerManager(tmp_path)
    script = tmp_path/'invalid.py'
    script.write_text('broken(')
    with pytest.raises(SyntaxError):
        manager.start(sys.executable,script)
    with pytest.raises(ValueError,match='Invalid worker ID'):
        manager.status('../outside')
    assert manager.jobs == {}


def test_validated_source_is_snapshotted_even_if_original_changes(tmp_path, monkeypatch):
    manager = WorkerManager(tmp_path/'jobs')
    script = tmp_path/'recipe.py'
    script.write_text('print("validated")', encoding='utf-8')
    def validator(source):
        assert 'validated' in source
        script.write_text('raise RuntimeError("changed")', encoding='utf-8')
    def capture(command, cwd, timeout_seconds, **metadata):
        config = json.loads(Path(command[-1]).read_text())
        assert Path(config['source_path']).read_text() == 'print("validated")'
        assert config['script_path'] == str(script)
        assert cwd == script.parent
        return {'id': metadata['job_id']}
    monkeypatch.setattr(manager, '_spawn', capture)
    manager.start(sys.executable, script, validator=validator)


def test_wait_returns_terminal_error_without_requesting_logs(tmp_path):
    manager = WorkerManager(tmp_path)
    job = manager._spawn([sys.executable, '-c', 'raise RuntimeError("useful failure")'], tmp_path, 5)
    result = manager.wait(job['id'], 5)
    assert result['state'] == 'failed'
    assert result['log_tail'] == ''
    assert 'useful failure' in result['failure_tail']


@pytest.mark.skipif(os.name != 'nt', reason='Windows job object lifetime')
def test_windows_crashed_manager_kills_owned_process_tree(tmp_path):
    # The nested manager exits with os._exit: no atexit or finally cleanup.
    pid_file = tmp_path/'child.pid'
    nested = tmp_path/'nested.py'
    nested.write_text('''import os, sys, time
from pathlib import Path
from blender_mcp.workers import WorkerManager
manager = WorkerManager(Path(sys.argv[1])/'jobs')
code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid,flush=True); time.sleep(60)"
job = manager._spawn([sys.executable,'-c',code], Path(sys.argv[1]), 60)
deadline = time.monotonic()+5
while time.monotonic()<deadline:
    log = manager.status(job['id'], 100)['log_tail'].strip()
    if log:
        Path(sys.argv[2]).write_text(log)
        os._exit(0)
    time.sleep(.02)
raise RuntimeError('Child did not start')
''', encoding='utf-8')
    subprocess.run([sys.executable, str(nested), str(tmp_path), str(pid_file)], check=True, timeout=10)
    import ctypes as c
    from ctypes import wintypes as w
    api = c.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    api.OpenProcess.restype = w.HANDLE
    api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    api.WaitForSingleObject.restype = w.DWORD
    api.CloseHandle.argtypes = [w.HANDLE]
    handle = api.OpenProcess(0x00100000, False, int(pid_file.read_text()))
    if handle:
        try:
            assert api.WaitForSingleObject(handle, 3000) == 0, 'Grandchild survived the manager crash'
        finally:
            api.CloseHandle(handle)

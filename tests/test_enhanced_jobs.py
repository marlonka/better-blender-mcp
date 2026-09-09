"""Cooperative job and digest invariants against the actual addon class."""
import queue
import time
from types import SimpleNamespace as NS

import pytest
from test_server_threading import _load_server_class


@pytest.fixture
def server():
    cls, _ = _load_server_class()
    return cls()


def test_all_stages_compile_before_any_mutation(server):
    with pytest.raises(SyntaxError):
        server.submit_job([{'code':'bpy.changed = True'}, {'code':'broken('}])
    assert server.jobs == {}
    assert not hasattr(server.submit_job.__globals__['bpy'], 'changed')


def test_stage_yield_shared_namespace_and_idempotency(server):
    steps = [{'code':'x = 41'}, {'code':'print(x + 1)'}]
    before = server.submit_job(steps, 'stable-id')
    server._advance_job()
    progress = server.get_job_status('stable-id')
    assert progress['completed'] == 1
    assert before['results'] == []  # queued socket replies must be immutable
    server._advance_job()
    done = server.submit_job(steps, 'stable-id')
    assert done['state'] == 'succeeded'
    assert done['completed'] == 2
    assert done['results'][1]['output'] == '42\n'
    assert len(progress['results']) == 1
    assert server._job_order == []
    with pytest.raises(ValueError, match='different content'):
        server.submit_job([{'code':'x = 0'}], 'stable-id')


@pytest.mark.parametrize('failure', ['raise ValueError("stop")', 'raise SystemExit(1)'])
def test_failure_never_replays_or_runs_later_stages(server, failure):
    job = server.submit_job([{'code':failure}, {'code':'bpy.bad = True'}])
    server._advance_job()
    server._advance_job()
    status = server.get_job_status(job['id'])
    assert status['state'] == 'failed'
    assert len(status['results']) == 1
    assert 'namespace' not in server.jobs[job['id']]
    assert not hasattr(server.submit_job.__globals__['bpy'], 'bad')


def test_output_bounded_during_execution(server):
    job = server.submit_job([{'code':'print("x" * 100_000)'}])
    server._advance_job()
    row = server.get_job_status(job['id'])['results'][0]
    assert len(row['output']) == 2048
    assert row['dropped_chars'] == 100001 - 2048


def test_cancel_and_stop_release_namespaces(server):
    a = server.submit_job([{'code':'x = 1'}, {'code':'x = 2'}])
    b = server.submit_job([{'code':'x = 3'}])
    server._advance_job()
    server.cancel_job(a['id'])
    server.stop()
    for job in (a, b):
        assert server.get_job_status(job['id'])['state'] == 'cancelled'
        assert 'namespace' not in server.jobs[job['id']]
    assert not server._job_order


def test_job_queue_and_history_are_bounded(server):
    for i in range(8):
        server.submit_job([{'code':'pass'}], str(i))
    with pytest.raises(ValueError, match='queue full'):
        server.submit_job([{'code':'pass'}])
    for i in range(8):
        server._advance_job()
    for i in range(130):
        server.submit_job([{'code':'pass'}], 'history-'+str(i))
        server._advance_job()
    assert len(server.jobs) == 128


def test_command_budget_yields_and_expired_commands_do_not_run(server):
    server.running = True
    executed = []
    def execute(cmd):
        executed.append(cmd)
        time.sleep(.012)  # one operation exceeds 8ms; second must yield
        return {'status':'success'}
    server.execute_command = execute
    for i in range(3):
        reply = queue.Queue(1)
        reply.expires_at = time.monotonic() + (10 if i else -1)
        server.command_queue.put((i, reply))
    server._drain_command_queue()
    assert executed == [1]
    assert server.command_queue.qsize() == 1


def object_row(name):
    return NS(name=name,type='MESH',location=[0,0,0],rotation_euler=[0,0,0],
        dimensions=[1,1,1],material_slots=[],data=NS(vertices=[0]*8,polygons=[0]*6))


def test_digest_changes_removals_query_changes_and_explicit_pagination(server):
    bpy = server.scene_digest.__globals__['bpy']
    a,b = object_row('A'),object_row('B')
    bpy.context.scene = NS(name='Study',objects=[b,a])
    first = server.scene_digest(limit=1)
    assert list(first['objects']) == ['A']
    assert first['next_offset'] == 1
    unchanged = server.scene_digest(since=first['revision'],limit=1)
    assert unchanged['delta'] and not unchanged['objects']
    all_rows = server.scene_digest()
    a.location[0] = .000012
    changed = server.scene_digest(since=all_rows['revision'])
    assert list(changed['objects']) == ['A']
    bpy.context.scene.objects = [a]
    removed = server.scene_digest(since=changed['revision'])
    assert removed['removed'] == ['B']
    filtered = server.scene_digest(names=['A'], since=removed['revision'])
    assert not filtered['delta']
@pytest.mark.parametrize('code', [
    'bpy.ops.render.render(write_still=True)',
    'import bpy as b; b.ops.object.bake(type="NORMAL")',
    'from bpy import ops; ops.ptcache.bake_all()',
    'r = bpy.ops.render.render; r()',
])
def test_known_blocking_work_is_rejected_before_any_stage_runs(server, code):
    with pytest.raises(ValueError, match='blender_worker'):
        server.submit_job([{'code':'bpy.marker = "must not run"'}, {'code':code}])
    assert not server.jobs


def test_blocking_alias_is_tracked_across_stages(server):
    with pytest.raises(ValueError, match='blender_worker'):
        server.submit_job([{'code':'render = bpy.ops.render.render'}, {'code':'render()'}])
    assert not server.jobs

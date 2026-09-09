import json
import socket

import pytest
from blender_mcp.connection import BlenderCommandError, BlenderConnection, JsonFrame


class Socket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.sent = []
        self.closed = False
    def settimeout(self, seconds):
        self.timeout = seconds
    def sendall(self, value):
        self.sent.append(value)
    def recv(self, size):
        item = next(self.chunks, b'')
        if isinstance(item, Exception):
            raise item
        return item
    def close(self):
        self.closed = True


def test_fragmented_unicode_escaped_quotes_and_braces():
    raw = json.dumps({'status':'success','result':{'text':'Nüsse " } \\ [ 🍂'}},ensure_ascii=False).encode()
    sock = Socket([bytes([b]) for b in raw])
    c = BlenderConnection('local',1,sock=sock)
    assert c.send_command('test')['text'] == 'Nüsse " } \\ [ 🍂'
    assert c.metrics['response_bytes'] == len(raw)


@pytest.mark.parametrize('chunks', [[b'{"status":'], [socket.timeout('late')]])
def test_disconnect_and_timeout_never_replay_mutations(chunks):
    sock = Socket(chunks)
    c = BlenderConnection('local',1,sock=sock)
    with pytest.raises(ConnectionError,match='not replayed'):
        c.send_command('mutate')
    assert len(sock.sent) == 1
    assert sock.closed and c.sock is None


def test_blender_error_retains_valid_connection():
    sock = Socket([b'{"status":"error","message":"Bad mesh"}'])
    c = BlenderConnection('local',1,sock=sock)
    with pytest.raises(BlenderCommandError,match='Bad mesh'):
        c.send_command('test')
    assert not sock.closed


def test_receive_memory_limit_and_ambiguous_framing():
    frame = JsonFrame()
    with pytest.raises(ValueError,match='byte limit'):
        frame.feed(b'{"large":"' + b'x'*100, 20)
    with pytest.raises(ValueError,match='Unexpected data'):
        JsonFrame().feed(b'{}{}',100)


def test_deadline_is_absolute_even_when_bytes_keep_arriving(monkeypatch):
    from blender_mcp import connection
    times = iter([10.,10.6,11.1])
    monkeypatch.setattr(connection.time,'monotonic',lambda:next(times))
    sock = Socket([b'{',b'"s"'])
    c = BlenderConnection('local',1,sock=sock)
    with pytest.raises(TimeoutError):
        c.receive_full_response(sock,deadline=11)


def test_request_limit_rejects_before_send():
    sock = Socket([])
    c = BlenderConnection('local',1,sock=sock)
    with pytest.raises(ValueError,match='2 MB'):
        c.send_command('test',{'code':'x'*2_000_000})
    assert not sock.sent


def test_expired_deadline_does_not_send_a_mutation(monkeypatch):
    from blender_mcp import connection
    times = iter([0,1.1])
    monkeypatch.setattr(connection.time,'monotonic',lambda:next(times))
    sock = Socket([])
    c = BlenderConnection('local',1,sock=sock,timeout=1)
    with pytest.raises(TimeoutError,match='not sent'):
        c.send_command('mutate')
    assert not sock.sent

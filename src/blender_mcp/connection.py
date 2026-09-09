"""Bounded, serialized transport for both legacy and enhanced Blender addons."""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any


class BlenderCommandError(RuntimeError):
    """Blender received the request and reported failure; connection is valid."""


class JsonFrame:
    """Find a JSON object's boundary in O(n), including split UTF-8 strings."""
    def __init__(self):
        self.data = bytearray()
        self.depth = 0
        self.quoted = False
        self.escaped = False
        self.started = False
        self.complete = False

    def feed(self, chunk: bytes, limit: int) -> bool:
        if len(self.data) + len(chunk) > limit:
            raise ValueError(f"Response exceeds {limit} byte limit")
        self.data.extend(chunk)
        for char in chunk:
            if self.complete:
                if char not in b' \t\r\n':
                    raise ValueError('Unexpected data after JSON response')
                continue
            if self.quoted:
                if self.escaped:
                    self.escaped = False
                elif char == 92:
                    self.escaped = True
                elif char == 34:
                    self.quoted = False
                continue
            if not self.started:
                if char in b' \t\r\n':
                    continue
                if char != 123:
                    raise ValueError('Response must be a JSON object')
                self.started = True
            if char == 34:
                self.quoted = True
            elif char in (123, 91):
                self.depth += 1
            elif char in (125, 93):
                self.depth -= 1
                if self.depth == 0:
                    self.complete = True
        return self.complete


@dataclass
class BlenderConnection:
    host: str
    port: int
    sock: Any = None
    timeout: float = 180.0
    max_response_bytes: int = 16_000_000
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    metrics: dict = field(default_factory=dict)

    def connect(self) -> bool:
        if self.sock is not None:
            return True
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=min(5, self.timeout))
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return True
        except OSError:
            self.disconnect()
            return False

    def disconnect(self):
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def receive_full_response(self, sock, buffer_size=65536, deadline=None):
        deadline = deadline or time.monotonic() + self.timeout
        frame = JsonFrame()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Blender response deadline exceeded')
            sock.settimeout(remaining)
            chunk = sock.recv(buffer_size)
            if not chunk:
                raise ConnectionError('Connection closed before a complete response')
            if frame.feed(chunk, self.max_response_bytes):
                return bytes(frame.data)

    def send_command(self, command_type: str, params: dict | None = None) -> dict:
        started = time.monotonic()
        measured = time.perf_counter()
        if not self._lock.acquire(timeout=self.timeout):
            raise TimeoutError('Another Blender request is still running; request was not sent')
        sent = False
        try:
            if not self.connect():
                raise ConnectionError(f'Cannot connect to Blender at {self.host}:{self.port}')
            request = json.dumps({'type':command_type, 'params':params or {}}, separators=(',', ':')).encode('utf-8')
            if len(request) > 2_000_000:
                raise ValueError('Command exceeds 2 MB transport limit')
            remaining = self.timeout-(time.monotonic()-started)
            if remaining <= 0:
                raise TimeoutError('Request deadline exhausted before send; request was not sent')
            self.sock.settimeout(remaining)
            # A failed send may still have delivered bytes. Never replay it.
            sent = True
            self.sock.sendall(request)
            raw = self.receive_full_response(self.sock, deadline=started+self.timeout)
            response = json.loads(raw.decode('utf-8'))
            self.metrics = dict(request_bytes=len(request), response_bytes=len(raw),
                elapsed_ms=round((time.perf_counter()-measured)*1000, 3))
            if response.get('status') == 'error':
                raise BlenderCommandError(response.get('message', 'Blender command failed'))
            if response.get('status') != 'success':
                raise ValueError('Invalid Blender response status')
            return response.get('result', {})
        except BlenderCommandError:
            raise
        except Exception as exc:
            self.disconnect()
            if sent:
                raise ConnectionError(f'{exc}. Execution state unknown; not replayed. Query job status before retrying mutations.') from exc
            raise
        finally:
            self._lock.release()

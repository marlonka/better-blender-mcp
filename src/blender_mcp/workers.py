"""Isolated Blender processes: bounded logs, deadlines and explicit cancellation."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

from .process_guard import ProcessGuard


class WorkerManager:
    def __init__(self, directory: Path, max_active=2):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.lock = threading.RLock()
        self.max_active = max_active

    def start(self, binary, script_path=None, blend_path=None, timeout_seconds=120,
              *, job_id=None, audit=True, reference_path=None, validator=None):
        if not script_path and not blend_path:
            raise ValueError('Provide a script_path or blend_path')
        script, source = None, None
        if script_path:
            script = Path(script_path).resolve(strict=True)
            if not script.is_file() or script.suffix != '.py' or script.stat().st_size > 1_000_000:
                raise ValueError('script_path must be an existing .py file up to 1 MB')
            source = script.read_text(encoding='utf-8')
            compile(source, str(script), 'exec')
            if validator:
                validator(source)
        if not 1 <= timeout_seconds <= 3600:
            raise ValueError('timeout_seconds must be 1-3600')
        executable = Path(binary).resolve(strict=True)
        command = [str(executable), '--background', '--factory-startup', '--disable-autoexec', '--threads', '6']
        blend = None
        if blend_path:
            blend = Path(blend_path).resolve(strict=True)
            if not blend.is_file() or blend.suffix != '.blend':
                raise ValueError('blend_path must be an existing .blend file')
            command.append(str(blend))
        reference = str(Path(reference_path).resolve(strict=True)) if reference_path else None
        job_id = job_id or uuid.uuid4().hex
        self._validate_id(job_id)
        fingerprint = hashlib.sha256(json.dumps(dict(binary=str(executable), script=str(script),
            source=source, blend=str(blend), blend_stat=[blend.stat().st_mtime_ns, blend.stat().st_size] if blend else None,
            audit=audit, reference=reference, timeout=timeout_seconds), sort_keys=True).encode()).hexdigest()
        with self.lock:
            if job_id in self.jobs or (self.directory/(job_id+'.json')).exists():
                existing = self.status(job_id)
                if existing.get('fingerprint') != fingerprint:
                    raise ValueError('Worker ID already exists with different inputs; not replayed')
                return existing
            config = dict(script_path=str(script) if script else None,
                source_path=str(self.directory/(job_id+'.source.py')),
                result_path=str(self.directory/(job_id+'.result.json')),
                audit=audit, reference_path=reference, started=time.time())
            config_path = self.directory/(job_id+'.config.json')
            if source is not None:
                Path(config['source_path']).write_text(source, encoding='utf-8')
            config_path.write_text(json.dumps(config), encoding='utf-8')
            command += ['--python-exit-code', '1', '--python', str(Path(__file__).with_name('worker_bootstrap.py')), '--', str(config_path)]
            return self._spawn(command, script.parent if script else blend.parent, timeout_seconds,
                job_id=job_id, fingerprint=fingerprint, result_path=config['result_path'])

    def _spawn(self, command, cwd, timeout_seconds, *, job_id=None, **metadata):
        with self.lock:
            if sum(j['state'] == 'running' for j in self.jobs.values()) >= self.max_active:
                raise ValueError('Worker capacity reached; wait or cancel a worker')
            # Completed process records are durable on disk; bound in-memory data.
            if len(self.jobs) >= 64:
                oldest = next(k for k, v in self.jobs.items() if v['state'] != 'running')
                del self.jobs[oldest]
            job_id = job_id or uuid.uuid4().hex
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'
            process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
                creationflags=flags, env=env, start_new_session=os.name != 'nt')
            try:
                guard = ProcessGuard(process)
            except BaseException:
                process.kill()
                process.wait()
                process.stdout.close()
                raise
            job = dict(id=job_id, state='running', pid=process.pid, started=time.time(),
                elapsed_ms=0, returncode=None, log_tail='', log_chars=0,
                timeout_seconds=timeout_seconds, _process=process, _guard=guard,
                _done=threading.Event(), tree_cleanup='windows_job' if os.name == 'nt' else 'process_group', **metadata)
            self.jobs[job_id] = job
            self._persist(job)
        reader = threading.Thread(target=self._read_log, args=(job,), daemon=True)
        reader.start()
        threading.Thread(target=self._supervise, args=(job, reader), daemon=True).start()
        return self.status(job_id)

    def _read_log(self, job):
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        stream = job['_process'].stdout
        try:
            for chunk in iter(lambda: stream.read1(4096), b''):
                value = decoder.decode(chunk)
                with self.lock:
                    job['log_chars'] += len(value)
                    job['log_tail'] = (job['log_tail'] + value)[-8192:]
        finally:
            stream.close()
            with self.lock:
                self._persist(job)

    def _supervise(self, job, reader):
        process = job['_process']
        try:
            process.wait(timeout=job['timeout_seconds'])
        except subprocess.TimeoutExpired:
            with self.lock:
                if job['state'] == 'running':
                    job['state'] = 'timed_out'
            job['_guard'].kill()
            process.wait()
        # Close inherited stdout handles and terminate any surviving descendants.
        job['_guard'].close()
        # Publish terminal state only after the process's final error/output.
        reader.join(timeout=2)
        with self.lock:
            if job['state'] == 'running':
                job['state'] = 'succeeded' if process.returncode == 0 else 'failed'
            job['returncode'] = process.returncode
            job['elapsed_ms'] = round((time.time()-job['started'])*1000)
            result_path = job.get('result_path')
            if result_path and Path(result_path).is_file():
                try:
                    path = Path(result_path)
                    if path.stat().st_size > 5_000_000:
                        raise ValueError('Worker result exceeds 5 MB')
                    full = json.loads(path.read_text(encoding='utf-8'))
                    summary = {k: v for k, v in full.items() if k != 'audit'}
                    if 'audit' in full:
                        audit = full['audit']
                        summary['audit'] = {k: v for k, v in audit.items() if k not in {'objects', 'issues'}}
                        summary['audit']['issues'] = audit['issues'][:8]
                        summary['audit']['omitted_issues'] = max(0, len(audit['issues'])-8)
                    job['result'] = summary
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    job['result_error'] = str(exc)[:512]
            self._persist(job)
            job['_done'].set()

    def _persist(self, job):
        data = {k:v for k,v in job.items() if not k.startswith('_')}
        path = self.directory / (job['id'] + '.json')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temporary.replace(path)

    @staticmethod
    def _validate_id(job_id):
        if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('Invalid worker ID')

    def status(self, job_id, log_chars=0):
        self._validate_id(job_id)
        if not 0 <= log_chars <= 8192:
            raise ValueError('log_chars must be 0-8192')
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                path = self.directory / (job_id + '.json')
                if not path.exists():
                    raise ValueError('Unknown worker ID')
                job = json.loads(path.read_text(encoding='utf-8'))
                if job['state'] == 'running':
                    job['state'] = 'unknown_after_restart'
            result = {k:v for k,v in job.items() if not k.startswith('_')}
            if result['state'] == 'running':
                result['elapsed_ms'] = round((time.time()-job['started'])*1000)
            result['log_tail'] = job['log_tail'][-log_chars:] if log_chars else ''
            if not log_chars and job['state'] in {'failed', 'timed_out'}:
                result['failure_tail'] = job['log_tail'][-1500:]
            return result

    def wait(self, job_id, seconds=0, log_chars=0):
        if not 0 <= seconds <= 30:
            raise ValueError('wait_seconds must be 0-30')
        self.status(job_id, log_chars)
        with self.lock:
            done = self.jobs.get(job_id, {}).get('_done')
        if done and seconds:
            done.wait(seconds)
        return self.status(job_id, log_chars)

    def cancel(self, job_id):
        self.status(job_id, 0)  # validate identifier
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job['state'] == 'running':
                job['state'] = 'cancelled'
                job['_guard'].kill()
                self._persist(job)
        return self.status(job_id)

    def close(self):
        with self.lock:
            for job in list(self.jobs.values()):
                if job['state'] == 'running':
                    self.cancel(job['id'])

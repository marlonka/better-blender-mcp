"""Own a worker process tree; never recover ownership from a persisted PID."""
import os
import signal


class ProcessGuard:
    def __init__(self, process):
        self.process = process
        self.handle = None
        self.closed = False
        if os.name == 'nt':
            self._attach_windows_job()

    def _attach_windows_job(self):
        import ctypes as c
        from ctypes import wintypes as w

        class BasicLimits(c.Structure):
            _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64),
                ('flags', w.DWORD), ('minimum_working_set', c.c_size_t),
                ('maximum_working_set', c.c_size_t), ('active_processes', w.DWORD),
                ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class IOCounters(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in
                ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

        class ExtendedLimits(c.Structure):
            _fields_ = [('basic', BasicLimits), ('io', IOCounters),
                ('process_memory', c.c_size_t), ('job_memory', c.c_size_t),
                ('peak_process_memory', c.c_size_t), ('peak_job_memory', c.c_size_t)]

        api = c.WinDLL('kernel32', use_last_error=True)
        api.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        api.CreateJobObjectW.restype = w.HANDLE
        api.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        api.SetInformationJobObject.restype = w.BOOL
        api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        api.AssignProcessToJobObject.restype = w.BOOL
        api.CloseHandle.argtypes = [w.HANDLE]
        api.CloseHandle.restype = w.BOOL
        handle = api.CreateJobObjectW(None, None)  # Non-inheritable handle.
        if not handle:
            raise c.WinError(c.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not api.SetInformationJobObject(handle, 9, c.byref(limits), c.sizeof(limits)):
                raise c.WinError(c.get_last_error())
            if not api.AssignProcessToJobObject(handle, w.HANDLE(int(self.process._handle))):
                # A very short-lived child can finish before assignment.
                if self.process.poll() is None:
                    raise c.WinError(c.get_last_error())
        except BaseException:
            api.CloseHandle(handle)
            raise
        self.handle, self.api = handle, api

    def close(self):
        if self.closed:
            return
        self.closed = True
        if os.name == 'nt':
            if self.handle:
                handle, self.handle = self.handle, None
                self.api.CloseHandle(handle)
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def kill(self):
        self.close()
        if self.process.poll() is None:
            self.process.kill()

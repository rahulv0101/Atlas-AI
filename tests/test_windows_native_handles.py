import ctypes
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock

from atlas_ai.windows_native import kernel32


def test_windows_handles_use_pointer_width_for_creation_use_and_close(monkeypatch):
    names = ("CreateMutexW", "CloseHandle", "ReleaseMutex", "OpenProcess", "TerminateProcess", "WaitForSingleObject", "GetLastError", "SetLastError")
    native = SimpleNamespace(**{name: Mock() for name in names})
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=native), raising=False)
    assert kernel32() is native
    assert native.CreateMutexW.restype is wintypes.HANDLE
    assert native.OpenProcess.restype is wintypes.HANDLE
    for name in ("CloseHandle", "ReleaseMutex", "TerminateProcess", "WaitForSingleObject"):
        assert getattr(native, name).argtypes[0] is wintypes.HANDLE
    assert ctypes.sizeof(wintypes.HANDLE) == ctypes.sizeof(ctypes.c_void_p)

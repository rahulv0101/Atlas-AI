"""Pointer-width-safe signatures shared by Windows process and mutex guards."""
import ctypes
from ctypes import wintypes


def kernel32():
    native = ctypes.windll.kernel32
    signatures = {
        "CreateMutexW": ([ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "ReleaseMutex": ([wintypes.HANDLE], wintypes.BOOL),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "GetLastError": ([], wintypes.DWORD),
        "SetLastError": ([wintypes.DWORD], None),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(native, name)
        function.argtypes = arguments
        function.restype = result
    return native

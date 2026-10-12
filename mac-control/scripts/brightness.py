#!/usr/bin/env python3
"""主显示器亮度读取/设置。用法: brightness.py [get] | set <0.0-1.0> | up|down [步长=0.1]"""
import ctypes, sys

def _lib():
    cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cg.CGMainDisplayID.restype = ctypes.c_uint32
    ds = ctypes.CDLL('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
    return cg.CGMainDisplayID(), ds

def get(disp, ds):
    v = ctypes.c_float(-1)
    if ds.DisplayServicesGetBrightness(ctypes.c_uint32(disp), ctypes.byref(v)) != 0:
        raise SystemExit('DisplayServicesGetBrightness failed')
    return v.value

def set_(disp, ds, val):
    val = min(1.0, max(0.05, val))
    if ds.DisplayServicesSetBrightness(ctypes.c_uint32(disp), ctypes.c_float(val)) != 0:
        raise SystemExit('DisplayServicesSetBrightness failed')
    return val

if __name__ == '__main__':
    disp, ds = _lib()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'get'
    if cmd == 'get':
        print(f'{get(disp, ds):.3f}')
    elif cmd == 'set':
        target = set_(disp, ds, float(sys.argv[1 + 1]))
        print(f'set -> {target:.3f}, readback {get(disp, ds):.3f}')
    elif cmd in ('up', 'down'):
        step = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
        target = set_(disp, ds, get(disp, ds) + (step if cmd == 'up' else -step))
        print(f'{cmd} -> {target:.3f}, readback {get(disp, ds):.3f}')
    else:
        raise SystemExit(__doc__)

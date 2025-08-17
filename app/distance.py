import time, threading, statistics
from typing import Optional, Deque
from collections import deque

# Try Adafruit first (if available)
def _try_vl6180x(log):
    try:
        import board, busio, adafruit_vl6180x
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        sensor = adafruit_vl6180x.VL6180X(i2c)
        log("using Adafruit VL6180X")
        return ("VL6180X", sensor)
    except Exception as e:
        log(f"VL6180X import/open failed: {e}")
        return (None, None)

try:
    import smbus2
    from smbus2 import i2c_msg
except Exception:
    smbus2 = None
    i2c_msg = None

# VL6180X registers
ID_MODEL                   = 0x0000
SYSTEM_FRESH_OUT_OF_RESET  = 0x0016
SYSRANGE_START             = 0x0018
RESULT_INT_STATUS          = 0x004F
RESULT_RANGE_VAL           = 0x0062
SYSTEM_INTERRUPT_CLEAR     = 0x0015

def _r8(bus, addr, reg16):
    bus.i2c_rdwr(i2c_msg.write(addr, [(reg16>>8)&0xFF, reg16&0xFF]))
    rh = i2c_msg.read(addr, 1)
    bus.i2c_rdwr(rh)
    return list(rh)[0]

def _w8(bus, addr, reg16, val):
    bus.i2c_rdwr(i2c_msg.write(addr, [(reg16>>8)&0xFF, reg16&0xFF, val&0xFF]))

def _tune(bus, addr):
    # Recommended tuning set (common set used by working drivers)
    seq=[(0x0207,0x01),(0x0208,0x01),(0x0096,0x00),(0x0097,0xFD),
         (0x00E3,0x00),(0x00E4,0x04),(0x00E5,0x02),(0x00E6,0x01),(0x00E7,0x03),
         (0x00F5,0x02),(0x00D9,0x05),(0x00DB,0xCE),(0x00DC,0x03),(0x00DD,0xF8),
         (0x009F,0x00),(0x00A3,0x3C),(0x00B7,0x00),(0x00BB,0x3C),
         (0x00B2,0x09),(0x00CA,0x09),(0x0198,0x01),(0x01B0,0x17),(0x01AD,0x00),
         (0x00FF,0x05),(0x0100,0x05),(0x0199,0x05),(0x01A6,0x1B),(0x01AC,0x3E),
         (0x01A7,0x1F),(0x0030,0x00)]
    for r,v in seq: _w8(bus, addr, r, v)

def _single_shot_mm(bus, addr, timeout_ms=600)->Optional[int]:
    # start single shot
    _w8(bus, addr, SYSRANGE_START, 0x01)
    t0=time.time()
    while True:
        st=_r8(bus, addr, RESULT_INT_STATUS)&0x07
        if st==0x04: break
        if (time.time()-t0)*1000>timeout_ms: return None
        time.sleep(0.003)
    mm=_r8(bus, addr, RESULT_RANGE_VAL)
    _w8(bus, addr, SYSTEM_INTERRUPT_CLEAR, 0x07)
    return None if mm in (0,255) else int(mm)

class DistanceReader:
    def __init__(self, cfg, logger=print):
        self.log=(lambda m: logger(f"[Distance] {m}")) if logger else (lambda *_: None)
        d=cfg.get("distance",{})
        try: self.addr=int(str(d.get("addr","0x29")),16)
        except Exception: self.addr=0x29
        self.enabled=bool(d.get("enabled",True))
        self._mm=None; self._history: Deque[int]=deque(maxlen=3)
        self.backend=None; self._sensor=None; self.last_error=None
        if not self.enabled: self.log("disabled"); return

        # Prefer Adafruit (if available)
        b,s = _try_vl6180x(self.log)
        if b: self.backend,self._sensor=b,s
        elif smbus2 and i2c_msg:
            try:
                with smbus2.SMBus(1) as bus:
                    _ = _r8(bus, self.addr, ID_MODEL)
                    # If fresh reset bit is set, run tuning
                    try:
                        if _r8(bus, self.addr, SYSTEM_FRESH_OUT_OF_RESET)==1:
                            _tune(bus, self.addr)
                    except Exception: pass
                self.backend="RAW6180X"; self.log("using RAW VL6180X")
            except Exception as e:
                self.last_error=str(e); self.log(f"raw init failed: {e}")

        if self.backend:
            threading.Thread(target=self._loop, daemon=True).start()
        else:
            self.log("no backends")

    def _loop(self):
        last=None
        while True:
            try:
                val=None
                if self.backend=="VL6180X":
                    r=getattr(self._sensor,"range",None)  # cm
                    if r is not None and r>0: val=int(r)*10
                elif self.backend=="RAW6180X":
                    with smbus2.SMBus(1) as bus:
                        # retry up to 3 times
                        for _ in range(3):
                            val=_single_shot_mm(bus, self.addr, 700)
                            if val is not None: break
                # smooth + change-log
                if val is not None:
                    self._history.append(val)
                    filt=int(statistics.median(self._history))
                    self._mm=filt
                    if filt!=last:
                        last=filt
                        self.log(f"value {filt} mm ({filt/10:.1f} cm)")
                else:
                    self._mm=None
            except Exception as e:
                self.last_error=str(e)
            time.sleep(0.2)

    def read_mm(self)->Optional[int]:
        return self._mm
PY
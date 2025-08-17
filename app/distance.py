import time
from typing import Optional
def _adafruit_vl6180x():
    try:
        import board, busio, adafruit_vl6180x
        i2c = busio.I2C(board.SCL, board.SDA)
        return ("VL6180X", adafruit_vl6180x.VL6180X(i2c))
    except Exception:
        return None
def _adafruit_vl53l0x():
    try:
        import board, busio, adafruit_vl53l0x
        i2c = busio.I2C(board.SCL, board.SDA)
        return ("VL53L0X", adafruit_vl53l0x.VL53L0X(i2c))
    except Exception:
        return None
try:
    import smbus2
    from smbus2 import i2c_msg
except Exception:
    smbus2 = None
    i2c_msg = None
ID_MODEL                   = 0x0000
SYSTEM_FRESH_OUT_OF_RESET  = 0x0016
SYSRANGE_START             = 0x0018
RESULT_INT_STATUS          = 0x004F
RESULT_RANGE_VAL           = 0x0062
SYSTEM_INTERRUPT_CLEAR     = 0x0015
def _r8(bus, addr, reg16):
    wh = i2c_msg.write(addr, [(reg16>>8)&0xFF, reg16&0xFF])
    rh = i2c_msg.read(addr, 1)
    bus.i2c_rdwr(wh, rh); return list(rh)[0]
def _w8(bus, addr, reg16, val):
    bus.i2c_rdwr(i2c_msg.write(addr, [(reg16>>8)&0xFF, reg16&0xFF, val&0xFF]))
_TUNED=False
def _load_tuning(bus, addr):
    seq=[(0x0207,0x01),(0x0208,0x01),(0x0096,0x00),(0x0097,0xFD),
         (0x00E3,0x00),(0x00E4,0x04),(0x00E5,0x02),(0x00E6,0x01),(0x00E7,0x03),
         (0x00F5,0x02),(0x00D9,0x05),(0x00DB,0xCE),(0x00DC,0x03),(0x00DD,0xF8),
         (0x009F,0x00),(0x00A3,0x3C),(0x00B7,0x00),(0x00BB,0x3C),
         (0x00B2,0x09),(0x00CA,0x09),(0x0198,0x01),(0x01B0,0x17),(0x01AD,0x00),
         (0x00FF,0x05),(0x0100,0x05),(0x0199,0x05),(0x01A6,0x1B),(0x01AC,0x3E),
         (0x01A7,0x1F),(0x0030,0x00)]
    for r,v in seq: _w8(bus, addr, r, v)
def _ensure_tuned(bus, addr):
    global _TUNED
    if _TUNED: return True
    try:
        _ = _r8(bus, addr, ID_MODEL)
        if _r8(bus, addr, SYSTEM_FRESH_OUT_OF_RESET)==1:
            _w8(bus, addr, SYSTEM_FRESH_OUT_OF_RESET, 0x00)
        _load_tuning(bus, addr); _TUNED=True; return True
    except Exception:
        return False
def _single_shot_mm(bus, addr, timeout_ms=350)->Optional[int]:
    _w8(bus, addr, SYSRANGE_START, 0x01)
    t0=time.time()
    while True:
        st=_r8(bus, addr, RESULT_INT_STATUS)&0x07
        if st==0x04: break
        if (time.time()-t0)*1000>timeout_ms: return None
        time.sleep(0.004)
    mm=_r8(bus, addr, RESULT_RANGE_VAL)
    try: _w8(bus, addr, SYSTEM_INTERRUPT_CLEAR, 0x07)
    except Exception: pass
    return None if mm==255 else int(mm)
class DistanceReader:
    def __init__(self, cfg, logger=print):
        self.log=(lambda m: logger(f"[Distance] {m}")) if logger else (lambda *_: None)
        d=cfg.get("distance",{})
        self.enabled=bool(d.get("enabled",True))
        try: self.addr = int(str(d.get("addr","0x29")),16)
        except Exception: self.addr=0x29
        self.backend=None; self._sensor=None; self.last_error=None
        if not self.enabled: self.log("disabled")
        ada618=_adafruit_vl6180x()
        if ada618: self.backend,self._sensor=ada618; self.log("using Adafruit VL6180X"); return
        ada53=_adafruit_vl53l0x()
        if ada53: self.backend,self._sensor=ada53; self.log("using Adafruit VL53L0X"); return
        if smbus2 and i2c_msg:
            self.backend="RAW6180X"; self.log("using RAW VL6180X")
        else:
            self.last_error="No backends available"; self.log(self.last_error)
    def read_mm(self)->Optional[int]:
        if not self.enabled: return None
        try:
            if self.backend=="VL6180X":
                mm=int(self._sensor.range); return None if mm==255 else mm
            if self.backend=="VL53L0X":
                mm=int(self._sensor.range); return None if mm in (0,8191,65535) else mm
            if self.backend=="RAW6180X":
                with smbus2.SMBus(1) as bus:
                    if not _ensure_tuned(bus, self.addr): self.last_error="tuning failed"; return None
                    mm=_single_shot_mm(bus, self.addr, 350)
                    if mm is None: mm=_single_shot_mm(bus, self.addr, 500)
                    return mm
        except Exception as e:
            self.last_error=str(e); self.log(f"read error: {e}"); return None

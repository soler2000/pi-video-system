# app/distance.py  — prefers VL53L1X, then VL53L0X, then VL6180X, else RAW6180X
import time, threading, statistics
from typing import Optional, Deque
from collections import deque

# --- Adafruit backends (preferred) ---
def _try_vl53l1x(log):
    try:
        import board, busio, adafruit_vl53l1x
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l1x.VL53L1X(i2c)
        # tune: long range, 50 ms budget; start continuous ranging
        try: sensor.distance_mode = 2  # 1=short, 2=long
        except Exception: pass
        try: sensor.timing_budget = 50
        except Exception: pass
        sensor.start_ranging()
        log("using Adafruit VL53L1X")
        return ("VL53L1X", sensor, None)
    except Exception as e:
        return (None, None, f"VL53L1X import/open failed: {e}")

def _try_vl53l0x(log):
    try:
        import board, busio, adafruit_vl53l0x
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l0x.VL53L0X(i2c)
        log("using Adafruit VL53L0X")
        return ("VL53L0X", sensor, None)
    except Exception as e:
        return (None, None, f"VL53L0X import/open failed: {e}")

def _try_vl6180x(log):
    try:
        import board, busio, adafruit_vl6180x
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl6180x.VL6180X(i2c)
        log("using Adafruit VL6180X")
        return ("VL6180X", sensor, None)
    except Exception as e:
        return (None, None, f"VL6180X import/open failed: {e}")

# --- RAW VL6180X fallback (last resort) ---
try:
    import smbus2
    from smbus2 import i2c_msg
except Exception:
    smbus2 = None
    i2c_msg = None

ID_MODEL           = 0x0000
SYSRANGE_START     = 0x0018
RESULT_INT_STATUS  = 0x004F
RESULT_RANGE_VAL   = 0x0062
SYSTEM_INT_CLEAR   = 0x0015

def _r8(bus, addr, reg16):
    wh = i2c_msg.write(addr, [(reg16>>8)&0xFF, reg16&0xFF])
    rh = i2c_msg.read(addr, 1)
    bus.i2c_rdwr(wh, rh)  # repeated-start
    return list(rh)[0]

def _w8(bus, addr, reg16, val):
    bus.i2c_rdwr(i2c_msg.write(addr, [(reg16>>8)&0xFF, reg16&0xFF, val&0xFF]))

def _single_shot_mm(bus, addr, timeout_ms=900)->Optional[int]:
    try:
        _w8(bus, addr, SYSRANGE_START, 0x01)
        t0=time.time()
        while True:
            st=_r8(bus, addr, RESULT_INT_STATUS)&0x07
            if st==0x04: break
            if (time.time()-t0)*1000>timeout_ms: return None
            time.sleep(0.003)
        mm=_r8(bus, addr, RESULT_RANGE_VAL)
        _w8(bus, addr, SYSTEM_INT_CLEAR, 0x07)
        return None if mm in (0,255) else int(mm)
    except Exception:
        return None

class DistanceReader:
    """Threaded distance reader with tiny 3-sample median smoothing and backend auto-select."""
    def __init__(self, cfg, logger=print):
        self.log=(lambda m: logger(f"[Distance] {m}")) if logger else (lambda *_: None)
        d=cfg.get("distance",{})
        try:  self.addr = int(str(d.get("addr","0x29")),16)
        except Exception: self.addr=0x29
        self.enabled=bool(d.get("enabled",True))
        self.backend=None; self._sensor=None; self.last_error=None
        self._mm=None
        self._history: Deque[int] = deque(maxlen=3)
        if not self.enabled:
            self.log("disabled"); return

        # Prefer VL53L1X → VL53L0X → VL6180X
        for chooser in (_try_vl53l1x, _try_vl53l0x, _try_vl6180x):
            b,s,err = chooser(self.log)
            if b:
                self.backend,self._sensor=b,s
                break
            elif err:
                self.log(err)

        # RAW fallback only helps VL6180X boards; harmless to keep as last resort
        if not self.backend and smbus2 and i2c_msg:
            try:
                with smbus2.SMBus(1) as bus:
                    _ = _r8(bus, self.addr, ID_MODEL)
                self.backend="RAW6180X"; self.log("using RAW VL6180X")
            except Exception as e:
                self.last_error=str(e); self.log(f"raw init failed: {e}")
        elif not self.backend:
            self.log("no backends available")

        if self.backend:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        last=None
        while True:
            try:
                val=None
                if self.backend=="VL53L1X":
                    # Adafruit VL53L1X returns distance in CENTIMETERS (int) or None
                    cm = getattr(self._sensor, "distance", None)
                    if cm is not None and cm>0:
                        val = int(cm)*10
                elif self.backend=="VL53L0X":
                    # Adafruit VL53L0X returns distance in MILLIMETERS (int)
                    r = int(self._sensor.range)
                    val = None if r in (0,8191,65535) else r
                elif self.backend=="VL6180X":
                    # returns cm; convert to mm
                    r = getattr(self._sensor, "range", None)
                    if r is not None and r>0:
                        val = int(r)*10
                elif self.backend=="RAW6180X":
                    # retry a few times to avoid stale read
                    with smbus2.SMBus(1) as bus:
                        for _ in range(5):
                            val=_single_shot_mm(bus, self.addr, 900)
                            if val is not None:
                                break
                            time.sleep(0.01)

                if val is not None:
                    self._history.append(val)
                    filt=int(statistics.median(self._history))
                    self._mm=filt
                    if last != filt:
                        last=filt
                        self.log(f"value {filt} mm ({filt/10:.1f} cm)")
                else:
                    self._mm=None
            except Exception as e:
                self.last_error=str(e)
            time.sleep(0.1)  # 10 Hz for L1X is fine

    def read_mm(self)->Optional[int]:
        return self._mm
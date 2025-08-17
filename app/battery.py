import smbus2
def _estimate_percent(v, vmin=3.0, vmax=4.2):
    if v is None: return None
    v = max(vmin, min(vmax, v))
    return int(round(((v - vmin) / (vmax - vmin)) * 100))
def _read_bus_voltage_mv(bus, addr):
    raw = bus.read_word_data(addr, 0x02)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)
    val = (raw >> 3) & 0x1FFF
    return val * 4
def read_ina219_voltage(addr=0x43):
    try:
        with smbus2.SMBus(1) as bus:
            mv = _read_bus_voltage_mv(bus, addr)
        return round(mv / 1000.0, 3)
    except Exception as e:
        print(f"[Battery] read fail @0x{addr:02X}:", e)
        return None
def autodetect_addr(preferred=None):
    c=[]
    if preferred is not None: c.append(preferred)
    c += [0x43,0x40,0x41,0x44,0x45,0x46,0x47]
    seen=set()
    for a in c:
        if a in seen: continue
        seen.add(a)
        try:
            v = read_ina219_voltage(a)
            if v is not None:
                return a
        except Exception:
            pass
    return preferred or 0x43
class BatteryReader:
    def __init__(self, cfg):
        u = cfg.get("ups", {})
        pref = u.get("ina219_addr","0x43")
        try: pref_int = int(str(pref),16)
        except Exception: pref_int = 0x43
        self.addr = autodetect_addr(pref_int)
        self.vmin = float(u.get("battery_min_v",3.0))
        self.vmax = float(u.get("battery_max_v",4.2))
        self.enabled = bool(u.get("enabled",True))
        print(f"[Battery] INA219 using 0x{self.addr:02X}")
    def read(self):
        if not self.enabled: return {"voltage": None, "percent": None}
        v = read_ina219_voltage(self.addr)
        return {"voltage": v, "percent": _estimate_percent(v, self.vmin, self.vmax) if v is not None else None}

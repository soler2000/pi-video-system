# Replace with your working VL53L1X reader; keep interface

def get_state():
    return {"mm": None, "cm": None, "m": None, "backend": "stub", "last_error": None}

def read_mm():
    return get_state().get("mm")

def read_cm():
    return get_state().get("cm")

def read_m():
    return get_state().get("m")

import time, subprocess
import psutil
from flask import Flask, render_template, request, jsonify

from .config import get_config
from .camera import CameraSupervisor
from .battery import BatteryReader
from .distance import DistanceReader
from .led import LedRing

app = Flask(__name__, static_folder="static", template_folder="templates")

cfg = get_config()
cam = CameraSupervisor()
bat = BatteryReader(cfg)
dist = DistanceReader(cfg)
led = LedRing(cfg); led.start()

@app.after_request
def _nocache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

_autostart_done=False
@app.before_request
def _auto_start_once():
    global _autostart_done
    if _autostart_done: return
    try: cam.start("reversing")
    except Exception as e: print("[AutoStart] failed:", e)
    _autostart_done=True

def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f: return round(int(f.read().strip())/1000.0,1)
    except Exception: return None

def wifi_dbm():
    try:
        out = subprocess.check_output("iw dev wlan0 link", shell=True, text=True)
        for line in out.splitlines():
            if "signal:" in line: return int(line.split()[1])
    except Exception: return None
    return None

def _distance_warn_hz():
    dcfg = cfg.get("distance",{})
    min_cm=float(dcfg.get("min_cm",10)); max_cm=float(dcfg.get("max_cm",150))
    fmin=float(dcfg.get("warn_freq_min_hz",1)); fmax=float(dcfg.get("warn_freq_max_hz",20))
    mm = dist.read_mm()
    if mm is None: return None
    cm = mm/10.0
    if cm <= min_cm: hz=fmax
    elif cm >= max_cm: hz=fmin
    else:
        ratio=(max_cm - cm)/max(1e-6,(max_cm-min_cm))
        hz = fmin + (fmax - fmin)*ratio
    return round(hz,2)

@app.route("/")
def root(): return render_template("dashboard.html")

@app.route("/reverse")
def reverse(): return render_template("reverse.html")

@app.route("/settings/led")
def settings_led(): return render_template("settings_led.html")

@app.route("/api/stats")
def stats():
    if getattr(led, "anim", "") == "distance_warn":
        hz = _distance_warn_hz()
        if hz: led.set_warn_hz(hz)
    b = bat.read()
    host = request.host.split(":")[0]
    hls_url = f"http://{host}:8888/reversing/index.m3u8"
    t0=time.perf_counter(); mm = dist.read_mm(); read_ms=int(round((time.perf_counter()-t0)*1000))
    stats.__dict__.setdefault("SEQ",0); stats.__dict__["SEQ"] += 1
    return jsonify({
        "seq": stats.__dict__["SEQ"],
        "cpu_temp": cpu_temp(),
        "cpu_load": psutil.cpu_percent(interval=0),
        "wifi_dbm": wifi_dbm(),
        "battery": b,
        "distance_mm": mm,
        "distance_cm": (None if mm is None else round(mm/10.0,1)),
        "read_ms": read_ms,
        "hls": hls_url,
        "show_latency": True,
        "ts": time.time()
    })

@app.route("/api/led/apply", methods=["POST"])
def led_apply():
    data = request.get_json(force=True, silent=True) or {}
    if "brightness" in data: led.set_brightness(float(data["brightness"]))
    if "speed" in data: led.set_speed(float(data["speed"]))
    if "anim" in data: led.anim = str(data["anim"])
    return {"ok": True, "anim": led.anim}

@app.route("/api/debug/distance")
def _dbg_dist():
    dr=DistanceReader(cfg); mm=dr.read_mm()
    return {"addr": ("0x%02X" % getattr(dr, "addr", 0x29)), "mm": mm, "cm": (None if mm is None else round(mm/10.0,1)), "backend": getattr(dr,"backend",None), "last_error": getattr(dr,"last_error",None)}

@app.route("/api/debug/battery")
def _dbg_batt():
    br=BatteryReader(cfg); r=br.read() or {}
    return {"addr": hex(getattr(br,"addr",0x43)), **r}

if __name__ == "__main__":
    try:
        from gevent.pywsgi import WSGIServer
        print("Serving with gevent on http://0.0.0.0:8080")
        WSGIServer(("0.0.0.0",8080), app).serve_forever()
    except Exception as e:
        print("[Startup] gevent failed, using Flask:", e)
        app.run(host="0.0.0.0", port=8080)

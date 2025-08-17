from __future__ import annotations
import os, time, subprocess
from flask import Flask, render_template, jsonify, request

try:
    from . import battery
except Exception:
    battery = None
try:
    from . import distance
except Exception:
    distance = None
try:
    from . import led
except Exception:
    led = None
try:
    from . import camera
except Exception:
    camera = None

app = Flask(__name__, template_folder="templates", static_folder="static")

def _cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip())/1000.0, 1)
    except Exception:
        return None

def _cpu_load():
    try:
        import psutil
        return psutil.cpu_percent(interval=0)
    except Exception:
        return None

def _wifi_dbm():
    try:
        out = subprocess.check_output(["/usr/sbin/iwconfig"], stderr=subprocess.STDOUT, text=True, timeout=1.5)
        for line in out.splitlines():
            if "Signal level=" in line:
                part = line.split("Signal level=")[1]
                return int(part.split()[0])
    except Exception:
        pass
    return None

@app.after_request
def _api_no_cache(resp):
    try:
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
    except Exception:
        pass
    return resp

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/reverse")
def reverse():
    return render_template("reverse.html")

@app.route("/settings/led")
def settings_led():
    return render_template("settings_led.html")

@app.route("/api/stats")
def api_stats():
    host = request.host.split(":")[0]
    data = {
        "ts": time.time(),
        "cpu_temp": _cpu_temp(),
        "cpu_load": _cpu_load(),
        "wifi_dbm": _wifi_dbm(),
        "battery": None,
        "distance_mm": None,
        "distance_cm": None,
        "distance_m": None,
        "hls": f"http://{host}:8888/reversing/index.m3u8",
        "show_latency": True,
    }

    # Battery
    if battery and hasattr(battery, "get_state"):
        try:
            b = battery.get_state()
            if isinstance(b, dict):
                data["battery"] = {"percent": b.get("percent"), "voltage": b.get("voltage")}
        except Exception as e:
            print("[Battery] error:", e)

    # Distance
    cm = None; mm = None; m = None
    try:
        if distance:
            if hasattr(distance, "get_state"):
                ds = distance.get_state() or {}
                mm = ds.get("mm"); cm = ds.get("cm"); m = ds.get("m")
            if mm is None and hasattr(distance, "read_mm"): mm = distance.read_mm()
            if cm is None and hasattr(distance, "read_cm"): cm = distance.read_cm()
            if m  is None and hasattr(distance, "read_m"):  m  = distance.read_m()
    except Exception as e:
        print("[Distance] error:", e)

    if isinstance(mm, (int, float)): data["distance_mm"] = int(mm)
    if isinstance(cm, (int, float)): data["distance_cm"] = float(cm)

    if isinstance(m, (int, float)):
        data["distance_m"] = round(float(m), 2)
    elif isinstance(m, str):
        data["distance_m"] = m
    else:
        if isinstance(cm, (int, float)):
            mv = cm / 100.0
            data["distance_m"] = mv if mv <= 4.0 else ">4.0"
        else:
            data["distance_m"] = None

    return jsonify(data)

@app.route("/api/debug/distance")
def api_debug_distance():
    res = {"backend": None, "mm": None, "cm": None, "m": None, "last_error": None}
    try:
        if distance and hasattr(distance, "get_state"):
            d = distance.get_state() or {}
            res.update({
                "mm": d.get("mm"),
                "cm": d.get("cm"),
                "m":  d.get("m"),
                "backend": d.get("backend"),
                "last_error": d.get("last_error"),
            })
        else:
            if distance and hasattr(distance, "read_mm"):
                res["mm"] = distance.read_mm()
            if distance and hasattr(distance, "read_cm"):
                res["cm"] = distance.read_cm()
            if distance and hasattr(distance, "read_m"):
                res["m"] = distance.read_m()
    except Exception as e:
        res["last_error"] = str(e)
    return jsonify(res)

@app.route("/api/led/state")
def api_led_state():
    try:
        if led and hasattr(led, "get_state"):
            return jsonify(led.get_state())
    except Exception as e:
        print("[LED] state error:", e)
        return jsonify({"error": str(e)}), 500
    return jsonify({})

@app.route("/api/led/apply", methods=["POST"])
def api_led_apply():
    try:
        body = request.get_json(force=True, silent=True) or {}
        if led and hasattr(led, "apply_state"):
            led.apply_state(body)
        return jsonify({"ok": True, "applied": body})
    except Exception as e:
        print("[LED] apply error:", e)
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/start_mode", methods=["POST"])
def api_start_mode():
    try:
        mode = (request.get_json(silent=True) or {}).get("mode", "reversing")
        if camera and hasattr(camera, "start_reversing") and hasattr(camera, "start_surveillance"):
            camera.start_reversing() if mode == "reversing" else camera.start_surveillance()
        return jsonify({"ok": True, "started": mode})
    except Exception as e:
        print("[Camera] start error:", e)
        return jsonify({"ok": False, "error": str(e)}), 500

def _run_flask():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    print(f"[Startup] Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)

def _run_gevent():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    try:
        from gevent.pywsgi import WSGIServer
        print(f"[Startup] gevent WSGI on {host}:{port}")
        WSGIServer((host, port), app).serve_forever()
    except Exception as e:
        print("[Startup] gevent unavailable, falling back to Flask:", e)
        _run_flask()

def main():
    if os.environ.get("USE_FLASK", "0") == "1":
        _run_flask()
    else:
        _run_gevent()

if __name__ == "__main__":
    main()

import yaml, os, threading
CFG_PATH = "/opt/pi-video-system/current/config/config.yaml"
_lock = threading.Lock()
_cache = None
def load_config():
    global _cache
    try:
        with open(CFG_PATH, "r") as f:
            _cache = yaml.safe_load(f) or {}
    except Exception:
        _cache = {}
    return _cache
def get_config():
    global _cache
    if _cache is None:
        load_config()
    return _cache
def save_config(cfg):
    global _cache
    with _lock:
        _cache = cfg
        os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
        with open(CFG_PATH, "w") as f:
            yaml.safe_dump(cfg, f)

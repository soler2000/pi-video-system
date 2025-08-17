import time, threading
try:
    import rpi_ws281x as neopixel
except Exception:
    neopixel = None
class LedRing:
    def __init__(self, cfg, logger=print):
        self.cfg = cfg.get("led", {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.count = int(self.cfg.get("count", 16))
        self.pin = int(self.cfg.get("gpio_pin", 12))
        self.brightness = float(self.cfg.get("brightness", 0.4))
        self.anim = self.cfg.get("anim","off")
        self._warn_hz = 1.0
        self._speed = 10.0
        self._stop = threading.Event()
        self._t = None
        self._pixels = None
        if neopixel and self.enabled:
            try:
                self._pixels = neopixel.Adafruit_NeoPixel(self.count, self.pin, 800000, 10, False, int(self.brightness*255), 0)
                self._pixels.begin()
            except Exception as e:
                print("[LED] WS281x init failed:", e)
    def start(self):
        if self._t: return
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
    def stop(self):
        self._stop.set(); self._t=None
    def set_warn_hz(self, hz: float):
        self._warn_hz = max(0.1, float(hz))
    def set_speed(self, factor: float):
        self._speed = max(0.1, float(factor))
    def set_brightness(self, b: float):
        self.brightness = max(0.0, min(1.0, float(b)))
        if self._pixels:
            self._pixels.setBrightness(int(self.brightness*255))
    def _fill(self, r,g,b):
        if not self._pixels: return
        for i in range(self.count):
            self._pixels.setPixelColorRGB(i, r,g,b)
        self._pixels.show()
    def _loop(self):
        on = False
        while not self._stop.is_set():
            if self.anim == "off":
                self._fill(0,0,0); time.sleep(0.2*self._speed)
            elif self.anim == "white_on":
                self._fill(255,255,255); time.sleep(0.2*self._speed)
            elif self.anim == "distance_warn":
                period = 1.0 / max(0.1, self._warn_hz)
                period *= self._speed
                on = not on
                if on: self._fill(255,255,255)
                else:  self._fill(255,0,0)
                time.sleep(period/2.0)
            else:
                time.sleep(0.2*self._speed)

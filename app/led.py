import time, threading, math

def _hex_to_rgb(h):
    h = (h or "#FFFFFF").lstrip("#")
    if len(h) == 3: h = "".join([c*2 for c in h])
    try: return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))
    except Exception: return (255,255,255)

def _wheel(pos):
    # 0..255 → RGB rainbow
    pos = int(pos) % 256
    if pos < 85:   return (pos*3, 255-pos*3, 0)
    if pos < 170:  pos -= 85; return (255-pos*3, 0, pos*3)
    pos -= 170;    return (0, pos*3, 255-pos*3)

try:
    import rpi_ws281x as neopixel
except Exception:
    neopixel = None

class LedRing:
    def __init__(self, cfg, logger=print):
        self.cfg = cfg.get("led", {})
        self.enabled   = bool(self.cfg.get("enabled", True))
        self.count     = int(self.cfg.get("count", 16))
        self.pin       = int(self.cfg.get("gpio_pin", 12))
        self.brightness= float(self.cfg.get("brightness", 0.4))
        self.anim      = str(self.cfg.get("anim","off"))
        self.color_hex = str(self.cfg.get("color", "#FFFFFF"))
        self.color     = _hex_to_rgb(self.color_hex)
        self._warn_hz  = 1.0
        self._speed    = float(self.cfg.get("speed", 10.0))  # default 10× slower
        self._stop     = threading.Event()
        self._t        = None
        self._pixels   = None
        self._phase    = 0.0   # for pulse/rainbow
        self._idx      = 0     # for chase

        if neopixel and self.enabled:
            try:
                self._pixels = neopixel.Adafruit_NeoPixel(
                    self.count, self.pin, 800000, 10, False,
                    int(self.brightness*255), 0
                )
                self._pixels.begin()
            except Exception as e:
                print("[LED] WS281x init failed:", e)

    # ------- public controls -------
    def start(self):
        if self._t: return
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set(); self._t=None

    def set_enabled(self, on: bool):
        self.enabled = bool(on)
        if not self.enabled: self._fill(0,0,0)

    def set_warn_hz(self, hz: float):
        self._warn_hz = max(0.1, float(hz))

    def set_speed(self, factor: float):
        self._speed = max(0.1, float(factor))

    def set_brightness(self, b: float):
        self.brightness = max(0.0, min(1.0, float(b)))
        if self._pixels:
            self._pixels.setBrightness(int(self.brightness*255))

    def set_color(self, hexstr: str):
        self.color_hex = str(hexstr or "#FFFFFF")
        self.color = _hex_to_rgb(self.color_hex)

    # ------- internal helpers -------
    def _fill(self, r,g,b):
        if not self._pixels: return
        for i in range(self.count):
            self._pixels.setPixelColorRGB(i, r,g,b)
        self._pixels.show()

    def _fill_idx(self, idx, r,g,b):
        if not self._pixels: return
        for i in range(self.count):
            self._pixels.setPixelColorRGB(i, 0,0,0)
        self._pixels.setPixelColorRGB(idx % self.count, r,g,b)
        self._pixels.show()

    # ------- animation loop -------
    def _loop(self):
        on = False
        while not self._stop.is_set():
            if not self.enabled or self.anim == "off":
                self._fill(0,0,0); time.sleep(0.2*self._speed); continue

            if self.anim == "white_on":
                r,g,b = self.color
                self._fill(r,g,b); time.sleep(0.2*self._speed)

            elif self.anim == "distance_warn":
                period = (1.0 / max(0.1, self._warn_hz)) * self._speed
                on = not on
                r,g,b = (self.color if on else (255,0,0))
                self._fill(*r if isinstance(r, tuple) else (r,g,b)) if isinstance(r, tuple) else self._fill(r,g,b)
                time.sleep(period/2.0)

            elif self.anim == "pulse":
                # Sinusoidal brightness 0..1 applied to chosen color
                self._phase = (self._phase + 0.08/self._speed) % (2*math.pi)
                amp = (math.sin(self._phase) + 1.0) / 2.0  # 0..1
                r,g,b = self.color
                self._fill(int(r*amp), int(g*amp), int(b*amp))
                time.sleep(0.02*self._speed)

            elif self.anim == "chase":
                self._idx = (self._idx + 1) % self.count
                r,g,b = self.color
                self._fill_idx(self._idx, r,g,b)
                time.sleep(0.04*self._speed)

            elif self.anim == "rainbow":
                # Global rainbow sweep across ring
                self._phase = (self._phase + 2/self._speed) % 256
                if self._pixels:
                    for i in range(self.count):
                        r,g,b = _wheel(int(self._phase + (i*256//self.count)))
                        self._pixels.setPixelColorRGB(i, r,g,b)
                    self._pixels.show()
                time.sleep(0.03*self._speed)

            else:
                time.sleep(0.1*self._speed)

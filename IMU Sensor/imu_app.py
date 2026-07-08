#!/usr/bin/env python3
"""
MPU-6050 IMU Monitor  —  a real-time Tkinter dashboard.

Reads accelerometer, gyroscope, and die-temperature from an MPU-6050 over I2C
and displays them live: an attitude indicator (artificial horizon) derived from
the accelerometer, bipolar gyro/accel bars, and a temperature gauge.

Runs LIVE on a Raspberry Pi with the sensor wired to I2C. If smbus or the sensor
is unavailable (e.g. running on a laptop), it automatically starts in SIMULATION
mode so the interface is fully usable for testing.

Keys:  F11 toggle fullscreen   ·   Q or Esc quit
"""

import math
import time
import random
import threading
import tkinter as tk
from tkinter import font as tkfont

# ----------------------------------------------------------------------------
# Palette  (shared with the web control pages: dark instrument + amber accent)
# ----------------------------------------------------------------------------
C = {
    "void":      "#090c12",
    "panel":     "#111623",
    "panel2":    "#151d2b",
    "inset":     "#0b0f17",
    "line":      "#202a39",
    "line2":     "#2b3748",
    "text":      "#e9eef5",
    "muted":     "#6a7580",
    "amber":     "#ffb020",
    "amber_hi":  "#ffd873",
    "amber_deep":"#a85e05",
    "sky":       "#1b2635",
    "ground":    "#0a0e15",
    "ladder":    "#7d8894",
    "warn":      "#ff6b5e",
}

DISP_FACES = ["Space Grotesk", "Inter", "Segoe UI", "DejaVu Sans", "Helvetica", "Arial"]
MONO_FACES = ["IBM Plex Mono", "JetBrains Mono", "DejaVu Sans Mono", "Consolas",
              "Menlo", "Courier New", "Courier"]

# Sensor scale factors (MPU-6050 defaults matching the original script)
ACCEL_SCALE = 16384.0      # LSB per g at +/-2g
GYRO_SCALE  = 131.0        # LSB per deg/s at +/-250 deg/s


# ----------------------------------------------------------------------------
# Sensor back-ends
# ----------------------------------------------------------------------------
class MPU6050:
    """Live reader over I2C via smbus. Raises on any bus/sensor problem."""
    PWR_MGMT_1 = 0x6B
    SMPLRT_DIV = 0x19
    CONFIG     = 0x1A
    GYRO_CONFIG = 0x1B
    INT_ENABLE = 0x38
    ACCEL_XOUT_H = 0x3B
    TEMP_OUT_H   = 0x41
    GYRO_XOUT_H  = 0x43
    WHO_AM_I     = 0x75

    def __init__(self, bus_num=1, address=0x68):
        import smbus  # imported here so the app still runs without it
        self.bus = smbus.SMBus(bus_num)
        self.addr = address
        # Presence check — raises OSError if nothing answers at the address.
        self.bus.read_byte_data(self.addr, self.WHO_AM_I)
        # Wake + configure (same register writes as the original script).
        self.bus.write_byte_data(self.addr, self.SMPLRT_DIV, 7)
        self.bus.write_byte_data(self.addr, self.PWR_MGMT_1, 1)
        self.bus.write_byte_data(self.addr, self.CONFIG, 0)
        self.bus.write_byte_data(self.addr, self.GYRO_CONFIG, 24)
        self.bus.write_byte_data(self.addr, self.INT_ENABLE, 1)

    def _word(self, reg):
        hi = self.bus.read_byte_data(self.addr, reg)
        lo = self.bus.read_byte_data(self.addr, reg + 1)
        val = (hi << 8) | lo
        if val >= 0x8000:              # two's-complement -> signed
            val -= 0x10000
        return val

    def read(self):
        ax = self._word(0x3B) / ACCEL_SCALE
        ay = self._word(0x3D) / ACCEL_SCALE
        az = self._word(0x3F) / ACCEL_SCALE
        temp = self._word(0x41) / 340.0 + 36.53
        gx = self._word(0x43) / GYRO_SCALE
        gy = self._word(0x45) / GYRO_SCALE
        gz = self._word(0x47) / GYRO_SCALE
        return dict(ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz, temp=temp)


class SimulatedIMU:
    """Plausible moving data so the UI works without hardware."""
    def __init__(self):
        self.t0 = time.time()

    def read(self):
        t = time.time() - self.t0
        roll  = math.radians(20 * math.sin(t * 0.45))
        pitch = math.radians(13 * math.sin(t * 0.31 + 1.1))
        j = lambda s: random.uniform(-s, s)
        # gravity projected into the sensor frame for this tilt
        ax = -math.sin(pitch) + j(0.008)
        ay =  math.sin(roll) * math.cos(pitch) + j(0.008)
        az =  math.cos(roll) * math.cos(pitch) + j(0.008)
        gx = 55 * math.cos(t * 0.45) + j(3)
        gy = 38 * math.cos(t * 0.31 + 1.1) + j(3)
        gz = 22 * math.sin(t * 0.8) + j(3)
        temp = 34.0 + 1.6 * math.sin(t * 0.05) + j(0.04)
        return dict(ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz, temp=temp)


def make_sensor():
    """Return (sensor, mode) — 'LIVE' if the real sensor answered, else 'SIM'."""
    try:
        return MPU6050(), "LIVE"
    except Exception as exc:
        print("[imu] live sensor unavailable (%s) -> simulation mode" % exc)
        return SimulatedIMU(), "SIM"


# ----------------------------------------------------------------------------
# Background reader thread — decouples I2C timing from the render loop.
# ----------------------------------------------------------------------------
class Reader(threading.Thread):
    def __init__(self, sensor, hz=80):
        super().__init__(daemon=True)
        self.sensor = sensor
        self.dt = 1.0 / hz
        self.lock = threading.Lock()
        self.latest = dict(ax=0, ay=0, az=1, gx=0, gy=0, gz=0, temp=0)
        self.running = True
        self.rate = 0.0
        self._n = 0
        self._t = time.time()

    def run(self):
        while self.running:
            try:
                d = self.sensor.read()
                now = time.time()
                with self.lock:
                    self.latest = d
                    self._n += 1
                    if now - self._t >= 0.5:
                        self.rate = self._n / (now - self._t)
                        self._n = 0
                        self._t = now
            except Exception as exc:
                print("[imu] read error:", exc)
            time.sleep(self.dt)

    def snapshot(self):
        with self.lock:
            return dict(self.latest), self.rate

    def stop(self):
        self.running = False


# ----------------------------------------------------------------------------
# Canvas helpers
# ----------------------------------------------------------------------------
def pick_font(root, faces, size, weight="normal"):
    have = {f.lower() for f in tkfont.families(root)}
    for fam in faces:
        if fam.lower() in have:
            return tkfont.Font(root=root, family=fam, size=size, weight=weight)
    return tkfont.Font(root=root, family="TkFixedFont", size=size, weight=weight)


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


# ----------------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------------
class Dashboard(tk.Tk):
    def __init__(self, reader, mode):
        super().__init__()
        self.reader = reader
        self.mode = mode
        self.title("MPU-6050 · IMU Monitor")
        self.configure(bg=C["void"])
        self.geometry("960x600")
        self.minsize(760, 480)

        self.cv = tk.Canvas(self, bg=C["void"], highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self.f_h1   = pick_font(self, DISP_FACES, 15, "bold")
        self.f_big  = pick_font(self, DISP_FACES, 30, "bold")
        self.f_num  = pick_font(self, MONO_FACES, 15, "bold")
        self.f_lbl  = pick_font(self, MONO_FACES, 11, "bold")
        self.f_small= pick_font(self, MONO_FACES, 10)
        self.f_tiny = pick_font(self, MONO_FACES, 9)

        # smoothed values for a stable display
        self.s = dict(ax=0.0, ay=0.0, az=1.0, gx=0.0, gy=0.0, gz=0.0, temp=0.0)
        self.pitch = 0.0
        self.roll = 0.0
        self.rate = 0.0
        self._fs = False

        self.bind("<Escape>", lambda e: self.close())
        self.bind("q", lambda e: self.close())
        self.bind("<F11>", self.toggle_fullscreen)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.after(30, self.tick)

    # ---- lifecycle ---------------------------------------------------------
    def toggle_fullscreen(self, _=None):
        self._fs = not self._fs
        self.attributes("-fullscreen", self._fs)

    def close(self):
        try:
            self.reader.stop()
        except Exception:
            pass
        self.destroy()

    def tick(self):
        d, rate = self.reader.snapshot()
        a = 0.22
        for k in self.s:
            self.s[k] += a * (d[k] - self.s[k])
        ax, ay, az = self.s["ax"], self.s["ay"], self.s["az"]
        self.roll = math.degrees(math.atan2(ay, az))
        self.pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
        self.rate = rate
        self.draw()
        self.after(45, self.tick)     # ~22 fps

    # ---- drawing -----------------------------------------------------------
    def draw(self):
        cv = self.cv
        cv.delete("all")
        W = cv.winfo_width() or 960
        H = cv.winfo_height() or 600
        pad = 16
        gap = 14

        cv.create_rectangle(0, 0, W, H, fill=C["void"], outline="")
        # ambient top glow
        cv.create_oval(W * 0.2, -H * 0.5, W * 0.8, H * 0.35,
                       fill="#111a28", outline="")

        head_h = 52
        foot_h = 74
        header = (pad, pad, W - pad, pad + head_h)
        body_y0 = pad + head_h + gap
        body_y1 = H - pad - foot_h - gap
        footer = (pad, H - pad - foot_h, W - pad, H - pad)

        left_w = (W - 2 * pad - gap) * 0.46
        left = (pad, body_y0, pad + left_w, body_y1)
        rx0 = pad + left_w + gap
        rh = (body_y1 - body_y0 - gap) / 2
        gyro_rect = (rx0, body_y0, W - pad, body_y0 + rh)
        accel_rect = (rx0, body_y0 + rh + gap, W - pad, body_y1)

        self.draw_header(*header)
        self.draw_attitude_panel(*left)
        self.draw_vector_panel(gyro_rect, "GYROSCOPE",  "\u00b0/s", 250.0,
                               [("X", self.s["gx"]), ("Y", self.s["gy"]), ("Z", self.s["gz"])],
                               "%+.1f")
        self.draw_vector_panel(accel_rect, "ACCELERATION", "g", 2.0,
                               [("X", self.s["ax"]), ("Y", self.s["ay"]), ("Z", self.s["az"])],
                               "%+.2f")
        self.draw_footer(*footer)

    def panel(self, x1, y1, x2, y2):
        round_rect(self.cv, x1, y1, x2, y2, 16, fill=C["panel"], outline=C["line"])

    def draw_header(self, x1, y1, x2, y2):
        cv = self.cv
        self.panel(x1, y1, x2, y2)
        cy = (y1 + y2) / 2
        # live dot + identity
        cv.create_oval(x1 + 20, cy - 4, x1 + 28, cy + 4,
                       fill=C["amber"], outline="")
        cv.create_text(x1 + 40, cy, anchor="w", text="MPU-6050",
                       fill=C["text"], font=self.f_h1)
        cv.create_text(x1 + 128, cy, anchor="w", text="6-AXIS IMU",
                       fill=C["muted"], font=self.f_small)
        cv.create_text((x1 + x2) / 2, cy, text="I\u00b2C  0x68",
                       fill=C["muted"], font=self.f_small)
        # right: rate + LIVE/SIM badge
        cv.create_text(x2 - 118, cy, anchor="e",
                       text="%0.0f Hz" % self.rate,
                       fill=C["muted"], font=self.f_small)
        bx2 = x2 - 20
        bx1 = bx2 - 84
        if self.mode == "LIVE":
            round_rect(cv, bx1, cy - 13, bx2, cy + 13, 13,
                       fill=C["amber"], outline="")
            cv.create_text((bx1 + bx2) / 2, cy, text="\u25cf LIVE",
                           fill="#20140a", font=self.f_lbl)
        else:
            round_rect(cv, bx1, cy - 13, bx2, cy + 13, 13,
                       fill=C["panel2"], outline=C["line2"])
            cv.create_text((bx1 + bx2) / 2, cy, text="\u25cf SIM",
                           fill=C["muted"], font=self.f_lbl)

    # ---- attitude indicator (signature element) ---------------------------
    def draw_attitude_panel(self, x1, y1, x2, y2):
        cv = self.cv
        self.panel(x1, y1, x2, y2)
        cv.create_text(x1 + 18, y1 + 18, anchor="w", text="ATTITUDE",
                       fill=C["muted"], font=self.f_lbl)

        cx = (x1 + x2) / 2
        # leave room under the dial for the pitch/roll readouts
        avail_h = (y2 - 44) - (y1 + 30)
        cyc = (y1 + 34) + avail_h / 2
        r = min((x2 - x1) * 0.5, avail_h * 0.5) * 0.86

        self._attitude(cx, cyc, r, self.pitch, self.roll)

        # pitch / roll numeric readouts
        by = y2 - 22
        cv.create_text(cx - r * 0.5, by, text="PITCH",
                       fill=C["muted"], font=self.f_tiny)
        cv.create_text(cx - r * 0.5, by + 16, text="%+.1f\u00b0" % self.pitch,
                       fill=C["text"], font=self.f_num)
        cv.create_text(cx + r * 0.5, by, text="ROLL",
                       fill=C["muted"], font=self.f_tiny)
        cv.create_text(cx + r * 0.5, by + 16, text="%+.1f\u00b0" % self.roll,
                       fill=C["text"], font=self.f_num)

    def _attitude(self, cx, cy, r, pitch, roll):
        cv = self.cv
        ppd = r / 55.0                     # pixels per degree of pitch
        rr = math.radians(-roll)
        ca, sa = math.cos(rr), math.sin(rr)

        def rot(px, py):
            dx, dy = px - cx, py - cy
            return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

        big = r * 2.4
        hy = cy + pitch * ppd              # horizon y (local, pre-rotation)

        def poly(pts):
            flat = []
            for px, py in pts:
                rx, ry = rot(px, py)
                flat += [rx, ry]
            return flat

        # sky + ground
        cv.create_polygon(poly([(cx - big, cy - big), (cx + big, cy - big),
                                (cx + big, hy), (cx - big, hy)]),
                          fill=C["sky"], outline="")
        cv.create_polygon(poly([(cx - big, hy), (cx + big, hy),
                                (cx + big, cy + big), (cx - big, cy + big)]),
                          fill=C["ground"], outline="")

        # pitch ladder
        for p in (-30, -20, -10, 10, 20, 30):
            ly = cy + (pitch - p) * ppd
            if abs(ly - cy) > r * 1.05:
                continue
            half = r * (0.34 if p % 20 else 0.46)
            x0, y0 = rot(cx - half, ly)
            x1b, y1b = rot(cx + half, ly)
            cv.create_line(x0, y0, x1b, y1b, fill=C["ladder"], width=1)
            lx, ly2 = rot(cx + half + 12, ly)
            cv.create_text(lx, ly2, text=str(abs(p)),
                           fill=C["ladder"], font=self.f_tiny)

        # horizon line
        hx0, hy0 = rot(cx - big, hy)
        hx1, hy1 = rot(cx + big, hy)
        cv.create_line(hx0, hy0, hx1, hy1, fill=C["amber"], width=2)

        # circular mask: thick ring in panel colour hides everything outside r
        ring_w = big
        cv.create_oval(cx - r - ring_w / 2, cy - r - ring_w / 2,
                       cx + r + ring_w / 2, cy + r + ring_w / 2,
                       outline=C["panel"], width=ring_w)
        # bezel
        cv.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=C["line2"], width=2)

        # roll scale (rotates under a fixed top index)
        for p in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            ang = math.radians(-90 + (p - roll))
            inner = r - (11 if p % 30 == 0 else 7)
            x0 = cx + inner * math.cos(ang); y0 = cy + inner * math.sin(ang)
            x1b = cx + r * math.cos(ang);    y1b = cy + r * math.sin(ang)
            col = C["amber_hi"] if p == 0 else C["ladder"]
            cv.create_line(x0, y0, x1b, y1b, fill=col,
                           width=2 if p % 30 == 0 else 1)
        # fixed top index triangle
        cv.create_polygon(cx, cy - r + 2, cx - 7, cy - r - 12, cx + 7, cy - r - 12,
                          fill=C["amber"], outline="")

        # fixed aircraft reticle
        w = r * 0.36
        cv.create_line(cx - w, cy, cx - w * 0.32, cy, fill=C["amber"], width=3)
        cv.create_line(cx + w * 0.32, cy, cx + w, cy, fill=C["amber"], width=3)
        cv.create_line(cx - w * 0.32, cy, cx, cy + 8, fill=C["amber"], width=3)
        cv.create_line(cx, cy + 8, cx + w * 0.32, cy, fill=C["amber"], width=3)
        cv.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                       fill=C["amber"], outline="")

    # ---- gyro / accel bar panels ------------------------------------------
    def draw_vector_panel(self, rect, title, unit, vmax, rows, fmt):
        cv = self.cv
        x1, y1, x2, y2 = rect
        self.panel(x1, y1, x2, y2)
        cv.create_text(x1 + 18, y1 + 18, anchor="w", text=title,
                       fill=C["muted"], font=self.f_lbl)
        cv.create_text(x2 - 18, y1 + 18, anchor="e", text=unit,
                       fill=C["muted"], font=self.f_small)

        top = y1 + 42
        bottom = y2 - 16
        n = len(rows)
        step = (bottom - top) / n
        for i, (label, value) in enumerate(rows):
            ry = top + step * (i + 0.5)
            self._bar(x1 + 18, x2 - 18, ry, label, value, vmax, fmt % value)

    def _bar(self, x0, x1, y, label, value, vmax, valstr):
        cv = self.cv
        lab_w = 16
        val_w = 66
        bx0 = x0 + lab_w + 6
        bx1 = x1 - val_w
        bw = bx1 - bx0
        cxb = (bx0 + bx1) / 2

        cv.create_text(x0, y, anchor="w", text=label,
                       fill=C["text"], font=self.f_lbl)
        # track
        round_rect(cv, bx0, y - 5, bx1, y + 5, 5,
                   fill=C["inset"], outline=C["line"])
        # centre tick
        cv.create_line(cxb, y - 8, cxb, y + 8, fill=C["line2"], width=1)
        # fill
        frac = max(-1.0, min(1.0, value / vmax))
        over = abs(value) > vmax
        if frac >= 0:
            fx0, fx1 = cxb, cxb + frac * (bw / 2)
        else:
            fx0, fx1 = cxb + frac * (bw / 2), cxb
        if fx1 - fx0 > 1.5:
            round_rect(cv, fx0, y - 4, fx1, y + 4, 4,
                       fill=C["warn"] if over else C["amber"], outline="")
        # value
        cv.create_text(x1, y, anchor="e", text=valstr,
                       fill=C["amber_hi"], font=self.f_num)

    # ---- footer: temperature + magnitude + hints --------------------------
    def draw_footer(self, x1, y1, x2, y2):
        cv = self.cv
        self.panel(x1, y1, x2, y2)
        cy = (y1 + y2) / 2

        # cell A: temperature gauge + reading
        ax = x1 + 20
        cv.create_text(ax, y1 + 16, anchor="w", text="DIE TEMPERATURE",
                       fill=C["muted"], font=self.f_tiny)
        t = self.s["temp"]
        gx0, gx1 = ax, ax + 190
        gy = cy + 12
        round_rect(cv, gx0, gy - 5, gx1, gy + 5, 5,
                   fill=C["inset"], outline=C["line"])
        lo, hi = 10.0, 60.0
        frac = max(0.0, min(1.0, (t - lo) / (hi - lo)))
        if frac > 0.01:
            round_rect(cv, gx0, gy - 4, gx0 + (gx1 - gx0) * frac, gy + 4, 4,
                       fill=C["amber"], outline="")
        cv.create_text(gx1 + 18, cy, anchor="w", text="%.1f" % t,
                       fill=C["text"], font=self.f_big)
        cv.create_text(gx1 + 18 + self.f_big.measure("%.1f" % t) + 6, cy + 6,
                       anchor="w", text="\u00b0C", fill=C["amber_hi"], font=self.f_num)

        # divider
        midx = x1 + (x2 - x1) * 0.62
        cv.create_line(midx, y1 + 14, midx, y2 - 14, fill=C["line"], width=1)

        # cell B: gravity magnitude
        gmag = math.sqrt(self.s["ax"] ** 2 + self.s["ay"] ** 2 + self.s["az"] ** 2)
        cv.create_text(midx + 24, y1 + 16, anchor="w", text="VECTOR MAGNITUDE",
                       fill=C["muted"], font=self.f_tiny)
        cv.create_text(midx + 24, cy + 4, anchor="w",
                       text="|g| %.2f" % gmag, fill=C["text"], font=self.f_num)
        gyro_mag = math.sqrt(self.s["gx"] ** 2 + self.s["gy"] ** 2 + self.s["gz"] ** 2)
        cv.create_text(midx + 150, cy + 4, anchor="w",
                       text="|\u03c9| %.0f\u00b0/s" % gyro_mag,
                       fill=C["muted"], font=self.f_num)

        # hints, bottom-right
        cv.create_text(x2 - 18, y2 - 12, anchor="e",
                       text="F11 FULLSCREEN   \u00b7   Q QUIT",
                       fill=C["muted"], font=self.f_tiny)


def main():
    sensor, mode = make_sensor()
    reader = Reader(sensor)
    reader.start()
    app = Dashboard(reader, mode)
    app.mainloop()


if __name__ == "__main__":
    main()

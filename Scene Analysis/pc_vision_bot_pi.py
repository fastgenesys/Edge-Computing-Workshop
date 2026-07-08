import os
import time
import threading

import cv2
import ollama
import pyttsx3
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk

# Picamera2 is only available on Raspberry Pi OS with the camera stack
# installed. Import it optionally so the app still runs on dev machines /
# with a plain USB webcam.
try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except Exception:
    Picamera2 = None
    PICAMERA_AVAILABLE = False

# Pillow resampling constant (works across Pillow versions)
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


# ============================================================================
# Raspberry Pi camera wrapper (Picamera2)
# ----------------------------------------------------------------------------
# Lifted from the working Pi capture code. cv2.VideoCapture(0) does NOT see the
# Pi 5 CSI camera (it goes through libcamera), so on the Pi we grab frames with
# Picamera2 instead. Frames are returned as BGR numpy arrays (OpenCV-style) so
# the rest of the pipeline — cv2.imwrite, cv2.cvtColor — works unchanged.
# ============================================================================
class PiCamera:
    # Preview-friendly resolution. Plenty for a live feed and for llava; keeps
    # the feed smooth on the Pi (max-res frames are heavy and lag the preview).
    TARGET = (1280, 720)

    def __init__(self):
        if not PICAMERA_AVAILABLE:
            raise RuntimeError(
                "picamera2 is not installed. "
                "Run: sudo apt install -y python3-picamera2")
        self._cam = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._cam = Picamera2()

        # Try an RGB888 preview at our target size, then fall back to the
        # library default if the camera rejects it.
        started = False
        builders = (
            lambda: self._cam.create_preview_configuration(
                main={"format": "RGB888", "size": self.TARGET}),
            lambda: self._cam.create_preview_configuration(),
        )
        for build in builders:
            try:
                self._cam.configure(build())
                self._cam.start()
                started = True
                break
            except Exception as e:
                print(f"[Camera] config attempt failed: {e}")
                try:
                    self._cam.stop()
                except Exception:
                    pass

        if not started:
            raise RuntimeError("Could not start the Pi camera.")

        time.sleep(0.5)  # let auto-exposure / auto-WB settle
        self._running = True

    def get_frame(self):
        """Return the latest frame as a BGR numpy array, or None."""
        if not self._running or self._cam is None:
            return None
        try:
            arr = self._cam.capture_array()
        except Exception as e:
            print(f"[Camera] capture_array failed: {e}")
            return None
        if arr is None:
            return None
        # picamera2 quirk: format="RGB888" is actually laid out as BGR
        # (matches OpenCV). If we got a 4-channel buffer, drop the alpha.
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        return arr

    def stop(self):
        if not self._running:
            return
        try:
            self._cam.stop()
        except Exception:
            pass
        try:
            self._cam.close()
        except Exception:
            pass
        self._cam = None
        self._running = False


# ----------------------------------------------------------------------------
# 1. Local Text-to-Speech Engine  (unchanged behaviour from the original)
# ----------------------------------------------------------------------------
engine = pyttsx3.init()
engine.setProperty('rate', 165)  # Set comfortable speaking speed

_speech_lock = threading.Lock()


def speak(text):
    print(f"\n[Bot]: {text}")
    with _speech_lock:
        engine.say(text)
        engine.runAndWait()


def speak_async(text):
    """Speak without blocking the UI thread."""
    threading.Thread(target=speak, args=(text,), daemon=True).start()


IMAGE_PATH = "pc_live_scene.jpg"

# ---- palette ----
BG      = "#0e1017"
PANEL   = "#141826"
CARD    = "#0c0f1a"
VIDEOBG = "#05070d"
BORDER  = "#222739"
ACCENT  = "#22d3ee"
TXT     = "#e6e8ee"
MUTED   = "#7c8497"
GREEN   = "#2dd4a7"
RED     = "#ff4d5e"
YELLOW  = "#f5b301"

VIDEO_W = 700
VIDEO_H = 520


class VisionBotApp:
    def __init__(self, root):
        self.root = root
        self.picam = None          # Picamera2 backend
        self.cap = None            # OpenCV backend
        self.backend = None        # "picamera2" | "opencv" | None
        self.latest_frame = None
        self.running = True
        self.analyzing = False
        self.pulse_on = False
        self.full_text = ""
        self.typed = 0

        self._fonts()
        self._build_ui()
        self._start_camera()

        self._update_video()   # display loop
        self._pulse()          # LIVE dot animation

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- fonts ------------------------------------------------------------
    def _fonts(self):
        self.f_title  = tkfont.Font(family="DejaVu Sans", size=18, weight="bold")
        self.f_sub    = tkfont.Font(family="DejaVu Sans", size=10)
        self.f_label  = tkfont.Font(family="DejaVu Sans", size=10, weight="bold")
        self.f_body   = tkfont.Font(family="DejaVu Sans", size=13)
        self.f_btn    = tkfont.Font(family="DejaVu Sans", size=13, weight="bold")
        self.f_badge  = tkfont.Font(family="DejaVu Sans", size=9,  weight="bold")

    # ---- layout -----------------------------------------------------------
    def _build_ui(self):
        self.root.title("Vision Bot — Live Scene Analyzer")
        self.root.configure(bg=BG)
        self.root.geometry("1120x680")
        self.root.minsize(960, 600)

        # header
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=22, pady=(18, 8))

        title = tk.Label(header, text="◉  VISION BOT", font=self.f_title,
                         fg="#ffffff", bg=BG)
        title.grid(row=0, column=0, sticky="w")
        sub = tk.Label(header,
                       text="Local live-camera analysis · powered by llava-phi3",
                       font=self.f_sub, fg=MUTED, bg=BG)
        sub.grid(row=1, column=0, sticky="w")

        # body
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(8, 22))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=360)
        body.rowconfigure(0, weight=1)

        # ---- left: video card ----
        video_card = tk.Frame(body, bg=VIDEOBG, highlightbackground=BORDER,
                              highlightthickness=1)
        video_card.grid(row=0, column=0, sticky="nsew", padx=(0, 18))

        self.video_container = tk.Frame(video_card, bg=VIDEOBG,
                                        width=VIDEO_W, height=VIDEO_H)
        self.video_container.pack(expand=True)
        self.video_container.pack_propagate(False)

        self.video_label = tk.Label(self.video_container, bg=VIDEOBG,
                                    fg="#4b5468", font=self.f_sub,
                                    text="Connecting to camera…")
        self.video_label.pack(expand=True, fill="both")

        # floating LIVE badge (placed over the video)
        self.live_badge = tk.Frame(self.video_container, bg="#0a0c12",
                                   highlightbackground="#2a2f42",
                                   highlightthickness=1)
        self.live_badge.place(x=16, y=16)
        self.live_canvas = tk.Canvas(self.live_badge, width=10, height=10,
                                     bg="#0a0c12", highlightthickness=0)
        self.live_canvas.pack(side="left", padx=(9, 5), pady=6)
        self.live_oval = self.live_canvas.create_oval(1, 1, 9, 9,
                                                      fill=RED, outline=RED)
        tk.Label(self.live_badge, text="LIVE", font=self.f_badge,
                 fg="#ffd7db", bg="#0a0c12").pack(side="left", padx=(0, 11))

        # floating ANALYZING pill (hidden until needed)
        self.analyzing_pill = tk.Label(self.video_container, text="ANALYZING",
                                       font=self.f_label, fg="#05070d",
                                       bg=ACCENT, padx=18, pady=8)

        # ---- right: analysis panel ----
        panel = tk.Frame(body, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        panel.grid(row=0, column=1, sticky="nsew")

        inner = tk.Frame(panel, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(inner, text="SCENE ANALYSIS", font=self.f_label,
                 fg=ACCENT, bg=PANEL).pack(anchor="w", pady=(0, 12))

        resp_wrap = tk.Frame(inner, bg=CARD, highlightbackground=BORDER,
                             highlightthickness=1)
        resp_wrap.pack(fill="both", expand=True)
        self.response = tk.Text(resp_wrap, wrap="word", font=self.f_body,
                                bg=CARD, fg="#d4d8e4", bd=0,
                                padx=14, pady=14, relief="flat",
                                insertbackground=ACCENT,
                                selectbackground="#8b5cf6",
                                highlightthickness=0)
        self.response.pack(fill="both", expand=True)
        self.response.insert("1.0",
            "Awaiting first capture.\n\nPress “Capture & Analyze” and the model "
            "will describe what the camera sees.")
        self.response.config(state="disabled")

        # status row
        status = tk.Frame(inner, bg=PANEL)
        status.pack(fill="x", pady=(12, 12))
        self.status_canvas = tk.Canvas(status, width=12, height=12, bg=PANEL,
                                       highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(0, 8))
        self.status_dot = self.status_canvas.create_oval(1, 1, 11, 11,
                                                         fill=YELLOW, outline=YELLOW)
        self.status_text = tk.Label(status, text="Starting up…", font=self.f_sub,
                                    fg=MUTED, bg=PANEL)
        self.status_text.pack(side="left")

        # analyze button
        self.analyze_btn = tk.Label(inner, text="⚡  Capture & Analyze",
                                    font=self.f_btn, fg="#05070d", bg=ACCENT,
                                    pady=14, cursor="hand2")
        self.analyze_btn.pack(fill="x")
        self.analyze_btn.bind("<Button-1>", lambda e: self._analyze())
        self.analyze_btn.bind("<Enter>", lambda e: self._btn_hover(True))
        self.analyze_btn.bind("<Leave>", lambda e: self._btn_hover(False))
        self._btn_enabled = False
        self._set_btn_enabled(False)

    # ---- button helpers ---------------------------------------------------
    def _btn_hover(self, over):
        if not self._btn_enabled:
            return
        self.analyze_btn.config(bg="#38dcf3" if over else ACCENT)

    def _set_btn_enabled(self, enabled):
        self._btn_enabled = enabled
        self.analyze_btn.config(bg=ACCENT if enabled else "#2a2f42",
                                fg="#05070d" if enabled else "#6b7286",
                                cursor="hand2" if enabled else "arrow")

    # ---- camera -----------------------------------------------------------
    def _start_camera(self):
        # Preferred path on the Raspberry Pi: Picamera2 (CSI camera / libcamera)
        if PICAMERA_AVAILABLE:
            try:
                self.picam = PiCamera()
                self.picam.start()
                self.backend = "picamera2"
                print("[Camera] using Picamera2 backend")
            except Exception as e:
                print(f"[Camera] Picamera2 unavailable: {e}")
                self.picam = None

        # Fallback: plain USB webcam via OpenCV (dev machines / USB cams)
        if self.backend is None:
            self.cap = cv2.VideoCapture(0)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            if self.cap.isOpened():
                self.backend = "opencv"
                print("[Camera] using OpenCV/USB backend")
            else:
                self.cap.release()
                self.cap = None

        if self.backend is None:
            self.video_label.config(
                text="⚠  Could not open any camera.\nCheck connections or permissions.")
            self._set_status("Camera unavailable", RED)
            speak_async("I cannot access the video device.")
            return

        self.grab_thread = threading.Thread(target=self._grab_loop, daemon=True)
        self.grab_thread.start()
        speak_async("System ready. Capturing live frame from webcam.")

    def _grab_loop(self):
        while self.running:
            frame = None
            if self.backend == "picamera2" and self.picam is not None:
                frame = self.picam.get_frame()
            elif self.backend == "opencv" and self.cap is not None:
                ret, f = self.cap.read()
                frame = f if ret else None
            if frame is not None:
                self.latest_frame = frame
            time.sleep(0.02)

    def _fit(self, img):
        w, h = img.size
        scale = min(VIDEO_W / w, VIDEO_H / h)
        return img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                          RESAMPLE)

    def _update_video(self):
        if self.latest_frame is not None:
            rgb = cv2.cvtColor(self.latest_frame, cv2.COLOR_BGR2RGB)
            img = self._fit(Image.fromarray(rgb))
            imgtk = ImageTk.PhotoImage(img)
            self.video_label.imgtk = imgtk          # keep a reference!
            self.video_label.config(image=imgtk, text="")

            if not self._btn_enabled and not self.analyzing:
                self._set_btn_enabled(True)
                self._set_status("Ready — press Analyze", GREEN)

        if self.running:
            self.root.after(40, self._update_video)

    # ---- analysis ---------------------------------------------------------
    def _analyze(self):
        if self.latest_frame is None or self.analyzing or not self._btn_enabled:
            return
        self.analyzing = True
        self._set_btn_enabled(False)
        self.analyze_btn.config(text="Analyzing")
        self._set_status("Analyzing…", ACCENT)
        self._set_response("")

        self.analyzing_pill.place(relx=0.5, rely=0.5, anchor="center")
        self._analyzing_anim(0)

        frame = self.latest_frame.copy()
        threading.Thread(target=self._analyze_worker, args=(frame,),
                         daemon=True).start()

    def _analyze_worker(self, frame):
        try:
            # Save the frame locally as a JPEG
            cv2.imwrite(IMAGE_PATH, frame)
            print(f"[System]: Image saved to {IMAGE_PATH}")

            self._ui(self._set_status, "Analyzing the environment frame now.", ACCENT)
            speak("Analyzing the environment frame now.")

            # Request analysis from local Vision Model
            response = ollama.chat(
                model='moondream',
                messages=[{
                    'role': 'user',
                    'content': 'Describe what you see in this environment in two or three concise sentences.',
                    'images': [IMAGE_PATH]
                }]
            )

            analysis_result = response['message']['content']
            self._ui(self._start_typewriter, analysis_result)
            speak(analysis_result)
            self._ui(self._analysis_done)

        except Exception as e:
            speak("An error occurred during execution.")
            self._ui(self._analysis_failed, str(e))

        finally:
            if os.path.exists(IMAGE_PATH):
                os.remove(IMAGE_PATH)

    def _analysis_done(self):
        self.analyzing = False
        self.analyzing_pill.place_forget()
        self.analyze_btn.config(text="⚡  Capture & Analyze")
        self._set_btn_enabled(True)
        self._set_status("Done — ready for next capture", GREEN)

    def _analysis_failed(self, detail):
        self.analyzing = False
        self.analyzing_pill.place_forget()
        self._set_response(f"⚠  An error occurred during execution.\n\n{detail}")
        self.analyze_btn.config(text="⚡  Capture & Analyze")
        self._set_btn_enabled(True)
        self._set_status("Error — see panel", RED)
        print(f"Details: {detail}")

    # ---- typewriter reveal ------------------------------------------------
    def _start_typewriter(self, text):
        self.full_text = text.strip()
        self.typed = 0
        self._set_response("")
        self._type_tick()

    def _type_tick(self):
        if self.typed >= len(self.full_text):
            return
        self.typed = min(self.typed + 2, len(self.full_text))
        self._set_response(self.full_text[:self.typed])
        self.response.see("end")
        if self.typed < len(self.full_text):
            self.root.after(12, self._type_tick)

    # ---- animations -------------------------------------------------------
    def _analyzing_anim(self, n):
        if not self.analyzing:
            return
        dots = "." * (n % 4)
        self.analyze_btn.config(text="Analyzing" + dots)
        self.analyzing_pill.config(text="ANALYZING" + dots)
        self.root.after(400, self._analyzing_anim, n + 1)

    def _pulse(self):
        self.pulse_on = not self.pulse_on
        color = RED if self.pulse_on else "#5a2730"
        self.live_canvas.itemconfig(self.live_oval, fill=color, outline=color)
        if self.running:
            self.root.after(600, self._pulse)

    # ---- small helpers ----------------------------------------------------
    def _ui(self, fn, *args):
        """Schedule a UI update from a worker thread (Tkinter is single-threaded)."""
        self.root.after(0, lambda: fn(*args))

    def _set_status(self, text, color):
        self.status_text.config(text=text)
        self.status_canvas.itemconfig(self.status_dot, fill=color, outline=color)

    def _set_response(self, text):
        self.response.config(state="normal")
        self.response.delete("1.0", "end")
        self.response.insert("1.0", text)
        self.response.config(state="disabled")

    # ---- shutdown ---------------------------------------------------------
    def _on_close(self):
        self.running = False
        time.sleep(0.05)
        if self.picam is not None:
            self.picam.stop()
        if self.cap is not None:
            self.cap.release()
        if os.path.exists(IMAGE_PATH):
            os.remove(IMAGE_PATH)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    VisionBotApp(root)
    root.mainloop()

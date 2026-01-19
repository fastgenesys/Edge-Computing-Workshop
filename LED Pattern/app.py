#!/usr/bin/env python3
import time
from threading import Thread, Event
from flask import Flask, render_template, redirect, url_for
from gpiozero import LED

app = Flask(__name__)

# GPIO pins (BCM numbering)
PINS = [17, 27, 22]
leds = [LED(p) for p in PINS]

stop_event = Event()
worker_thread = None

def all_off():
    for led in leds:
        led.off()

def pattern_loop():
    all_off()
    current = 0
    direction = 1  # 1 = forward, -1 = backward

    while not stop_event.is_set():
        all_off()
        leds[current].on()
        time.sleep(1.0)  # speed control

        if current == len(leds) - 1:
            direction = -1
        elif current == 0:
            direction = 1

        current += direction

    all_off()

def is_running():
    # If Stop was requested, show STOPPED immediately (even if thread is still exiting)
    if stop_event.is_set():
        return False
    return worker_thread is not None and worker_thread.is_alive()

@app.route("/")
def index():
    return render_template("index.html", running=is_running(), pins=PINS)

@app.route("/start")
def start():
    global worker_thread

    # Clear stop request and start a fresh thread if not running
    if not is_running():
        stop_event.clear()
        worker_thread = Thread(target=pattern_loop, daemon=True)
        worker_thread.start()

    return redirect(url_for("index"))

@app.route("/stop")
def stop():
    global worker_thread

    stop_event.set()
    all_off()

    # Optional: wait briefly so thread has time to exit cleanly (helps consistency)
    if worker_thread is not None:
        worker_thread.join(timeout=0.2)

    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

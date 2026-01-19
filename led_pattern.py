#!/usr/bin/env python3
import time, os, subprocess

LEDS = [17, 27, 22]
STOP_FILE = "/tmp/led_stop.flag"

def run(cmd):
    # capture output for debugging
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.stdout:
        print(p.stdout.strip())

def setup():
    for pin in LEDS:
        run(f"pinctrl set {pin} op")

def all_off():
    for pin in LEDS:
        run(f"pinctrl set {pin} dl")

def pulse(pin, delay=2):
    run(f"pinctrl set {pin} dh")
    time.sleep(delay)
    run(f"pinctrl set {pin} dl")

def should_stop():
    return os.path.exists(STOP_FILE)

def main():
    setup()
    all_off()

    while True:
        if should_stop(): break

        for pin in LEDS:
            if should_stop(): break
            pulse(pin, 2)

        if should_stop(): break

        for pin in reversed(LEDS):
            if should_stop(): break
            pulse(pin, 2)

    all_off()
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

if __name__ == "__main__":
    main()

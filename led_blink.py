import time
import subprocess

LED_PIN = 17

def run(cmd):
    subprocess.run(cmd, shell=True)

# Set GPIO 17 as OUTPUT
run(f"pinctrl set {LED_PIN} op")

print("Blinking LED on GPIO 17. Press Ctrl+C to stop.")

try:
    while True:
        run(f"pinctrl set {LED_PIN} dh")   # LED ON
        time.sleep(1)

        run(f"pinctrl set {LED_PIN} dl")   # LED OFF
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping... Turning LED OFF")
    run(f"pinctrl set {LED_PIN} dl")

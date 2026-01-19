from flask import Flask, render_template
from gpiozero import LED

app = Flask(__name__)

led = LED(17)  # GPIO17 = physical pin 11

@app.route("/")
def main():
    return render_template("main.html", state=led.is_lit, message="")

@app.route("/<action>")
def action(action):
    if action == "on":
        led.on()
        message = "LED turned ON"
    elif action == "off":
        led.off()
        message = "LED turned OFF"
    else:
        message = "Unknown action"

    return render_template("main.html", state=led.is_lit, message=message)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

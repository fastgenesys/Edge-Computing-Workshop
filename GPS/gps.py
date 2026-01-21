"""
This Raspberry Pi code was developed by newbiely.com
This Raspberry Pi code is made available for public use without any restriction
For comprehensive instructions and wiring diagrams, please visit:
https://newbiely.com/tutorials/raspberry-pi/raspberry-pi-gps
"""


import serial
import time
from datetime import datetime

GPS_BAUD = 9600

# Create serial object for GPS
GPS = serial.Serial('/dev/serial0', GPS_BAUD, timeout=1)

print("Raspberry Pi - GPS Module")

try:
    while True:
        if GPS.in_waiting > 0:
            gps_data = GPS.readline().decode('utf-8').strip()

            if gps_data.startswith('$GPGGA'):
                # Process GPS data using TinyGPS++
                # You may need to adapt this part based on the structure of your GPS data
                print(f"Received GPS data: {gps_data}")

                # Extract relevant information
                data_parts = gps_data.split(',')
                latitude = data_parts[2]
                longitude = data_parts[4]
                altitude = data_parts[9]

                # Print extracted information
                print(f"- Latitude: {latitude}")
                print(f"- Longitude: {longitude}")
                print(f"- Altitude: {altitude} meters")

                # You can add more processing as needed

        time.sleep(1)

except KeyboardInterrupt:
    print("\nExiting the script.")
    GPS.close()

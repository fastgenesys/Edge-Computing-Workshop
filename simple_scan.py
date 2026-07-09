from pyrplidar import PyRPlidar
import time

def simple_scan():
    lidar = PyRPlidar()
    
    # 1. Open the connection at the required 256000 baudrate for the A2
    lidar.connect(port="/dev/ttyUSB0", baudrate=256000, timeout=3)
                  
    # 2. Spin up the motor
    print("Starting motor...")
    lidar.set_motor_pwm(500)
    time.sleep(2)
    
    # 3. CRITICAL: Use start_scan() instead of force_scan() for A-series
    print("Sending scan request to A2 hardware...")
    scan_generator = lidar.start_scan()
    
    print("\nReading data from RPLIDAR A2... Press Ctrl+C to exit.\n")
    for count, scan in enumerate(scan_generator()):
        print(f"Scan {count}: {scan}")
        if count == 50: 
            break

    # 4. Clean shutdown
    print("\nShutting down LiDAR safely...")
    lidar.stop()
    lidar.set_motor_pwm(0)
    lidar.disconnect()

if __name__ == "__main__":
    simple_scan()

import math
import pygame
import time
from pyrplidar import PyRPlidar

# Screen setup
WIDTH, HEIGHT = 800, 800
CENTER = (WIDTH // 2, HEIGHT // 2)
MIN_DISTANCE = 50     # mm
MAX_DISTANCE = 3000   # mm
SCALE = (WIDTH // 2) / MAX_DISTANCE

# Colors
BLACK = (10, 15, 10)       # Dark sci-fi green-black
GREEN = (0, 255, 100)
YELLOW = (240, 240, 0)
RED = (255, 50, 50)
DARK_GREEN = (0, 50, 15)
SWEEP_GREEN = (0, 150, 60)
WHITE = (240, 240, 240)

def polar_to_cartesian(angle_deg, distance_mm):
    # Adjusting 0 degrees to point straight up (North) on your display
    angle_rad = math.radians(90 - angle_deg)
    r = distance_mm * SCALE
    x = CENTER[0] + int(r * math.cos(angle_rad))
    y = CENTER[1] - int(r * math.sin(angle_rad))
    return x, y

def radar_with_circles_and_colors():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Sparklers Ultra-Stable LiDAR Radar")
    clock = pygame.time.Clock()

    font_small = pygame.font.SysFont("monospace", 14)
    font_title = pygame.font.SysFont("sans-serif", 24, bold=True)

    # Initialize LiDAR connection
    lidar = PyRPlidar()
    lidar.connect(port="/dev/ttyUSB0", baudrate=256000, timeout=3)
    
    # HARD RESET STABILITY FORCE: Clear out stuck bytes from prior crashes
    print("Resetting hardware data lines to prevent sync mismatch...")
    try:
        lidar.stop()
        time.sleep(0.5)
    except:
        pass
    
    # Spin up the motor safely
    print("Starting motor spinning...")
    lidar.set_motor_pwm(500)
    time.sleep(2)  # Wait for motor to stabilize RPM
    
    # Secondary flush to dump any noise generated during power-up
    lidar.stop() 
    time.sleep(0.2)

    print("Requesting clean A2 scan stream...")
    scan_generator = lidar.start_scan()

    # Dictionary to hold the absolute latest points per degree angle
    stable_map = {} 
    prev_angle = 0
    running = True

    try:
        for scan in scan_generator():
            # Check if user clicked the "X" on the Pygame window
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    
            if not running:
                break

            # Populate the stable display dictionary
            if MIN_DISTANCE <= scan.distance <= MAX_DISTANCE:
                approx_angle = round(scan.angle)
                stable_map[approx_angle] = scan.distance
            elif scan.distance == 0:
                # Remove an element if the path becomes completely clear
                approx_angle = round(scan.angle)
                stable_map.pop(approx_angle, None)

            # Draw a fresh frame at the end of every complete 360 rotation loop
            if scan.angle < prev_angle:
                screen.fill(BLACK)

                # 1. Draw UI Grid Background (Crosshairs)
                pygame.draw.line(screen, DARK_GREEN, (0, CENTER[1]), (WIDTH, CENTER[1]), 1)
                pygame.draw.line(screen, DARK_GREEN, (CENTER[0], 0), (CENTER[0], HEIGHT), 1)
                
                # 2. Draw Range Ring Grids + Millimeter Text Labels
                for r in range(500, MAX_DISTANCE + 1, 500):
                    pygame.draw.circle(screen, DARK_GREEN, CENTER, int(r * SCALE), 1)
                    label = font_small.render(f"{r}mm", True, DARK_GREEN)  
                    screen.blit(label, (CENTER[0] + int(r * SCALE) + 5, CENTER[1] + 5))

                # 3. Draw the sweeping radar beam line
                sweep_x, sweep_y = polar_to_cartesian(scan.angle, MAX_DISTANCE)
                pygame.draw.line(screen, SWEEP_GREEN, CENTER, (sweep_x, sweep_y), 2)

                # 4. Render stable point map and extract the absolute closest obstacle
                if stable_map:
                    closest_angle = min(stable_map, key=stable_map.get)
                    closest_dist = stable_map[closest_angle]

                    for ang, dist in list(stable_map.items()):
                        px, py = polar_to_cartesian(ang, dist)
                        
                        # Distance based color assignment logic
                        if dist <= 800:
                            color = RED
                            size = 3
                        elif dist <= 1800:
                            color = YELLOW
                            size = 2
                        else:
                            color = GREEN
                            size = 2
                            
                        pygame.draw.circle(screen, color, (px, py), size)

                        # Lock visual highlight onto the absolute closest target in the room
                        if ang == closest_angle and dist == closest_dist:
                            pygame.draw.circle(screen, WHITE, (px, py), 6, 1)
                            tag = font_small.render(f" TARGET: {int(dist)}mm", True, WHITE)
                            screen.blit(tag, (px + 10, py - 10))

                # 5. Interface HUD Status Text Overlays
                title_surface = font_title.render("SPARKLERS STABLE LIDAR RADAR", True, GREEN)
                screen.blit(title_surface, (20, 20))
                status_text = font_small.render(f"Mapped Array Points: {len(stable_map)} | Active Bearing: {int(scan.angle)}°", True, WHITE)
                screen.blit(status_text, (20, 55))

                pygame.display.flip()
                clock.tick(60)

            prev_angle = scan.angle

    except KeyboardInterrupt:
        print("\nKeyboard Exit command intercepted.")
    finally:
        print("Safely powering down and disconnecting your LiDAR module...")
        try:
            lidar.stop()
            lidar.set_motor_pwm(0)
            lidar.disconnect()
        except Exception as e:
            print(f"Forced hardware cleanup needed: {e}")
        pygame.quit()
        print("Done. Clean exit completed.")

if __name__ == "__main__":
    radar_with_circles_and_colors()

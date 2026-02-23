"""
UE5 Command Bridge - Sends Python commands to UE5 via TCP.
Requires ue_listener.py to be running inside UE5.

Usage:
  python ue_bridge.py "unreal.log('hello')"
  python ue_bridge.py --file path/to/script.py
  python ue_bridge.py --screenshot                  # In-engine viewport capture
  python ue_bridge.py --survey                      # Multi-angle survey (8 cameras)
  python ue_bridge.py --cleanup [N]                 # Keep last N screenshots
"""
import sys
import os
import socket
import json
import time

PORT = 9876
EXTRAS_DIR = os.path.dirname(os.path.abspath(__file__))


def send_command(command, timeout=120):
    """Send a Python command to UE5 and return the result."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(('127.0.0.1', PORT))
        sock.sendall(command.encode('utf-8') + b'\n__END__\n')

        data = b''
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
        sock.close()

        if data:
            result = json.loads(data.decode('utf-8'))
            if result.get('output'):
                print(result['output'])
            if not result.get('success'):
                print(f"ERROR: {result.get('error', 'Unknown')}")
            return result
        else:
            print("No response from UE5")
            return None
    except ConnectionRefusedError:
        print("ERROR: Cannot connect to UE5. Run ue_listener.py first.")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def take_screenshot(viewport_only=False):
    """Capture the UE5 viewport using in-engine HighResShot."""
    from ue_capture import capture_ue5
    path = capture_ue5(viewport_only=viewport_only)
    return path


def screenshot_and_command(command, delay=1.0):
    """Execute a command in UE5, wait for render, then capture the result."""
    result = send_command(command)
    if delay > 0:
        time.sleep(delay)
    path = take_screenshot()
    return result, path


def survey(center_y=3000.0, radius=4000.0, ground_z=0.0):
    """
    Capture scene from 8 predefined camera angles for full coverage.

    Returns list of screenshot paths.
    """
    from ue_capture import capture_from_angles

    eye_z = ground_z + 180  # Player eye height
    high_z = ground_z + 3000  # Elevated view

    angles = [
        {"name": "overhead",
         "pos": (0, center_y, ground_z + 8000),
         "rot": (-90, 0, 0)},
        {"name": "entry_pov",
         "pos": (0, -500, eye_z),
         "rot": (-5, 90, 0)},
        {"name": "mid_pov",
         "pos": (0, center_y, eye_z),
         "rot": (-5, 90, 0)},
        {"name": "exit_back",
         "pos": (0, center_y + radius * 0.8, eye_z),
         "rot": (-5, -90, 0)},
        {"name": "elev_left",
         "pos": (-radius * 0.6, center_y, high_z),
         "rot": (-35, 45, 0)},
        {"name": "elev_right",
         "pos": (radius * 0.6, center_y, high_z),
         "rot": (-35, -45, 0)},
        {"name": "ground_close",
         "pos": (300, center_y * 0.5, ground_z + 50),
         "rot": (5, 90, 0)},
        {"name": "wide_establish",
         "pos": (-radius, center_y * 0.3, high_z * 1.5),
         "rot": (-25, 30, 0)},
    ]

    return capture_from_angles(angles, prefix="survey")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python ue_bridge.py \"python_code\"")
        print("       python ue_bridge.py --file path/to/script.py")
        print("       python ue_bridge.py --screenshot")
        print("       python ue_bridge.py --survey")
        print("       python ue_bridge.py --cleanup [N]")
        sys.exit(1)

    if sys.argv[1] == '--screenshot':
        take_screenshot()
    elif sys.argv[1] == '--survey':
        survey()
    elif sys.argv[1] == '--cleanup':
        from ue_capture import cleanup_screenshots
        keep = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cleanup_screenshots(keep)
    elif sys.argv[1] == '--file':
        filepath = sys.argv[2]
        with open(filepath, 'r') as f:
            command = f.read()
        send_command(command)
    else:
        command = ' '.join(sys.argv[1:])
        send_command(command)

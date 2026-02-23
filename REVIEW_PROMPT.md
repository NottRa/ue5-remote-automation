# Code Review Prompt — UE5 Remote Automation Tool

Copy everything below this line and paste it into Claude web.

---

I'm building a Python toolchain for remote-controlling Unreal Engine 5.7 from the command line. The goal is to enable AI-assisted level design: Claude Code sends Python commands to UE5 via TCP, executes them on the game thread, captures in-engine screenshots, and iterates on the scene.

I need you to do a thorough code review. Find every bug, security hole, race condition, architectural weakness, missing error handling, and design flaw. Be brutally honest. Tell me what's wrong, what's fragile, what won't scale, and what I'm missing.

## Architecture

```
Claude Code / CLI (outside UE5)
       │
       ▼
  ue_bridge.py      ──TCP port 9876──►  ue_listener.py (inside UE5)
       │                                       │
       ▼                                       ▼
  ue_capture.py     ◄── file on disk ◄── SceneCapture2D + ExportRenderTarget
```

- `ue_listener.py` runs inside UE5 (started via Tools > Execute Python Script). It opens a TCP server on a background thread, queues incoming commands, and executes them on the game thread via `register_slate_post_tick_callback`.
- `ue_bridge.py` runs outside UE5. It sends Python code strings over TCP and reads back JSON results.
- `ue_capture.py` runs outside UE5. It sends a SceneCapture2D script to UE5 via the bridge, which spawns a temporary capture actor, renders to a RenderTarget, exports to PNG, then the Python side polls for the file.

## The 3 Core Files

### ue_listener.py (runs INSIDE UE5)

```python
"""
UE5 Command Listener - Run ONCE via Tools > Execute Python Script.
After this, Claude can push commands directly to UE5.
Stays active for the entire editor session.
"""
import unreal
import socket
import json
import threading
import queue
import traceback

PORT = 9876
_cmd_queue = queue.Queue()

def _listener_thread():
    """Background thread: accepts TCP connections, queues commands."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('127.0.0.1', PORT))
    except OSError:
        unreal.log_warning(f"Port {PORT} already in use - listener may already be running")
        return
    server.listen(5)
    server.settimeout(2.0)

    while True:
        try:
            conn, addr = server.accept()
            data = b''
            conn.settimeout(120.0)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b'\n__END__\n'):
                    break
            command = data[:-9].decode('utf-8')
            event = threading.Event()
            result_holder = [None]
            _cmd_queue.put((command, conn, event, result_holder))
            event.wait(timeout=120)
        except socket.timeout:
            continue
        except Exception as e:
            pass

def _tick(delta_time):
    """Main thread tick: executes queued commands safely on game thread."""
    while not _cmd_queue.empty():
        try:
            command, conn, event, result_holder = _cmd_queue.get_nowait()
        except queue.Empty:
            break

        result = {"success": True, "output": "", "error": ""}

        # Capture output by monkey-patching unreal.log temporarily
        log_lines = []
        original_log = unreal.log
        original_warn = unreal.log_warning
        original_err = unreal.log_error

        def capture_log(msg):
            log_lines.append(str(msg))
            original_log(msg)
        def capture_warn(msg):
            log_lines.append(f"WARNING: {msg}")
            original_warn(msg)
        def capture_err(msg):
            log_lines.append(f"ERROR: {msg}")
            original_err(msg)

        unreal.log = capture_log
        unreal.log_warning = capture_warn
        unreal.log_error = capture_err

        try:
            exec_globals = {
                "unreal": unreal,
                "__builtins__": __builtins__,
                "__name__": "__remote__",
            }
            exec(command, exec_globals)
            result["success"] = True
        except Exception as e:
            result["success"] = False
            result["error"] = traceback.format_exc()
            log_lines.append(f"EXCEPTION: {traceback.format_exc()}")
        finally:
            unreal.log = original_log
            unreal.log_warning = original_warn
            unreal.log_error = original_err

        result["output"] = "\n".join(log_lines)

        try:
            response = json.dumps(result).encode('utf-8')
            conn.sendall(response)
            conn.close()
        except:
            pass

        event.set()

# Start listener thread
_thread = threading.Thread(target=_listener_thread, daemon=True)
_thread.start()

# Register tick callback for main-thread execution
_handle = unreal.register_slate_post_tick_callback(_tick)

unreal.log("")
unreal.log("=" * 50)
unreal.log("  COMMAND LISTENER ACTIVE (port 9876)")
unreal.log("  Claude can now push commands directly!")
unreal.log("=" * 50)
```

### ue_bridge.py (runs OUTSIDE UE5)

```python
"""
UE5 Command Bridge - Sends Python commands to UE5 via TCP.
Requires ue_listener.py to be running inside UE5.

Usage:
  python ue_bridge.py "unreal.log('hello')"
  python ue_bridge.py --file path/to/script.py
  python ue_bridge.py --screenshot
  python ue_bridge.py --survey
  python ue_bridge.py --cleanup [N]
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
    """Capture the UE5 viewport using in-engine SceneCapture2D."""
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
    """Capture scene from 8 predefined camera angles for full coverage."""
    from ue_capture import capture_from_angles

    eye_z = ground_z + 180
    high_z = ground_z + 3000

    angles = [
        {"name": "overhead",      "pos": (0, center_y, ground_z + 8000), "rot": (-90, 0, 0)},
        {"name": "entry_pov",     "pos": (0, -500, eye_z),              "rot": (-5, 90, 0)},
        {"name": "mid_pov",       "pos": (0, center_y, eye_z),          "rot": (-5, 90, 0)},
        {"name": "exit_back",     "pos": (0, center_y + radius*0.8, eye_z), "rot": (-5, -90, 0)},
        {"name": "elev_left",     "pos": (-radius*0.6, center_y, high_z), "rot": (-35, 45, 0)},
        {"name": "elev_right",    "pos": (radius*0.6, center_y, high_z),  "rot": (-35, -45, 0)},
        {"name": "ground_close",  "pos": (300, center_y*0.5, ground_z+50), "rot": (5, 90, 0)},
        {"name": "wide_establish","pos": (-radius, center_y*0.3, high_z*1.5), "rot": (-25, 30, 0)},
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
```

### ue_capture.py (runs OUTSIDE UE5, sends capture commands via bridge)

```python
"""
UE5 Viewport Capture - In-engine SceneCapture2D.

Captures the actual rendered viewport from inside UE5's render pipeline
using SceneCapture2D + RenderTarget + ExportRenderTarget. No Win32 hacks.

Requires ue_listener.py to be running inside UE5.
"""
import sys
import os
import time
import socket
import json
import glob as globmod

EXTRAS_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(EXTRAS_DIR, "Screenshots")
PORT = 9876

CAPTURE_WIDTH = 1920
CAPTURE_HEIGHT = 1080
CAPTURE_EXPOSURE_BIAS = 3.0


def _send_command(command, timeout=30):
    """Send a Python command to UE5 via TCP bridge and return the result."""
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
            return json.loads(data.decode('utf-8'))
        return None
    except ConnectionRefusedError:
        print("ERROR: Cannot connect to UE5. Is ue_listener.py running?")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def capture_ue5(viewport_only=False, camera_pos=None, camera_rot=None,
                width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT,
                exposure_bias=CAPTURE_EXPOSURE_BIAS, auto_delete=True):
    """
    Capture the UE5 viewport using in-engine SceneCapture2D.

    Spawns a temporary SceneCapture2D actor, renders to a RenderTarget,
    exports to PNG, then cleans up.
    """
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename_base = f"viewport_{timestamp}"
    output_path = os.path.join(SCREENSHOT_DIR, filename_base)
    final_path = output_path + ".png"

    if camera_pos and camera_rot:
        pos_str = f"unreal.Vector({camera_pos[0]}, {camera_pos[1]}, {camera_pos[2]})"
        rot_str = f"unreal.Rotator({camera_rot[0]}, {camera_rot[1]}, {camera_rot[2]})"
    else:
        pos_str = "cam_pos"
        rot_str = "cam_rot"

    capture_script = f"""
import unreal, os

EL = unreal.EditorLevelLibrary
KRL = unreal.RenderingLibrary

subsys = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
cam_result = subsys.get_level_viewport_camera_info()
cam_pos = cam_result[0]
cam_rot = cam_result[1]

rt = KRL.create_render_target2d(EL.get_editor_world(), {width}, {height})
rt.set_editor_property('render_target_format', unreal.TextureRenderTargetFormat.RTF_RGBA8)

cap = EL.spawn_actor_from_class(unreal.SceneCapture2D, {pos_str})
cap.set_actor_label('_CaptureCamera_')
cap.set_actor_rotation({rot_str}, False)

comp = cap.capture_component2d
comp.texture_target = rt
comp.capture_every_frame = False
comp.capture_on_movement = False
comp.capture_source = unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR

pp = comp.post_process_settings
pp.set_editor_property('override_auto_exposure_method', True)
pp.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_MANUAL)
pp.set_editor_property('override_auto_exposure_bias', True)
pp.set_editor_property('auto_exposure_bias', {exposure_bias})
comp.post_process_blend_weight = 1.0

comp.capture_scene()
KRL.export_render_target(EL.get_editor_world(), rt, r'{SCREENSHOT_DIR}', '{filename_base}')

src = r'{output_path}'
dst = r'{final_path}'
if os.path.exists(src) and not os.path.exists(dst):
    os.rename(src, dst)
elif os.path.exists(src):
    os.replace(src, dst)

EL.destroy_actor(cap)
unreal.log(f'Captured: {{dst}}')
"""

    result = _send_command(capture_script, timeout=30)
    if result is None:
        print("ERROR: Failed to send capture command to UE5")
        return None

    for _ in range(20):
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            break
        time.sleep(0.2)
    else:
        if os.path.exists(output_path):
            os.rename(output_path, final_path)
        else:
            print("ERROR: Capture file not found")
            return None

    if auto_delete:
        _cleanup_old(keep=3)

    print(final_path)
    return final_path


def capture_from_angles(angles, prefix="survey", auto_delete=True):
    """Capture the scene from multiple camera positions."""
    paths = []
    for i, angle in enumerate(angles):
        pos = tuple(angle['pos']) if 'pos' in angle else None
        rot = tuple(angle['rot']) if 'rot' in angle else None
        name = angle.get('name', f'{i:02d}')

        path = capture_ue5(camera_pos=pos, camera_rot=rot, auto_delete=False)
        if path:
            new_name = f"{prefix}_{name}_{time.strftime('%H%M%S')}.png"
            new_path = os.path.join(SCREENSHOT_DIR, new_name)
            os.rename(path, new_path)
            paths.append(new_path)
            print(f"  [{name}] {new_path}")
        else:
            print(f"  [{name}] FAILED")

    if auto_delete:
        _cleanup_old(keep=len(paths) + 2)

    return paths


def get_latest_screenshot():
    pattern = os.path.join(SCREENSHOT_DIR, "*.png")
    files = sorted(globmod.glob(pattern), key=os.path.getmtime)
    return files[-1] if files else None


def _cleanup_old(keep=3):
    pattern = os.path.join(SCREENSHOT_DIR, "*.png")
    files = sorted(globmod.glob(pattern), key=os.path.getmtime)
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        try:
            os.remove(f)
        except OSError:
            pass


def cleanup_screenshots(keep=5):
    _cleanup_old(keep=keep)
    remaining = len(globmod.glob(os.path.join(SCREENSHOT_DIR, "*.png")))
    print(f"Cleanup done, {remaining} screenshots remaining")
```

## Context

- This runs on Windows 10, UE5.7, Python 3.9+
- The TCP bridge is localhost-only (127.0.0.1)
- The tool is used by Claude Code (AI coding agent) to automate level design
- The primary workflow is: send command to place/modify actors → capture screenshot → AI analyzes screenshot → send next command
- We previously used Win32 PrintWindow which gave stale/black frames with DX12. We switched to SceneCapture2D inside UE5's render pipeline.
- There is no authentication on the TCP socket
- Commands are executed via `exec()` on the game thread

## What I Want You To Review

1. **Security**: The `exec()` usage, the open TCP port, any injection vectors
2. **Race conditions**: Thread safety between the listener thread and game thread tick, the monkey-patching of `unreal.log`
3. **Reliability**: What fails silently? What error paths are unhandled? What happens when UE5 is busy/frozen?
4. **Architecture**: Is this the right design? What would you change fundamentally?
5. **Capture system**: The SceneCapture2D approach — exposure issues, render target lifecycle, file I/O race conditions
6. **Missing features**: What's obviously missing for a production-quality tool?
7. **Code quality**: Duplicated code, naming, API design, anything sloppy

Don't hold back. I want the hard truth about where this breaks.

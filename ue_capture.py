"""
UE5 Viewport Capture - In-engine SceneCapture2D.

Captures the actual rendered viewport from inside UE5's render pipeline
using SceneCapture2D + RenderTarget + ExportRenderTarget. No Win32 hacks.

Requires ue_listener.py to be running inside UE5.

Usage:
  python ue_capture.py                       # Capture from editor camera
  python ue_capture.py --move X Y Z P Y R   # Move camera first, then capture
  python ue_capture.py --latest              # Print path of most recent screenshot
  python ue_capture.py --cleanup 10          # Keep only last N screenshots
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

# Default capture resolution
CAPTURE_WIDTH = 1920
CAPTURE_HEIGHT = 1080
# Exposure bias for SceneCapture2D (scene uses manual exposure)
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
                exposure_bias=CAPTURE_EXPOSURE_BIAS, auto_delete=True,
                fov_deg=None, lumen_override=False):
    """
    Capture the UE5 viewport using in-engine SceneCapture2D.

    Spawns a temporary SceneCapture2D actor, renders to a RenderTarget,
    exports to PNG, then cleans up. Captures the actual GPU-rendered frame.

    Args:
        viewport_only: Ignored (kept for API compat).
        camera_pos: (x, y, z) tuple. Defaults to current editor camera.
        camera_rot: (pitch, yaw, roll) tuple. Defaults to current editor camera.
        width: Render target width.
        height: Render target height.
        exposure_bias: Manual exposure bias for the capture.
        auto_delete: If True, only keep the latest screenshot (saves storage).
        fov_deg: Override field of view in degrees. None = default.
        lumen_override: If True, force Lumen GI+Reflections on capture component.

    Returns:
        Path to saved screenshot, or None on failure.
    """
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    # UE5 export_render_target doesn't add .png extension
    filename_base = f"viewport_{timestamp}"
    output_path = os.path.join(SCREENSHOT_DIR, filename_base)
    final_path = output_path + ".png"

    # Build the position/rotation part of the command
    if camera_pos and camera_rot:
        pos_str = f"unreal.Vector({camera_pos[0]}, {camera_pos[1]}, {camera_pos[2]})"
        rot_str = f"unreal.Rotator({camera_rot[0]}, {camera_rot[1]}, {camera_rot[2]})"
    else:
        # Use current editor viewport camera
        pos_str = "cam_pos"
        rot_str = "cam_rot"

    capture_script = f"""
import unreal, os

EL = unreal.EditorLevelLibrary
KRL = unreal.RenderingLibrary

# Get editor camera position if not overridden
subsys = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
cam_result = subsys.get_level_viewport_camera_info()
cam_pos = cam_result[0]
cam_rot = cam_result[1]

# Create render target (RGBA8 = PNG export)
rt = KRL.create_render_target2d(EL.get_editor_world(), {width}, {height})
rt.set_editor_property('render_target_format', unreal.TextureRenderTargetFormat.RTF_RGBA8)

# Spawn temporary capture camera
cap = EL.spawn_actor_from_class(unreal.SceneCapture2D, {pos_str})
cap.set_actor_label('_CaptureCamera_')
cap.set_actor_rotation({rot_str}, False)

comp = cap.capture_component2d
comp.texture_target = rt
comp.capture_every_frame = False
comp.capture_on_movement = False
comp.capture_source = unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR

# Override exposure for consistent capture brightness
pp = comp.post_process_settings
pp.set_editor_property('override_auto_exposure_method', True)
pp.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_MANUAL)
pp.set_editor_property('override_auto_exposure_bias', True)
pp.set_editor_property('auto_exposure_bias', {exposure_bias})
comp.post_process_blend_weight = 1.0
"""

    # Add Lumen override if requested
    if lumen_override:
        capture_script += """
# Force Lumen GI and Reflections on capture component
try:
    pp.set_editor_property('override_dynamic_global_illumination_method', True)
    pp.set_editor_property('dynamic_global_illumination_method', unreal.DynamicGlobalIlluminationMethod.LUMEN)
except:
    pass
try:
    pp.set_editor_property('override_reflection_method', True)
    pp.set_editor_property('reflection_method', unreal.ReflectionMethod.LUMEN)
except:
    pass
"""

    # Add FOV override if requested
    if fov_deg is not None:
        capture_script += f"""
comp.set_editor_property('fov_angle', {fov_deg})
"""

    capture_script += f"""

# Capture and export
comp.capture_scene()
KRL.export_render_target(EL.get_editor_world(), rt, r'{SCREENSHOT_DIR}', '{filename_base}')

# Rename to add .png extension
src = r'{output_path}'
dst = r'{final_path}'
if os.path.exists(src) and not os.path.exists(dst):
    os.rename(src, dst)
elif os.path.exists(src):
    os.replace(src, dst)

# Cleanup capture actor
EL.destroy_actor(cap)
unreal.log(f'Captured: {dst}')
"""

    result = _send_command(capture_script, timeout=30)
    if result is None:
        print("ERROR: Failed to send capture command to UE5")
        return None

    # Wait for file
    for _ in range(20):
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            break
        time.sleep(0.2)
    else:
        # Check if file exists without extension
        if os.path.exists(output_path):
            os.rename(output_path, final_path)
        else:
            print("ERROR: Capture file not found")
            return None

    # Auto-delete old screenshots to save storage
    if auto_delete:
        _cleanup_old(keep=3)

    print(final_path)
    return final_path


def capture_from_angles(angles, prefix="survey", auto_delete=True):
    """
    Capture the scene from multiple camera positions.

    Args:
        angles: List of dicts with 'pos' (x,y,z) and 'rot' (pitch,yaw,roll)
                and optionally 'name' for the capture label.
        prefix: Filename prefix for this survey batch.
        auto_delete: Clean up old files after capture.

    Returns:
        List of saved screenshot paths.
    """
    paths = []
    for i, angle in enumerate(angles):
        pos = tuple(angle['pos']) if 'pos' in angle else None
        rot = tuple(angle['rot']) if 'rot' in angle else None
        name = angle.get('name', f'{i:02d}')

        path = capture_ue5(camera_pos=pos, camera_rot=rot, auto_delete=False)
        if path:
            # Rename with survey prefix
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
    """Return path to the most recent screenshot."""
    pattern = os.path.join(SCREENSHOT_DIR, "*.png")
    files = sorted(globmod.glob(pattern), key=os.path.getmtime)
    if files:
        return files[-1]
    return None


def _cleanup_old(keep=3):
    """Delete old screenshots, keeping the most recent N."""
    pattern = os.path.join(SCREENSHOT_DIR, "*.png")
    files = sorted(globmod.glob(pattern), key=os.path.getmtime)
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        try:
            os.remove(f)
        except OSError:
            pass


def cleanup_screenshots(keep=5):
    """Public cleanup: delete old screenshots, keeping the most recent N."""
    _cleanup_old(keep=keep)
    remaining = len(globmod.glob(os.path.join(SCREENSHOT_DIR, "*.png")))
    print(f"Cleanup done, {remaining} screenshots remaining")


if __name__ == "__main__":
    if "--latest" in sys.argv:
        latest = get_latest_screenshot()
        if latest:
            print(latest)
        else:
            print("No screenshots found")
    elif "--cleanup" in sys.argv:
        idx = sys.argv.index("--cleanup")
        keep = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 5
        cleanup_screenshots(keep)
    elif "--move" in sys.argv:
        idx = sys.argv.index("--move")
        args = sys.argv[idx + 1:]
        if len(args) >= 6:
            pos = (float(args[0]), float(args[1]), float(args[2]))
            rot = (float(args[3]), float(args[4]), float(args[5]))
            capture_ue5(camera_pos=pos, camera_rot=rot)
        elif len(args) >= 3:
            pos = (float(args[0]), float(args[1]), float(args[2]))
            capture_ue5(camera_pos=pos)
        else:
            print("Usage: --move X Y Z [Pitch Yaw Roll]")
    else:
        capture_ue5()

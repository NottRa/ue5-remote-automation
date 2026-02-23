"""DXCam-based capture fallback. Zero VRAM cost.
Uses DXGI Desktop Duplication to grab the screen.
Optional dependency: pip install dxcam Pillow

This is the fallback when SceneCapture2D VRAM overhead is too high.
UE5 must be visible on-screen in borderless windowed mode."""

import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CAPTURE_WIDTH, CAPTURE_HEIGHT, JPEG_QUALITY

_camera = None


def is_available():
    """Check if dxcam is installed and functional."""
    try:
        import dxcam
        return True
    except ImportError:
        return False


def _get_camera():
    """Lazy-init the DXCam camera."""
    global _camera
    if _camera is None:
        import dxcam
        _camera = dxcam.create(output_color="BGR")
    return _camera


def capture_viewport(width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT,
                     quality=JPEG_QUALITY, region=None):
    """Capture the screen via DXGI Desktop Duplication.
    Returns base64 JPEG string or None.

    Args:
        width: Target output width (resizes if needed).
        height: Target output height (resizes if needed).
        quality: JPEG quality (1-100).
        region: (left, top, right, bottom) tuple to crop. None = full screen.
    """
    if not is_available():
        return None

    try:
        from PIL import Image
        camera = _get_camera()
        frame = camera.grab(region=region)
        if frame is None:
            return None

        # Convert BGR to RGB
        img = Image.fromarray(frame[:, :, ::-1])

        # Resize if needed
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        return base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        return None


def find_ue5_window_region():
    """Try to find the UE5 editor viewport region on screen.
    Returns (left, top, right, bottom) or None.
    Requires pywin32."""
    try:
        import win32gui

        def callback(hwnd, results):
            title = win32gui.GetWindowText(hwnd)
            if "Unreal Editor" in title and win32gui.IsWindowVisible(hwnd):
                rect = win32gui.GetWindowRect(hwnd)
                results.append(rect)

        results = []
        win32gui.EnumWindows(callback, results)
        if results:
            return results[0]  # (left, top, right, bottom)
        return None
    except ImportError:
        return None

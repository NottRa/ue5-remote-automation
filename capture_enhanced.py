"""Enhanced capture pipeline for the autonomous agent.
Provides JPEG/base64 in-memory capture (no permanent disk writes),
survey captures, and verification shots.
Runs OUTSIDE UE5."""

import base64
import io
import math
import os
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CAPTURE_WIDTH, CAPTURE_HEIGHT, CAPTURE_EXPOSURE_BIAS, JPEG_QUALITY,
    CAPTURE_TEMP_PREFIX, SCREENSHOTS_DIR, VERIFY_CLOSEUP_RADIUS_MULT,
    VERIFY_CONTEXT_RADIUS_MULT, VERIFY_CLOSEUP_ELEV_DEG, VERIFY_CONTEXT_ELEV_DEG,
    VERIFY_CLOSEUP_FOV_DEG, VERIFY_CONTEXT_FOV_DEG, ensure_dirs,
)
from ue_capture import capture_ue5

try:
    from PIL import Image
except ImportError:
    Image = None


def _png_to_jpeg_b64(png_path, quality=JPEG_QUALITY):
    """Read a PNG file, convert to JPEG bytes, return base64 string.
    Deletes the temp PNG after conversion."""
    if Image is None:
        # Fallback: return PNG as base64 if Pillow not available
        with open(png_path, 'rb') as f:
            data = f.read()
        try:
            os.remove(png_path)
        except OSError:
            pass
        return base64.b64encode(data).decode('ascii')

    try:
        img = Image.open(png_path)
        img = img.convert('RGB')  # JPEG doesn't support alpha
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    finally:
        try:
            os.remove(png_path)
        except OSError:
            pass
    return b64


def _media_type():
    """Return the MIME type for the capture format."""
    if Image is not None:
        return "image/jpeg"
    return "image/png"


def capture_to_base64(camera_pos=None, camera_rot=None,
                      width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT,
                      quality=JPEG_QUALITY, exposure_bias=CAPTURE_EXPOSURE_BIAS,
                      fov_deg=None, lumen_override=True):
    """Capture scene and return as base64-encoded JPEG string.
    UE5 exports temp PNG → host converts to JPEG → base64 → deletes temp.
    Returns: base64 string, or None on failure."""
    ensure_dirs()

    png_path = capture_ue5(
        camera_pos=camera_pos,
        camera_rot=camera_rot,
        width=width,
        height=height,
        exposure_bias=exposure_bias,
        auto_delete=False,
        fov_deg=fov_deg,
        lumen_override=lumen_override,
    )
    if png_path is None or not os.path.exists(png_path):
        return None

    return _png_to_jpeg_b64(png_path, quality=quality)


def capture_to_disk(camera_pos=None, camera_rot=None,
                    width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT,
                    exposure_bias=CAPTURE_EXPOSURE_BIAS,
                    fov_deg=None, lumen_override=True,
                    filename_prefix="agent"):
    """Capture scene and save to disk as PNG. For archival/debug.
    Returns: file path or None."""
    ensure_dirs()

    png_path = capture_ue5(
        camera_pos=camera_pos,
        camera_rot=camera_rot,
        width=width,
        height=height,
        exposure_bias=exposure_bias,
        auto_delete=False,
        fov_deg=fov_deg,
        lumen_override=lumen_override,
    )
    if png_path is None:
        return None

    # Rename to agent screenshots dir with prefix
    ts = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(SCREENSHOTS_DIR, f"{filename_prefix}_{ts}.png")
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    try:
        os.replace(png_path, dest)
    except OSError:
        return png_path
    return dest


# ---------------------------------------------------------------------------
# Survey Captures
# ---------------------------------------------------------------------------

def _camera_orbit_pos(center, radius, azimuth_deg, elevation_deg):
    """Calculate camera position on a sphere around center."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    dx = radius * math.cos(el) * math.cos(az)
    dy = radius * math.cos(el) * math.sin(az)
    dz = radius * math.sin(el)
    return (center[0] + dx, center[1] + dy, center[2] + dz)


def _look_at_rotation(camera_pos, target):
    """Calculate pitch/yaw for camera to look at target.
    Returns (pitch, yaw, roll=0)."""
    dx = target[0] - camera_pos[0]
    dy = target[1] - camera_pos[1]
    dz = target[2] - camera_pos[2]
    dist_xy = math.sqrt(dx * dx + dy * dy)
    pitch = math.degrees(math.atan2(dz, dist_xy))  # negative = looking down
    yaw = math.degrees(math.atan2(dy, dx))
    return (pitch, yaw, 0)


def survey_scene(center=(0, 3000, 0), radius=4000.0):
    """5-angle survey: 4 cardinal directions at 30deg elevation + 1 overhead.
    Returns list of dicts: [{"name": str, "b64": str, "media_type": str}]."""
    results = []
    cz = center[2] if len(center) > 2 else 0

    angles = [
        {"name": "north", "azimuth": 90, "elevation": 30},
        {"name": "east", "azimuth": 0, "elevation": 30},
        {"name": "south", "azimuth": -90, "elevation": 30},
        {"name": "west", "azimuth": 180, "elevation": 30},
        {"name": "overhead", "azimuth": 0, "elevation": 80},
    ]

    for angle in angles:
        pos = _camera_orbit_pos(center, radius, angle["azimuth"], angle["elevation"])
        rot = _look_at_rotation(pos, center)

        b64 = capture_to_base64(camera_pos=pos, camera_rot=rot)
        if b64:
            results.append({
                "name": angle["name"],
                "b64": b64,
                "media_type": _media_type(),
            })

    return results


# ---------------------------------------------------------------------------
# Verification Captures
# ---------------------------------------------------------------------------

def capture_closeup(actor_center, bounding_sphere_radius, azimuth_deg=135.0):
    """Close-up verification shot at 2.5x bounding sphere radius,
    45deg elevation, ~50mm focal length.
    Returns: {"b64": str, "media_type": str} or None."""
    dist = max(bounding_sphere_radius * VERIFY_CLOSEUP_RADIUS_MULT, 200.0)
    pos = _camera_orbit_pos(actor_center, dist, azimuth_deg, VERIFY_CLOSEUP_ELEV_DEG)
    rot = _look_at_rotation(pos, actor_center)

    b64 = capture_to_base64(
        camera_pos=pos, camera_rot=rot,
        fov_deg=VERIFY_CLOSEUP_FOV_DEG,
    )
    if b64:
        return {"b64": b64, "media_type": _media_type()}
    return None


def capture_context(actor_center, bounding_sphere_radius, azimuth_deg=315.0):
    """Context verification shot at 6x bounding sphere radius,
    55deg elevation, ~35mm wide angle.
    Returns: {"b64": str, "media_type": str} or None."""
    dist = max(bounding_sphere_radius * VERIFY_CONTEXT_RADIUS_MULT, 500.0)
    pos = _camera_orbit_pos(actor_center, dist, azimuth_deg, VERIFY_CONTEXT_ELEV_DEG)
    rot = _look_at_rotation(pos, actor_center)

    b64 = capture_to_base64(
        camera_pos=pos, camera_rot=rot,
        fov_deg=VERIFY_CONTEXT_FOV_DEG,
    )
    if b64:
        return {"b64": b64, "media_type": _media_type()}
    return None


def capture_verification_pair(actor_center, bounding_sphere_radius, azimuth_deg=135.0):
    """Capture both close-up and context shots for verification.
    Returns: (closeup_dict, context_dict) — either can be None."""
    closeup = capture_closeup(actor_center, bounding_sphere_radius, azimuth_deg)
    context = capture_context(actor_center, bounding_sphere_radius, azimuth_deg + 180)
    return closeup, context


# ---------------------------------------------------------------------------
# VRAM Monitoring
# ---------------------------------------------------------------------------

def check_vram_pressure():
    """Check VRAM usage level.
    Returns: {"used_mb": float, "budget_mb": float, "pressure": str}."""
    try:
        from ue_commands import get_vram_usage
        result = get_vram_usage()
        used = result.get('used_mb', -1)
        budget = result.get('budget_mb', 8192)
        if used < 0:
            return {"used_mb": -1, "budget_mb": budget, "pressure": "unknown"}
        pct = used / budget
        if pct > 0.95:
            pressure = "critical"
        elif pct > 0.90:
            pressure = "high"
        elif pct > 0.80:
            pressure = "medium"
        else:
            pressure = "low"
        return {"used_mb": used, "budget_mb": budget, "pressure": pressure}
    except Exception:
        return {"used_mb": -1, "budget_mb": 8192, "pressure": "unknown"}

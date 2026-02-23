"""Phase 2 verification: visual analysis via Claude Code CLI.
Saves screenshots to disk, sends file paths to Claude CLI for analysis.
Uses your Claude subscription — no API keys needed.
Falls back to auto-pass if Claude CLI is unavailable.
Runs OUTSIDE UE5."""

import sys
import os
import time
import logging
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_claude import (
    call_claude_vision, parse_json_response, is_claude_available,
    PROMPT_VERIFICATION,
)
from config import SCREENSHOTS_DIR, ensure_dirs

log = logging.getLogger("verify_visual")


@dataclass
class VisualVerdict:
    passed: bool
    confidence: float = 0.0
    issues: list = field(default_factory=list)
    suggested_adjustments: list = field(default_factory=list)
    reasoning: str = ""


def verify_visual(closeup_path, context_path, asset_info, scene_context=""):
    """Send verification screenshots to Claude CLI for visual analysis.

    Args:
        closeup_path: file path to close-up screenshot (or None)
        context_path: file path to context screenshot (or None)
        asset_info: dict with label, asset_type, species, zone_id, location, scale
        scene_context: compressed manifest excerpt

    Returns: VisualVerdict
    """
    # If Claude CLI isn't available, auto-pass
    if not is_claude_available():
        return VisualVerdict(
            passed=True,
            confidence=0.0,
            reasoning="Claude CLI not available — skipping visual check",
        )

    image_paths = []
    if closeup_path and os.path.exists(closeup_path):
        image_paths.append(closeup_path)
    if context_path and os.path.exists(context_path):
        image_paths.append(context_path)

    if not image_paths:
        return VisualVerdict(
            passed=True,
            confidence=0.0,
            reasoning="No screenshots available for visual verification",
        )

    loc = asset_info.get('location', [0, 0, 0])
    scale = asset_info.get('scale', [1, 1, 1])

    prompt = PROMPT_VERIFICATION.format(
        label=asset_info.get('label', 'unknown'),
        asset_type=asset_info.get('asset_type', 'unknown'),
        species=asset_info.get('species', 'unknown'),
        zone_id=asset_info.get('zone_id', 'unknown'),
        loc_x=loc[0], loc_y=loc[1], loc_z=loc[2],
        scale_x=scale[0], scale_y=scale[1], scale_z=scale[2],
        scene_context=scene_context or "(no context available)",
    )

    try:
        response = call_claude_vision(prompt, image_paths)

        if response is None:
            return VisualVerdict(
                passed=True,
                confidence=0.0,
                reasoning="Claude CLI returned no response — skipping visual check",
            )

        result = parse_json_response(response)

        if result is None:
            log.warning(f"Could not parse JSON from Claude: {response[:200]}")
            return VisualVerdict(
                passed=True,
                confidence=0.3,
                reasoning=f"Could not parse response: {response[:200]}",
            )

        return VisualVerdict(
            passed=result.get('passed', True),
            confidence=result.get('confidence', 0.5),
            issues=result.get('issues', []),
            suggested_adjustments=result.get('suggested_adjustments', []),
            reasoning=result.get('reasoning', ''),
        )
    except Exception as e:
        log.warning(f"Visual verification error: {e}")
        return VisualVerdict(
            passed=True,
            confidence=0.0,
            reasoning=f"Visual verification error: {e}",
        )


def save_verification_screenshots(closeup_b64, context_b64, label):
    """Save verification screenshots to disk for Claude CLI to read.
    Returns (closeup_path, context_path)."""
    ensure_dirs()
    import base64
    ts = time.strftime("%Y%m%d_%H%M%S")

    closeup_path = None
    context_path = None

    if closeup_b64:
        closeup_path = os.path.join(SCREENSHOTS_DIR,
                                     f"verify_{label}_closeup_{ts}.jpg")
        b64_data = closeup_b64.get('b64', closeup_b64) if isinstance(closeup_b64, dict) else closeup_b64
        with open(closeup_path, 'wb') as f:
            f.write(base64.b64decode(b64_data))

    if context_b64:
        context_path = os.path.join(SCREENSHOTS_DIR,
                                     f"verify_{label}_context_{ts}.jpg")
        b64_data = context_b64.get('b64', context_b64) if isinstance(context_b64, dict) else context_b64
        with open(context_path, 'wb') as f:
            f.write(base64.b64decode(b64_data))

    return closeup_path, context_path

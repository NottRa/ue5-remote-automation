"""Claude integration via Claude Code CLI (uses your existing subscription).
No API keys needed — calls 'claude -p' as a subprocess.
Falls back to local-only mode if Claude CLI is not available.
Runs OUTSIDE UE5."""

import json
import os
import re
import subprocess
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger("agent_claude")

_claude_available = None
_claude_path = "claude"  # resolved path to the claude CLI


def _find_claude_cli():
    """Find the claude CLI binary, checking common install locations."""
    # Try bare 'claude' first (already in PATH)
    for candidate in ["claude"]:
        try:
            result = subprocess.run(
                [candidate, '--version'],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # On Windows, check npm global bin (common location for Claude Code CLI)
    if sys.platform == "win32":
        npm_global = os.path.join(
            os.environ.get("APPDATA", ""), "npm", "claude.cmd")
        if os.path.isfile(npm_global):
            try:
                result = subprocess.run(
                    [npm_global, '--version'],
                    capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return npm_global
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    return None


def is_claude_available():
    """Check if the claude CLI is installed and accessible."""
    global _claude_available, _claude_path
    if _claude_available is not None:
        return _claude_available

    found = _find_claude_cli()
    if found:
        _claude_path = found
        _claude_available = True
        log.info(f"Claude CLI detected at '{found}' — will use subscription "
                 f"for visual analysis")
    else:
        _claude_available = False
        log.info("Claude CLI not found — running in local-only mode")

    return _claude_available


def call_claude(prompt, image_paths=None, timeout=180):
    """Call Claude via the Claude Code CLI (uses your subscription).

    Args:
        prompt: The text prompt to send.
        image_paths: Optional list of image file paths for Claude to read.
        timeout: Max seconds to wait for response.

    Returns: Claude's response text, or None if unavailable/failed.
    """
    if not is_claude_available():
        return None

    # Build prompt — include image file paths so Claude reads them
    full_prompt = prompt
    if image_paths:
        paths_text = "\n".join(
            f"  {os.path.abspath(p)}" for p in image_paths if os.path.exists(p))
        if paths_text:
            full_prompt += (
                f"\n\nPlease read and analyze these screenshot images:\n{paths_text}")

    try:
        result = subprocess.run(
            [_claude_path, '-p', full_prompt, '--output-format', 'text'],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if result.stderr:
            log.warning(f"Claude CLI stderr: {result.stderr[:300]}")
        return None
    except subprocess.TimeoutExpired:
        log.warning(f"Claude CLI timed out after {timeout}s")
        return None
    except FileNotFoundError:
        log.warning("Claude CLI not found in PATH")
        return None
    except Exception as e:
        log.warning(f"Claude CLI error: {e}")
        return None


def call_claude_vision(prompt, image_paths, timeout=180):
    """Send image file paths + prompt to Claude for visual analysis.
    Uses your Claude subscription via CLI — no API key needed.
    Returns: response text or None."""
    return call_claude(prompt, image_paths=image_paths, timeout=timeout)


def call_claude_planning(prompt, timeout=120):
    """Send a planning request to Claude via CLI.
    Uses your Claude subscription — no API key needed.
    Returns: response text or None."""
    return call_claude(prompt, timeout=timeout)


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------

def parse_json_response(text):
    """Extract JSON from Claude's response.
    Handles markdown code blocks and raw JSON."""
    if not text:
        return None

    # Try markdown code block first
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try raw JSON (find first { ... } or [ ... ])
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    return None


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_AGENT = """You are an autonomous UE5 scene-building agent.
You are placing assets in a forest scene to create a cinematic tunnel walkway.

Coordinate system: UE5 left-handed, X=Forward, Y=Right, Z=Up, units in centimeters.

Composition rules:
- Never place assets in uniform grids. Use asymmetrical fractal patterns.
- Primary clusters: 3-7 items, secondary: 2-4, tertiary: 1-2.
- Minimum 3 tree species per zone. Full 360 degree random yaw.
- Scale range: 0.75-1.25x with Gaussian distribution.
- Edge transitions: 500-2000cm, never hard borders.

{scene_brief}
"""

PROMPT_PERIODIC_REVIEW = """Review the scene progress after {n} placements.

Current manifest:
{compressed_manifest}

Survey screenshots saved at: {screenshot_dir}

Evaluate:
1. Overall composition quality (natural clustering? good variety?)
2. Density balance across zones
3. Layer completeness (ground cover, mid-vegetation, canopy all present?)
4. Any obvious problems (gaps, overcrowding, unnatural patterns)

Respond with JSON:
{{
  "overall_score": <1-10>,
  "issues": ["<issue1>", "<issue2>"],
  "recommendations": ["<rec1>", "<rec2>"],
  "zones_needing_attention": ["<zone_id>"],
  "should_continue": true
}}
"""

PROMPT_VERIFICATION = """You are verifying a UE5 scene asset placement.

Asset: {label} ({asset_type}, {species})
Zone: {zone_id}
Location: ({loc_x:.0f}, {loc_y:.0f}, {loc_z:.0f}) cm
Scale: ({scale_x:.2f}, {scale_y:.2f}, {scale_z:.2f})

Please read the close-up and context screenshots and check for:
1. Is the asset properly grounded? (not floating, not buried)
2. Does the scale look natural relative to surroundings?
3. Is the orientation natural? (slight lean OK, extreme tilt = fail)
4. Does it visually fit the scene? (species match, density, spacing)
5. Any clipping with other objects?

Scene context:
{scene_context}

Respond with JSON:
{{
  "passed": true,
  "confidence": 0.0,
  "issues": ["<issue>"],
  "suggested_adjustments": [{{"action": "move|rotate|scale", "delta": [x, y, z]}}],
  "reasoning": "<brief explanation>"
}}
"""

PROMPT_RECOVERY_RECONCILE = """The UE5 editor was restarted. Reconcile the scene.

Expected manifest:
{compressed_manifest}

Discrepancies:
- Missing in UE5: {missing_in_ue5}
- Unexpected in UE5: {missing_in_manifest}
- Matched: {matched}

Decide what to do. Respond with JSON:
{{
  "re_place": ["<label1>"],
  "remove": ["<label2>"],
  "resume_from_zone": "<zone_id>",
  "reasoning": "<explanation>"
}}
"""

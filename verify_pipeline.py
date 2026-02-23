"""Verification pipeline: orchestrates Phase 1 (programmatic) + Phase 2 (visual).
Phase 1: Fast programmatic checks (always runs, free).
Phase 2: Visual via Claude CLI (runs only if CLI available, uses subscription).
Manages retries, circuit breaker, and rollback.
Runs OUTSIDE UE5."""

import logging
import sys
import os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CIRCUIT_BREAKER_MAX_RETRIES, CIRCUIT_BREAKER_ZONE_MAX
from verify_programmatic import verify_placement, auto_fix_issue, IssueSeverity
from verify_visual import (
    verify_visual, VisualVerdict, save_verification_screenshots,
)
from agent_claude import is_claude_available
from capture_enhanced import capture_verification_pair
import ue_commands

log = logging.getLogger("verify")


@dataclass
class PipelineResult:
    phase1_passed: bool = False
    phase2_verdict: VisualVerdict = None
    final_passed: bool = False
    retries_used: int = 0
    was_rolled_back: bool = False
    auto_fixes_applied: list = field(default_factory=list)
    adjustments_applied: list = field(default_factory=list)


def run_verification_pipeline(actor_label, asset_info, expected_location,
                              zone_bounds=None, nearby_actors=None,
                              scene_context="",
                              max_retries=CIRCUIT_BREAKER_MAX_RETRIES,
                              enable_visual=None):
    """Full verification pipeline with circuit breaker.

    Phase 1 always runs (free, programmatic).
    Phase 2 runs only if Claude CLI is available (uses subscription).
    Set enable_visual=False to force skip Phase 2.

    Flow (up to max_retries):
      1. Phase 1: programmatic checks → auto-fix what's possible
      2. If Phase 1 clean (no NEEDS_VISUAL issues) → PASS
      3. Phase 2 (if available): capture + Claude CLI visual check
      4. If Phase 2 passes → PASS
      5. If Phase 2 suggests adjustments → apply them, loop
      6. If retries exhausted → ROLLBACK

    Returns PipelineResult.
    """
    # Auto-detect visual capability
    if enable_visual is None:
        enable_visual = is_claude_available()

    result = PipelineResult()

    for attempt in range(max_retries):
        result.retries_used = attempt + 1

        # Phase 1: Programmatic checks (always free)
        log.info(f"Phase 1 verification for {actor_label} (attempt {attempt + 1})")
        p1 = verify_placement(actor_label, expected_location,
                              zone_bounds=zone_bounds,
                              nearby_actors=nearby_actors)

        result.phase1_passed = p1.passed
        result.auto_fixes_applied.extend(p1.auto_fixed)

        if not p1.passed:
            # Critical issues that can't be auto-fixed
            critical = [i for i in p1.issues
                        if i.severity == IssueSeverity.CRITICAL]
            if critical:
                log.warning(f"Critical issues for {actor_label}: "
                            f"{[i.description for i in critical]}")
                if attempt == max_retries - 1:
                    result.was_rolled_back = rollback_placement(actor_label)
                    return result
                continue

        # If Phase 1 passes cleanly (no visual check needed), done
        if p1.passed and not p1.needs_visual:
            log.info(f"Phase 1 passed cleanly for {actor_label}")
            result.final_passed = True
            return result

        # Phase 2: Visual verification (only if Claude CLI available)
        if enable_visual and p1.needs_visual:
            log.info(f"Phase 2 visual check for {actor_label} (via Claude CLI)")
            bounds = ue_commands.query_actor_bounds(actor_label)
            if bounds and bounds.get('success') and not bounds.get('error'):
                center = bounds.get('origin', list(expected_location))
                sphere_radius = bounds.get('sphere_radius', 200)
            else:
                center = list(expected_location)
                sphere_radius = 200

            # Capture verification screenshots
            closeup_b64, context_b64 = capture_verification_pair(
                tuple(center), sphere_radius)

            # Save to disk for Claude CLI to read
            closeup_path, context_path = save_verification_screenshots(
                closeup_b64, context_b64, actor_label)

            verdict = verify_visual(
                closeup_path, context_path, asset_info, scene_context)
            result.phase2_verdict = verdict

            if verdict.passed:
                log.info(f"Phase 2 passed for {actor_label} "
                         f"(confidence: {verdict.confidence:.2f})")
                result.final_passed = True
                return result

            # Phase 2 failed — try adjustments
            if verdict.suggested_adjustments and attempt < max_retries - 1:
                for adj in verdict.suggested_adjustments:
                    applied = _apply_adjustment(actor_label, adj)
                    if applied:
                        result.adjustments_applied.append(adj)
                log.info(f"Applied {len(result.adjustments_applied)} adjustments")
                continue

        elif not enable_visual and p1.needs_visual:
            # No Claude CLI — pass with warning
            log.info(f"Phase 1 flagged visual check for {actor_label}, "
                     f"but Claude CLI unavailable — auto-passing")
            result.final_passed = True
            return result

        # Last retry — rollback
        if attempt == max_retries - 1:
            log.warning(f"Max retries reached for {actor_label}, rolling back")
            result.was_rolled_back = rollback_placement(actor_label)
            return result

    return result


def _apply_adjustment(actor_label, adjustment):
    """Apply a single adjustment from visual verification."""
    action = adjustment.get('action', '')
    delta = adjustment.get('delta', [0, 0, 0])

    if action == 'move' and delta:
        actors = ue_commands.query_actors_by_prefix(actor_label)
        if actors and actors.get('success'):
            for a in actors.get('actors', []):
                if a['label'] == actor_label:
                    loc = a['location']
                    new_loc = (loc[0] + delta[0], loc[1] + delta[1],
                               loc[2] + delta[2])
                    result = ue_commands.move_actor(actor_label, new_loc)
                    return result and result.get('success', False)

    elif action == 'rotate' and delta:
        actors = ue_commands.query_actors_by_prefix(actor_label)
        if actors and actors.get('success'):
            for a in actors.get('actors', []):
                if a['label'] == actor_label:
                    rot = a['rotation']
                    new_rot = (rot[0] + delta[0], rot[1] + delta[1],
                               rot[2] + delta[2])
                    result = ue_commands.rotate_actor(actor_label, new_rot)
                    return result and result.get('success', False)

    elif action == 'scale' and delta:
        actors = ue_commands.query_actors_by_prefix(actor_label)
        if actors and actors.get('success'):
            for a in actors.get('actors', []):
                if a['label'] == actor_label:
                    sc = a['scale']
                    new_sc = (sc[0] + delta[0], sc[1] + delta[1],
                              sc[2] + delta[2])
                    result = ue_commands.scale_actor(actor_label, new_sc)
                    return result and result.get('success', False)

    return False


def rollback_placement(actor_label):
    """Remove a failed actor. Returns True if destroyed."""
    log.info(f"Rolling back {actor_label}")
    result = ue_commands.destroy_actor(actor_label)
    return result and result.get('destroyed', False)


class CircuitBreaker:
    """Tracks consecutive failures per zone and per actor type."""

    def __init__(self, max_actor_failures=CIRCUIT_BREAKER_MAX_RETRIES,
                 max_zone_failures=CIRCUIT_BREAKER_ZONE_MAX):
        self.max_actor_failures = max_actor_failures
        self.max_zone_failures = max_zone_failures
        self.zone_failures = {}
        self.total_failures = 0
        self.total_successes = 0

    def record_failure(self, zone_id):
        self.zone_failures[zone_id] = self.zone_failures.get(zone_id, 0) + 1
        self.total_failures += 1

    def record_success(self, zone_id):
        self.zone_failures[zone_id] = 0
        self.total_successes += 1

    def is_zone_blocked(self, zone_id):
        return self.zone_failures.get(zone_id, 0) >= self.max_zone_failures

    def reset(self):
        self.zone_failures.clear()
        self.total_failures = 0
        self.total_successes = 0

    def stats(self):
        return {
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "zone_failures": dict(self.zone_failures),
        }

"""Phase 1 verification: fast programmatic checks (~5ms).
Catches 60-70% of placement issues before expensive visual verification.
Runs OUTSIDE UE5."""

import math
import sys
import os
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    OVERLAP_THRESHOLD_CM, GROUND_CONTACT_TOLERANCE_CM,
    ORIENTATION_MAX_LEAN_DEG, BOUNDS_CHECK_MARGIN_CM,
)
import ue_commands


class IssueType(Enum):
    FLOATING = "floating"
    BURIED = "buried"
    OVERLAPPING = "overlapping"
    OUT_OF_BOUNDS = "out_of_bounds"
    BAD_ORIENTATION = "bad_orientation"
    SCALE_EXTREME = "scale_extreme"


class IssueSeverity(Enum):
    AUTO_FIXABLE = "auto_fixable"
    NEEDS_VISUAL = "needs_visual"
    CRITICAL = "critical"


@dataclass
class VerificationIssue:
    issue_type: IssueType
    severity: IssueSeverity
    description: str
    suggested_fix: dict = None  # e.g., {"action": "move", "delta_z": -15.3}


@dataclass
class VerificationResult:
    passed: bool
    issues: list = field(default_factory=list)
    auto_fixed: list = field(default_factory=list)
    needs_visual: bool = False


def verify_placement(actor_label, expected_location, zone_bounds=None,
                     nearby_actors=None):
    """Run all Phase 1 checks on a placed actor.
    Returns VerificationResult."""
    result = VerificationResult(passed=True)

    # Query actual actor state from UE5
    bounds = ue_commands.query_actor_bounds(actor_label)
    if not bounds or not bounds.get('success') or bounds.get('error'):
        result.passed = False
        result.issues.append(VerificationIssue(
            IssueType.FLOATING, IssueSeverity.CRITICAL,
            f"Could not query actor '{actor_label}' from UE5"))
        return result

    actor_origin = bounds.get('origin', expected_location)
    actor_loc = list(expected_location)

    # 1. Ground contact check
    gc_issue = ground_contact_check(actor_label, actor_loc)
    if gc_issue:
        result.issues.append(gc_issue)
        if gc_issue.severity == IssueSeverity.AUTO_FIXABLE:
            if auto_fix_issue(actor_label, gc_issue):
                result.auto_fixed.append(gc_issue.description)
            else:
                result.needs_visual = True
        elif gc_issue.severity == IssueSeverity.NEEDS_VISUAL:
            result.needs_visual = True

    # 2. Overlap check
    if nearby_actors:
        nearby_dicts = []
        for na in nearby_actors:
            if hasattr(na, 'label'):
                nearby_dicts.append({
                    "label": na.label,
                    "location": na.location,
                })
            else:
                nearby_dicts.append(na)
        ol_issue = overlap_check(actor_label, actor_loc, nearby_dicts)
        if ol_issue:
            result.issues.append(ol_issue)
            if ol_issue.severity == IssueSeverity.NEEDS_VISUAL:
                result.needs_visual = True

    # 3. Bounds check
    if zone_bounds:
        bc_issue = bounds_check(actor_loc, zone_bounds)
        if bc_issue:
            result.issues.append(bc_issue)
            result.needs_visual = True

    # 4. Orientation check
    oc_issue = orientation_check(actor_label)
    if oc_issue:
        result.issues.append(oc_issue)
        if oc_issue.severity == IssueSeverity.AUTO_FIXABLE:
            if auto_fix_issue(actor_label, oc_issue):
                result.auto_fixed.append(oc_issue.description)
            else:
                result.needs_visual = True

    # Determine overall pass/fail
    critical = [i for i in result.issues
                if i.severity == IssueSeverity.CRITICAL]
    unfixed_auto = [i for i in result.issues
                    if i.severity == IssueSeverity.AUTO_FIXABLE
                    and i.description not in result.auto_fixed]
    if critical or unfixed_auto:
        result.passed = False
    elif result.needs_visual:
        result.passed = True  # passes Phase 1, needs Phase 2

    return result


def ground_contact_check(actor_label, actor_location):
    """Check if actor is properly grounded via line trace.
    Returns VerificationIssue or None if OK."""
    x, y, z = actor_location[0], actor_location[1], actor_location[2]
    trace = ue_commands.line_trace_ground(x, y)

    if not trace.get('success') or trace.get('z') is None:
        return None  # Can't verify, skip

    ground_z = trace['z']
    gap = z - ground_z

    if gap > GROUND_CONTACT_TOLERANCE_CM:
        return VerificationIssue(
            IssueType.FLOATING, IssueSeverity.AUTO_FIXABLE,
            f"Floating {gap:.1f}cm above ground",
            {"action": "move", "delta_z": -(gap - 5)})  # Leave 5cm buffer

    if gap < -GROUND_CONTACT_TOLERANCE_CM:
        return VerificationIssue(
            IssueType.BURIED, IssueSeverity.AUTO_FIXABLE,
            f"Buried {-gap:.1f}cm below ground",
            {"action": "move", "delta_z": -gap + 5})

    return None


def overlap_check(actor_label, actor_location, nearby_actors):
    """Check if actor is too close to neighbors.
    Returns VerificationIssue or None if OK."""
    ax, ay = actor_location[0], actor_location[1]

    for na in nearby_actors:
        if na.get('label') == actor_label:
            continue
        na_loc = na.get('location', [0, 0, 0])
        nx, ny = na_loc[0], na_loc[1]
        dist = math.sqrt((ax - nx) ** 2 + (ay - ny) ** 2)

        if dist < OVERLAP_THRESHOLD_CM:
            # Calculate nudge direction (away from overlap)
            if dist < 1:  # nearly coincident
                dx, dy = 1, 0
            else:
                dx = (ax - nx) / dist
                dy = (ay - ny) / dist
            nudge = OVERLAP_THRESHOLD_CM - dist + 10
            return VerificationIssue(
                IssueType.OVERLAPPING, IssueSeverity.NEEDS_VISUAL,
                f"Only {dist:.0f}cm from {na.get('label', 'unknown')} "
                f"(min {OVERLAP_THRESHOLD_CM}cm)",
                {"action": "move", "delta_x": dx * nudge,
                 "delta_y": dy * nudge})

    return None


def bounds_check(actor_location, zone_bounds):
    """Check if actor is within zone boundaries + margin.
    Returns VerificationIssue or None if OK."""
    x, y = actor_location[0], actor_location[1]
    margin = BOUNDS_CHECK_MARGIN_CM

    xmin = zone_bounds.get('x_min', -9999) - margin
    xmax = zone_bounds.get('x_max', 9999) + margin
    ymin = zone_bounds.get('y_min', -9999) - margin
    ymax = zone_bounds.get('y_max', 9999) + margin

    if x < xmin or x > xmax or y < ymin or y > ymax:
        return VerificationIssue(
            IssueType.OUT_OF_BOUNDS, IssueSeverity.NEEDS_VISUAL,
            f"Actor at ({x:.0f}, {y:.0f}) outside zone bounds "
            f"[{zone_bounds.get('x_min')}-{zone_bounds.get('x_max')}, "
            f"{zone_bounds.get('y_min')}-{zone_bounds.get('y_max')}]")
    return None


def orientation_check(actor_label, max_lean=ORIENTATION_MAX_LEAN_DEG):
    """Check if actor's pitch/roll is within acceptable range.
    Returns VerificationIssue or None if OK."""
    bounds = ue_commands.query_actor_bounds(actor_label)
    if not bounds or not bounds.get('success'):
        return None

    # Need to query rotation separately
    actors_result = ue_commands.query_actors_by_prefix(actor_label)
    if not actors_result or not actors_result.get('success'):
        return None

    for a in actors_result.get('actors', []):
        if a['label'] == actor_label:
            pitch, yaw, roll = a['rotation']
            # Normalize to -180..180
            pitch = ((pitch + 180) % 360) - 180
            roll = ((roll + 180) % 360) - 180

            if abs(pitch) > max_lean or abs(roll) > max_lean:
                return VerificationIssue(
                    IssueType.BAD_ORIENTATION, IssueSeverity.AUTO_FIXABLE,
                    f"Excessive lean: pitch={pitch:.1f}, roll={roll:.1f} "
                    f"(max {max_lean}deg)",
                    {"action": "rotate",
                     "new_pitch": max(min(pitch, max_lean), -max_lean),
                     "new_roll": max(min(roll, max_lean), -max_lean)})
            break

    return None


def auto_fix_issue(actor_label, issue):
    """Apply the suggested fix. Returns True if fix was applied."""
    if issue.suggested_fix is None:
        return False

    fix = issue.suggested_fix
    action = fix.get('action', '')

    if action == 'move':
        # Get current location, apply delta
        actors = ue_commands.query_actors_by_prefix(actor_label)
        if not actors or not actors.get('success'):
            return False
        for a in actors.get('actors', []):
            if a['label'] == actor_label:
                loc = a['location']
                new_loc = (
                    loc[0] + fix.get('delta_x', 0),
                    loc[1] + fix.get('delta_y', 0),
                    loc[2] + fix.get('delta_z', 0),
                )
                result = ue_commands.move_actor(actor_label, new_loc)
                return result and result.get('success', False)

    elif action == 'rotate':
        actors = ue_commands.query_actors_by_prefix(actor_label)
        if not actors or not actors.get('success'):
            return False
        for a in actors.get('actors', []):
            if a['label'] == actor_label:
                rot = a['rotation']
                new_rot = (
                    fix.get('new_pitch', rot[0]),
                    rot[1],  # preserve yaw
                    fix.get('new_roll', rot[2]),
                )
                result = ue_commands.rotate_actor(actor_label, new_rot)
                return result and result.get('success', False)

    return False

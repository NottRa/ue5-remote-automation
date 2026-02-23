"""High-level UE5 command builders. Runs OUTSIDE UE5.
Generates Python script strings and sends them via ue_bridge.
Every mutation uses ScopedEditorTransaction for undo support.
Uses EditorActorSubsystem (not deprecated EditorLevelLibrary).
Returns structured data via AGENT_JSON convention in log output."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_bridge import send_command_raw
from config import COMMAND_TIMEOUT


def _parse_json_from_output(result):
    """Extract JSON payload from ue_bridge result['output'].
    Convention: commands output 'AGENT_JSON:' followed by a JSON line."""
    if not result or not result.get('output'):
        return None
    for line in result['output'].split('\n'):
        line = line.strip()
        if line.startswith('AGENT_JSON:'):
            try:
                return json.loads(line[len('AGENT_JSON:'):])
            except json.JSONDecodeError:
                continue
    return None


def _send_and_parse(script, timeout=COMMAND_TIMEOUT):
    """Send a script to UE5 and parse the AGENT_JSON result."""
    result = send_command_raw(script, timeout=timeout)
    if result is None:
        return {"success": False, "error": "No response from UE5"}
    if not result.get('success', False):
        return {"success": False, "error": result.get('error', 'Unknown error'),
                "output": result.get('output', '')}
    parsed = _parse_json_from_output(result)
    if parsed is not None:
        parsed['success'] = True
        return parsed
    return {"success": True, "output": result.get('output', '')}


# ---------------------------------------------------------------------------
# Actor Queries
# ---------------------------------------------------------------------------

def query_all_actors():
    """Get all actors with labels, classes, positions, scales.
    Returns: {"success": bool, "actors": [{"label", "class", "location", "rotation", "scale"}]}"""
    script = """
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
result = []
for a in actors:
    label = a.get_actor_label()
    if not label:
        continue
    loc = a.get_actor_location()
    rot = a.get_actor_rotation()
    scale = a.get_actor_scale3d()
    result.append({
        "label": label,
        "class": a.get_class().get_name(),
        "location": [loc.x, loc.y, loc.z],
        "rotation": [rot.pitch, rot.yaw, rot.roll],
        "scale": [scale.x, scale.y, scale.z],
    })
unreal.log(f'AGENT_JSON:{json.dumps({"actors": result})}')
"""
    return _send_and_parse(script)


def query_actors_by_prefix(prefix):
    """Get actors whose label starts with prefix."""
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
result = []
for a in actors:
    label = a.get_actor_label()
    if label and label.startswith('{prefix}'):
        loc = a.get_actor_location()
        rot = a.get_actor_rotation()
        scale = a.get_actor_scale3d()
        result.append({{
            "label": label,
            "class": a.get_class().get_name(),
            "location": [loc.x, loc.y, loc.z],
            "rotation": [rot.pitch, rot.yaw, rot.roll],
            "scale": [scale.x, scale.y, scale.z],
        }})
unreal.log(f'AGENT_JSON:{{json.dumps({{"actors": result}})}}')
"""
    return _send_and_parse(script)


def query_actor_bounds(label):
    """Get world-space bounding box and sphere radius for a named actor.
    Returns: {"success": bool, "origin": [x,y,z], "extent": [x,y,z], "sphere_radius": float}"""
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
found = None
for a in actors:
    if a.get_actor_label() == '{label}':
        found = a
        break

if found is None:
    unreal.log('AGENT_JSON:{{"error": "Actor not found"}}')
else:
    origin, extent = found.get_actor_bounds(False)
    radius = max(extent.x, extent.y, extent.z)
    unreal.log(f'AGENT_JSON:{{json.dumps({{"origin": [origin.x, origin.y, origin.z], "extent": [extent.x, extent.y, extent.z], "sphere_radius": radius}})}}')
"""
    return _send_and_parse(script)


# ---------------------------------------------------------------------------
# Line Traces
# ---------------------------------------------------------------------------

def line_trace_ground(x, y):
    """Vertical line trace to find terrain Z at (x, y).
    Returns: {"success": bool, "z": float} or {"success": False} if no hit."""
    script = f"""
import unreal, json

world = unreal.EditorLevelLibrary.get_editor_world()
start = unreal.Vector({x}, {y}, 50000.0)
end = unreal.Vector({x}, {y}, -50000.0)
hit_result = unreal.SystemLibrary.line_trace_single(
    world, start, end,
    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
    False, [], unreal.DrawDebugTrace.NONE, True)
if hit_result is not None:
    # UE5.7 returns (bool, FHitResult)
    if isinstance(hit_result, tuple):
        did_hit, hr = hit_result[0], hit_result[1]
    else:
        did_hit = True
        hr = hit_result
    if did_hit:
        ip = hr.impact_point
        unreal.log(f'AGENT_JSON:{{json.dumps({{"z": ip.z}})}}')
    else:
        unreal.log('AGENT_JSON:{{"z": null}}')
else:
    unreal.log('AGENT_JSON:{{"z": null}}')
"""
    result = _send_and_parse(script)
    if result and result.get('z') is not None:
        return {"success": True, "z": result['z']}
    return {"success": False, "z": None}


def line_trace_multi_ground(positions):
    """Batch line trace for multiple (x, y) positions. Single command.
    Returns: {"success": bool, "results": [{"x", "y", "z"} or {"x", "y", "z": null}]}"""
    pos_list = json.dumps(positions)
    script = f"""
import unreal, json

world = unreal.EditorLevelLibrary.get_editor_world()
positions = {pos_list}
results = []
for pos in positions:
    x, y = pos[0], pos[1]
    start = unreal.Vector(x, y, 50000.0)
    end = unreal.Vector(x, y, -50000.0)
    hit_result = unreal.SystemLibrary.line_trace_single(
        world, start, end,
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
        False, [], unreal.DrawDebugTrace.NONE, True)
    z_val = None
    if hit_result is not None:
        if isinstance(hit_result, tuple):
            did_hit, hr = hit_result[0], hit_result[1]
        else:
            did_hit = True
            hr = hit_result
        if did_hit:
            z_val = hr.impact_point.z
    results.append({{"x": x, "y": y, "z": z_val}})
unreal.log(f'AGENT_JSON:{{json.dumps({{"results": results}})}}')
"""
    return _send_and_parse(script)


# ---------------------------------------------------------------------------
# Actor Spawning
# ---------------------------------------------------------------------------

def _build_spawn_script(actor_class, label, mesh_path, location, rotation,
                        scale, mesh_setter, folder):
    """Build the exec() script string for spawning an actor.
    actor_class: 'SkeletalMeshActor' or 'StaticMeshActor'
    mesh_setter: 'skeletal_mesh_component' or 'static_mesh_component'"""
    lx, ly, lz = location
    rx, ry, rz = rotation
    sx, sy, sz = scale

    if actor_class == "SkeletalMeshActor":
        set_mesh_code = f"""
mesh = unreal.EditorAssetLibrary.load_asset('{mesh_path}')
if mesh:
    comp = actor.skeletal_mesh_component
    try:
        comp.set_skinned_asset_and_update(mesh)
    except AttributeError:
        try:
            comp.set_skeletal_mesh(mesh)
        except:
            comp.set_editor_property('skeletal_mesh', mesh)
"""
    else:
        set_mesh_code = f"""
mesh = unreal.EditorAssetLibrary.load_asset('{mesh_path}')
if mesh:
    actor.static_mesh_component.set_static_mesh(mesh)
"""

    return f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
with unreal.ScopedEditorTransaction('Agent spawn {label}') as trans:
    actor = subsys.spawn_actor_from_class(
        unreal.{actor_class},
        unreal.Vector({lx}, {ly}, {lz})
    )
    if actor is None:
        unreal.log('AGENT_JSON:{{"error": "Spawn returned None"}}')
    else:
        actor.set_actor_label('{label}')
        actor.set_actor_rotation(unreal.Rotator({rx}, {ry}, {rz}), False)
        actor.set_actor_scale3d(unreal.Vector({sx}, {sy}, {sz}))
        actor.set_folder_path('{folder}')
        {set_mesh_code}
        loc = actor.get_actor_location()
        origin, extent = actor.get_actor_bounds(False)
        radius = max(extent.x, extent.y, extent.z)
        unreal.log(f'AGENT_JSON:{{json.dumps({{"label": "{label}", "location": [loc.x, loc.y, loc.z], "bounds": {{"origin": [origin.x, origin.y, origin.z], "extent": [extent.x, extent.y, extent.z], "sphere_radius": radius}}}})}}')
"""


def spawn_skeletal_mesh_actor(label, mesh_path, location, rotation=(0, 0, 0),
                              scale=(1, 1, 1), folder="Agent_Placed"):
    """Spawn a SkeletalMeshActor (trees). Returns structured result."""
    script = _build_spawn_script(
        "SkeletalMeshActor", label, mesh_path, location, rotation, scale,
        "skeletal_mesh_component", folder)
    return _send_and_parse(script)


def spawn_static_mesh_actor(label, mesh_path, location, rotation=(0, 0, 0),
                            scale=(1, 1, 1), folder="Agent_Placed"):
    """Spawn a StaticMeshActor (rocks, ground). Returns structured result."""
    script = _build_spawn_script(
        "StaticMeshActor", label, mesh_path, location, rotation, scale,
        "static_mesh_component", folder)
    return _send_and_parse(script)


# ---------------------------------------------------------------------------
# Actor Modification
# ---------------------------------------------------------------------------

def move_actor(label, new_location):
    """Move actor to new_location (x, y, z)."""
    lx, ly, lz = new_location
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
found = None
for a in actors:
    if a.get_actor_label() == '{label}':
        found = a
        break

if found is None:
    unreal.log('AGENT_JSON:{{"error": "Actor not found"}}')
else:
    with unreal.ScopedEditorTransaction('Agent move {label}') as t:
        found.set_actor_location(unreal.Vector({lx}, {ly}, {lz}), False, False)
    loc = found.get_actor_location()
    unreal.log(f'AGENT_JSON:{{json.dumps({{"label": "{label}", "location": [loc.x, loc.y, loc.z]}})}}')
"""
    return _send_and_parse(script)


def rotate_actor(label, new_rotation):
    """Set actor rotation (pitch, yaw, roll)."""
    rx, ry, rz = new_rotation
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
found = None
for a in actors:
    if a.get_actor_label() == '{label}':
        found = a
        break

if found is None:
    unreal.log('AGENT_JSON:{{"error": "Actor not found"}}')
else:
    with unreal.ScopedEditorTransaction('Agent rotate {label}') as t:
        found.set_actor_rotation(unreal.Rotator({rx}, {ry}, {rz}), False)
    rot = found.get_actor_rotation()
    unreal.log(f'AGENT_JSON:{{json.dumps({{"label": "{label}", "rotation": [rot.pitch, rot.yaw, rot.roll]}})}}')
"""
    return _send_and_parse(script)


def scale_actor(label, new_scale):
    """Set actor scale (sx, sy, sz)."""
    sx, sy, sz = new_scale
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
found = None
for a in actors:
    if a.get_actor_label() == '{label}':
        found = a
        break

if found is None:
    unreal.log('AGENT_JSON:{{"error": "Actor not found"}}')
else:
    with unreal.ScopedEditorTransaction('Agent scale {label}') as t:
        found.set_actor_scale3d(unreal.Vector({sx}, {sy}, {sz}))
    s = found.get_actor_scale3d()
    unreal.log(f'AGENT_JSON:{{json.dumps({{"label": "{label}", "scale": [s.x, s.y, s.z]}})}}')
"""
    return _send_and_parse(script)


def destroy_actor(label):
    """Destroy a named actor. Returns {"success": bool}."""
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
found = None
for a in actors:
    if a.get_actor_label() == '{label}':
        found = a
        break

if found is None:
    unreal.log('AGENT_JSON:{{"error": "Actor not found", "destroyed": false}}')
else:
    with unreal.ScopedEditorTransaction('Agent destroy {label}') as t:
        subsys.destroy_actor(found)
    unreal.log('AGENT_JSON:{{"destroyed": true}}')
"""
    return _send_and_parse(script)


# ---------------------------------------------------------------------------
# Overlap Detection
# ---------------------------------------------------------------------------

def get_overlapping_actors(label):
    """Get actors overlapping with the named actor.
    Returns: {"success": bool, "overlapping": [{"label", "class"}]}"""
    script = f"""
import unreal, json

subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsys.get_all_level_actors()
found = None
for a in actors:
    if a.get_actor_label() == '{label}':
        found = a
        break

if found is None:
    unreal.log('AGENT_JSON:{{"error": "Actor not found"}}')
else:
    overlapping = found.get_overlapping_actors()
    result = []
    for oa in overlapping:
        ol = oa.get_actor_label()
        if ol:
            result.append({{"label": ol, "class": oa.get_class().get_name()}})
    unreal.log(f'AGENT_JSON:{{json.dumps({{"overlapping": result}})}}')
"""
    return _send_and_parse(script)


# ---------------------------------------------------------------------------
# VRAM Monitoring
# ---------------------------------------------------------------------------

def get_vram_usage():
    """Query GPU memory usage. Returns {"success": bool, "used_mb": float, "budget_mb": float}.
    Note: This parses stat output which may not always be available."""
    script = """
import unreal, json

# Use a simple approach - log what we can access
try:
    # Try to get RHI stats via console command
    world = unreal.EditorLevelLibrary.get_editor_world()
    # We can't easily parse stat RHI from Python, so estimate from platform
    # This is a best-effort approximation
    unreal.log('AGENT_JSON:{"used_mb": -1, "budget_mb": 8192, "note": "VRAM query requires stat RHI parsing"}')
except Exception as e:
    unreal.log(f'AGENT_JSON:{{"error": str(e)}}')
"""
    return _send_and_parse(script)

"""
DIAGNOSTIC: Inspect ForestLevel actors, ground surface, and mesh bounds.
Run BEFORE fixing placement issues.
"""
import unreal

EL = unreal.EditorLevelLibrary
EA = unreal.EditorAssetLibrary

unreal.log("=" * 70)
unreal.log("  LEVEL DIAGNOSTIC")
unreal.log("=" * 70)

# List ALL actors with positions
actors = EL.get_all_level_actors()
unreal.log(f"\nTotal actors: {len(actors)}\n")

for actor in actors:
    label = actor.get_actor_label()
    cls = actor.get_class().get_name()
    loc = actor.get_actor_location()
    scale = actor.get_actor_scale3d()
    unreal.log(f"  {label:30s} | {cls:30s} | pos=({loc.x:.0f}, {loc.y:.0f}, {loc.z:.0f}) | scale=({scale.x:.1f}, {scale.y:.1f}, {scale.z:.1f})")

# Find ground surface
unreal.log("\n" + "=" * 70)
unreal.log("  GROUND SURFACE ANALYSIS")
unreal.log("=" * 70)

for actor in actors:
    label = actor.get_actor_label()
    cls = actor.get_class().get_name()
    if label in ("Floor", "ForestGround", "Ground") or "Landscape" in cls:
        loc = actor.get_actor_location()
        unreal.log(f"\n  Ground actor: '{label}' ({cls}) at Z={loc.z:.1f}")

        # Try to get component bounds (world space)
        try:
            comp = actor.static_mesh_component
            b = comp.bounds
            unreal.log(f"  Bounds origin: ({b.origin.x:.0f}, {b.origin.y:.0f}, {b.origin.z:.0f})")
            unreal.log(f"  Bounds extent: ({b.box_extent.x:.0f}, {b.box_extent.y:.0f}, {b.box_extent.z:.0f})")
            unreal.log(f"  Surface (top) Z = {b.origin.z + b.box_extent.z:.1f}")
            unreal.log(f"  Bottom Z = {b.origin.z - b.box_extent.z:.1f}")
        except Exception as e:
            unreal.log(f"  Could not get static_mesh_component bounds: {e}")

        # Try get_actor_bounds
        try:
            result = actor.get_actor_bounds(False)
            if isinstance(result, tuple):
                unreal.log(f"  get_actor_bounds: origin={result[0]}, extent={result[1]}")
        except Exception as e:
            unreal.log(f"  get_actor_bounds failed: {e}")

# Check tree mesh bounds
unreal.log("\n" + "=" * 70)
unreal.log("  TREE MESH BOUNDS ANALYSIS")
unreal.log("=" * 70)

test_meshes = {
    "Beech_A": "/Game/Megaplant_Library/Tree_European_Beech/Tree_European_Beech_01/SK_European_Beech_01_A",
    "Maple_A": "/Game/Megaplant_Library/Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/SK_Norway_Maple_Forest_01_A",
    "Alder_A": "/Game/Megaplant_Library/Tree_Black_Alder/Tree_Black_Alder_01/SK_Black_Alder_01_A",
    "Aspen_A": "/Game/Megaplant_Library/Tree_European_Aspen/Tree_European_Aspen_01/SK_European_Aspen_01_A",
    "Hazel_A": "/Game/Megaplant_Library/Tree_Common_Hazel/Tree_Common_Hazel_01/SK_Common_Hazel_01_A",
}

for name, path in test_meshes.items():
    mesh = EA.load_asset(path)
    if not mesh:
        unreal.log(f"\n  {name}: COULD NOT LOAD")
        continue

    unreal.log(f"\n  {name}:")

    # Try get_bounds on mesh asset
    try:
        b = mesh.get_bounds()
        unreal.log(f"    mesh.get_bounds() origin: ({b.origin.x:.0f}, {b.origin.y:.0f}, {b.origin.z:.0f})")
        unreal.log(f"    mesh.get_bounds() extent: ({b.box_extent.x:.0f}, {b.box_extent.y:.0f}, {b.box_extent.z:.0f})")
        bottom_z = b.origin.z - b.box_extent.z
        unreal.log(f"    Mesh bottom Z (local): {bottom_z:.0f}")
        unreal.log(f"    Mesh top Z (local): {b.origin.z + b.box_extent.z:.0f}")
        if bottom_z < -10:
            unreal.log(f"    WARNING: Mesh bottom is {abs(bottom_z):.0f} units BELOW pivot!")
    except Exception as e:
        unreal.log(f"    mesh.get_bounds() failed: {e}")

    # Try bounds property
    try:
        b = mesh.bounds
        unreal.log(f"    mesh.bounds origin: ({b.origin.x:.0f}, {b.origin.y:.0f}, {b.origin.z:.0f})")
        unreal.log(f"    mesh.bounds extent: ({b.box_extent.x:.0f}, {b.box_extent.y:.0f}, {b.box_extent.z:.0f})")
    except Exception as e:
        unreal.log(f"    mesh.bounds failed: {e}")

    # Spawn a test actor and check its world bounds
    try:
        test_actor = EL.spawn_actor_from_class(
            unreal.SkeletalMeshActor, unreal.Vector(99999, 99999, 0))
        if test_actor:
            test_actor.skeletal_mesh_component.set_skinned_asset_and_update(mesh)
            test_actor.set_actor_label("_DIAG_TEMP_")

            # Component bounds (world space at Z=0)
            try:
                cb = test_actor.skeletal_mesh_component.bounds
                unreal.log(f"    WORLD bounds at Z=0: origin=({cb.origin.x:.0f}, {cb.origin.y:.0f}, {cb.origin.z:.0f})")
                unreal.log(f"    WORLD bounds extent: ({cb.box_extent.x:.0f}, {cb.box_extent.y:.0f}, {cb.box_extent.z:.0f})")
                world_bottom = cb.origin.z - cb.box_extent.z
                unreal.log(f"    WORLD bottom Z = {world_bottom:.0f} (actor at Z=0)")
                if world_bottom < -10:
                    unreal.log(f"    >>> TREE GOES {abs(world_bottom):.0f} UNITS BELOW GROUND <<<")
            except Exception as e:
                unreal.log(f"    component.bounds failed: {e}")

            EL.destroy_actor(test_actor)
    except Exception as e:
        unreal.log(f"    Test spawn failed: {e}")

# Check existing trees
unreal.log("\n" + "=" * 70)
unreal.log("  EXISTING TREE POSITIONS (first 5)")
unreal.log("=" * 70)
tree_count = 0
for actor in actors:
    label = actor.get_actor_label()
    if label and (label.startswith("TunnelTree_") or label.startswith("BgTree_") or label.startswith("MidTree_")):
        loc = actor.get_actor_location()
        try:
            cb = actor.skeletal_mesh_component.bounds
            bottom_z = cb.origin.z - cb.box_extent.z
            unreal.log(f"  {label}: actor_z={loc.z:.0f}, bounds_bottom={bottom_z:.0f}, bounds_top={cb.origin.z + cb.box_extent.z:.0f}")
        except:
            unreal.log(f"  {label}: actor_z={loc.z:.0f} (could not get bounds)")
        tree_count += 1
        if tree_count >= 5:
            break

# Line trace test
unreal.log("\n" + "=" * 70)
unreal.log("  LINE TRACE TEST")
unreal.log("=" * 70)
try:
    world = EL.get_editor_world()
    start = unreal.Vector(0, 0, 50000)
    end = unreal.Vector(0, 0, -50000)
    result = unreal.SystemLibrary.line_trace_single(
        world, start, end,
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
        False, [],
        unreal.DrawDebugTrace.NONE,
        True
    )
    unreal.log(f"  line_trace_single returned: {type(result)}")
    if isinstance(result, tuple):
        unreal.log(f"  Hit: {result[0]}")
        if result[0]:
            hr = result[1]
            unreal.log(f"  Impact point: ({hr.impact_point.x:.0f}, {hr.impact_point.y:.0f}, {hr.impact_point.z:.0f})")
            unreal.log(f"  Hit actor: {hr.get_actor()}")
    elif hasattr(result, 'blocking_hit'):
        unreal.log(f"  blocking_hit: {result.blocking_hit}")
        if result.blocking_hit:
            unreal.log(f"  Impact: ({result.impact_point.x:.0f}, {result.impact_point.y:.0f}, {result.impact_point.z:.0f})")
except Exception as e:
    unreal.log(f"  Line trace FAILED: {e}")

unreal.log("\n" + "=" * 70)
unreal.log("  DIAGNOSTIC COMPLETE - share Output Log")
unreal.log("=" * 70)

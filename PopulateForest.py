"""
PopulateForest.py - Places trees and rocks on the ForestTerrain using line traces.
Designed to be sent via ue_bridge.py to UE5.
Creates a cinematic forest tunnel walkway with eerie atmosphere.
"""
import unreal
import random
import math

EL = unreal.EditorLevelLibrary
EA = unreal.EditorAssetLibrary

random.seed(42)  # Deterministic for reproducibility

# ========================================================================
#  ASSET DEFINITIONS
# ========================================================================
TREE_SPECIES = {
    "Beech": [
        "/Game/Megaplant_Library/Tree_European_Beech/Tree_European_Beech_01/SK_European_Beech_01_A",
        "/Game/Megaplant_Library/Tree_European_Beech/Tree_European_Beech_01/SK_European_Beech_01_B",
    ],
    "Maple": [
        "/Game/Megaplant_Library/Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/SK_Norway_Maple_Forest_01_A",
        "/Game/Megaplant_Library/Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/SK_Norway_Maple_Forest_01_B",
    ],
    "Alder": [
        "/Game/Megaplant_Library/Tree_Black_Alder/Tree_Black_Alder_01/SK_Black_Alder_01_A",
        "/Game/Megaplant_Library/Tree_Black_Alder/Tree_Black_Alder_01/SK_Black_Alder_01_B",
    ],
    "Aspen": [
        "/Game/Megaplant_Library/Tree_European_Aspen/Tree_European_Aspen_01/SK_European_Aspen_01_A",
        "/Game/Megaplant_Library/Tree_European_Aspen/Tree_European_Aspen_01/SK_European_Aspen_01_B",
    ],
    "Hazel": [
        "/Game/Megaplant_Library/Tree_Common_Hazel/Tree_Common_Hazel_01/SK_Common_Hazel_01_A",
        "/Game/Megaplant_Library/Tree_Common_Hazel/Tree_Common_Hazel_01/SK_Common_Hazel_01_B",
    ],
}

ROCK_MESH = "/Game/Megaplant_Library/Mossy_Rocks/Mossy_Rocks_tjmudcfda_High"

# ========================================================================
#  CLEANUP - Remove any previously spawned forest actors
# ========================================================================
CLEANUP_PREFIXES = (
    "TunnelTree_", "MidTree_", "BgTree_", "Rock_", "ForestMist",
    "ForestPlayerStart", "PCG_TestZone", "ForestFog_",
)

actors = EL.get_all_level_actors()
removed = 0
for a in actors:
    label = a.get_actor_label()
    if label and any(label.startswith(p) for p in CLEANUP_PREFIXES):
        EL.destroy_actor(a)
        removed += 1
unreal.log(f"Cleaned up {removed} old forest actors")

# ========================================================================
#  LOAD ASSETS
# ========================================================================
loaded_trees = {}
for species, paths in TREE_SPECIES.items():
    meshes = []
    for p in paths:
        m = EA.load_asset(p)
        if m:
            meshes.append(m)
        else:
            unreal.log(f"WARNING: Could not load {p}")
    if meshes:
        loaded_trees[species] = meshes
        unreal.log(f"Loaded {species}: {len(meshes)} variants")

rock_mesh_asset = None
# Try to find the rock mesh - it might be a static mesh or skeletal mesh
rock_mesh_asset = EA.load_asset(ROCK_MESH)
if rock_mesh_asset:
    unreal.log(f"Loaded rock mesh: {ROCK_MESH}")
    unreal.log(f"Rock mesh type: {rock_mesh_asset.get_class().get_name()}")
else:
    unreal.log(f"WARNING: Could not load rock mesh at {ROCK_MESH}")

# ========================================================================
#  LINE TRACE HELPER
# ========================================================================
def get_ground_z(x, y):
    """Use line trace to find terrain surface Z at (x, y)."""
    world = EL.get_editor_world()
    start = unreal.Vector(x, y, 5000.0)
    end = unreal.Vector(x, y, -5000.0)

    result = unreal.SystemLibrary.line_trace_single(
        world, start, end,
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
        False, [],
        unreal.DrawDebugTrace.NONE,
        True
    )

    if result is not None:
        try:
            t = result.to_tuple()
            blocking_hit = t[0]
            if blocking_hit:
                impact_point = t[4]  # Vector
                return impact_point.z
        except:
            pass

    return 0.0  # Fallback to Z=0

# ========================================================================
#  TREE PLACEMENT
# ========================================================================
def spawn_tree(label, x, y, species_name, scale_range=(0.8, 1.2)):
    """Spawn a tree at world (x,y) on the terrain surface."""
    if species_name not in loaded_trees:
        return None

    mesh = random.choice(loaded_trees[species_name])
    z = get_ground_z(x, y)

    # Random scale variation
    base_scale = random.uniform(*scale_range)
    # Slight non-uniform scale for natural look
    sx = base_scale * random.uniform(0.95, 1.05)
    sy = base_scale * random.uniform(0.95, 1.05)
    sz = base_scale * random.uniform(0.95, 1.05)

    # Random rotation
    yaw = random.uniform(0, 360)

    actor = EL.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(x, y, z))
    if actor:
        actor.skeletal_mesh_component.set_skinned_asset_and_update(mesh)
        actor.set_actor_label(label)
        actor.set_actor_rotation(unreal.Rotator(0, yaw, 0), False)
        actor.set_actor_scale3d(unreal.Vector(sx, sy, sz))
    return actor

# ========================================================================
#  FOREST LAYOUT - Tunnel walkway composition
# ========================================================================
unreal.log("")
unreal.log("=" * 50)
unreal.log("  PLACING FOREST - Tunnel Walkway Layout")
unreal.log("=" * 50)

tree_count = 0
species_list = list(loaded_trees.keys())

# --- TUNNEL TREES (line the path, creating a canopy tunnel) ---
# Tunnel runs along Y axis (forward), X=0 is center
tunnel_y_start = -2000
tunnel_y_end = 5000
tunnel_spacing = 120  # Distance between trees along the path
tunnel_width = 500    # Distance from center to tree line

for i, y_pos in enumerate(range(tunnel_y_start, tunnel_y_end, tunnel_spacing)):
    y_jitter = random.uniform(-30, 30)

    # Left side
    x_left = -tunnel_width + random.uniform(-80, 40)
    sp = random.choice(["Beech", "Maple", "Alder"])
    label = f"TunnelTree_L{i:03d}"
    if spawn_tree(label, x_left, y_pos + y_jitter, sp, scale_range=(0.9, 1.15)):
        tree_count += 1

    # Right side
    x_right = tunnel_width + random.uniform(-40, 80)
    sp = random.choice(["Beech", "Maple", "Alder"])
    label = f"TunnelTree_R{i:03d}"
    if spawn_tree(label, x_right, y_pos + y_jitter, sp, scale_range=(0.9, 1.15)):
        tree_count += 1

unreal.log(f"  Tunnel trees: {tree_count}")

# --- MID-RANGE TREES (surrounding forest density) ---
mid_count_before = tree_count
for i in range(40):
    # Random position in forest area, avoiding the tunnel path center
    angle = random.uniform(0, 2 * math.pi)
    dist = random.uniform(700, 3000)
    x = math.cos(angle) * dist + random.uniform(-200, 200)
    y = math.sin(angle) * dist + random.uniform(-500, 2500)

    # Skip if too close to tunnel center
    if abs(x) < 400:
        x = 400 * (1 if x >= 0 else -1) + random.uniform(100, 300) * (1 if x >= 0 else -1)

    sp = random.choice(species_list)
    label = f"MidTree_{i:03d}"
    # Mid-range trees can be slightly larger
    if spawn_tree(label, x, y, sp, scale_range=(0.85, 1.3)):
        tree_count += 1

unreal.log(f"  Mid-range trees: {tree_count - mid_count_before}")

# --- BACKGROUND TREES (far distance, fill out the horizon) ---
bg_count_before = tree_count
for i in range(25):
    angle = random.uniform(0, 2 * math.pi)
    dist = random.uniform(3000, 6000)
    x = math.cos(angle) * dist
    y = math.sin(angle) * dist + 1000

    sp = random.choice(species_list)
    label = f"BgTree_{i:03d}"
    # Background trees slightly larger to compensate for distance
    if spawn_tree(label, x, y, sp, scale_range=(1.0, 1.5)):
        tree_count += 1

unreal.log(f"  Background trees: {tree_count - bg_count_before}")

# ========================================================================
#  ROCK PLACEMENT
# ========================================================================
rock_count = 0

if rock_mesh_asset:
    rock_class_name = rock_mesh_asset.get_class().get_name()
    is_static_mesh = "StaticMesh" in rock_class_name
    is_skeletal_mesh = "SkeletalMesh" in rock_class_name or "Skeleton" in rock_class_name

    for i in range(25):
        # Rocks scattered around the forest floor, some near tunnel path
        if i < 8:
            # Near tunnel path
            x = random.uniform(-600, 600)
            y = random.uniform(tunnel_y_start, tunnel_y_end)
        else:
            # Scattered in forest
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(200, 3500)
            x = math.cos(angle) * dist
            y = math.sin(angle) * dist + 1000

        z = get_ground_z(x, y)
        # Partially bury rocks
        z -= random.uniform(5, 25)

        scale = random.uniform(0.5, 2.0)
        yaw = random.uniform(0, 360)
        pitch = random.uniform(-10, 10)
        roll_val = random.uniform(-10, 10)

        if is_static_mesh:
            actor = EL.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x, y, z))
            if actor:
                actor.static_mesh_component.set_static_mesh(rock_mesh_asset)
                actor.set_actor_label(f"Rock_{i:03d}")
                actor.set_actor_rotation(unreal.Rotator(pitch, yaw, roll_val), False)
                actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
                rock_count += 1
        elif is_skeletal_mesh:
            actor = EL.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(x, y, z))
            if actor:
                actor.skeletal_mesh_component.set_skinned_asset_and_update(rock_mesh_asset)
                actor.set_actor_label(f"Rock_{i:03d}")
                actor.set_actor_rotation(unreal.Rotator(pitch, yaw, roll_val), False)
                actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
                rock_count += 1
        else:
            unreal.log(f"WARNING: Rock mesh is {rock_class_name}, unsupported type")
            break

unreal.log(f"  Rocks placed: {rock_count}")

# ========================================================================
#  SUMMARY
# ========================================================================
total = tree_count + rock_count
unreal.log("")
unreal.log("=" * 50)
unreal.log(f"  FOREST COMPLETE: {tree_count} trees + {rock_count} rocks = {total} actors")
unreal.log("=" * 50)

"""
PCG Collision Guard - Forest Demo Level
========================================
Run on your existing ForestLevel with lighting already set up.
Script inspects the level first to find ground surface, then places
all assets ON or ABOVE that surface.

Tools > Execute Python Script > this file
"""

import unreal
import random
import math
import os

random.seed(42)

EL = unreal.EditorLevelLibrary
EA = unreal.EditorAssetLibrary

# ============================================================
#  STEP 1: INSPECT LEVEL - find ground surface
# ============================================================
unreal.log("=== INSPECTING LEVEL ===")
ground_z = None
ground_actor = None

for actor in EL.get_all_level_actors():
    label = actor.get_actor_label()
    cls_name = actor.get_class().get_name()
    loc = actor.get_actor_location()

    # Check for landscape (best ground)
    if "Landscape" in cls_name:
        ground_z = loc.z
        unreal.log(f"  Found Landscape at Z={loc.z}")
        break

    # Check for floor/ground actors
    if label in ("Floor", "ForestGround", "Ground"):
        ground_z = loc.z
        ground_actor = actor
        unreal.log(f"  Found '{label}' ({cls_name}) at Z={loc.z}")

if ground_z is None:
    ground_z = 0.0
    unreal.log(f"  No ground found, defaulting to Z=0")
else:
    unreal.log(f"  Ground surface Z = {ground_z}")

# ============================================================
#  STEP 2: CLEANUP previous script actors only
# ============================================================
cleanup_prefixes = ("TunnelTree_", "MidTree_", "BgTree_", "Rock_",
                    "ForestGround", "ForestMist", "ForestPlayerStart", "PCG_TestZone")
removed = 0
for actor in EL.get_all_level_actors():
    label = actor.get_actor_label()
    if label and label.startswith(cleanup_prefixes):
        EL.destroy_actor(actor)
        removed += 1
unreal.log(f"Cleanup: removed {removed} previous script actors")

# ============================================================
#  STEP 3: LOAD ALL 5 TREE SPECIES
# ============================================================
TREE_ASSETS = {
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

loaded_trees = {}
for species, paths in TREE_ASSETS.items():
    loaded_trees[species] = []
    for path in paths:
        mesh = EA.load_asset(path)
        if mesh:
            loaded_trees[species].append(mesh)
        else:
            unreal.log_warning(f"Could not load: {path}")

total_loaded = sum(len(v) for v in loaded_trees.values())
unreal.log(f"Loaded {total_loaded} tree meshes across {len(loaded_trees)} species")

ROCK_MESH_PATH = "/Game/Megaplant_Library/Mossy_Rocks/Mossy_Rocks_tjmudcfda_High"
rock_mesh = EA.load_asset(ROCK_MESH_PATH)
if rock_mesh:
    unreal.log("Loaded Mossy Rock mesh")

mesh_plane = EA.load_asset("/Engine/BasicShapes/Plane")

# ============================================================
#  STEP 4: LOAD/CREATE FOREST FLOOR MATERIAL
# ============================================================
FF_DEST = "/Game/Megaplant_Library/Forest_Floor"
ground_mat = None
try:
    ground_mat = EA.load_asset(f"{FF_DEST}/M_ForestFloor")
    if ground_mat:
        unreal.log("Loaded existing Forest Floor material")
except:
    pass

if not ground_mat:
    PROJECT_DIR = "G:/UE_5 Projects/HorrorTechDemo 5.7"
    FF_DIR = os.path.join(PROJECT_DIR, "Content", "Megaplant_Library", "Forest_Floor")
    tex_files = {
        "BaseColor": "Forest_Floor_sfjmafua_4K_BaseColor.jpg",
        "Normal":    "Forest_Floor_sfjmafua_4K_Normal.jpg",
        "Roughness": "Forest_Floor_sfjmafua_4K_Roughness.jpg",
    }
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    import_tasks = []
    for tex_name, filename in tex_files.items():
        src_path = os.path.join(FF_DIR, filename)
        if not os.path.exists(src_path):
            continue
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", src_path)
        task.set_editor_property("destination_path", FF_DEST)
        task.set_editor_property("destination_name", f"T_ForestFloor_{tex_name}")
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        import_tasks.append(task)
    if import_tasks:
        asset_tools.import_asset_tasks(import_tasks)

    tex_bc = EA.load_asset(f"{FF_DEST}/T_ForestFloor_BaseColor")
    tex_n = EA.load_asset(f"{FF_DEST}/T_ForestFloor_Normal")
    tex_r = EA.load_asset(f"{FF_DEST}/T_ForestFloor_Roughness")

    if tex_bc:
        try:
            mat_factory = unreal.MaterialFactoryNew()
            ground_mat = asset_tools.create_asset(
                "M_ForestFloor", FF_DEST, unreal.Material, mat_factory
            )
            mel = unreal.MaterialEditingLibrary
            node_bc = mel.create_material_expression(
                ground_mat, unreal.MaterialExpressionTextureSample, -400, -300)
            node_bc.texture = tex_bc
            mel.connect_material_property(node_bc, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
            if tex_n:
                node_n = mel.create_material_expression(
                    ground_mat, unreal.MaterialExpressionTextureSample, -400, 0)
                node_n.texture = tex_n
                node_n.sampler_type = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
                mel.connect_material_property(node_n, "RGB", unreal.MaterialProperty.MP_NORMAL)
            if tex_r:
                node_rr = mel.create_material_expression(
                    ground_mat, unreal.MaterialExpressionTextureSample, -400, 300)
                node_rr.texture = tex_r
                mel.connect_material_property(node_rr, "R", unreal.MaterialProperty.MP_ROUGHNESS)
            node_tc = mel.create_material_expression(
                ground_mat, unreal.MaterialExpressionTextureCoordinate, -700, -300)
            node_tc.set_editor_property("u_tiling", 50.0)
            node_tc.set_editor_property("v_tiling", 50.0)
            mel.connect_material_expressions(node_tc, "", node_bc, "UVs")
            if tex_n:
                mel.connect_material_expressions(node_tc, "", node_n, "UVs")
            if tex_r:
                mel.connect_material_expressions(node_tc, "", node_rr, "UVs")
            mel.recompile_material(ground_mat)
            unreal.log("Forest Floor material created")
        except Exception as e:
            unreal.log_warning(f"Material creation failed: {e}")
            ground_mat = None

# ============================================================
#  STEP 5: GROUND SETUP
#  - Modify existing template Floor if present
#  - Otherwise create a new ground plane
#  - Ground placed at detected ground_z
# ============================================================
unreal.log("=== Setting up ground ===")

# Try to find and modify the existing template Floor
floor_modified = False
for actor in EL.get_all_level_actors():
    label = actor.get_actor_label()
    if label == "Floor":
        actor.set_actor_label("ForestGround")
        actor.set_actor_scale3d(unreal.Vector(600, 600, 1))
        if ground_mat:
            try:
                actor.static_mesh_component.set_material(0, ground_mat)
            except:
                pass
        ground_z = actor.get_actor_location().z
        floor_modified = True
        unreal.log(f"Modified template Floor -> ForestGround (Z={ground_z})")
        break

if not floor_modified:
    ground = EL.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(0, 3000, ground_z))
    if ground:
        ground.set_actor_label("ForestGround")
        ground.static_mesh_component.set_static_mesh(mesh_plane)
        ground.set_actor_scale3d(unreal.Vector(600, 600, 1))
        if ground_mat:
            ground.static_mesh_component.set_material(0, ground_mat)
        unreal.log(f"Created ForestGround at Z={ground_z}")

# ============================================================
#  STEP 6: GROUND Z FINDER (line trace with fallback)
# ============================================================
def find_ground_at(x, y):
    """Line trace downward to find ground surface. Falls back to ground_z."""
    try:
        world = EL.get_editor_world()
        start = unreal.Vector(x, y, 50000.0)
        end = unreal.Vector(x, y, -50000.0)
        result = unreal.SystemLibrary.line_trace_single(
            world, start, end,
            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
            False, [],
            unreal.DrawDebugTrace.NONE,
            True
        )
        if isinstance(result, tuple) and result[0]:
            return result[1].impact_point.z
    except:
        pass
    return ground_z

# Test line trace once
test_z = find_ground_at(0.0, 0.0)
use_trace = (test_z != ground_z)
unreal.log(f"Line trace test: Z={test_z} (trace {'active' if use_trace else 'fallback to ' + str(ground_z)})")

def get_placement_z(x, y):
    """Get the Z position to place an object at (x, y) - always ON the ground."""
    if use_trace:
        return find_ground_at(x, y)
    return ground_z

# ============================================================
#  STEP 7: FOG
# ============================================================
try:
    fog = EL.spawn_actor_from_class(
        unreal.ExponentialHeightFog, unreal.Vector(0, 3000, ground_z + 30))
    if fog:
        fog.set_actor_label("ForestMist")
        fc = fog.component
        for prop, val in {
            "fog_density": 0.004,
            "fog_height_falloff": 0.15,
            "fog_max_opacity": 0.5,
            "start_distance": 500.0,
        }.items():
            try:
                fc.set_editor_property(prop, val)
            except:
                pass
        unreal.log("Forest fog placed")
except Exception as e:
    unreal.log_warning(f"Fog: {e}")

# ============================================================
#  STEP 8: PLAYER START
# ============================================================
try:
    ps = EL.spawn_actor_from_class(
        unreal.PlayerStart, unreal.Vector(0, -100, ground_z + 90))
    if ps:
        ps.set_actor_label("ForestPlayerStart")
        ps.set_actor_rotation(unreal.Rotator(0, 90, 0), False)
except:
    pass

# ============================================================
#  STEP 9: TREE PLACEMENT
# ============================================================
TUNNEL_LENGTH = 6000
TUNNEL_HALF_WIDTH = 280        # half the walkable path width
ROW_OFFSET = 120               # extra offset from path edge for tree trunks
FOREST_SPREAD = 3500
MIN_TREE_SPACING = 280
TOTAL_TREES = 80

placed_positions = []

def too_close(x, y, min_dist=MIN_TREE_SPACING):
    for px, py in placed_positions:
        dx, dy = x - px, y - py
        if (dx*dx + dy*dy) < (min_dist * min_dist):
            return True
    return False

all_meshes = []
for species, meshes in loaded_trees.items():
    for m in meshes:
        all_meshes.append((species, m))

if not all_meshes:
    unreal.log_error("No tree meshes loaded!")
else:
    trees_spawned = 0

    # ---- INNER TUNNEL TREES (dense rows lining the walkway) ----
    for i in range(20):
        side = -1 if i % 2 == 0 else 1
        row_index = i // 2
        y_pos = 100 + row_index * (TUNNEL_LENGTH / 11) + random.uniform(-40, 40)
        x_pos = side * (TUNNEL_HALF_WIDTH + ROW_OFFSET + random.uniform(0, 100))

        if too_close(x_pos, y_pos):
            continue

        species, skel_mesh = random.choice(all_meshes)
        z_pos = get_placement_z(x_pos, y_pos)
        yaw = random.uniform(0, 360)
        scale_factor = random.uniform(0.9, 1.15)
        # Very slight lean toward center (1-2 degrees max)
        lean = side * random.uniform(-2, -0.5)

        try:
            tree_actor = EL.spawn_actor_from_class(
                unreal.SkeletalMeshActor, unreal.Vector(x_pos, y_pos, z_pos))
            if tree_actor:
                tree_actor.set_actor_label(f"TunnelTree_{trees_spawned:03d}")
                tree_actor.skeletal_mesh_component.set_skinned_asset_and_update(skel_mesh)
                tree_actor.set_actor_scale3d(
                    unreal.Vector(scale_factor, scale_factor, scale_factor))
                tree_actor.set_actor_rotation(unreal.Rotator(0, yaw, lean), False)
                placed_positions.append((x_pos, y_pos))
                trees_spawned += 1
        except Exception as e:
            unreal.log_warning(f"TunnelTree error: {e}")

    tunnel_count = trees_spawned
    unreal.log(f"Inner tunnel: {tunnel_count} trees")

    # ---- MID-RANGE TREES ----
    mid_target = 30
    attempts = 0
    mid_spawned = 0
    while mid_spawned < mid_target and attempts < 500:
        attempts += 1
        side = random.choice([-1, 1])
        x_pos = side * random.uniform(TUNNEL_HALF_WIDTH + ROW_OFFSET + 150, 1500)
        y_pos = random.uniform(-300, TUNNEL_LENGTH + 300)

        if too_close(x_pos, y_pos):
            continue

        species, skel_mesh = random.choice(all_meshes)
        z_pos = get_placement_z(x_pos, y_pos)
        scale_factor = random.uniform(0.8, 1.3)

        try:
            tree_actor = EL.spawn_actor_from_class(
                unreal.SkeletalMeshActor, unreal.Vector(x_pos, y_pos, z_pos))
            if tree_actor:
                tree_actor.set_actor_label(f"MidTree_{trees_spawned:03d}")
                tree_actor.skeletal_mesh_component.set_skinned_asset_and_update(skel_mesh)
                tree_actor.set_actor_scale3d(
                    unreal.Vector(scale_factor, scale_factor, scale_factor))
                tree_actor.set_actor_rotation(
                    unreal.Rotator(0, random.uniform(0, 360), 0), False)
                placed_positions.append((x_pos, y_pos))
                trees_spawned += 1
                mid_spawned += 1
        except Exception as e:
            unreal.log_warning(f"MidTree error: {e}")

    unreal.log(f"Mid-range: {mid_spawned} trees")

    # ---- BACKGROUND TREES (surround the forest) ----
    bg_target = TOTAL_TREES - trees_spawned
    attempts = 0
    bg_spawned = 0
    while bg_spawned < bg_target and attempts < 1000:
        attempts += 1
        angle = random.uniform(0, math.pi * 2)
        dist = random.uniform(1500, FOREST_SPREAD)
        x_pos = math.cos(angle) * dist
        y_pos = TUNNEL_LENGTH / 2 + math.sin(angle) * dist

        if too_close(x_pos, y_pos, 220):
            continue

        species, skel_mesh = random.choice(all_meshes)
        z_pos = get_placement_z(x_pos, y_pos)
        scale_factor = random.uniform(0.7, 1.4)

        try:
            tree_actor = EL.spawn_actor_from_class(
                unreal.SkeletalMeshActor, unreal.Vector(x_pos, y_pos, z_pos))
            if tree_actor:
                tree_actor.set_actor_label(f"BgTree_{trees_spawned:03d}")
                tree_actor.skeletal_mesh_component.set_skinned_asset_and_update(skel_mesh)
                tree_actor.set_actor_scale3d(
                    unreal.Vector(scale_factor, scale_factor, scale_factor))
                tree_actor.set_actor_rotation(
                    unreal.Rotator(0, random.uniform(0, 360), 0), False)
                placed_positions.append((x_pos, y_pos))
                trees_spawned += 1
                bg_spawned += 1
        except Exception as e:
            unreal.log_warning(f"BgTree error: {e}")

    unreal.log(f"Background: {bg_spawned} trees")
    unreal.log(f"TOTAL TREES: {trees_spawned}")

# ============================================================
#  STEP 10: MOSSY ROCKS
# ============================================================
rocks_spawned = 0
if rock_mesh:
    ROCK_COUNT = 25
    attempts = 0
    while rocks_spawned < ROCK_COUNT and attempts < 300:
        attempts += 1
        x_pos = random.uniform(-1200, 1200)
        y_pos = random.uniform(-100, TUNNEL_LENGTH + 100)

        z_pos = get_placement_z(x_pos, y_pos) - random.uniform(3, 10)
        scale_factor = random.uniform(0.4, 1.8)

        try:
            rock_actor = EL.spawn_actor_from_class(
                unreal.StaticMeshActor, unreal.Vector(x_pos, y_pos, z_pos))
            if rock_actor:
                rock_actor.set_actor_label(f"Rock_{rocks_spawned:03d}")
                rock_actor.static_mesh_component.set_static_mesh(rock_mesh)
                rock_actor.set_actor_scale3d(
                    unreal.Vector(scale_factor, scale_factor, scale_factor))
                rock_actor.set_actor_rotation(
                    unreal.Rotator(random.uniform(-8, 8),
                                   random.uniform(0, 360),
                                   random.uniform(-8, 8)), False)
                rocks_spawned += 1
        except Exception as e:
            unreal.log_warning(f"Rock error: {e}")

    unreal.log(f"Placed {rocks_spawned} rocks")

# ============================================================
#  STEP 11: PCG VOLUME
# ============================================================
try:
    pcg_class = unreal.load_class(None, "/Script/PCG.PCGVolume")
    pcg_actor = EL.spawn_actor_from_class(
        pcg_class, unreal.Vector(0, 3000, ground_z))
    if pcg_actor:
        pcg_actor.set_actor_label("PCG_TestZone")
        pcg_actor.set_actor_scale3d(unreal.Vector(10, 40, 5))
        unreal.log("PCG Volume placed")
except:
    unreal.log_warning("Could not spawn PCGVolume")

# ============================================================
#  DONE
# ============================================================
unreal.log("")
unreal.log("=" * 60)
unreal.log("  FOREST DEMO READY!")
unreal.log(f"  Ground Z = {ground_z}")
unreal.log(f"  {trees_spawned} trees | {rocks_spawned} rocks")
unreal.log(f"  Line trace: {'active' if use_trace else 'fallback'}")
unreal.log("  Lighting: untouched (from level template)")
unreal.log("")
unreal.log("  TIP: For terrain depth, switch to Landscape Mode")
unreal.log("  and create a landscape. Then re-run this script -")
unreal.log("  it will detect the landscape and place trees on it.")
unreal.log("=" * 60)

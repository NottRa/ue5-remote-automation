"""Composition intelligence: professional forest layout generation.
Encodes level design knowledge for natural-looking placement.
Uses Poisson disc sampling, asymmetric clustering, and layer hierarchy.
Runs OUTSIDE UE5."""

import math
import random
import sys
import os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    TREE_SPECIES, ROCK_MESH, LAYER_ORDER, MIN_TREE_SPECIES,
    SCALE_RANGE, YAW_RANGE, LEAN_RANGE,
    CLUSTER_PRIMARY_RANGE, CLUSTER_SECONDARY_RANGE, CLUSTER_TERTIARY_RANGE,
    EDGE_TRANSITION_CM, POISSON_DISC_MIN_DISTANCE,
)


# ---------------------------------------------------------------------------
# Asset Catalog
# ---------------------------------------------------------------------------

@dataclass
class AssetSpec:
    name: str
    mesh_path: str
    asset_type: str       # "tree", "rock", "ground_cover"
    species: str
    layer: str            # from LAYER_ORDER
    typical_height_cm: float = 0
    typical_radius_cm: float = 0


def build_asset_catalog():
    """Build the full asset catalog from config."""
    catalog = {}

    # Trees (skeletal mesh, canopy layer)
    for species, paths in TREE_SPECIES.items():
        for i, path in enumerate(paths):
            key = f"{species}_{chr(65+i)}"  # Beech_A, Beech_B, etc.
            catalog[key] = AssetSpec(
                name=key,
                mesh_path=path,
                asset_type="tree",
                species=species,
                layer="canopy",
                typical_height_cm=1500,
                typical_radius_cm=300,
            )

    # Rocks (static mesh, ground_cover layer)
    catalog["MossyRock"] = AssetSpec(
        name="MossyRock",
        mesh_path=ROCK_MESH,
        asset_type="rock",
        species="N/A",
        layer="ground_cover",
        typical_height_cm=60,
        typical_radius_cm=80,
    )

    return catalog


ASSET_CATALOG = build_asset_catalog()


# ---------------------------------------------------------------------------
# Poisson Disc Sampling
# ---------------------------------------------------------------------------

def poisson_disc_sample(bounds, min_distance, max_attempts=30):
    """Generate well-spaced random points using Poisson disc sampling.
    bounds: {"x_min", "x_max", "y_min", "y_max"}
    Returns: list of (x, y) tuples."""
    x_min, x_max = bounds['x_min'], bounds['x_max']
    y_min, y_max = bounds['y_min'], bounds['y_max']
    width = x_max - x_min
    height = y_max - y_min

    cell_size = min_distance / math.sqrt(2)
    cols = max(1, int(math.ceil(width / cell_size)))
    rows = max(1, int(math.ceil(height / cell_size)))

    grid = [[None] * cols for _ in range(rows)]
    points = []
    active = []

    def grid_coords(x, y):
        return (int((x - x_min) / cell_size),
                int((y - y_min) / cell_size))

    def is_valid(x, y):
        if x < x_min or x > x_max or y < y_min or y > y_max:
            return False
        gx, gy = grid_coords(x, y)
        # Check neighborhood
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                nx, ny = gx + dx, gy + dy
                if 0 <= nx < cols and 0 <= ny < rows:
                    neighbor = grid[ny][nx]
                    if neighbor is not None:
                        px, py = neighbor
                        if (px - x) ** 2 + (py - y) ** 2 < min_distance ** 2:
                            return False
        return True

    # Start with a random seed point
    sx = random.uniform(x_min, x_max)
    sy = random.uniform(y_min, y_max)
    gx, gy = grid_coords(sx, sy)
    grid[gy][gx] = (sx, sy)
    points.append((sx, sy))
    active.append((sx, sy))

    while active:
        idx = random.randint(0, len(active) - 1)
        cx, cy = active[idx]
        found = False

        for _ in range(max_attempts):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(min_distance, 2 * min_distance)
            nx = cx + dist * math.cos(angle)
            ny = cy + dist * math.sin(angle)

            if is_valid(nx, ny):
                gx, gy = grid_coords(nx, ny)
                if 0 <= gx < cols and 0 <= gy < rows:
                    grid[gy][gx] = (nx, ny)
                    points.append((nx, ny))
                    active.append((nx, ny))
                    found = True
                    break

        if not found:
            active.pop(idx)

    return points


# ---------------------------------------------------------------------------
# Cluster Generation
# ---------------------------------------------------------------------------

@dataclass
class PlacementSpec:
    label: str
    mesh_path: str
    asset_type: str
    species: str
    layer: str
    x: float
    y: float
    z: float = 0         # filled by line trace
    pitch: float = 0
    yaw: float = 0
    roll: float = 0
    scale_x: float = 1
    scale_y: float = 1
    scale_z: float = 1
    cluster_id: str = ""
    needs_ground_trace: bool = True


def generate_cluster(center, primary_species, available_species,
                     cluster_id="", density="medium"):
    """Generate a natural-looking tree cluster.
    Returns list of PlacementSpec."""
    placements = []

    # Determine cluster sizes based on density
    if density == "dense":
        primary_count = random.randint(*CLUSTER_PRIMARY_RANGE)
        secondary_count = random.randint(*CLUSTER_SECONDARY_RANGE)
        tertiary_count = random.randint(*CLUSTER_TERTIARY_RANGE)
    elif density == "sparse":
        primary_count = random.randint(2, 4)
        secondary_count = random.randint(1, 2)
        tertiary_count = random.randint(0, 1)
    else:  # medium
        primary_count = random.randint(3, 5)
        secondary_count = random.randint(1, 3)
        tertiary_count = random.randint(1, 2)

    cx, cy = center

    # Primary group: tight cluster of primary species
    primary_positions = _jitter_positions(cx, cy, primary_count,
                                          spread=200, min_dist=100)
    primary_assets = list(TREE_SPECIES.get(primary_species, []))
    for i, (px, py) in enumerate(primary_positions):
        mesh = random.choice(primary_assets) if primary_assets else ""
        spec = _make_tree_spec(
            f"cluster_{cluster_id}_P{i:02d}", mesh, primary_species,
            px, py, cluster_id)
        placements.append(spec)

    # Secondary groups: offset from primary, mix species
    secondary_species = [s for s in available_species if s != primary_species]
    if not secondary_species:
        secondary_species = [primary_species]

    for sg in range(random.randint(1, 2)):
        offset_angle = random.uniform(0, 2 * math.pi)
        offset_dist = random.uniform(300, 800)
        sg_cx = cx + offset_dist * math.cos(offset_angle)
        sg_cy = cy + offset_dist * math.sin(offset_angle)
        sp = random.choice(secondary_species)
        sg_positions = _jitter_positions(sg_cx, sg_cy, secondary_count,
                                         spread=150, min_dist=80)
        sg_assets = list(TREE_SPECIES.get(sp, []))
        for i, (px, py) in enumerate(sg_positions):
            mesh = random.choice(sg_assets) if sg_assets else ""
            spec = _make_tree_spec(
                f"cluster_{cluster_id}_S{sg}_{i:02d}", mesh, sp,
                px, py, cluster_id)
            placements.append(spec)

    # Tertiary: scattered individuals
    for i in range(tertiary_count):
        offset_angle = random.uniform(0, 2 * math.pi)
        offset_dist = random.uniform(500, 1500)
        tx = cx + offset_dist * math.cos(offset_angle)
        ty = cy + offset_dist * math.sin(offset_angle)
        sp = random.choice(available_species)
        t_assets = list(TREE_SPECIES.get(sp, []))
        mesh = random.choice(t_assets) if t_assets else ""
        spec = _make_tree_spec(
            f"cluster_{cluster_id}_T{i:02d}", mesh, sp,
            tx, ty, cluster_id)
        placements.append(spec)

    return placements


def _jitter_positions(cx, cy, count, spread=200, min_dist=80):
    """Generate jittered positions around a center with minimum spacing."""
    positions = []
    for _ in range(count * 10):  # max attempts
        if len(positions) >= count:
            break
        angle = random.uniform(0, 2 * math.pi)
        dist = random.gauss(0, spread / 2)
        dist = max(-spread, min(spread, dist))
        px = cx + dist * math.cos(angle)
        py = cy + dist * math.sin(angle)

        # Check min distance
        too_close = False
        for ex, ey in positions:
            if (px - ex) ** 2 + (py - ey) ** 2 < min_dist ** 2:
                too_close = True
                break
        if not too_close:
            positions.append((px, py))

    return positions


def _make_tree_spec(label, mesh_path, species, x, y, cluster_id):
    """Create a PlacementSpec for a tree with randomized variation."""
    scale_base = random.gauss(1.0, 0.1)
    scale_base = max(SCALE_RANGE[0], min(SCALE_RANGE[1], scale_base))
    # Slight scale variation between axes for natural look
    sx = scale_base * random.uniform(0.97, 1.03)
    sy = scale_base * random.uniform(0.97, 1.03)
    sz = scale_base * random.uniform(0.98, 1.02)

    yaw = random.uniform(*YAW_RANGE)
    pitch = random.gauss(0, 1.5)
    pitch = max(LEAN_RANGE[0], min(LEAN_RANGE[1], pitch))
    roll = random.gauss(0, 1.5)
    roll = max(LEAN_RANGE[0], min(LEAN_RANGE[1], roll))

    return PlacementSpec(
        label=label, mesh_path=mesh_path,
        asset_type="tree", species=species, layer="canopy",
        x=x, y=y, pitch=pitch, yaw=yaw, roll=roll,
        scale_x=sx, scale_y=sy, scale_z=sz,
        cluster_id=cluster_id, needs_ground_trace=True,
    )


# ---------------------------------------------------------------------------
# Zone Composition Planning
# ---------------------------------------------------------------------------

def plan_zone_composition(zone, existing_assets=None, density=None):
    """Generate a full placement plan for a zone.
    Returns list of PlacementSpec ordered by layer (bottom-up)."""
    if existing_assets is None:
        existing_assets = []
    if density is None:
        density = zone.get('target_density', 'medium')

    bounds = zone['bounds']
    zone_id = zone['zone_id']
    target_layers = zone.get('target_layers', ['canopy'])

    all_placements = []

    # Determine species mix (min 3 for variety)
    available_species = list(TREE_SPECIES.keys())
    random.shuffle(available_species)
    species_pool = available_species[:max(MIN_TREE_SPECIES, len(available_species))]

    # Generate cluster centers via Poisson disc
    min_dist = {
        "dense": POISSON_DISC_MIN_DISTANCE * 2,
        "medium": POISSON_DISC_MIN_DISTANCE * 3,
        "sparse": POISSON_DISC_MIN_DISTANCE * 5,
    }.get(density, POISSON_DISC_MIN_DISTANCE * 3)

    cluster_centers = poisson_disc_sample(bounds, min_dist)

    # Assign species to clusters in rotation
    for i, (cx, cy) in enumerate(cluster_centers):
        primary_sp = species_pool[i % len(species_pool)]
        cid = f"{zone_id}_C{i:03d}"
        cluster_placements = generate_cluster(
            (cx, cy), primary_sp, species_pool,
            cluster_id=cid, density=density)

        # Set proper labels with zone prefix
        for j, p in enumerate(cluster_placements):
            p.label = f"Agent_{zone_id}_{i:03d}_{j:02d}"

        all_placements.extend(cluster_placements)

    # Add rocks at ground_cover layer
    if "ground_cover" in target_layers:
        rock_placements = _plan_rocks(bounds, zone_id, density,
                                       len(cluster_centers))
        all_placements.extend(rock_placements)

    # Filter out positions that overlap with existing assets
    existing_positions = [(a.get('location', [0, 0])[0],
                           a.get('location', [0, 0])[1])
                          if isinstance(a, dict) else (a.location[0], a.location[1])
                          for a in existing_assets]
    all_placements = _filter_overlaps(all_placements, existing_positions)

    # Enforce variation rules
    all_placements = enforce_variation(all_placements)

    # Sort by layer order (bottom-up)
    layer_priority = {l: i for i, l in enumerate(LAYER_ORDER)}
    all_placements.sort(key=lambda p: layer_priority.get(p.layer, 99))

    return all_placements


def _plan_rocks(bounds, zone_id, density, cluster_count):
    """Plan rock placements for ground cover layer."""
    rock_count = {
        "dense": max(3, cluster_count),
        "medium": max(2, cluster_count // 2),
        "sparse": max(1, cluster_count // 3),
    }.get(density, 2)

    positions = poisson_disc_sample(bounds, POISSON_DISC_MIN_DISTANCE * 1.5)
    positions = positions[:rock_count]

    rocks = []
    for i, (x, y) in enumerate(positions):
        scale = random.uniform(0.4, 1.8)
        rocks.append(PlacementSpec(
            label=f"Agent_{zone_id}_Rock_{i:03d}",
            mesh_path=ROCK_MESH,
            asset_type="rock",
            species="N/A",
            layer="ground_cover",
            x=x, y=y,
            z=-random.uniform(3, 10),  # partially buried
            pitch=random.uniform(-5, 5),
            yaw=random.uniform(0, 360),
            roll=random.uniform(-5, 5),
            scale_x=scale, scale_y=scale * random.uniform(0.8, 1.2),
            scale_z=scale * random.uniform(0.7, 1.0),
            needs_ground_trace=True,
        ))

    return rocks


def _filter_overlaps(placements, existing_positions, min_dist=100):
    """Remove placements that are too close to existing assets."""
    filtered = []
    for p in placements:
        too_close = False
        for ex, ey in existing_positions:
            if (p.x - ex) ** 2 + (p.y - ey) ** 2 < min_dist ** 2:
                too_close = True
                break
        if not too_close:
            filtered.append(p)
            existing_positions.append((p.x, p.y))
    return filtered


def enforce_variation(placements):
    """Post-process to ensure variation rules are met."""
    if not placements:
        return placements

    # Check species diversity among trees
    tree_placements = [p for p in placements if p.asset_type == "tree"]
    species_used = set(p.species for p in tree_placements)

    if len(species_used) < MIN_TREE_SPECIES and tree_placements:
        # Add species variety by reassigning some trees
        all_species = list(TREE_SPECIES.keys())
        missing = [s for s in all_species if s not in species_used]
        for sp in missing[:MIN_TREE_SPECIES - len(species_used)]:
            # Pick a random tree to reassign
            if tree_placements:
                target = random.choice(tree_placements)
                target.species = sp
                sp_meshes = TREE_SPECIES.get(sp, [])
                if sp_meshes:
                    target.mesh_path = random.choice(sp_meshes)

    # Ensure no two adjacent trees have identical species + similar scale
    for i in range(len(tree_placements) - 1):
        a, b = tree_placements[i], tree_placements[i + 1]
        dist = math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)
        if (dist < 300 and a.species == b.species
                and abs(a.scale_x - b.scale_x) < 0.05):
            # Vary the scale of the second tree
            b.scale_x *= random.choice([0.85, 1.15])
            b.scale_y *= random.choice([0.85, 1.15])
            b.scale_z *= random.choice([0.9, 1.1])

    return placements


def get_placement_order(placements):
    """Return assets in layer order: ground_cover → ... → canopy."""
    layer_priority = {l: i for i, l in enumerate(LAYER_ORDER)}
    return sorted(placements, key=lambda p: layer_priority.get(p.layer, 99))

"""Scene manifest: JSON ground truth for all placed assets.
Updated after every verified placement. Provides compressed view for context.
Runs OUTSIDE UE5."""

import json
import math
import os
import time
import sys
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    MANIFEST_PATH, MANIFEST_COMPRESSED_PATH, ZONE_SUMMARIES_DIR,
    DEFAULT_ZONES, ensure_dirs,
)


@dataclass
class AssetEntry:
    label: str
    mesh_path: str
    asset_type: str          # "tree", "rock", "ground_cover", "atmosphere"
    species: str             # "Beech", "Maple", etc. or "N/A"
    location: list           # [x, y, z]
    rotation: list           # [pitch, yaw, roll]
    scale: list              # [sx, sy, sz]
    zone_id: str
    layer: str               # from LAYER_ORDER
    placed_at: str = ""      # ISO timestamp
    verified: bool = False
    verification_method: str = ""  # "programmatic", "visual", "both"
    cluster_id: str = ""
    notes: str = ""


@dataclass
class ZoneDefinition:
    zone_id: str
    label: str
    bounds: dict             # {"x_min", "x_max", "y_min", "y_max"}
    center: list             # [x, y, z]
    target_density: str      # "sparse", "medium", "dense"
    target_layers: list      # which layers apply here
    status: str = "pending"  # "pending", "in_progress", "complete", "blocked"
    summary: str = ""
    asset_count: int = 0


@dataclass
class SceneManifest:
    version: int = 1
    scene_name: str = "ForestLevel"
    created_at: str = ""
    updated_at: str = ""
    zones: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    total_placed: int = 0
    total_verified: int = 0
    session_id: str = ""


class ManifestManager:
    """Manages the scene manifest: load, save, update, compress."""

    def __init__(self, manifest_path=MANIFEST_PATH):
        self.manifest_path = manifest_path
        self.manifest = SceneManifest()

    def load(self):
        """Load manifest from disk. Create empty if not found."""
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'r') as f:
                data = json.load(f)
            self.manifest = SceneManifest(
                version=data.get('version', 1),
                scene_name=data.get('scene_name', 'ForestLevel'),
                created_at=data.get('created_at', ''),
                updated_at=data.get('updated_at', ''),
                total_placed=data.get('total_placed', 0),
                total_verified=data.get('total_verified', 0),
                session_id=data.get('session_id', ''),
            )
            self.manifest.zones = [
                ZoneDefinition(**z) for z in data.get('zones', [])
            ]
            self.manifest.assets = [
                AssetEntry(**a) for a in data.get('assets', [])
            ]
        else:
            self.manifest = SceneManifest(
                created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
        return self.manifest

    def save(self):
        """Save full manifest to disk (Tier 3)."""
        ensure_dirs()
        self.manifest.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        data = {
            'version': self.manifest.version,
            'scene_name': self.manifest.scene_name,
            'created_at': self.manifest.created_at,
            'updated_at': self.manifest.updated_at,
            'total_placed': self.manifest.total_placed,
            'total_verified': self.manifest.total_verified,
            'session_id': self.manifest.session_id,
            'zones': [asdict(z) for z in self.manifest.zones],
            'assets': [asdict(a) for a in self.manifest.assets],
        }
        with open(self.manifest_path, 'w') as f:
            json.dump(data, f, indent=2)

    def add_asset(self, entry):
        """Add a verified asset to the manifest. Saves immediately."""
        if not entry.placed_at:
            entry.placed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.manifest.assets.append(entry)
        self.manifest.total_placed += 1
        if entry.verified:
            self.manifest.total_verified += 1
        # Update zone asset count
        for zone in self.manifest.zones:
            if zone.zone_id == entry.zone_id:
                zone.asset_count += 1
                break
        self.save()

    def remove_asset(self, label):
        """Remove an asset (after rollback). Saves immediately."""
        for i, a in enumerate(self.manifest.assets):
            if a.label == label:
                removed = self.manifest.assets.pop(i)
                self.manifest.total_placed -= 1
                if removed.verified:
                    self.manifest.total_verified -= 1
                for zone in self.manifest.zones:
                    if zone.zone_id == removed.zone_id:
                        zone.asset_count = max(0, zone.asset_count - 1)
                        break
                self.save()
                return True
        return False

    def update_asset(self, label, **kwargs):
        """Update fields on an existing asset."""
        for asset in self.manifest.assets:
            if asset.label == label:
                for key, value in kwargs.items():
                    if hasattr(asset, key):
                        setattr(asset, key, value)
                self.save()
                return True
        return False

    def update_zone_status(self, zone_id, status, summary=""):
        """Update zone status and summary."""
        for zone in self.manifest.zones:
            if zone.zone_id == zone_id:
                zone.status = status
                if summary:
                    zone.summary = summary
                self.save()
                return True
        return False

    def get_zone(self, zone_id):
        """Get zone definition by ID."""
        for zone in self.manifest.zones:
            if zone.zone_id == zone_id:
                return zone
        return None

    def get_assets_in_zone(self, zone_id):
        """Get all assets in a zone."""
        return [a for a in self.manifest.assets if a.zone_id == zone_id]

    def get_nearby_assets(self, x, y, radius):
        """Get all assets within radius of (x, y)."""
        result = []
        for a in self.manifest.assets:
            ax, ay = a.location[0], a.location[1]
            dist = math.sqrt((ax - x) ** 2 + (ay - y) ** 2)
            if dist <= radius:
                result.append(a)
        return result

    # --- Compression for Tier 1 ---

    def compress(self):
        """Generate compressed manifest for in-context use (~3-8K tokens)."""
        lines = []
        total = self.manifest.total_placed
        verified = self.manifest.total_verified
        zone_complete = sum(1 for z in self.manifest.zones if z.status == "complete")
        zone_total = len(self.manifest.zones)
        lines.append(f"# Scene: {self.manifest.scene_name} | "
                      f"{total} assets ({verified} verified) | "
                      f"{zone_complete}/{zone_total} zones complete")
        lines.append("")

        # Zone summaries
        lines.append("## Zones:")
        for zone in self.manifest.zones:
            status_tag = zone.status.upper()
            summary = zone.summary or f"{zone.asset_count} assets placed"
            lines.append(f"- {zone.zone_id} [{status_tag}] ({zone.label}): {summary}")
        lines.append("")

        # Recent assets (last 5)
        recent = self.manifest.assets[-5:] if self.manifest.assets else []
        if recent:
            lines.append("## Recent placements:")
            for a in reversed(recent):
                loc = f"({a.location[0]:.0f}, {a.location[1]:.0f}, {a.location[2]:.0f})"
                v = "verified" if a.verified else "unverified"
                lines.append(f"- {a.label}: {a.species} {a.asset_type} at {loc}, "
                              f"scale {a.scale[0]:.2f}, {v}")
            lines.append("")

        # Coverage gaps
        gaps = []
        for zone in self.manifest.zones:
            if zone.status in ("pending", "in_progress"):
                placed_layers = set()
                for a in self.manifest.assets:
                    if a.zone_id == zone.zone_id:
                        placed_layers.add(a.layer)
                missing = [l for l in zone.target_layers if l not in placed_layers]
                if missing:
                    gaps.append(f"- {zone.zone_id}: needs {', '.join(missing)}")
        if gaps:
            lines.append("## Coverage gaps:")
            lines.extend(gaps)

        return "\n".join(lines)

    def save_compressed(self):
        """Save compressed manifest to disk and return the string."""
        ensure_dirs()
        text = self.compress()
        with open(MANIFEST_COMPRESSED_PATH, 'w') as f:
            f.write(text)
        return text

    def save_zone_summary(self, zone_id):
        """Save per-zone detailed summary (Tier 2)."""
        ensure_dirs()
        zone = self.get_zone(zone_id)
        if zone is None:
            return
        assets = self.get_assets_in_zone(zone_id)
        data = {
            "zone": asdict(zone),
            "assets": [asdict(a) for a in assets],
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        path = os.path.join(ZONE_SUMMARIES_DIR, f"{zone_id}.json")
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    # --- Reconciliation ---

    def reconcile_with_ue5(self):
        """Compare manifest against actual UE5 actors.
        Returns: {"missing_in_ue5": [...], "missing_in_manifest": [...], "matched": int}"""
        from ue_commands import query_actors_by_prefix
        result = query_actors_by_prefix("Agent")
        if not result or not result.get('success'):
            return {"error": "Failed to query UE5 actors",
                    "missing_in_ue5": [], "missing_in_manifest": [], "matched": 0}

        ue5_labels = {a['label'] for a in result.get('actors', [])}
        manifest_labels = {a.label for a in self.manifest.assets}

        missing_in_ue5 = list(manifest_labels - ue5_labels)
        missing_in_manifest = list(ue5_labels - manifest_labels)
        matched = len(manifest_labels & ue5_labels)

        return {
            "missing_in_ue5": missing_in_ue5,
            "missing_in_manifest": missing_in_manifest,
            "matched": matched,
        }

    # --- Initialization ---

    def initialize_zones(self, zone_definitions=None):
        """Set up zone definitions for a new scene build."""
        if zone_definitions is None:
            zone_definitions = DEFAULT_ZONES

        self.manifest.zones = []
        for zd in zone_definitions:
            self.manifest.zones.append(ZoneDefinition(
                zone_id=zd["zone_id"],
                label=zd["label"],
                bounds=zd["bounds"],
                center=zd["center"],
                target_density=zd["target_density"],
                target_layers=zd["target_layers"],
            ))
        self.save()

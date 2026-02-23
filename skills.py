"""Skill library: pattern extraction and accumulation across sessions.
The outer loop of the dual-loop architecture.
Runs OUTSIDE UE5."""

import json
import os
import time
import sys
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SKILLS_DIR, ensure_dirs


@dataclass
class Skill:
    skill_id: str
    name: str
    description: str
    pattern: dict           # extracted pattern data
    success_rate: float = 1.0
    times_used: int = 0
    created_at: str = ""
    last_used: str = ""


class SkillLibrary:
    """Manages learned skills from successful placements."""

    def __init__(self, skills_dir=SKILLS_DIR):
        self.skills_dir = skills_dir
        self.skills = []

    def load(self):
        """Load all skills from disk."""
        ensure_dirs()
        self.skills = []
        skills_file = os.path.join(self.skills_dir, "skills.json")
        if os.path.exists(skills_file):
            with open(skills_file, 'r') as f:
                data = json.load(f)
            self.skills = [Skill(**s) for s in data]

    def save(self):
        """Save all skills to disk."""
        ensure_dirs()
        skills_file = os.path.join(self.skills_dir, "skills.json")
        with open(skills_file, 'w') as f:
            json.dump([asdict(s) for s in self.skills], f, indent=2)

    def extract_patterns(self, decision_log):
        """Analyze session history and extract reusable patterns.

        Looks for:
        - Successful cluster configurations (species mix, spacing, scale)
        - Effective auto-fixes (which adjustments work for which issues)
        - Zone composition recipes that scored well in reviews

        Args:
            decision_log: list of operation dicts from memory manager

        Returns: list of newly extracted skills.
        """
        new_skills = []

        # Pattern 1: Successful species combinations per zone type
        zone_species = {}
        for entry in decision_log:
            if (entry.get('action') == 'spawn'
                    and entry.get('result') == 'success'):
                details = entry.get('details', {})
                zone = details.get('zone', 'unknown')
                species = details.get('species', '')
                if zone and species:
                    zone_species.setdefault(zone, []).append(species)

        for zone, species_list in zone_species.items():
            if len(species_list) >= 5:
                # Count species frequency
                from collections import Counter
                counts = Counter(species_list)
                top_3 = counts.most_common(3)
                skill = Skill(
                    skill_id=f"species_mix_{zone}",
                    name=f"Species mix for {zone}",
                    description=f"Successful species distribution in {zone}",
                    pattern={
                        "zone_type": zone,
                        "species_distribution": dict(top_3),
                        "total_placed": len(species_list),
                    },
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
                new_skills.append(skill)

        # Pattern 2: Common auto-fix patterns
        fix_counts = {}
        for entry in decision_log:
            details = entry.get('details', {})
            auto_fixes = details.get('auto_fixes', [])
            for fix in auto_fixes:
                fix_type = fix if isinstance(fix, str) else str(fix)
                fix_counts[fix_type] = fix_counts.get(fix_type, 0) + 1

        for fix_type, count in fix_counts.items():
            if count >= 3:
                skill = Skill(
                    skill_id=f"autofix_{hash(fix_type) % 10000:04d}",
                    name=f"Common fix: {fix_type[:50]}",
                    description=f"Auto-fix applied {count} times",
                    pattern={"fix_type": fix_type, "frequency": count},
                    times_used=count,
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
                new_skills.append(skill)

        # Merge with existing skills (update if same ID, add if new)
        existing_ids = {s.skill_id for s in self.skills}
        for skill in new_skills:
            if skill.skill_id in existing_ids:
                for s in self.skills:
                    if s.skill_id == skill.skill_id:
                        s.pattern = skill.pattern
                        s.times_used = skill.times_used
                        s.last_used = skill.created_at
                        break
            else:
                self.skills.append(skill)

        self.save()
        return new_skills

    def get_relevant_skills(self, context):
        """Find skills relevant to the current placement context.
        context: {"zone_type": str, "layer": str, "species": str}"""
        relevant = []
        zone = context.get('zone_type', '')
        for skill in self.skills:
            pattern = skill.pattern
            if pattern.get('zone_type', '') == zone:
                relevant.append(skill)
        return relevant

    def update_skill_stats(self, skill_id, success):
        """Update usage count and success rate for a skill."""
        for skill in self.skills:
            if skill.skill_id == skill_id:
                skill.times_used += 1
                skill.last_used = time.strftime("%Y-%m-%dT%H:%M:%S")
                # Rolling average success rate
                n = skill.times_used
                skill.success_rate = ((skill.success_rate * (n - 1)
                                       + (1.0 if success else 0.0)) / n)
                self.save()
                return

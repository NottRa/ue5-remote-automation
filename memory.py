"""Three-tier memory management for the autonomous agent.
Tier 1: In-context (~15K tokens, always present)
Tier 2: On-disk, loadable on demand (zone summaries, decision log)
Tier 3: Full archive (complete manifest, all screenshots, full history)
Runs OUTSIDE UE5."""

import json
import os
import time
import sys
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    DECISION_LOG_PATH, HISTORY_DIR, SCREENSHOTS_DIR, ZONE_SUMMARIES_DIR,
    SLIDING_WINDOW_OPS, MAX_IMAGES_IN_CONTEXT, CONTEXT_BUDGET_TOKENS,
    CONTEXT_OFFLOAD_THRESHOLD, ensure_dirs,
)


@dataclass
class OperationRecord:
    op_id: int
    timestamp: str
    state: str               # agent state when this happened
    action: str              # "spawn", "verify", "adjust", "rollback", "survey"
    asset_label: str
    details: dict            # action-specific details
    result: str              # "success", "failed", "rolled_back"
    token_estimate: int = 0  # estimated tokens for this record

    def to_summary(self):
        """One-line summary for compressed context."""
        return (f"[{self.action}] {self.asset_label}: {self.result} "
                f"({self.details.get('zone', '')}, {self.details.get('species', '')})")


class MemoryManager:
    """Manages the three-tier memory system."""

    def __init__(self):
        self.system_prompt = ""
        self.scene_brief = ""
        self.compressed_manifest = ""
        self.current_asset = {}
        self.recent_operations = []    # Tier 1 sliding window
        self.images = []               # base64 strings, max MAX_IMAGES_IN_CONTEXT
        self.image_descriptions = []   # what each image shows
        self.operation_counter = 0
        self.all_operations = []       # Tier 2 buffer
        self._decision_log = []        # Tier 2 on-disk

    # --- Tier 1: In-Context ---

    def set_system_prompt(self, prompt):
        """Set the static system prompt."""
        self.system_prompt = prompt

    def set_scene_brief(self, brief):
        """Set the scene brief text."""
        self.scene_brief = brief

    def update_manifest(self, compressed_text):
        """Update the compressed manifest in context."""
        self.compressed_manifest = compressed_text

    def set_current_asset(self, asset_info):
        """Set the current asset being worked on."""
        self.current_asset = asset_info

    def add_operation(self, state, action, asset_label, details, result):
        """Record a new operation. Maintains sliding window in Tier 1,
        persists to Tier 2/3."""
        self.operation_counter += 1
        op = OperationRecord(
            op_id=self.operation_counter,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            state=state,
            action=action,
            asset_label=asset_label,
            details=details,
            result=result,
            token_estimate=self._estimate_tokens(json.dumps(details)),
        )

        # Tier 1: sliding window
        self.recent_operations.append(op)
        while len(self.recent_operations) > SLIDING_WINDOW_OPS:
            evicted = self.recent_operations.pop(0)
            self.all_operations.append(evicted)

        # Tier 2/3: persist
        self._save_operation(op)

        # Check context budget
        if self.estimated_tokens > CONTEXT_BUDGET_TOKENS * CONTEXT_OFFLOAD_THRESHOLD:
            self._offload_to_tier2()

        return op

    def set_images(self, images, descriptions=None):
        """Replace current images in context.
        images: list of {"b64": str, "media_type": str}
        descriptions: list of str describing each image."""
        self.images = images[:MAX_IMAGES_IN_CONTEXT]
        if descriptions:
            self.image_descriptions = descriptions[:MAX_IMAGES_IN_CONTEXT]
        else:
            self.image_descriptions = [f"Image {i+1}" for i in range(len(self.images))]

    @property
    def estimated_tokens(self):
        """Rough token estimate for the entire Tier 1 context."""
        total = 0
        total += self._estimate_tokens(self.system_prompt)
        total += self._estimate_tokens(self.scene_brief)
        total += self._estimate_tokens(self.compressed_manifest)
        total += self._estimate_tokens(json.dumps(self.current_asset))
        for op in self.recent_operations:
            total += op.token_estimate or self._estimate_tokens(
                json.dumps(asdict(op)))
        # Images: ~800 tokens per 960x540 JPEG
        total += len(self.images) * 800
        return total

    def build_messages(self):
        """Build the messages array for a Claude API call.
        Returns formatted messages list."""
        messages = []

        # User message with context + images
        content_blocks = []

        # Text context
        context_text = []
        if self.compressed_manifest:
            context_text.append(f"## Current Scene State\n{self.compressed_manifest}")
        if self.current_asset:
            context_text.append(f"## Current Task\n{json.dumps(self.current_asset, indent=2)}")
        if self.recent_operations:
            ops_text = "\n".join(op.to_summary() for op in self.recent_operations)
            context_text.append(f"## Recent Operations (last {len(self.recent_operations)})\n{ops_text}")

        if context_text:
            content_blocks.append({
                "type": "text",
                "text": "\n\n".join(context_text),
            })

        # Images
        for i, img in enumerate(self.images):
            if isinstance(img, dict):
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/jpeg"),
                        "data": img["b64"],
                    }
                })
            elif isinstance(img, str):
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img,
                    }
                })
            if i < len(self.image_descriptions):
                content_blocks.append({
                    "type": "text",
                    "text": f"[{self.image_descriptions[i]}]",
                })

        if content_blocks:
            messages.append({"role": "user", "content": content_blocks})

        return messages

    def get_system_message(self):
        """Build the system prompt string with scene brief."""
        parts = [self.system_prompt]
        if self.scene_brief:
            parts.append(f"\n## Scene Brief\n{self.scene_brief}")
        return "\n".join(parts)

    # --- Tier 2: On-Disk, Loadable ---

    def _offload_to_tier2(self):
        """Move oldest operations from Tier 1 to Tier 2 buffer."""
        while (len(self.recent_operations) > SLIDING_WINDOW_OPS
               and self.estimated_tokens > CONTEXT_BUDGET_TOKENS * 0.7):
            evicted = self.recent_operations.pop(0)
            self.all_operations.append(evicted)

    def load_zone_summary(self, zone_id):
        """Load a zone summary from disk."""
        path = os.path.join(ZONE_SUMMARIES_DIR, f"{zone_id}.json")
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return None

    def load_decision_log(self, last_n=20):
        """Load recent entries from the decision log."""
        if os.path.exists(DECISION_LOG_PATH):
            with open(DECISION_LOG_PATH, 'r') as f:
                log = json.load(f)
            return log[-last_n:]
        return []

    def search_operations(self, query):
        """Search past operations by keyword in details/action."""
        results = []
        log = self.load_decision_log(last_n=100)
        query_lower = query.lower()
        for entry in log:
            if (query_lower in entry.get('action', '').lower()
                    or query_lower in entry.get('asset_label', '').lower()
                    or query_lower in json.dumps(entry.get('details', {})).lower()):
                results.append(entry)
        return results

    # --- Tier 3: Full History ---

    def _save_operation(self, op):
        """Save operation to decision log (Tier 2) and full history (Tier 3)."""
        ensure_dirs()

        # Append to decision log
        log = []
        if os.path.exists(DECISION_LOG_PATH):
            with open(DECISION_LOG_PATH, 'r') as f:
                log = json.load(f)
        log.append(asdict(op))
        with open(DECISION_LOG_PATH, 'w') as f:
            json.dump(log, f, indent=2)

        # Append to session history file
        history_file = os.path.join(HISTORY_DIR,
                                     f"ops_{time.strftime('%Y%m%d')}.jsonl")
        with open(history_file, 'a') as f:
            f.write(json.dumps(asdict(op)) + '\n')

    def save_screenshot(self, b64_data, label):
        """Decode and save a screenshot to disk. Returns file path."""
        ensure_dirs()
        import base64
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"{label}_{ts}.jpg")
        with open(path, 'wb') as f:
            f.write(base64.b64decode(b64_data))
        return path

    # --- Token Estimation ---

    @staticmethod
    def _estimate_tokens(text):
        """Rough token estimate: ~4 chars per token."""
        if not text:
            return 0
        return len(text) // 4

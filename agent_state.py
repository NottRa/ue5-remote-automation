"""Agent state machine: states, transitions, session serialization.
Runs OUTSIDE UE5."""

import json
import os
import time
import sys
from enum import Enum
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SESSION_DIR, ensure_dirs


class AgentState(Enum):
    IDLE = "idle"
    SURVEY = "survey"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    ADJUST = "adjust"
    ROLLBACK = "rollback"
    PERIODIC_REVIEW = "periodic_review"
    RECOVER = "recover"
    COMPLETE = "complete"
    ERROR = "error"


# Valid state transitions
TRANSITIONS = {
    AgentState.IDLE:            [AgentState.SURVEY, AgentState.RECOVER],
    AgentState.SURVEY:          [AgentState.PLAN, AgentState.ERROR],
    AgentState.PLAN:            [AgentState.EXECUTE, AgentState.SURVEY, AgentState.COMPLETE, AgentState.ERROR],
    AgentState.EXECUTE:         [AgentState.VERIFY, AgentState.ROLLBACK, AgentState.ERROR],
    AgentState.VERIFY:          [AgentState.PLAN, AgentState.ADJUST, AgentState.ROLLBACK, AgentState.PERIODIC_REVIEW],
    AgentState.ADJUST:          [AgentState.VERIFY, AgentState.ROLLBACK],
    AgentState.ROLLBACK:        [AgentState.PLAN, AgentState.ERROR],
    AgentState.PERIODIC_REVIEW: [AgentState.PLAN, AgentState.SURVEY],
    AgentState.RECOVER:         [AgentState.SURVEY, AgentState.ERROR],
    AgentState.COMPLETE:        [],
    AgentState.ERROR:           [AgentState.RECOVER, AgentState.IDLE],
}


@dataclass
class AgentSession:
    session_id: str
    started_at: str
    current_state: AgentState = AgentState.IDLE
    current_zone_id: str = ""
    current_asset_label: str = ""
    operations_count: int = 0
    placements_since_review: int = 0
    consecutive_failures: int = 0
    zones_completed: list = field(default_factory=list)
    zone_order: list = field(default_factory=list)
    zone_index: int = 0

    def transition_to(self, new_state):
        """Transition to a new state. Returns True if valid, False if not."""
        allowed = TRANSITIONS.get(self.current_state, [])
        if new_state in allowed:
            self.current_state = new_state
            return True
        return False

    def next_zone(self):
        """Advance to the next zone in the order. Returns zone_id or None."""
        self.zone_index += 1
        if self.zone_index < len(self.zone_order):
            self.current_zone_id = self.zone_order[self.zone_index]
            return self.current_zone_id
        return None

    def to_dict(self):
        """Serialize to dict for JSON storage."""
        d = asdict(self)
        d['current_state'] = self.current_state.value
        return d

    @classmethod
    def from_dict(cls, data):
        """Deserialize from dict."""
        data = dict(data)
        data['current_state'] = AgentState(data.get('current_state', 'idle'))
        return cls(**data)

    def save(self, path=None):
        """Save session state to disk for resume capability."""
        ensure_dirs()
        if path is None:
            path = os.path.join(SESSION_DIR, f"{self.session_id}.json")
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, session_id=None, path=None):
        """Load session state from disk."""
        if path is None:
            path = os.path.join(SESSION_DIR, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def find_latest(cls):
        """Find the most recently saved session."""
        ensure_dirs()
        sessions = []
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.json'):
                path = os.path.join(SESSION_DIR, f)
                sessions.append((os.path.getmtime(path), path))
        if not sessions:
            return None
        sessions.sort(reverse=True)
        with open(sessions[0][1], 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)

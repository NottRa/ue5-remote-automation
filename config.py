"""Central configuration for the UE5 autonomous scene-building agent."""
import os

# === PATHS ===
EXTRAS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DATA_DIR = os.path.join(EXTRAS_DIR, "agent_data")
MANIFEST_PATH = os.path.join(AGENT_DATA_DIR, "manifest.json")
MANIFEST_COMPRESSED_PATH = os.path.join(AGENT_DATA_DIR, "manifest_compressed.json")
DECISION_LOG_PATH = os.path.join(AGENT_DATA_DIR, "decision_log.json")
ZONE_SUMMARIES_DIR = os.path.join(AGENT_DATA_DIR, "zone_summaries")
SKILLS_DIR = os.path.join(AGENT_DATA_DIR, "skills")
SCREENSHOTS_DIR = os.path.join(AGENT_DATA_DIR, "screenshots")
HISTORY_DIR = os.path.join(AGENT_DATA_DIR, "history")
SESSION_DIR = os.path.join(AGENT_DATA_DIR, "sessions")

# === TCP BRIDGE ===
UE_HOST = "127.0.0.1"
UE_PORT = 9876
COMMAND_TIMEOUT = 120  # seconds

# === CAPTURE ===
CAPTURE_WIDTH = 960
CAPTURE_HEIGHT = 540
CAPTURE_EXPOSURE_BIAS = 3.0
JPEG_QUALITY = 85
CAPTURE_TEMP_PREFIX = "_agent_capture_"

# === VERIFICATION ===
OVERLAP_THRESHOLD_CM = 50.0
GROUND_CONTACT_TOLERANCE_CM = 30.0
ORIENTATION_MAX_LEAN_DEG = 15.0
BOUNDS_CHECK_MARGIN_CM = 100.0
CIRCUIT_BREAKER_MAX_RETRIES = 3
CIRCUIT_BREAKER_ZONE_MAX = 5
VERIFY_CLOSEUP_RADIUS_MULT = 2.5
VERIFY_CONTEXT_RADIUS_MULT = 6.0
VERIFY_CLOSEUP_ELEV_DEG = 45.0
VERIFY_CONTEXT_ELEV_DEG = 55.0
VERIFY_CLOSEUP_FOV_DEG = 39.6   # ~50mm equivalent
VERIFY_CONTEXT_FOV_DEG = 54.4   # ~35mm equivalent

# === AGENT ===
PERIODIC_REVIEW_INTERVAL = 7
SURVEY_ANGLES_COUNT = 5
MAX_OPERATIONS_PER_SESSION = 200
SLIDING_WINDOW_OPS = 5
MAX_IMAGES_IN_CONTEXT = 2
CONTEXT_BUDGET_TOKENS = 15000
CONTEXT_OFFLOAD_THRESHOLD = 0.85

# === COMPOSITION ===
LAYER_ORDER = [
    "terrain", "ground_cover", "low_vegetation", "mid_vegetation",
    "canopy_support", "canopy", "atmosphere"
]
MIN_TREE_SPECIES = 3
SCALE_RANGE = (0.75, 1.25)
YAW_RANGE = (0, 360)
LEAN_RANGE = (-5, 5)
CLUSTER_PRIMARY_RANGE = (3, 7)
CLUSTER_SECONDARY_RANGE = (2, 4)
CLUSTER_TERTIARY_RANGE = (1, 2)
EDGE_TRANSITION_CM = (500, 2000)
POISSON_DISC_MIN_DISTANCE = 200.0  # cm between tree trunks

# === CLAUDE API ===
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 4096

# === WATCHDOG ===
UE_PROCESS_NAME = "UnrealEditor.exe"
UE_PROJECT_PATH = os.path.normpath(
    os.path.join(EXTRAS_DIR, "..", "HorrorTechDemo.uproject")
)
HEALTH_CHECK_INTERVAL = 30
CRASH_RECOVERY_WAIT = 60

# === ASSET CATALOG ===
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

# === DEFAULT ZONES ===
DEFAULT_ZONES = [
    {
        "zone_id": "entry",
        "label": "Entry Tunnel",
        "bounds": {"x_min": -800, "x_max": 800, "y_min": -2000, "y_max": 0},
        "center": [0, -1000, 0],
        "target_density": "dense",
        "target_layers": ["canopy", "canopy_support", "mid_vegetation", "ground_cover"],
    },
    {
        "zone_id": "mid_tunnel",
        "label": "Mid Tunnel",
        "bounds": {"x_min": -800, "x_max": 800, "y_min": 0, "y_max": 3000},
        "center": [0, 1500, 0],
        "target_density": "dense",
        "target_layers": ["canopy", "canopy_support", "mid_vegetation", "ground_cover"],
    },
    {
        "zone_id": "clearing",
        "label": "Clearing",
        "bounds": {"x_min": -1500, "x_max": 1500, "y_min": 3000, "y_max": 4500},
        "center": [0, 3750, 0],
        "target_density": "sparse",
        "target_layers": ["ground_cover", "low_vegetation", "atmosphere"],
    },
    {
        "zone_id": "exit",
        "label": "Exit Area",
        "bounds": {"x_min": -800, "x_max": 800, "y_min": 4500, "y_max": 6000},
        "center": [0, 5250, 0],
        "target_density": "medium",
        "target_layers": ["canopy", "mid_vegetation", "ground_cover"],
    },
    {
        "zone_id": "background",
        "label": "Background Forest",
        "bounds": {"x_min": -6000, "x_max": 6000, "y_min": -3000, "y_max": 8000},
        "center": [0, 2500, 0],
        "target_density": "sparse",
        "target_layers": ["canopy", "mid_vegetation"],
    },
]


def ensure_dirs():
    """Create all agent data directories."""
    for d in [AGENT_DATA_DIR, ZONE_SUMMARIES_DIR, SKILLS_DIR,
              SCREENSHOTS_DIR, HISTORY_DIR, SESSION_DIR]:
        os.makedirs(d, exist_ok=True)

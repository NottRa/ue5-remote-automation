# UE5 Remote Automation Tools

Python tooling for remote-controlling Unreal Engine 5 from the command line. Built for the HorrorTechDemo project to enable AI-assisted level design workflows.

## Architecture

```
Claude Code / CLI
       │
       ▼
  ue_bridge.py      (Outside UE5 — sends commands via TCP)
       │
       ▼
  ue_listener.py    (Inside UE5 — receives + executes on game thread)
       │
       ▼
  ue_capture.py     (SceneCapture2D — in-engine viewport screenshots)
```

## Setup

1. **Enable UE5 Python plugin**: Edit > Plugins > Python Editor Script Plugin > Enable + restart
2. **Start the listener**: In UE5, go to Tools > Execute Python Script > select `ue_listener.py`
3. **Send commands**: From any terminal, run `python ue_bridge.py "unreal.log('hello')"`

## Scripts

| Script | Runs | Purpose |
|--------|------|---------|
| `ue_listener.py` | Inside UE5 | TCP server on port 9876, executes Python on game thread |
| `ue_bridge.py` | Outside UE5 | CLI to send commands, take screenshots, run surveys |
| `ue_capture.py` | Outside UE5 | In-engine viewport capture via SceneCapture2D |
| `TuneLighting.py` | Inside UE5 | Configure directional light, sky, fog, post-process |
| `PopulateForest.py` | Inside UE5 | Place trees/rocks with tunnel walkway layout |
| `SetupPCGCollisionTest.py` | Inside UE5 | Full forest setup with PCG volume for collision testing |
| `DiagnoseLevel.py` | Inside UE5 | Inspect all actors, ground surface, mesh bounds |
| `InspectLighting.py` | Inside UE5 | Dump all lighting actor properties |

## Usage Examples

```bash
# Send a one-liner
python ue_bridge.py "unreal.log('hello from CLI')"

# Run a script file inside UE5
python ue_bridge.py --file TuneLighting.py

# Capture viewport screenshot (in-engine SceneCapture2D)
python ue_bridge.py --screenshot

# Multi-angle survey (8 cameras)
python ue_bridge.py --survey

# Capture from specific camera position
python ue_capture.py --move 0 3000 500 -15 90 0

# Cleanup old screenshots
python ue_bridge.py --cleanup 5
```

## Viewport Capture

Uses **SceneCapture2D** inside UE5's render pipeline (not Win32 PrintWindow). This captures the actual GPU-rendered frame with proper lighting, post-processing, and volumetric effects.

## Requirements

- Unreal Engine 5.7 with Python Editor Script Plugin
- Python 3.9+ (system or UE5's bundled Python)

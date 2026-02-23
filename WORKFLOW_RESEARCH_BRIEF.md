# Deep Research Brief: UE5 Remote Automation Workflow

## Context
I'm using Claude Code (CLI) to remotely control Unreal Engine 5.7 to build a cinematic forest scene. The goal is a "cinematic forest walkway tunnel with eerie atmosphere" using Megaplant Library assets for a PCG Collision Guard plugin demo.

## Current Architecture
1. **ue_listener.py** runs INSIDE UE5 (loaded as a startup Python script). It opens a TCP server on port 9876 and executes Python commands on UE5's game thread via `exec()`.
2. **ue_bridge.py** runs OUTSIDE UE5. It sends Python code strings to the listener via TCP and receives JSON results (success/error/output).
3. **ue_capture.py** captures the UE5 editor window using Win32 `PrintWindow` API and saves PNG screenshots that Claude Code can read.
4. Claude Code reads the screenshots, analyzes them, makes UE5 changes via the bridge, and repeats.

## Current Problems
1. **Screenshot reliability**: PrintWindow captures stale frames from UE5's DX12 viewport. Camera changes via Python don't always reflect in the next capture. No guaranteed fresh render per capture.
2. **No continuous visual feedback**: Getting 1 screenshot per change is slow. Want "video-like" multi-angle coverage but currently captures are unreliable.
3. **Nuclear vs iterative**: Changes have been too large (delete everything + rebuild). Need per-asset granular changes with verification after each.
4. **UE5 internal screenshot**: `HighResShot` and `Shot` console commands don't save files when executed via Python bridge. No KismetRenderingLibrary available in Python for render target export.
5. **Level design quality**: Tree placement is random scatter instead of natural clustering. Need professional-grade composition.

## Questions to Research

### 1. Viewport Capture Solutions
- What is the industry-standard way to programmatically capture UE5 editor viewport screenshots from an external process?
- Is there a way to force UE5 to save a viewport screenshot to disk via Python scripting?
- Does UE5's Movie Render Queue or Sequencer have Python APIs for rendering single frames?
- Can SceneCapture2D + TextureRenderTarget2D export to disk without KismetRenderingLibrary?

### 2. Pixel Streaming for AI Agents
- Has anyone used UE5 Pixel Streaming as a visual feedback loop for AI agents?
- What are the alternatives? (e.g., Remote Control API, Web Remote Control, nDisplay)
- UE5.7 has both PixelStreaming (v1) and PixelStreaming2 (v2) plugins. Which is simpler for local-only, single-frame capture?
- What about using UE5's Remote Control Web Interface for getting viewport data?

### 3. Optimal Iteration Workflow
- How do professional technical artists iterate on UE5 scenes programmatically?
- What does a "turntable render" or "camera sweep" workflow look like in Python?
- How many camera angles / positions are needed to adequately evaluate a scene composition?
- Is there a standard for automated quality checks (floating assets, Z-fighting, LOD issues)?

### 4. Level Design Best Practices
- What makes forest tree placement look natural vs "randomly scattered 3D models"?
- How does Poisson disc sampling or cluster-based placement compare to UE5's built-in Procedural Foliage Spawner?
- Should we use PCG (Procedural Content Generation) framework instead of manually spawning actors for forest population?
- What ground cover layers are essential? (leaf litter, ferns, grass, debris)

### 5. Alternative Approaches We May Be Missing
- Would it be better to use UE5's built-in Level Automation tools instead of custom TCP bridge?
- Is there a way to use Blueprints or Editor Utility Widgets for this automation?
- Would using the UE5 Remote Control Plugin (REST API) be more reliable than our TCP approach?
- Are there any UE5 plugins specifically designed for AI-assisted scene building?

## System Specs
- AMD Ryzen 5 2400G, 16GB RAM, NVIDIA RTX 3060 Ti
- UE 5.7 with Nanite, Lumen, Virtual Shadow Maps
- Megaplant Library (PVE-based skeletal mesh vegetation)

## Key Constraint
Everything must be automatable via Python/CLI. No manual clicking in the UE5 editor. Claude Code needs to see the viewport, make changes, and verify results autonomously.

## What I Need Back
A critical analysis of our current workflow with specific, actionable recommendations ranked by impact. Challenge every assumption. If there's a fundamentally better approach we're missing, tell me.

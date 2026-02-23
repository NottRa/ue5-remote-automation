"""CLI entry point for the autonomous UE5 scene-building agent.

No API keys needed. Visual verification uses your Claude Code CLI
subscription (auto-detected). Without CLI, runs fully local with
rule-based composition + programmatic verification.

Usage:
  python run_agent.py                    # Full autonomous run
  python run_agent.py --resume           # Resume last session
  python run_agent.py --step             # Single state transition
  python run_agent.py --survey-only      # Just survey and print manifest
  python run_agent.py --reconcile        # Compare manifest vs UE5
  python run_agent.py --max-ops 20       # Limit operations
  python run_agent.py --no-visual        # Skip Claude CLI visual checks
  python run_agent.py --status           # Print current session status
"""

import argparse
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import MAX_OPERATIONS_PER_SESSION, ensure_dirs
from agent import SceneBuildingAgent
from agent_claude import is_claude_available
from watchdog import UE5Watchdog
from manifest import ManifestManager


def main():
    parser = argparse.ArgumentParser(description="UE5 Autonomous Scene Builder")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last saved session")
    parser.add_argument("--session-id", type=str, default=None,
                        help="Session ID (auto-generated if not specified)")
    parser.add_argument("--max-ops", type=int, default=MAX_OPERATIONS_PER_SESSION,
                        help="Maximum operations before stopping")
    parser.add_argument("--step", action="store_true",
                        help="Single-step mode (one state transition)")
    parser.add_argument("--survey-only", action="store_true",
                        help="Just survey and print manifest")
    parser.add_argument("--reconcile", action="store_true",
                        help="Reconcile manifest with UE5 scene")
    parser.add_argument("--status", action="store_true",
                        help="Print current session status")
    parser.add_argument("--manifest", action="store_true",
                        help="Print compressed manifest")
    parser.add_argument("--no-visual", action="store_true",
                        help="Disable Claude CLI visual verification (local-only mode)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        )

    ensure_dirs()

    # Status/manifest commands don't need UE5
    if args.status:
        from agent_state import AgentSession
        session = AgentSession.find_latest()
        if session:
            print(json.dumps(session.to_dict(), indent=2))
        else:
            print("No saved session found")
        return

    if args.manifest:
        mgr = ManifestManager()
        mgr.load()
        print(mgr.compress())
        return

    # Pre-flight check
    watchdog = UE5Watchdog()
    if not watchdog.is_listener_responsive():
        print("ERROR: UE5 listener not responding on port 9876.")
        print("Start UE5 and ensure ue_listener.py is running.")
        print()
        print("Quick check:")
        print(f"  UE5 process running: {watchdog.is_ue5_running()}")
        sys.exit(1)

    print("UE5 connection OK")

    # Claude CLI detection
    if args.no_visual:
        print("Visual verification: DISABLED (--no-visual)")
    elif is_claude_available():
        print("Claude CLI detected — visual verification ENABLED (uses your subscription)")
    else:
        print("Claude CLI not found — running local-only (programmatic verification)")

    # Handle modes
    if args.reconcile:
        mgr = ManifestManager()
        mgr.load()
        result = mgr.reconcile_with_ue5()
        print(json.dumps(result, indent=2))
        return

    if args.survey_only:
        agent = SceneBuildingAgent(
            session_id=args.session_id, resume=args.resume)
        agent._handle_survey()
        print("\n" + agent.manifest.compress())
        return

    # Create and run agent
    enable_visual = None if not args.no_visual else False
    agent = SceneBuildingAgent(
        session_id=args.session_id,
        resume=args.resume,
        enable_visual=enable_visual,
    )

    if args.step:
        continued = agent.step()
        print(f"State: {agent.session.current_state.value}")
        print(f"Operations: {agent.session.operations_count}")
        if not continued:
            print("Agent has completed or errored")
    else:
        print(f"Starting autonomous run (max {args.max_ops} operations)...")
        print(f"Session: {agent.session.session_id}")
        print(f"Zones: {agent.session.zone_order}")
        print()
        agent.run(max_operations=args.max_ops)
        print()
        print("=== Final Summary ===")
        print(agent.manifest.compress())
        print(f"\nCircuit breaker stats: {agent.circuit_breaker.stats()}")


if __name__ == "__main__":
    main()

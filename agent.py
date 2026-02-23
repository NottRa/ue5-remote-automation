"""Main agent orchestrator: dual-loop autonomous scene builder.
Inner loop: SURVEY → PLAN → EXECUTE → VERIFY → ADJUST → NEXT_ASSET
Outer loop: Skill accumulation across sessions.

No API keys needed. Uses:
- Rule-based composition engine for placement decisions
- Phase 1: Programmatic verification (always free)
- Phase 2: Visual verification via Claude Code CLI (uses your subscription)
  Auto-detected; falls back to local-only if CLI not available.

Runs OUTSIDE UE5."""

import json
import logging
import time
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    MAX_OPERATIONS_PER_SESSION, PERIODIC_REVIEW_INTERVAL,
    DEFAULT_ZONES, TREE_SPECIES, SCREENSHOTS_DIR, ensure_dirs,
)
from agent_state import AgentState, AgentSession
from manifest import ManifestManager, AssetEntry
from memory import MemoryManager
from composition import plan_zone_composition, PlacementSpec, ASSET_CATALOG
from capture_enhanced import survey_scene, capture_to_disk
from verify_pipeline import run_verification_pipeline, CircuitBreaker
from skills import SkillLibrary
from watchdog import UE5Watchdog
import ue_commands

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
log = logging.getLogger("agent")


class SceneBuildingAgent:
    """Autonomous UE5 scene-building agent.
    No API keys needed — visual verification uses Claude Code CLI
    (your existing subscription). Falls back to local-only if CLI
    not available."""

    def __init__(self, session_id=None, resume=False, skip_capture=False,
                 enable_visual=None):
        self.session = AgentSession(
            session_id=session_id or str(uuid.uuid4())[:8],
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self.manifest = ManifestManager()
        self.memory = MemoryManager()
        self.circuit_breaker = CircuitBreaker()
        self.skills = SkillLibrary()
        self.watchdog = UE5Watchdog()
        self.zone_plans = {}      # zone_id → list[PlacementSpec]
        self.zone_plan_index = {} # zone_id → current index in plan
        self._current_spec = None # PlacementSpec being placed
        self.skip_capture = skip_capture  # skip screenshots (faster)
        self.enable_visual = enable_visual  # None=auto-detect, True=force, False=skip

        if resume:
            self._resume_session()
        else:
            self._init_session()

    # =======================================================================
    # Main Loop
    # =======================================================================

    def run(self, max_operations=MAX_OPERATIONS_PER_SESSION):
        """Main agent loop. Runs until complete or max_operations reached.
        No API calls — fully local."""
        visual_mode = ("auto-detect" if self.enable_visual is None
                       else "enabled" if self.enable_visual else "disabled")
        log.info(f"Starting agent session {self.session.session_id} "
                 f"(max {max_operations} ops, visual: {visual_mode})")

        # Initial transition to SURVEY
        self.session.transition_to(AgentState.SURVEY)

        while (self.session.current_state != AgentState.COMPLETE
               and self.session.current_state != AgentState.ERROR
               and self.session.operations_count < max_operations):

            # Health check
            if not self.watchdog.ensure_healthy():
                log.error("UE5 is not healthy and recovery failed")
                self.session.transition_to(AgentState.ERROR)
                break

            # Dispatch to state handler
            state = self.session.current_state
            handler = self._get_handler(state)
            if handler is None:
                log.error(f"No handler for state {state}")
                break

            try:
                handler()
                self.session.operations_count += 1
                self.session.save()
            except Exception as e:
                log.error(f"Error in state {state}: {e}", exc_info=True)
                if self.session.current_state != AgentState.ERROR:
                    self.session.transition_to(AgentState.ERROR)

        # Session complete — run outer loop
        log.info(f"Session complete. {self.session.operations_count} operations, "
                 f"{self.manifest.manifest.total_placed} assets placed")
        self._run_outer_loop()
        self.session.save()

        # Final survey for manual review
        if not self.skip_capture:
            log.info("Taking final survey screenshots for review...")
            self._save_review_screenshots("final")

    def step(self):
        """Execute a single state transition. Returns False when complete."""
        if self.session.current_state in (AgentState.COMPLETE, AgentState.ERROR):
            return False

        if self.session.current_state == AgentState.IDLE:
            self.session.transition_to(AgentState.SURVEY)

        handler = self._get_handler(self.session.current_state)
        if handler:
            handler()
            self.session.operations_count += 1
            self.session.save()
            return True
        return False

    def _get_handler(self, state):
        """Get the handler function for a state."""
        handlers = {
            AgentState.SURVEY: self._handle_survey,
            AgentState.PLAN: self._handle_plan,
            AgentState.EXECUTE: self._handle_execute,
            AgentState.VERIFY: self._handle_verify,
            AgentState.ADJUST: self._handle_adjust,
            AgentState.ROLLBACK: self._handle_rollback,
            AgentState.PERIODIC_REVIEW: self._handle_periodic_review,
            AgentState.RECOVER: self._handle_recover,
        }
        return handlers.get(state)

    # =======================================================================
    # State Handlers
    # =======================================================================

    def _handle_survey(self):
        """SURVEY: take screenshots for review, reconcile manifest."""
        log.info("=== SURVEY ===")

        # Reconcile manifest with UE5 on first survey
        if self.session.operations_count == 0:
            recon = self.manifest.reconcile_with_ue5()
            log.info(f"Reconciliation: {recon.get('matched', 0)} matched, "
                     f"{len(recon.get('missing_in_ue5', []))} missing in UE5, "
                     f"{len(recon.get('missing_in_manifest', []))} unexpected")

        # Save screenshots for manual review (optional)
        if not self.skip_capture:
            self._save_review_screenshots("survey")

        # Update compressed manifest
        compressed = self.manifest.save_compressed()
        self.memory.update_manifest(compressed)

        self.memory.add_operation(
            state="survey", action="survey",
            asset_label="", details={"phase": "initial"},
            result="success")

        self.session.transition_to(AgentState.PLAN)

    def _handle_plan(self):
        """PLAN: use composition engine to decide next placement.
        No API calls — all rule-based."""
        log.info("=== PLAN ===")
        zone_id = self.session.current_zone_id

        # Check if current zone is done or blocked
        if self.circuit_breaker.is_zone_blocked(zone_id):
            log.warning(f"Zone {zone_id} is blocked by circuit breaker, skipping")
            self._advance_zone()
            return

        # Generate zone plan if we don't have one
        if zone_id not in self.zone_plans or not self.zone_plans[zone_id]:
            zone = self.manifest.get_zone(zone_id)
            if zone is None:
                log.error(f"Zone {zone_id} not found in manifest")
                self._advance_zone()
                return

            zone_dict = {
                "zone_id": zone.zone_id,
                "bounds": zone.bounds,
                "center": zone.center,
                "target_density": zone.target_density,
                "target_layers": zone.target_layers,
            }
            existing = [{"location": a.location, "label": a.label}
                        for a in self.manifest.get_assets_in_zone(zone_id)]

            placements = plan_zone_composition(zone_dict, existing)
            self.zone_plans[zone_id] = placements
            self.zone_plan_index[zone_id] = 0
            log.info(f"Generated plan for zone {zone_id}: "
                     f"{len(placements)} placements")
            self.manifest.update_zone_status(zone_id, "in_progress")

        # Pop next placement from plan
        plan = self.zone_plans[zone_id]
        idx = self.zone_plan_index.get(zone_id, 0)

        if idx >= len(plan):
            log.info(f"Zone {zone_id} plan exhausted")
            self.manifest.update_zone_status(zone_id, "complete",
                                              self._summarize_zone(zone_id))
            self.session.zones_completed.append(zone_id)
            self._advance_zone()
            return

        spec = plan[idx]
        self.zone_plan_index[zone_id] = idx + 1
        self._current_spec = spec

        # Line trace for ground Z
        if spec.needs_ground_trace:
            trace = ue_commands.line_trace_ground(spec.x, spec.y)
            if trace.get('success') and trace.get('z') is not None:
                spec.z = trace['z'] + spec.z  # spec.z may have offset (buried rocks)
                log.info(f"Ground at ({spec.x:.0f}, {spec.y:.0f}): Z={trace['z']:.1f}")
            else:
                spec.z = 0
                log.warning(f"Line trace failed at ({spec.x:.0f}, {spec.y:.0f}), using Z=0")

        self.session.current_asset_label = spec.label
        self.memory.set_current_asset({
            "label": spec.label,
            "species": spec.species,
            "type": spec.asset_type,
            "zone": zone_id,
            "location": [spec.x, spec.y, spec.z],
        })

        log.info(f"Planned: {spec.label} ({spec.species} {spec.asset_type}) "
                 f"at ({spec.x:.0f}, {spec.y:.0f}, {spec.z:.0f})")

        self.session.transition_to(AgentState.EXECUTE)

    def _handle_execute(self):
        """EXECUTE: spawn the planned actor in UE5."""
        log.info("=== EXECUTE ===")
        spec = self._current_spec

        if spec is None:
            log.error("No current placement spec")
            self.session.transition_to(AgentState.ROLLBACK)
            return

        # Spawn the actor
        location = (spec.x, spec.y, spec.z)
        rotation = (spec.pitch, spec.yaw, spec.roll)
        scale = (spec.scale_x, spec.scale_y, spec.scale_z)
        folder = f"Agent_Placed/{self.session.current_zone_id}"

        if spec.asset_type == "tree":
            result = ue_commands.spawn_skeletal_mesh_actor(
                spec.label, spec.mesh_path, location, rotation, scale, folder)
        else:
            result = ue_commands.spawn_static_mesh_actor(
                spec.label, spec.mesh_path, location, rotation, scale, folder)

        if not result or not result.get('success') or result.get('error'):
            log.error(f"Spawn failed for {spec.label}: "
                      f"{result.get('error', 'unknown') if result else 'no response'}")
            self.memory.add_operation(
                state="execute", action="spawn", asset_label=spec.label,
                details={"species": spec.species, "zone": self.session.current_zone_id,
                         "error": result.get('error', '') if result else 'no response'},
                result="failed")
            self.session.transition_to(AgentState.ROLLBACK)
            return

        log.info(f"Spawned {spec.label} successfully")
        self.memory.add_operation(
            state="execute", action="spawn", asset_label=spec.label,
            details={"species": spec.species, "zone": self.session.current_zone_id,
                     "location": list(location), "scale": list(scale)},
            result="success")

        self.session.transition_to(AgentState.VERIFY)

    def _handle_verify(self):
        """VERIFY: Phase 1 (programmatic, always free) + Phase 2 (visual
        via Claude CLI, uses subscription) if available."""
        log.info("=== VERIFY ===")
        spec = self._current_spec
        if spec is None:
            self.session.transition_to(AgentState.PLAN)
            return

        zone = self.manifest.get_zone(self.session.current_zone_id)
        zone_bounds = zone.bounds if zone else None
        nearby = self.manifest.get_nearby_assets(spec.x, spec.y, 500)
        nearby_dicts = [{"label": a.label, "location": a.location}
                        for a in nearby]

        asset_info = {
            "label": spec.label,
            "asset_type": spec.asset_type,
            "species": spec.species,
            "zone_id": self.session.current_zone_id,
            "location": [spec.x, spec.y, spec.z],
            "scale": [spec.scale_x, spec.scale_y, spec.scale_z],
        }

        # Run verification pipeline (Phase 1 always, Phase 2 if Claude CLI available)
        compressed = self.manifest.compress()
        pipeline_result = run_verification_pipeline(
            spec.label, asset_info,
            expected_location=(spec.x, spec.y, spec.z),
            zone_bounds=zone_bounds,
            nearby_actors=nearby_dicts,
            scene_context=compressed,
            max_retries=3,
            enable_visual=self.enable_visual,
        )

        if pipeline_result.final_passed:
            method = ("visual" if pipeline_result.phase2_verdict
                      and pipeline_result.phase2_verdict.passed
                      else "programmatic")
            log.info(f"Verification PASSED for {spec.label} "
                     f"(method: {method}, auto-fixes: "
                     f"{pipeline_result.auto_fixes_applied})")

            # Add to manifest
            entry = AssetEntry(
                label=spec.label,
                mesh_path=spec.mesh_path,
                asset_type=spec.asset_type,
                species=spec.species,
                location=[spec.x, spec.y, spec.z],
                rotation=[spec.pitch, spec.yaw, spec.roll],
                scale=[spec.scale_x, spec.scale_y, spec.scale_z],
                zone_id=self.session.current_zone_id,
                layer=spec.layer,
                verified=True,
                verification_method=method,
                cluster_id=spec.cluster_id,
            )
            self.manifest.add_asset(entry)
            self.circuit_breaker.record_success(self.session.current_zone_id)

            # Update memory
            self.memory.update_manifest(self.manifest.save_compressed())
            self.memory.add_operation(
                state="verify", action="verify", asset_label=spec.label,
                details={"passed": True,
                         "auto_fixes": pipeline_result.auto_fixes_applied,
                         "species": spec.species,
                         "zone": self.session.current_zone_id},
                result="success")

            # Check if periodic review needed
            self.session.placements_since_review += 1
            if self.session.placements_since_review >= PERIODIC_REVIEW_INTERVAL:
                self.session.transition_to(AgentState.PERIODIC_REVIEW)
            else:
                self.session.transition_to(AgentState.PLAN)

        elif pipeline_result.was_rolled_back:
            log.warning(f"Verification FAILED and rolled back {spec.label}")
            self.circuit_breaker.record_failure(self.session.current_zone_id)
            self.memory.add_operation(
                state="verify", action="verify", asset_label=spec.label,
                details={"passed": False, "rolled_back": True,
                         "species": spec.species,
                         "zone": self.session.current_zone_id},
                result="rolled_back")
            self.session.transition_to(AgentState.PLAN)

        else:
            # Shouldn't happen with programmatic-only, but handle anyway
            self.session.transition_to(AgentState.ADJUST)

    def _handle_adjust(self):
        """ADJUST: re-verify after adjustments."""
        log.info("=== ADJUST ===")
        self.session.transition_to(AgentState.VERIFY)

    def _handle_rollback(self):
        """ROLLBACK: remove failed placement."""
        log.info("=== ROLLBACK ===")
        label = self.session.current_asset_label
        if label:
            ue_commands.destroy_actor(label)
            self.manifest.remove_asset(label)
            self.circuit_breaker.record_failure(self.session.current_zone_id)
            self.memory.add_operation(
                state="rollback", action="rollback", asset_label=label,
                details={"zone": self.session.current_zone_id},
                result="rolled_back")

        self.session.transition_to(AgentState.PLAN)

    def _handle_periodic_review(self):
        """PERIODIC_REVIEW: save screenshots and optionally run Claude CLI review."""
        log.info("=== PERIODIC REVIEW ===")
        self.session.placements_since_review = 0

        # Save review screenshots
        review_paths = []
        if not self.skip_capture:
            review_paths = self._save_review_screenshots(
                f"review_{self.manifest.manifest.total_placed}")
            log.info(f"Review screenshots saved: {review_paths}")

        # Log progress
        compressed = self.manifest.save_compressed()
        log.info(f"Progress:\n{compressed}")

        # Optional: Claude CLI periodic review
        review_result = None
        if self.enable_visual is not False and review_paths:
            from agent_claude import is_claude_available, call_claude_vision, \
                parse_json_response, PROMPT_PERIODIC_REVIEW
            if is_claude_available():
                prompt = PROMPT_PERIODIC_REVIEW.format(
                    n=self.manifest.manifest.total_placed,
                    compressed_manifest=compressed,
                    screenshot_dir=SCREENSHOTS_DIR,
                )
                response = call_claude_vision(prompt, review_paths)
                if response:
                    review_result = parse_json_response(response)
                    if review_result:
                        log.info(f"Claude review score: "
                                 f"{review_result.get('overall_score', '?')}/10")
                        if review_result.get('issues'):
                            log.info(f"Issues: {review_result['issues']}")

        self.memory.add_operation(
            state="periodic_review", action="review",
            asset_label="",
            details={"total_placed": self.manifest.manifest.total_placed,
                     "zones_complete": len(self.session.zones_completed),
                     "claude_review": review_result},
            result="success")

        self.session.transition_to(AgentState.PLAN)

    def _handle_recover(self):
        """RECOVER: handle UE5 crash or connection loss."""
        log.info("=== RECOVER ===")

        if self.watchdog.wait_for_recovery(max_wait=120):
            recon = self.manifest.reconcile_with_ue5()
            log.info(f"Recovery reconciliation: {recon}")

            self.memory.add_operation(
                state="recover", action="recover", asset_label="",
                details=recon, result="success")

            self.session.transition_to(AgentState.SURVEY)
        else:
            log.error("Recovery failed")
            self.session.transition_to(AgentState.ERROR)

    # =======================================================================
    # Review Screenshots (for Claude Code manual review)
    # =======================================================================

    def _save_review_screenshots(self, label="review"):
        """Save survey screenshots to disk for manual review via Claude Code.
        Returns list of file paths."""
        zone = self.manifest.get_zone(self.session.current_zone_id)
        center = tuple(zone.center) if zone else (0, 3000, 0)

        paths = []
        try:
            images = survey_scene(center=center, radius=4000.0)
            for img in images:
                path = os.path.join(SCREENSHOTS_DIR,
                                     f"{label}_{img['name']}_{time.strftime('%H%M%S')}.jpg")
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                import base64
                with open(path, 'wb') as f:
                    f.write(base64.b64decode(img['b64']))
                paths.append(path)
        except Exception as e:
            log.warning(f"Screenshot capture failed: {e}")

        return paths

    # =======================================================================
    # Zone Management
    # =======================================================================

    def _advance_zone(self):
        """Move to the next zone or complete if all done."""
        next_zone = self.session.next_zone()
        if next_zone is None:
            log.info("All zones processed")
            self.session.transition_to(AgentState.COMPLETE)
        else:
            log.info(f"Advancing to zone: {next_zone}")
            # Take a screenshot between zones for review
            if not self.skip_capture:
                self._save_review_screenshots(f"zone_complete_{self.session.current_zone_id}")
            self.session.transition_to(AgentState.PLAN)

    def _summarize_zone(self, zone_id):
        """Generate a text summary for a completed zone."""
        assets = self.manifest.get_assets_in_zone(zone_id)
        from collections import Counter
        species_counts = Counter(a.species for a in assets if a.species != "N/A")
        type_counts = Counter(a.asset_type for a in assets)

        parts = []
        for species, count in species_counts.most_common():
            parts.append(f"{count} {species}")
        for atype, count in type_counts.items():
            if atype != "tree":
                parts.append(f"{count} {atype}s")

        return f"{len(assets)} assets: {', '.join(parts)}"

    # =======================================================================
    # Session Management
    # =======================================================================

    def _init_session(self):
        """Initialize a new session."""
        ensure_dirs()

        # Load or create manifest
        self.manifest.load()
        if not self.manifest.manifest.zones:
            self.manifest.initialize_zones()
        self.manifest.manifest.session_id = self.session.session_id
        self.manifest.save()

        # Set zone order
        self.session.zone_order = [z.zone_id for z in self.manifest.manifest.zones]
        self.session.zone_index = 0
        self.session.current_zone_id = (
            self.session.zone_order[0] if self.session.zone_order else "")

        # Load skills
        self.skills.load()

        # Build initial context
        self.memory.set_system_prompt(
            "UE5 autonomous scene builder — Claude CLI visual verification")
        self.memory.update_manifest(self.manifest.compress())

        log.info(f"Session initialized: {len(self.session.zone_order)} zones, "
                 f"{self.manifest.manifest.total_placed} existing assets")

    def _resume_session(self):
        """Resume from a saved session state."""
        ensure_dirs()

        loaded = AgentSession.find_latest()
        if loaded:
            self.session = loaded
            log.info(f"Resumed session {self.session.session_id} "
                     f"at state {self.session.current_state.value}")
        else:
            log.warning("No saved session found, starting fresh")
            self._init_session()
            return

        # Reload manifest
        self.manifest.load()
        self.skills.load()

        # Rebuild context
        self.memory.set_system_prompt(
            "UE5 autonomous scene builder — Claude CLI visual verification")
        self.memory.update_manifest(self.manifest.compress())

    # =======================================================================
    # Outer Loop
    # =======================================================================

    def _run_outer_loop(self):
        """Run the outer loop: extract patterns into skill library."""
        log.info("Running outer loop: skill extraction")
        try:
            decision_log = self.memory.load_decision_log(last_n=100)
            new_skills = self.skills.extract_patterns(decision_log)
            if new_skills:
                log.info(f"Extracted {len(new_skills)} new skills")
            else:
                log.info("No new skills extracted")
        except Exception as e:
            log.error(f"Outer loop failed: {e}")

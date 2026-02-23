"""Watchdog: monitors UE5 editor health and handles crash recovery.
Runs OUTSIDE UE5."""

import logging
import subprocess
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    UE_PROCESS_NAME, UE_PROJECT_PATH, HEALTH_CHECK_INTERVAL,
    CRASH_RECOVERY_WAIT,
)
from ue_bridge import is_connected

log = logging.getLogger("watchdog")


class UE5Watchdog:
    """Monitors UE5 editor process and TCP connectivity."""

    def __init__(self):
        self.last_health_check = 0
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3

    def is_ue5_running(self):
        """Check if UnrealEditor.exe is running."""
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {UE_PROCESS_NAME}',
                 '/FO', 'CSV', '/NH'],
                capture_output=True, text=True, timeout=10)
            return UE_PROCESS_NAME.lower() in result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def is_listener_responsive(self, timeout=5.0):
        """Check if the TCP listener on port 9876 is responsive."""
        return is_connected(timeout=timeout)

    def health_check(self):
        """Full health check. Returns dict with status info."""
        self.last_health_check = time.time()
        process_running = self.is_ue5_running()
        listener_ok = self.is_listener_responsive() if process_running else False

        healthy = process_running and listener_ok

        if healthy:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        return {
            "process_running": process_running,
            "listener_responsive": listener_ok,
            "healthy": healthy,
            "consecutive_failures": self.consecutive_failures,
        }

    def wait_for_recovery(self, max_wait=300):
        """Block until UE5 is responsive or timeout (seconds).
        Polls every 10 seconds. Returns True if recovered."""
        log.info(f"Waiting for UE5 recovery (max {max_wait}s)...")
        start = time.time()
        while time.time() - start < max_wait:
            if self.is_listener_responsive(timeout=5.0):
                log.info("UE5 listener is responsive again")
                self.consecutive_failures = 0
                return True
            elapsed = int(time.time() - start)
            log.info(f"  Waiting... ({elapsed}s / {max_wait}s)")
            time.sleep(10)

        log.error(f"UE5 did not recover within {max_wait}s")
        return False

    def ensure_healthy(self):
        """Check health, attempt recovery if needed.
        Returns True if UE5 is healthy (possibly after recovery).
        Returns False if recovery failed."""
        # Skip if checked recently
        if time.time() - self.last_health_check < HEALTH_CHECK_INTERVAL:
            return True

        status = self.health_check()

        if status['healthy']:
            return True

        log.warning(f"UE5 health check failed: {status}")

        if not status['process_running']:
            log.error("UE5 is not running. Cannot auto-restart "
                      "(requires manual intervention).")
            # We don't auto-restart UE5 since it needs GPU access
            # and the user should be aware of crashes
            return self.wait_for_recovery(max_wait=CRASH_RECOVERY_WAIT)

        if not status['listener_responsive']:
            log.warning("UE5 running but listener unresponsive. "
                        "Waiting for recovery...")
            return self.wait_for_recovery(max_wait=60)

        return False

    def should_check(self):
        """Returns True if enough time has passed for another check."""
        return time.time() - self.last_health_check >= HEALTH_CHECK_INTERVAL

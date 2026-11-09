"""housekeeping — what the agent left behind gets cleaned up, at the end of a session and while it is idle.

Three passes, each one a call of an owner that already knows the rules:
  · browser: the tab sweep on this agent's own browser (reload tabs burning CPU, close old idle ones) and the idle
    reaper (a browser nobody drove for idleMinutes is stopped; it reopens on the next rainbow_start_browser);
  · documents: document leases that expired are closed if they are saved, and an Office/PDF app is quit only if an
    agent launched it and it has had no documents for ten minutes — an app that was already open is the human's;
  · processes: after a session, this agent's orphaned servers stop and its unused port leases go back.

The idle pass runs on a timer thread inside the Hermes process (default every 5 minutes, off with
housekeeping_minutes: 0). It starts with the first session, not when the plugin loads, and stops on unload.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class Housekeeper:
    def __init__(self, rainbow):
        self.rb = rainbow
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.last = {}

    def minutes(self) -> float:
        try:
            return max(float(self.rb.setting("housekeeping_minutes")), 0.0)
        except (TypeError, ValueError):
            return 5.0

    def start(self):
        with self._lock:
            if self._thread is not None or self.minutes() <= 0:
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="rainbowomma-housekeeping", daemon=True)
            self._thread.start()
            return True

    def stop(self):
        self._stop.set()
        with self._lock:
            t, self._thread = self._thread, None
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2)

    def _loop(self):
        while not self._stop.wait(max(self.minutes(), 0.5) * 60):
            if self.minutes() <= 0:
                continue
            try:
                self.idle_pass()
            except Exception as exc:                  # a failed pass never ends the timer
                logger.warning("rainbowomma housekeeping: %s: %s", type(exc).__name__, exc)

    def idle_pass(self) -> dict:
        """the timer's pass: tabs (when tab_cleanup isn't off), the idle reaper, expired document leases and idle apps"""
        me, out = self.rb.me, {}
        mode = str(self.rb.setting("tab_cleanup") or "apply")
        if mode != "off":
            out["tabs"] = self.rb.run("browser-owner.py", "tabs", me, *(["--apply"] if mode == "apply" else []))[1]
        out["browsers"] = self.rb.run("browser-owner.py", "heal", "--scheduled")[1]
        out["documents"] = self.rb.run("agent-office.py", "sweep", "--scheduled")[1]
        self.last = out
        return out

    def session_end(self, session_id: str = "") -> dict:
        """a session ended: the job's tabs close, the screen goes back, orphaned servers stop, unused ports go back"""
        me, out = self.rb.me, {}
        out["tabs"] = self.rb.run("browser-owner.py", "job-close", me)[1]
        out["screen"] = self.rb.run("screen-owner.py", "release", me)[1]
        out["processes"] = self.rb.run("proc-owner.py", "reap", me)[1]
        out["documents"] = self.rb.run("agent-office.py", "sweep", "--scheduled")[1]
        self.last = out
        return out

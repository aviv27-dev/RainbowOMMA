"""guard_hook — RainbowOMMA's guardrail as a Hermes pre_tool_call hook.

Before any tool runs, the guard judges it the way it judges every other agent framework's tool calls: a shell command
that would kill or quit Chrome, quit Word or close its windows, stop another agent's or the human's process, take a
port that isn't this agent's, touch the human's clipboard or Chrome profile, or drive the screen while the human is
typing is refused, and the refusal tells the model which rainbow_* tool does it safely. Sending through Messages or
Mail is not refused: it goes to Hermes's own approval gate, so the human decides.

The guard runs in a helper process per profile (guard_worker.py), kept alive between calls. It can't run inside
Hermes: it tells whose call this is from its environment, and one Hermes gateway process may serve several profiles.
No answer within the time limit, or a helper that died, is a refusal.
"""
from __future__ import annotations

import json
import logging
import os
import re
import select
import subprocess
import sys
import threading

from .core import HERE

logger = logging.getLogger(__name__)
OWN_PREFIX = "rainbow_"
ANSWER_S = 8.0
PAUSED = "the human paused all agents — nothing runs until they resume (/rainbow resume); wait, or ask them"

# The guard's hints name RainbowOMMA's command-line tools. Inside Hermes the same owners are the rainbow_* tools.
HINTS = [
    (re.compile(r"`proc-owner kill[^`]*`"), "the rainbow_stop_process tool"),
    (re.compile(r"`port-owner lease[^`]*`"), "the rainbow_lease_port tool"),
    (re.compile(r"`port-owner who[^`]*`"), "the rainbow_who_port tool"),
    (re.compile(r"`browser-owner mcp-config[^`]*`"), "the CDP port rainbow_browser_status reports"),
    (re.compile(r"`rainbowomma-clip[^`]*`"), "the rainbow_clip_copy and rainbow_clip_paste tools"),
    (re.compile(r"`sim-owner lease[^`]*`"), "the rainbow_sim_lease tool"),
    (re.compile(r"`office-owner close[^`]*`"), "the rainbow_close_document tool"),
    (re.compile(r"`browser-owner`"), "the rainbow_*_browser tools"),
    (re.compile(r"its name comes from as-agent or its settings"), "its name is its Hermes profile"),
]
HELP = ("The rainbow_* tools do this safely (your own browser, your own ports and processes, leased documents); "
        "/rainbow shows who holds what.")


def translate(why: str) -> str:
    for pattern, tool in HINTS:
        why = pattern.sub(tool, why)
    return why


class GuardWorker:
    """the helper process and the one-request-at-a-time conversation with it"""

    def __init__(self, spawn=None):
        self._proc, self._env, self._n = None, None, 0
        self._lock = threading.Lock()
        self._spawn = spawn or self._default_spawn

    @staticmethod
    def _default_spawn(env):
        return subprocess.Popen([sys.executable, "-I", str(HERE / "guard_worker.py")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                env={**os.environ, **env})

    def _readline(self, proc, seconds):
        ready, _, _ = select.select([proc.stdout], [], [], seconds)
        if not ready:
            raise TimeoutError("the guard did not answer in time")
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("the guard stopped")
        return json.loads(line)

    def _ensure(self, env):
        if self._proc is not None and (self._proc.poll() is not None or self._env != env):
            self.stop()
        if self._proc is None:
            self._proc, self._env = self._spawn(env), dict(env)
            self._readline(self._proc, ANSWER_S)       # {"ready": true}
        return self._proc

    def ask(self, env: dict, request: dict) -> dict:
        """one request → its answer; any failure raises (the caller refuses)"""
        with self._lock:
            try:
                proc = self._ensure(env)
                self._n += 1
                proc.stdin.write(json.dumps({**request, "id": self._n}, ensure_ascii=False) + "\n")
                proc.stdin.flush()
                out = self._readline(proc, ANSWER_S)
                if out.get("id") != self._n:
                    raise RuntimeError("the guard answered another request")
                return out
            except Exception:
                self.stop()
                raise

    def stop(self):
        proc, self._proc, self._env = self._proc, None, None
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass


def decide(worker: GuardWorker, tool_name: str, args: dict, env: dict):
    """→ None (let it run) or a pre_tool_call directive. `env` is this agent's identity (core.Rainbow.guard_env())."""
    if not tool_name:
        return None
    try:
        if tool_name.startswith(OWN_PREFIX):          # the plugin's own tools are the owners themselves — only the
            paused = worker.ask(env, {"ask": "paused"}).get("paused")   # human's pause stops them
            return {"action": "block", "message": f"Blocked by RainbowOMMA: {PAUSED}."} if paused else None
        out = worker.ask(env, {"event": {"tool_name": tool_name, "tool_input": args if isinstance(args, dict) else {}}})
    except Exception as exc:                          # can't tell → no
        logger.warning("rainbowomma guard: %s: %s", type(exc).__name__, exc)
        return {"action": "block",
                "message": f"Blocked by RainbowOMMA: the guard could not judge this call ({type(exc).__name__}), "
                           "and \"can't tell\" is a refusal. Try again; if it keeps happening, tell the human."}
    why = out.get("why")
    if not why:
        return None
    if out.get("kind") == "send":
        return {"action": "approve", "rule_key": "rainbowomma.send",
                "message": "RainbowOMMA: this sends through Messages or Mail and can't be taken back. Allow it?"}
    return {"action": "block", "message": f"Blocked by RainbowOMMA: {translate(why)}. {HELP}"}

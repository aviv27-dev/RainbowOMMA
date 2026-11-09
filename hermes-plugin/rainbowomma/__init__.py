"""RainbowOMMA for Hermes — one Mac, many agents: each Hermes agent gets its own colored browser, ports, processes and
documents, and a guard keeps it off the human's and the other agents'.

Tools: the owners of an installed RainbowOMMA (tools.py). Hook: pre_tool_call runs RainbowOMMA's guard on every tool
call (guard.py); on_session_finalize gives back what the session left behind (its orphaned servers, its port leases).
Which agent this Hermes is: the plugin's `agent` setting, else the profile's name — as long as browsers.json has a row
for it. See README.md for everything the plugin runs, reads and writes.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from . import guard, tools

logger = logging.getLogger(__name__)
DEFAULT_BIN = "~/bin"


class Settings:
    """the plugin's settings (plugins.entries.rainbowomma.settings), read when used so a change applies at once"""

    def __init__(self, ctx):
        self.ctx = ctx
        self._agents = (None, None)

    def _get(self, key, default):
        try:
            v = self.ctx.get_config(key, default=default)
        except Exception:
            v = default
        return default if v is None or v == "" else v

    @property
    def bin_dir(self):
        return str(Path(str(self._get("bin_dir", DEFAULT_BIN))).expanduser())

    @property
    def guard_on(self):
        return self._get("guard", True) is not False

    def registry_path(self):
        return Path(os.environ.get("BROWSER_OWNER_REGISTRY") or Path(self.bin_dir) / "browsers.json").expanduser()

    def agents(self):
        """the agent names browsers.json has rows for (re-read when the file changes)"""
        p = self.registry_path()
        try:
            stamp = p.stat().st_mtime
        except OSError:
            return set()
        if self._agents[0] != stamp:
            try:
                names = set((json.loads(p.read_text(encoding="utf-8")).get("agents") or {}).keys())
            except (OSError, ValueError, AttributeError):
                names = set()
            self._agents = (stamp, names)
        return self._agents[1]

    @property
    def agent(self):
        """this Hermes' agent name: the setting, else the profile name — only when browsers.json has a row for it"""
        name = str(self._get("agent", "") or "").strip().lower()
        if not name:
            try:
                name = str(self.ctx.profile_name or "").strip().lower()
            except Exception:
                name = ""
        return name if name and name in self.agents() else ""

    def installed(self):
        return (Path(self.bin_dir) / "browser-owner").is_file()


def register(ctx):
    s = Settings(ctx)

    for name, (schema, _argv) in tools.TOOLS.items():
        ctx.register_tool(
            name=name, toolset="rainbowomma", schema=schema,
            handler=(lambda n: lambda args, **kw: tools.run(s.bin_dir, s.agent, n, args))(name),
            check_fn=s.installed,                      # hidden until RainbowOMMA is installed
            description=schema["description"], emoji="🌈")

    def pre_tool_call(tool_name=None, args=None, task_id=None, **kwargs):
        if not s.guard_on or (tool_name or "") in tools.TOOLS:      # our own tools go through their owners' checks
            return None
        return guard.check(s.bin_dir, s.agent, tool_name or "", args)

    def on_session_finalize(session_id=None, **kwargs):
        """the session is over: the agent's orphaned servers stop and its unused port leases go back (proc-owner reap,
        what RainbowOMMA's session-end hook does for every framework). Never blocks: errors are logged."""
        agent, exe = s.agent, Path(s.bin_dir) / "proc-owner"
        if not agent or not exe.is_file():
            return None
        try:
            subprocess.run([str(exe), "reap", agent], capture_output=True, text=True, timeout=30,
                           env=tools.tool_env(agent), stdin=subprocess.DEVNULL)
        except Exception as exc:
            logger.warning("rainbowomma: reap after the session failed: %s", exc)
        return None

    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("on_session_finalize", on_session_finalize)

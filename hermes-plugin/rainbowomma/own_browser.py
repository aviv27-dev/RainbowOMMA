"""own_browser — Hermes's own browser tools, in this agent's own Chrome.

With `browser.cloud_provider: rainbowomma` in the profile's config, Hermes's built-in browser tools (navigate, click,
snapshot, the CDP tools, the credential vault) stop opening a throwaway Chromium and drive the agent's colour-framed
Chrome instead — the one the human can see, and the one whose tabs the housekeeping closes.

A browser provider hands Hermes a CDP address and nothing else. Starting the browser is browser-owner's job, so a
browser the human closed is not reopened behind their back: the session fails with the owner's reason. Ending a
session leaves the browser running — it is the agent's, and its idle stop ends it.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

NAME = "rainbowomma"
CHROME = "/Applications/Google Chrome.app"
UP = ("started", "up", "already-up", "running")


def session_for(me: str, session=None) -> str:
    """the browser_exec session name this agent's call runs under. Hermes's browser daemon is found by its session name
    (`default` when the model gives none), and two Hermes processes on one Mac that use the same name share one daemon —
    the second agent would drive the first one's browser. Every call is put under the agent's own name."""
    import re
    own = "rb-" + re.sub(r"[^A-Za-z0-9_-]", "-", me)[:28]
    given = str(session or "").strip()
    if not given:
        return own
    if given == own or given.startswith(own + "-"):
        return given
    return (own + "-" + re.sub(r"[^A-Za-z0-9_-]", "-", given))[:64]


def debugger_url(port: int, timeout: float = 5.0) -> str:
    """the browser's websocket address, read from its own DevTools port on this Mac (127.0.0.1 only)"""
    with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/json/version", timeout=timeout) as resp:
        return str(json.loads(resp.read().decode("utf-8"))["webSocketDebuggerUrl"])


def make_provider(rb, base, read_url=debugger_url):
    """a BrowserProvider for this profile's agent. `base` is Hermes's BrowserProvider ABC, passed in so this module
    loads without Hermes (the tests use a plain class)."""

    class RainbowBrowser(base):
        @property
        def name(self) -> str:
            return NAME

        @property
        def display_name(self) -> str:
            return "RainbowOMMA (this agent's own Chrome)"

        def is_available(self) -> bool:
            return sys.platform == "darwin" and os.path.isdir(CHROME)

        def get_setup_schema(self) -> dict:
            return {"name": "RainbowOMMA", "badge": "local", "tag": "This agent's own colour-framed Chrome on this Mac",
                    "env_vars": []}

        def create_session(self, task_id: str) -> dict:
            me = rb.me
            _ok, out = rb.run("browser-owner.py", "start", me, "--by", me)
            if out.get("status") not in UP:
                raise RuntimeError(f"RainbowOMMA: {me}'s browser did not start ({out.get('status')}): "
                                   f"{out.get('why') or out.get('detail') or 'no reason given'}")
            _ok, st = rb.run("browser-owner.py", "status", me)
            try:
                url = read_url(int(st["port"]))
            except Exception as exc:
                raise RuntimeError(f"RainbowOMMA: {me}'s browser is up but its DevTools port did not answer "
                                   f"({type(exc).__name__})") from exc
            return {"session_name": f"rainbowomma-{me}-{task_id}", "bb_session_id": me, "cdp_url": url,
                    "features": {"own_browser": True, "visible": True}}

        def close_session(self, session_id: str) -> bool:
            return True                                # the browser is the agent's: it stays, and idles out by itself

        def emergency_cleanup(self, session_id: str) -> None:
            return None

    return RainbowBrowser()

"""The pre_tool_call guard: RainbowOMMA's own rules, judged in-process for every tool call.

The rules live in the installed RainbowOMMA (`rainbowomma-guard.py` in its bin folder): the same file every other
agent framework's hook runs, so Hermes agents are held to exactly the same rules. It is loaded once and asked through
its `decide(event, me)` function — no subprocess per call. A call the guard refuses is vetoed with
{"action": "block", "message"}; an error while judging is a refusal too ("can't tell" never means yes). Without an
installed RainbowOMMA there is nothing to judge with, and the guard stays out of the way (the tools say how to install).
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import logging
import shlex
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
GUARD_FILE = "rainbowomma-guard.py"
_lock = threading.Lock()
_loaded: dict = {}


def load(bin_dir):
    """the installed guard module (cached per file), or None when RainbowOMMA isn't installed there"""
    path = Path(bin_dir).expanduser() / GUARD_FILE
    if not path.is_file():
        return None
    key = str(path)
    with _lock:
        if key not in _loaded:
            loader = importlib.machinery.SourceFileLoader("rainbowomma_guard_rules", key)
            spec = importlib.util.spec_from_loader(loader.name, loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            _loaded[key] = mod
        return _loaded[key]


def _legacy_decide(path, event, agent):
    """an install from before decide() (RainbowOMMA 0.4.0 and older): its guard as the hook every framework runs —
    the payload on stdin, exit 2 and the reason on stderr"""
    from .tools import tool_env
    r = subprocess.run([sys.executable, "-I", str(path)], input=json.dumps(event), capture_output=True, text=True,
                       timeout=30, env=tool_env(agent or ""))
    if r.returncode == 0:
        return None
    return (r.stderr or "").strip().removeprefix("Blocked by RainbowOMMA:").strip() or f"the guard refused (exit {r.returncode})"


def decide(bin_dir, mod, event, agent):
    if callable(getattr(mod, "decide", None)):
        return mod.decide(event, me=agent or None)
    return _legacy_decide(Path(bin_dir).expanduser() / GUARD_FILE, event, agent)


def event_for(tool_name, args):
    """a Hermes tool call in the payload shape the guard reads (the tool's arguments as tool_input)"""
    args = args if isinstance(args, dict) else {}
    if tool_name == "execute_code" and isinstance(args.get("code"), str):
        # code Hermes runs itself: judged as the inline code it is (`python3 -c …`), so e.g. os.kill is caught
        return {"tool_name": tool_name, "tool_input": {"command": "python3 -c " + shlex.quote(args["code"])}}
    return {"tool_name": tool_name, "tool_input": args}


def check(bin_dir, agent, tool_name, args, loader=load):
    """→ None (let it run) or {"action": "block", "message": …}"""
    try:
        mod = loader(bin_dir)
    except Exception as exc:                   # an install the guard can't load: can't tell → no
        return {"action": "block", "message": f"Blocked by RainbowOMMA: its guard could not be loaded ({type(exc).__name__}: "
                                              f"{exc}) — run rainbowomma-doctor"[:400]}
    if mod is None:
        return None
    try:
        why = decide(bin_dir, mod, event_for(tool_name, args), agent)
    except Exception as exc:
        why = f"the guard could not judge this call ({type(exc).__name__}) — can't tell means no"
    if not why:
        return None
    help_ = getattr(mod, "HELP", "")
    return {"action": "block", "message": f"Blocked by RainbowOMMA: {why}. {help_}".strip()}

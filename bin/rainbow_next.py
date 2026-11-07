#!/usr/bin/env python3
"""rainbow_next — every refusal and failure says what happened (`why`) and what to do next (`next`).

The owners print one JSON answer. When its status is a refusal or a failure, `rainbow_next.dumps` makes sure that:
  · `why` is never empty, and an exception caught by a "one JSON answer, always" handler reads as an unexpected error
    in that tool (with the exception kept in it), not just `TypeError: …`;
  · `next` is there: a command to run, or "ask the human". An answer that already carries `next` keeps its own.
Status words, the other keys and exit codes are never changed; only these two fields are filled in.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
from rainbow_i18n import t  # noqa: E402

BAD = ("refused", "failed", "blocked", "busy", "blocked-by-dialog", "hung", "profile-busy")
GENERIC = {"refused": "nx.refused", "failed": "nx.failed", "blocked": "nx.blocked", "busy": "nx.busy",
           "blocked-by-dialog": "nx.dialog", "hung": "nx.hung", "profile-busy": "nx.profile_busy"}
# a tool's own advice, where it has a better one than the generic
OWN = {("port-owner", "refused"): "nx.port.refused", ("proc-owner", "refused"): "nx.proc.refused",
       ("screen-owner", "refused"): "nx.screen.refused", ("auth-owner", "refused"): "nx.auth.refused",
       ("sim-owner", "refused"): "nx.sim.refused", ("rainbowomma-approve", "refused"): "nx.approve.refused"}
EXC = re.compile(r"(?:^|: )[A-Z][A-Za-z]*(?:Error|Exception|Exit|Interrupt|Warning)\b")


def tool_name(argv0=None):
    n = Path(argv0 or sys.argv[0]).name
    n = n[:-3] if n.endswith(".py") else n
    return {"agent-office": "office-owner"}.get(n, n)


def fill(obj, tool=None):
    """the same answer, with `why` and `next` filled in when its status is a refusal or a failure"""
    if not isinstance(obj, dict) or obj.get("status") not in BAD:
        return obj
    tool = tool or tool_name()
    st = obj["status"]
    why = str(obj.get("why") or "").strip()
    unexpected = bool(EXC.search(why))
    out = dict(obj)
    if not why:
        out["why"] = t("nx.no_why", tool=tool, status=st)
    elif unexpected:
        out["why"] = t("nx.unexpected", tool=tool, what=why)
    if not out.get("next"):
        agent = obj.get("agent") or os.environ.get("RAINBOW_AGENT") or "AGENT"
        key = "nx.report" if unexpected or (st == "failed" and not why) else OWN.get((tool, st)) or GENERIC[st]
        out["next"] = t(key, tool=tool, agent=agent)
    return out


def dumps(obj, tool=None, **kw):
    """json.dumps of the answer with `why` and `next` filled in"""
    kw.setdefault("ensure_ascii", False)
    tool = tool or tool_name(sys._getframe(1).f_globals.get("__file__"))   # the owner that is answering, even run in-process
    filled = fill(obj, tool)
    audit = os.environ.get("RAINBOW_NEXT_AUDIT")   # the test suite: every refusal and failure it saw, one line each
    if audit and isinstance(filled, dict) and filled.get("status") in BAD:
        try:
            with open(audit, "a", encoding="utf-8") as f:
                f.write(json.dumps({"tool": tool, **filled}, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return json.dumps(filled, **kw)

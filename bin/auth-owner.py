#!/usr/bin/env python3
"""auth-owner — one agent at a time signs in to a site, and the human hands the one-time code to that agent only.

    auth-owner lease AGENT SITE [--minutes M] [--wait S]   sign in to SITE now (it is yours until you release it, or M minutes)
    auth-owner release AGENT SITE                         done signing in
    auth-owner code AGENT SITE [--why TEXT]               ask the human for the one-time code (SMS, app) — a dialog; the code
                                                          comes back to you only, and only while you hold SITE
    auth-owner who SITE · auth-owner list

Two agents signing in to the same account at once log each other out, and a one-time code typed into the wrong agent's
window is lost. Optional: it does nothing until browsers.json lists "authSites" (["accounts.example.com", …]); then the
guardrail refuses an agent's browser tools on those sites unless it holds the site. Exit codes: 0 ok · 2 refused ·
1 failure. One JSON answer.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder
import rainbow_receipts  # noqa: E402

DEFAULT_MINUTES = 10
ASK = None                       # tests replace it: (agent, site, why) -> the code, or None


def state_file():
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "state" / "auth.json"


def site_of(text):
    """a site from a URL or a host: lower case, no scheme, port, path or leading www."""
    t = str(text).strip().lower()
    t = re.sub(r"^[a-z][a-z0-9+.-]*://", "", t).split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1].split(":", 1)[0].rstrip(".")
    return t[4:] if t.startswith("www.") else t


def covered(host, sites):
    """the authSites entry this host falls under, or None"""
    h = site_of(host)
    return next((d for d in sites if h == d or h.endswith("." + d)), None)


class locked:
    def __enter__(self):
        state_file().parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(state_file().with_suffix(".lock")), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        os.close(self.fd)


def leases(now=None):
    """→ {site: {"holder", "until", "at"}} for the leases still in force"""
    try:
        d = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = now or time.time()
    return {k: v for k, v in d.items() if isinstance(v, dict) and v.get("holder") and float(v.get("until") or 0) > now}


def _write(d):
    f = state_file()
    fd, tmp = tempfile.mkstemp(prefix=".auth.", suffix=".tmp", dir=str(f.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d))
    os.replace(tmp, f)


def holder(site):
    cur = leases().get(site_of(site))
    return cur["holder"] if cur else None


def try_lease(agent, site, minutes):
    with locked():
        d = leases()
        cur = d.get(site)
        if cur and cur["holder"] != agent:
            return False, cur
        d[site] = {"holder": agent, "until": time.time() + minutes * 60, "at": (cur or {}).get("at") or time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        _write(d)
        return True, d[site]


def cmd_lease(agent, site, minutes, wait):
    if not (0 < minutes <= 60 and 0 <= wait <= 600) or not math.isfinite(minutes):
        return 2, {"status": "refused", "why": "minutes must be more than 0 and at most 60, --wait at most 600 seconds"}
    deadline = time.time() + wait
    while True:
        ok, cur = try_lease(agent, site, minutes)
        if ok:
            rainbow_receipts.write("auth-owner", "lease", agent, agent, "leased", site=site, minutes=minutes)
            return 0, {"status": "leased", "site": site, "until": int(cur["until"])}
        if time.time() >= deadline:
            return 2, {"status": "refused", "why": f"{cur['holder']} is signing in to {site} — wait (--wait 120), or ask the human",
                       "holder": cur["holder"], "until": int(cur["until"])}
        time.sleep(2.0)


def cmd_release(agent, site):
    with locked():
        d = leases()
        if d.get(site, {}).get("holder") != agent:
            return 0, {"status": "not-held", "site": site}
        d.pop(site)
        _write(d)
    rainbow_receipts.write("auth-owner", "release", agent, agent, "released", site=site)
    return 0, {"status": "released", "site": site}


def ask_human(agent, site, why):
    """a dialog for the code; → the code, or None (cancelled, or no answer in 3 minutes)"""
    if ASK:
        return ASK(agent, site, why)
    text = f"{agent} is signing in to {site} and needs the one-time code you just got." + (f"\n\nWhy: {why}" if why else "")
    script = (f"display dialog {json.dumps(text)} with title \"RainbowOMMA\" default answer \"\" buttons {{\"Cancel\", \"Give the code\"}} "
              f"default button \"Give the code\" with icon note giving up after 180")
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=200)
    except Exception:
        return None
    m = re.search(r"text returned:(.*?)(?:, gave up:|$)", r.stdout.strip())
    return m.group(1).strip() if r.returncode == 0 and m and "gave up:true" not in r.stdout else None


def cmd_code(agent, site, why):
    if holder(site) != agent:
        return 2, {"status": "refused", "why": f"take {site} first: `auth-owner lease {agent} {site}` — the code goes to the agent signing in"}
    why = re.sub(r"[\x00-\x1f\x7f]+", " ", why or "").strip()[:200]
    code = ask_human(agent, site, why)
    rainbow_receipts.write("auth-owner", "code", agent, agent, "given" if code else "refused", site=site)   # never the code itself
    if not code:
        return 2, {"status": "refused", "why": "the human gave no code (cancelled, or no answer in 3 minutes) — ask them"}
    return 0, {"status": "given", "site": site, "code": code}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="auth-owner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    le = sub.add_parser("lease"); le.add_argument("agent"); le.add_argument("site")
    le.add_argument("--minutes", type=float, default=DEFAULT_MINUTES); le.add_argument("--wait", type=float, default=0)
    rl = sub.add_parser("release"); rl.add_argument("agent"); rl.add_argument("site")
    co = sub.add_parser("code"); co.add_argument("agent"); co.add_argument("site"); co.add_argument("--why", default="")
    w = sub.add_parser("who"); w.add_argument("site")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if a.cmd in ("lease", "release", "code") and rainbow_receipts.acting_as(a.agent):
        print(json.dumps({"status": "refused", "why": rainbow_receipts.acting_as(a.agent)}, ensure_ascii=False))
        return 2
    try:
        if a.cmd == "lease":
            code, out = cmd_lease(a.agent.strip().lower(), site_of(a.site), a.minutes, a.wait)
        elif a.cmd == "release":
            code, out = cmd_release(a.agent.strip().lower(), site_of(a.site))
        elif a.cmd == "code":
            code, out = cmd_code(a.agent.strip().lower(), site_of(a.site), a.why)
        elif a.cmd == "who":
            code, out = 0, {"site": site_of(a.site), "holder": holder(a.site)}
        else:
            code, out = 0, {"leases": leases()}
    except Exception as exc:   # one JSON answer, always
        code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())

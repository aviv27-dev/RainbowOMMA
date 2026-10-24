"""rainbow_tabs — tab housekeeping for the agents' own browsers: a tab that keeps burning CPU long after anyone used it is
reloaded, and if it stays hot, closed. Run by `browser-owner tabs` (and its launchd job every 15 minutes).

    one run        through each agent's own CDP port: every page tab, its renderer's main-thread time over a few seconds
                   (Performance.getMetrics TaskDuration) → % of one core
    the rule       hot (≥ cpuPercent) in every run for hotMinutes, and stale (seen for minAgeHours, or on the same URL for
                   idleMinutes), and no other client attached to it (an agent driving it) → reload it; still hot for another
                   hotMinutes after the reload → close it. Never the browser's last tab.
    never          the human's Chrome or any browser outside browsers.json; an agent with "tabSweep": false, one in
                   tabSweep.exclude, or one managedBy another tool (a logged-in smart-card session, say); a browser whose
                   port isn't its own tree's. Nothing is killed: reload and close go through CDP (Page.reload,
                   Target.closeTarget) — no process is ever signalled.
    dry run        the default: what it would do is reported and logged, nothing is touched, until browsers.json says
                   "tabSweep": {"mode": "apply"} (or --apply is given by hand).

Settings (browsers.json, top level, all optional):
    "tabSweep": {"mode": "dry-run", "cpuPercent": 10, "hotMinutes": 30, "minAgeHours": 6, "idleMinutes": 120,
                 "sampleSeconds": 10, "gpuPercent": 15, "exclude": ["delta"]}
The browser's GPU process is measured too (SystemInfo.getProcessInfo): it can't be told per tab, so it is only reported,
with one notification when it stays above gpuPercent for hotMinutes.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from urllib.parse import urlsplit

DEFAULTS = {"mode": "dry-run", "cpuPercent": 10.0, "hotMinutes": 30.0, "minAgeHours": 6.0, "idleMinutes": 120.0,
            "sampleSeconds": 10.0, "gpuPercent": 15.0, "exclude": []}
SKIP_URLS = ("devtools://", "chrome://", "chrome-extension://", "chrome-untrusted://", "about:blank")


def config(raw):
    """the tabSweep settings from the registry's raw JSON, with defaults; nonsense values fall back to the defaults"""
    got = raw.get("tabSweep") if isinstance(raw.get("tabSweep"), dict) else {}
    out = dict(DEFAULTS)
    for k, v in got.items():
        if k == "mode" and v in ("dry-run", "apply"):
            out[k] = v
        elif k == "exclude" and isinstance(v, list):
            out[k] = [str(x).strip().lower() for x in v]
        elif k in DEFAULTS and k not in ("mode", "exclude") and isinstance(v, (int, float)) and v > 0:
            out[k] = float(v)
    out["sampleSeconds"] = min(out["sampleSeconds"], 60.0)
    return out


def host(url):
    try:
        return urlsplit(url).hostname or url[:40]
    except ValueError:
        return url[:40]


def gpu_time(cdp):
    """the browser's GPU process CPU time so far (seconds), or None — it can't be told per tab, only per browser"""
    try:
        procs = cdp.call("SystemInfo.getProcessInfo").get("processInfo", [])
        return sum(float(x.get("cpuTime") or 0) for x in procs if x.get("type") == "GPU") if procs else None
    except OSError:
        return None


def sample(cdp, seconds, sleep=time.sleep):
    """→ ([{"id", "url", "title", "attached", "cpu"}] for every page tab, the number of page tabs, the GPU process's % of
    one core) — cpu: % over the window, None when unknown. One connection, flattened sessions; detached at the end."""
    infos = cdp.call("Target.getTargets").get("targetInfos", [])
    g1, t1 = gpu_time(cdp), time.monotonic()
    pages = [t for t in infos if t.get("type") == "page" and not str(t.get("url", "")).startswith(SKIP_URLS)]
    first = {}
    for t in pages:
        try:
            sid = cdp.call("Target.attachToTarget", {"targetId": t["targetId"], "flatten": True})["sessionId"]
            cdp.call("Performance.enable", {}, sid)
            first[t["targetId"]] = (sid, _metrics(cdp.call("Performance.getMetrics", {}, sid)))
        except OSError:
            continue
    if first or g1 is not None:
        sleep(seconds)
    g2, wall_g = gpu_time(cdp), max(time.monotonic() - t1, seconds)
    gpu = round(max(0.0, g2 - g1) / wall_g * 100, 1) if g1 is not None and g2 is not None else None
    out = []
    for t in pages:
        cpu, sid = None, None
        if t["targetId"] in first:
            sid, m1 = first[t["targetId"]]
            try:
                m2 = _metrics(cdp.call("Performance.getMetrics", {}, sid))
                wall = m2.get("Timestamp", 0) - m1.get("Timestamp", 0)
                if wall > 0 and "TaskDuration" in m1 and "TaskDuration" in m2:
                    cpu = round(max(0.0, m2["TaskDuration"] - m1["TaskDuration"]) / wall * 100, 1)
            except OSError:
                pass
        out.append({"id": t["targetId"], "url": str(t.get("url", "")), "title": str(t.get("title", ""))[:80],
                    "attached": bool(t.get("attached")), "cpu": cpu, "session": sid})
    return out, len([t for t in infos if t.get("type") == "page"]), gpu


def _metrics(res):
    return {m.get("name"): float(m.get("value") or 0) for m in res.get("metrics", []) if isinstance(m, dict)}


def plan(tabs, recs, cfg, now, page_count):
    """the rule, with no I/O → (tabs with an "action", the new per-tab records). action: None · reload · close ·
    skip-in-use (a client is attached: an agent drives it) · skip-last-tab"""
    new, out, left = {}, [], page_count
    for t in tabs:
        r = dict(recs.get(t["id"]) or {"firstSeen": now, "url": t["url"], "urlSince": now})
        if r.get("url") != t["url"]:                     # it navigated: someone uses it — start over
            r.update(url=t["url"], urlSince=now, hotSince=None, reloaded=False)
        hot = t["cpu"] is not None and t["cpu"] >= cfg["cpuPercent"]
        if hot:
            r["hotSince"] = r.get("hotSince") or now
            r.pop("coolSince", None)
        else:
            r["hotSince"] = None
            r["coolSince"] = r.get("coolSince") or now
            if now - r["coolSince"] >= cfg["hotMinutes"] * 60:
                r["reloaded"] = False                    # cool long enough: a later fever starts with a reload again
        hot_long = hot and now - r["hotSince"] >= cfg["hotMinutes"] * 60
        stale = now - r["firstSeen"] >= cfg["minAgeHours"] * 3600 or now - r["urlSince"] >= cfg["idleMinutes"] * 60
        action = None
        if hot_long and stale:
            if t["attached"]:
                action = "skip-in-use"
            elif not r.get("reloaded"):
                action = "reload"
            elif left <= 1:
                action = "skip-last-tab"
            else:
                action = "close"
                left -= 1
        new[t["id"]] = r
        out.append({**t, "action": action, "hotForMinutes": int((now - r["hotSince"]) / 60) if r.get("hotSince") else 0,
                    "seenForHours": round((now - r["firstSeen"]) / 3600, 1)})
    return out, new


def state_path(shared, agent):
    return shared / "state" / f"tabs-{agent}.json"


def load_state(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, d):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d, ensure_ascii=False))
    os.replace(tmp, path)


def sweep_agent(a, cfg, apply, view, shared, cdp_class, now=None, sleep=time.sleep):
    """one agent's browser → {"agent", "status", "tabs": [...]}; acts only when apply. view, shared and cdp_class are
    browser-owner's (its picture of the browser, $RAINBOW_HOME, its CDP client)"""
    now = time.time() if now is None else now
    v = view(a)
    if v["status"] != "up":                              # down, hung, blocked (a foreign listener on its port) …: nothing to do
        return {"agent": a["name"], "status": v["status"], "tabs": []}
    sp = state_path(shared, a["name"])
    st = load_state(sp)
    with cdp_class(a["port"], timeout=10) as cdp:
        tabs, pages, gpu = sample(cdp, cfg["sampleSeconds"], sleep)
        planned, recs = plan(tabs, st.get("tabs") or {}, cfg, now, pages)
        for t in planned:
            t["done"] = False
            if not apply or t["action"] not in ("reload", "close"):
                continue
            try:
                if t["action"] == "reload":
                    cdp.call("Page.reload", {"ignoreCache": False}, t["session"])
                    recs[t["id"]].update(reloaded=True, reloadedAt=now, hotSince=None)
                else:
                    cdp.call("Target.closeTarget", {"targetId": t["id"]})
                    recs.pop(t["id"], None)
                t["done"] = True
            except OSError as exc:
                t["error"] = str(exc)[:120]
        for t in tabs:
            if t["session"]:
                try:
                    cdp.call("Target.detachFromTarget", {"sessionId": t["session"]})
                except OSError:
                    pass
    st["tabs"] = recs                                    # tabs that are gone drop out with it
    save_state(sp, st)
    st["gpuHotSince"] = (st.get("gpuHotSince") or now) if gpu is not None and gpu >= cfg["gpuPercent"] else None
    alert = bool(st["gpuHotSince"]) and now - st["gpuHotSince"] >= cfg["hotMinutes"] * 60 and not st.get("gpuAlerted")
    st["gpuAlerted"] = bool(st["gpuHotSince"]) and (alert or bool(st.get("gpuAlerted")))     # once per hot spell
    save_state(sp, st)
    return {"agent": a["name"], "status": "swept", "gpu": gpu, "gpuAlert": alert,
            "gpuHotMinutes": int((now - st["gpuHotSince"]) / 60) if st.get("gpuHotSince") else 0,
            "tabs": [{k: x[k] for k in ("id", "url", "title", "cpu", "action", "done", "hotForMinutes", "seenForHours", "attached")}
                     | ({"error": x["error"]} if "error" in x else {}) for x in planned]}


def summarize(results, cpu_percent):
    """counts across agents → {"reloaded", "closed", "wouldReload", "wouldClose", "hot"}"""
    c = {"reloaded": 0, "closed": 0, "wouldReload": 0, "wouldClose": 0, "hot": 0, "gpuHot": 0}
    for r in results:
        if r.get("gpuHotMinutes"):
            c["gpuHot"] += 1
        for t in r.get("tabs", []):
            if (t.get("cpu") or 0) >= cpu_percent:
                c["hot"] += 1
            if t.get("action") == "reload":
                c["reloaded" if t.get("done") else "wouldReload"] += 1
            elif t.get("action") == "close":
                c["closed" if t.get("done") else "wouldClose"] += 1
    return c


def daily(shared, counts, today=None):
    """add this run's counts to today's; → yesterday's totals when the day just changed (one summary a day), else None"""
    today = today or time.strftime("%Y-%m-%d")
    p = shared / "state" / "tabs-daily.json"
    d = load_state(p)
    prev = None
    if d.get("day") and d["day"] != today:
        prev = {"day": d["day"], **{k: d.get(k, 0) for k in counts}}
        d = {}
    d["day"] = today
    for k, v in counts.items():
        d[k] = int(d.get(k, 0)) + int(v)
    save_state(p, d)
    return prev

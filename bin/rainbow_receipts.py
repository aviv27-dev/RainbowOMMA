#!/usr/bin/env python3
"""rainbow_receipts — one line per thing the owners did or refused, for the human to read back.

Every owner (browser-owner, port-owner, proc-owner, office-owner) and the guard append one JSON line to
$RAINBOW_HOME/logs/receipts.jsonl: when, which tool, what, for which agent, by whom, the status word, and a few details.
Read-only commands (list, status, who, whose) leave no receipt. A receipt that can't be written never stops the tool.

    receipts [--agent NAME] [--tool TOOL] [--since 2026-10-19T08:00] [-n 50]     the last receipts, oldest first
    receipts --export-otlp [URL]     send the receipts not sent yet to an OpenTelemetry collector (OTLP/HTTP JSON logs;
                                     default $OTEL_EXPORTER_OTLP_ENDPOINT) — Langfuse, Honeycomb, Grafana … read them there
"""
from __future__ import annotations

import argparse
import calendar
import fcntl
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

MAX_FIELD = 300


def path():
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "logs" / "receipts.jsonl"


def write(tool, action, agent=None, by=None, status=None, **detail):
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool, "action": action, "agent": agent, "by": by, "status": status}
    rec.update({k: (v[:MAX_FIELD] if isinstance(v, str) else v) for k, v in detail.items() if v not in (None, "", [], {})})
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        pass
    return rec


def read(agent=None, tool=None, since=None, n=50):
    try:
        lines = path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if agent and r.get("agent") != agent:
            continue
        if tool and r.get("tool") != tool:
            continue
        if since and str(r.get("at", ""))[:len(since)] < since:
            continue
        out.append(r)
    return out[-n:] if n else out


def _attr(k, v):
    return {"key": k, "value": {"intValue": str(v)} if isinstance(v, int) and not isinstance(v, bool) else {"stringValue": str(v)}}


def _nanos(at):
    try:
        t = time.strptime(at[:19], "%Y-%m-%dT%H:%M:%S")
        off = int(at[19:22]) * 3600 + int(at[19] + at[22:24]) * 60 if len(at) >= 24 else 0
        return str((calendar.timegm(t) - off) * 10**9)
    except (ValueError, IndexError):
        return str(time.time_ns())


def otlp_payload(recs):
    """receipts → one OTLP/JSON logs request (GenAI semantic conventions: gen_ai.agent.name)"""
    logs = []
    for r in recs:
        attrs = [_attr("gen_ai.agent.name", r["agent"])] if r.get("agent") else []
        attrs += [_attr(f"rainbowomma.{k}", v) for k, v in r.items() if k not in ("at", "agent") and v not in (None, "", [], {})]
        bad = r.get("status") in ("refused", "blocked", "failed", "busy")
        logs.append({"timeUnixNano": _nanos(str(r.get("at", ""))), "severityText": "WARN" if bad else "INFO",
                     "severityNumber": 13 if bad else 9, "body": {"stringValue": f"{r.get('tool')} {r.get('action')} → {r.get('status')}"},
                     "attributes": attrs})
    return {"resourceLogs": [{"resource": {"attributes": [_attr("service.name", "rainbowomma")]},
                              "scopeLogs": [{"scope": {"name": "rainbowomma.receipts"}, "logRecords": logs}]}]}


def export_otlp(url):
    """send the receipts written since the last export; the cursor moves only when the collector took them → (sent, error)"""
    cursor = path().with_name("receipts.otlp-cursor")
    try:
        done = int(cursor.read_text().strip() or 0)
    except (OSError, ValueError):
        done = 0
    recs = read(n=0)
    if done > len(recs):
        done = 0                                         # the receipts file was replaced
    todo = recs[done:]
    if not todo:
        return 0, None
    endpoint = url.rstrip("/") + ("" if url.rstrip("/").endswith("/v1/logs") else "/v1/logs")
    req = urllib.request.Request(endpoint, data=json.dumps(otlp_payload(todo)).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 300:
                return 0, f"HTTP {resp.status}"
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"[:200]
    cursor.write_text(str(len(recs)))
    return len(todo), None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="receipts")
    ap.add_argument("--agent"); ap.add_argument("--tool"); ap.add_argument("--since"); ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--export-otlp", nargs="?", const="", metavar="URL")
    a = ap.parse_args(argv)
    if a.export_otlp is not None:
        url = a.export_otlp or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or ""
        if not url:
            print(json.dumps({"status": "failed", "why": "no collector: pass a URL or set OTEL_EXPORTER_OTLP_ENDPOINT"}))
            return 1
        sent, err = export_otlp(url)
        print(json.dumps({"status": "failed", "why": err} if err else {"status": "exported", "sent": sent}))
        return 1 if err else 0
    for r in read(a.agent, a.tool, a.since, a.n):
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

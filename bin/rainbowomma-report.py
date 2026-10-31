#!/usr/bin/env python3
"""rainbowomma-report — file a bug or a feature request on RainbowOMMA's GitHub, after a privacy scan of what you send.

    rainbowomma-report bug|feature --title TEXT --body-file FILE [--repo OWNER/NAME] [--dry-run]
    rainbowomma-report scan FILE...            only the scan: every finding, nothing sent

The title and body are scanned before anything leaves the Mac. A finding stops it (exit 2) and says where; fix the text and
run it again. What counts as a finding:
  · built in: e-mail addresses (a GitHub/Anthropic noreply one is fine), home paths (/Users/<name>, /home/<name>), private and
    Tailscale (100.64/10) IP addresses, *.ts.net names, API keys and tokens (sk-, ghp_, github_pat_, xox*, AKIA…), phone numbers;
  · from this Mac: your user name and the computer's name, and every agent name and label in your browsers.json (the
    placeholders alpha / bravo / charlie / human are fine);
  · yours: one regular expression per line in $RAINBOW_HOME/report-deny.txt (never in the repository) — names, clients,
    case numbers, domains, anything that would say whose Mac this is. Lines starting with # are comments.

The body must follow the repository's issue template (its bold headings, in order); the template's label (bug, enhancement)
is set. `gh` sends it: `gh issue create -R REPO --title … --body-file … --label …` (`gh auth login` once). The body is
sent as given — never rewritten.

Exit codes: 0 sent (or a clean dry run / scan) · 2 refused (a finding, or the template's headings missing) · 1 failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "aviv27-dev/RainbowOMMA"
ROOT = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or "~/.rainbowomma"))
REGISTRY = Path(os.environ.get("BROWSER_OWNER_REGISTRY") or HERE / "browsers.json")
PLACEHOLDERS = {"alpha", "bravo", "charlie", "human", "you", "user", "agent"}

# the issue templates' headings (.github/ISSUE_TEMPLATE/*.md — a test keeps these equal) and labels
TEMPLATES = {
    "bug": {"label": "bug", "headings": ["What happened", "What you expected", "Command and its JSON answer", "Setup"]},
    "feature": {"label": "enhancement", "headings": ["The problem on a shared Mac", "What you'd like RainbowOMMA to do",
                                                     "Agent framework, if it's about one"]},
}

BUILTIN = [
    ("e-mail address", r"[A-Za-z0-9._%+-]+@(?!(?:users\.noreply\.github\.com|noreply\.github\.com|anthropic\.com)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("home path", r"/(?:Users|home)/(?!you\b|x\b|user\b|me\b|Shared\b)[A-Za-z0-9._-]+"),
    ("private IP address", r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    ("Tailscale address", r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
    ("Tailscale name", r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b"),
    ("API key or token", r"\b(?:sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b"),
    ("phone number", r"(?<![\w.])\+?\d{1,3}[ -]?\(?\d{2,3}\)?[ -]?\d{3}[ -]?\d{4}(?![\w.])"),
]


def local_terms():
    """this Mac's own identifying words: the user, the computer, the agents' names and labels (not the placeholders)"""
    words = set()
    for w in (os.environ.get("USER"), os.environ.get("LOGNAME"), socket.gethostname().split(".")[0]):
        if w and len(w) >= 3:
            words.add(w)
    try:
        agents = json.loads(REGISTRY.read_text(encoding="utf-8")).get("agents", {})
        for name, row in agents.items():
            for w in (name, (row or {}).get("label")):
                if isinstance(w, str) and len(w.strip()) >= 3:
                    words.add(w.strip())
    except (OSError, ValueError, AttributeError):
        pass
    return sorted(w for w in words if w.lower() not in PLACEHOLDERS)


def deny_patterns(path=None):
    """$RAINBOW_HOME/report-deny.txt — the person's own list; a line that isn't a valid expression is matched literally"""
    out = []
    try:
        lines = Path(path or ROOT / "report-deny.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        try:
            out.append(re.compile(ln, re.I))
        except re.error:
            out.append(re.compile(re.escape(ln), re.I))
    return out


def scan(text, where="body", deny=None, terms=None):
    """[(where, line, kind)] — the kind of finding only, never the matched text (the report itself must not repeat it)"""
    rules = [(k, re.compile(p)) for k, p in BUILTIN]
    rules += [("a name from this Mac", re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])", re.I)) for w in (local_terms() if terms is None else terms)]
    rules += [("your report-deny.txt", rx) for rx in (deny_patterns() if deny is None else deny)]
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for kind, rx in rules:
            if rx.search(line):
                hits.append((where, n, kind))
    return hits


def template_gaps(kind, body):
    """the template's bold headings this body lacks, or has out of order"""
    pos, gaps = -1, []
    for h in TEMPLATES[kind]["headings"]:
        i = body.find(f"**{h}**")
        if i < 0 or i < pos:
            gaps.append(h)
        else:
            pos = i
    return gaps


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rainbowomma-report")
    ap.add_argument("kind", choices=["bug", "feature", "scan"])
    ap.add_argument("files", nargs="*", help="scan: the files to scan")
    ap.add_argument("--title")
    ap.add_argument("--body-file")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.kind == "scan":
        hits = []
        for f in a.files:
            hits += scan(Path(f).read_text(encoding="utf-8"), where=f)
        print(json.dumps({"status": "clean" if not hits else "findings", "findings": [f"{w}:{n}: {k}" for w, n, k in hits]}, ensure_ascii=False))
        return 0 if not hits else 2

    if not a.title or not a.body_file:
        print(json.dumps({"status": "failed", "why": "--title and --body-file are needed"}))
        return 1
    try:
        body = Path(a.body_file).read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"status": "failed", "why": f"body: {exc}"[:200]}))
        return 1
    hits = scan(a.title, where="title") + scan(body)
    gaps = template_gaps(a.kind, body)
    if hits or gaps:
        print(json.dumps({"status": "refused", "findings": [f"{w}:{n}: {k}" for w, n, k in hits],
                          "missingHeadings": gaps, "why": "fix the text and run it again — nothing was sent"}, ensure_ascii=False))
        return 2
    cmd = ["gh", "issue", "create", "-R", a.repo, "--title", a.title, "--body-file", a.body_file, "--label", TEMPLATES[a.kind]["label"]]
    if a.dry_run:
        print(json.dumps({"status": "would-send", "command": cmd}, ensure_ascii=False))
        return 0
    if not shutil.which("gh"):
        print(json.dumps({"status": "failed", "why": "gh is not installed (brew install gh, then gh auth login)"}))
        return 1
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(json.dumps({"status": "failed", "why": (r.stderr or r.stdout).strip()[-300:]}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "sent", "url": r.stdout.strip().splitlines()[-1:][0] if r.stdout.strip() else ""}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

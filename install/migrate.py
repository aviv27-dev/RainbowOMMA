#!/usr/bin/env python3
"""migrate.py — move a pre-release (legacy) RainbowOMMA install's state into $RAINBOW_HOME. install.sh --migrate-from runs it.

    python3 install/migrate.py OLD_DIR NEW_HOME [--registry browsers.json] [--dry-run]

Copies, never moves: the old folder is left as it was. A file already in the new home is kept (never overwritten). An
agent's browser state with a legacy stop flag named after the person (offBy<Name>) gets offByHuman — any such flag set,
or one that can't be read, means stopped: a browser the human closed must stay closed. Locks, sockets, a broker's keys
and Word's temp copies are not carried over. Rows of browsers.json that still point into the old folder are reported.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

LEGACY_OFF = re.compile(r"^offBy[A-Z]\w*$")
SKIP_DIRS = {"__pycache__", "cdp", "office_inflight"}          # per-install keys and sockets; conversions in flight
SKIP_SUFFIX = (".lock", ".sock", ".tmp", ".pid")
TEMP_DIRS = {"word-convert"}                                 # Word's temp copies: never worth carrying over


def stop_flag(d):
    """an agent's browser state with offByHuman decided from any legacy offBy<Name> key → (state, changed)"""
    if not isinstance(d, dict) or "offByHuman" in d:
        return d, False
    legacy = {k: v for k, v in d.items() if LEGACY_OFF.match(k)}
    if not legacy:
        return d, False
    d = dict(d)
    d["offByHuman"] = any(v is not False and v is not None and v != 0 for v in legacy.values())   # in doubt: stopped
    return d, True


def plan(old, new):
    """→ [(action, rel, detail)] for every file under old"""
    out = []
    for root, dirs, files in os.walk(old, followlinks=False):
        rel_root = Path(root).relative_to(old)
        top = rel_root.parts[0] if rel_root.parts else ""
        if top in TEMP_DIRS:
            out += [("skip", str(rel_root / f), "Word's temp copy") for f in files]
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not (Path(root) / x).is_symlink()]
        for f in files:
            rel, src = rel_root / f, Path(root) / f
            if src.is_symlink():
                out.append(("skip", str(rel), "a symlink"))
            elif f.endswith(SKIP_SUFFIX):
                out.append(("skip", str(rel), "a lock, socket or temp file"))
            elif (Path(new) / rel).exists():
                out.append(("keep", str(rel), "already in the new home — not overwritten"))
            elif rel.parts and rel.parts[0] == "browsers" and f.endswith(".json"):
                try:
                    _, changed = stop_flag(json.loads(src.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    changed = False
                out.append(("copy", str(rel), "legacy stop flag → offByHuman" if changed else ""))
            else:
                out.append(("copy", str(rel), ""))
    return out


def apply(old, new, steps):
    for action, rel, _ in steps:
        if action != "copy":
            continue
        src, dst = Path(old) / rel, Path(new) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if Path(rel).parts[0] == "browsers" and rel.endswith(".json"):
            try:
                d, changed = stop_flag(json.loads(src.read_text(encoding="utf-8")))
                if changed:
                    dst.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    shutil.copystat(src, dst)
                    continue
            except (OSError, ValueError):
                pass
        shutil.copy2(src, dst)


def registry_refs(registry, old):
    """rows of browsers.json whose state / log / launcher path still points into the old folder"""
    try:
        agents = json.loads(Path(registry).read_text(encoding="utf-8")).get("agents", {})
    except (OSError, ValueError, AttributeError):
        return []
    old_r = os.path.realpath(old)
    got = []
    for name, row in agents.items():
        for k in ("state", "log", "launcher", "profile"):
            v = row.get(k) if isinstance(row, dict) else None
            if isinstance(v, str) and os.path.realpath(os.path.expanduser(v)).startswith(old_r + os.sep):
                got.append(f"{name}.{k} = {v}")
    return got


def main(argv=None):
    ap = argparse.ArgumentParser(prog="migrate")
    ap.add_argument("old"); ap.add_argument("new"); ap.add_argument("--registry"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    old, new = Path(os.path.expanduser(a.old)), Path(os.path.expanduser(a.new))
    if not old.is_dir():
        print(f"migrate: {old} is not a folder", file=sys.stderr)
        return 2
    ro, rn = os.path.realpath(old), os.path.realpath(new)
    if ro == rn or rn.startswith(ro + os.sep) or ro.startswith(rn + os.sep):
        print("migrate: the old and the new folder must be separate", file=sys.stderr)
        return 2
    steps = plan(old, new)
    if not a.dry_run:
        new.mkdir(parents=True, exist_ok=True)
        os.chmod(new, 0o700)
        apply(old, new, steps)
    verb = "would copy" if a.dry_run else "copied"
    n = {k: sum(1 for s in steps if s[0] == k) for k in ("copy", "keep", "skip")}
    print(f"migrate {old} → {new}{' (dry run — nothing changed)' if a.dry_run else ''}")
    for action, rel, detail in steps:
        if action != "copy" or detail:
            print(f"  {verb if action == 'copy' else action}: {rel}{' — ' + detail if detail else ''}")
    print(f"  {n['copy']} {verb}, {n['keep']} kept, {n['skip']} skipped; the old folder is unchanged")
    for ref in registry_refs(a.registry, old) if a.registry else []:
        print(f"  browsers.json still points into the old folder: {ref} — change it to the new home")
    return 0


if __name__ == "__main__":
    sys.exit(main())

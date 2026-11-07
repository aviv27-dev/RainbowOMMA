#!/usr/bin/env python3
"""changes.py OLD NEW CHANGELOG.md — what changed between two releases, short, for the end of an upgrade.

Every release after OLD up to NEW: its headings and the first line of each entry. Entries under "### Action needed"
are printed in full at the end, because they ask something of the person (a job to reinstall, a setting to add).
Prints nothing when OLD isn't older than NEW (a first install, a reinstall, a downgrade) or a version can't be read.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))   # -I drops the script's folder; the catalog is in bin/
from rainbow_i18n import t  # noqa: E402

WIDTH = 110


def ver(s):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (s or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def sections(text):
    """[(version, title line, body)] for every released section, newest first"""
    out = []
    heads = list(re.finditer(r"^## \[(\d+\.\d+\.\d+)\][^\n]*$", text, re.M))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        body = re.split(r"^\[\d+\.\d+\.\d+\]: ", body, flags=re.M)[0]      # the link list at the bottom
        out.append((m.group(1), m.group(0)[3:].strip(), body))
    return out


def entries(body):
    """[(heading, [lines of one entry])] in order"""
    out, head, cur = [], None, None
    for ln in body.splitlines():
        if ln.startswith("### "):
            head, cur = ln[4:].strip(), None
        elif ln.startswith("- "):
            cur = [ln[2:].strip()]
            out.append((head, cur))
        elif cur is not None and ln.startswith("  ") and ln.strip():
            cur.append(ln.strip())
        elif not ln.strip():
            cur = None
    return out


def short(s):
    s = s.strip()
    return s if len(s) <= WIDTH else s[:WIDTH - 1].rstrip() + "…"


def report(old, new, text):
    o, n = ver(old), ver(new)
    if not o or not n or o >= n:
        return ""
    lines, actions = [t("ch.since", old=old.lstrip("v"), new=new.lstrip("v"))], []
    for v, title, body in sections(text):
        if not (o < ver(v) <= n):
            continue
        lines.append(f"  {title}")
        last = None
        for head, e in entries(body):
            if head == "Action needed":
                actions.append((v, " ".join(e)))
                continue
            if head != last:
                lines.append(f"    {head}")
                last = head
            lines.append(f"      · {short(e[0])}")
    if actions:
        lines += ["", t("ch.action")]
        lines += [f"  · {e} ({v})" for v, e in actions]
    lines += ["", t("ch.full")]
    return "\n".join(lines)


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        text = Path(argv[2]).read_text(encoding="utf-8")
    except OSError:
        return 0                     # no notes beside this copy: nothing to say, and never a reason to fail an install
    out = report(argv[0], argv[1], text)
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

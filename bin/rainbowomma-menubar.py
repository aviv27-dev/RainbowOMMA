#!/usr/bin/env python3
"""rainbowomma-menubar — the menu-bar item (a SwiftBar plugin): every agent as a dot in its color, a stop button for all.

SwiftBar (https://swiftbar.app) runs the plugin install.sh --with-menubar writes, every 10 seconds; this prints its menu:
    the title     one dot per agent — filled when its browser is up — or ⏸ while the human paused all agents
    the menu      each agent: its status, open / bring to front, close · pause / resume all agents (⌘⌥⌃P)
                  · take over the screen / hand it back
                  · the latest receipts · the doctor
Read-only: every action in the menu runs the same tool the human could run in a terminal.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
import rainbow_receipts  # noqa: E402
from rainbow_i18n import t  # noqa: E402

PAUSE_SHORTCUT = "CMD+OPTION+CTRL+P"


def ansi_dot(hex_rgb, filled):
    v = int(hex_rgb[1:], 16)
    return f"\033[38;2;{(v >> 16) & 255};{(v >> 8) & 255};{v & 255}m{'●' if filled else '○'}\033[0m"


def run_json(*argv):
    try:
        r = subprocess.run([str(HERE / argv[0]), *argv[1:]], capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {}


def action(tool, *params, terminal=False, refresh=True):
    """SwiftBar's parameters for running one of the tools beside this one"""
    def q(x):
        x = str(x)
        return f'"{x}"' if any(c in x for c in " \t\"'") else x       # SwiftBar reads double-quoted values
    out = f"bash={q(HERE / tool)}"
    for i, p in enumerate(params, 1):
        out += f" param{i}={q(p)}"
    return out + f" terminal={'true' if terminal else 'false'}" + (" refresh=true" if refresh else "")


def clean(x):
    """one menu line's text: a newline or | in a label, a holder or a receipt would start a menu item of its own (bash=…)"""
    return re.sub(r"[\x00-\x1f\x7f|]+", " ", str(x if x is not None else ""))


def menu(agents, paused, receipts, screen=None):
    lines = []
    if paused:
        lines.append(f"⏸ {t('mb.paused_title')}")
    else:
        lines.append(" ".join(ansi_dot(a["color"], a.get("up")) for a in agents) + " | ansi=true" if agents else "🌈")
    lines.append("---")
    for a in agents:
        color = a["color"] if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(a.get("color"))) else "#757575"
        lines.append(f"{clean(a['label'])} — {clean(a['status'])} | color={color}")
        lines.append(f"--{t('mb.front') if a.get('up') else t('mb.open')} | " + action("desk-browser.sh", "open", a["agent"]))
        if a.get("up"):
            lines.append(f"--{t('mb.close')} | " + action("desk-browser.sh", "close", a["agent"]))
    lines.append("---")
    if paused:
        lines.append(f"▶ {t('mb.resume_all')} | " + action("rainbowomma-pause", "off") + f" shortcut={PAUSE_SHORTCUT}")
    else:
        lines.append(f"⏸ {t('mb.pause_all')} | " + action("rainbowomma-pause", "on") + f" shortcut={PAUSE_SHORTCUT}")
    if screen and screen.get("holder") == "human":
        lines.append(f"🖐 {t('mb.handback')} | " + action("screen-owner", "handback"))
    else:
        if screen and screen.get("holder"):
            lines.append(f"{clean(t('mb.screen_held', who=screen['holder']))} | color=#757575")
        lines.append(f"🖐 {t('mb.takeover')} | " + action("screen-owner", "takeover"))
    lines.append("---")
    lines.append(t("mb.recent"))
    for r in reversed(receipts):
        who = r.get("agent") or "—"
        lines.append("--" + clean(f"{str(r.get('at', ''))[11:16]} {who}: {r.get('tool')} {r.get('action')} → {r.get('status')}")[:120]
                     + " | size=12")
    lines.append(f"{t('mb.doctor')} | " + action("rainbowomma-doctor", terminal=True, refresh=False))
    return "\n".join(lines)


def main():
    listing = run_json("browser-owner", "list").get("agents", [])
    paused = (rainbow_receipts.path().parent.parent / "state" / "paused.json").exists()     # $RAINBOW_HOME/state
    print(menu(listing, paused, rainbow_receipts.read(n=8), run_json("screen-owner", "who")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

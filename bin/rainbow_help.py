#!/usr/bin/env python3
"""rainbow_help — every tool's --help, in one shape and in every language the catalog speaks.

    rainbow_help.py TOOL      print TOOL's help (for the shell scripts)

The shape, for every tool in bin/:
    TOOL — what it is for
    Commands:   each command, a line on what it does, and an example
    Exit codes: what each one means
    More:       where to read more

`--help` and `-h` print this and exit 0. They never act: no browser opens, no process stops, nothing is read from stdin.
A command's own options stay with argparse (`port-owner lease --help`). A test runs --help on every tool and checks the shape.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
from rainbow_i18n import M, lang  # noqa: E402

HEAD = ("help.commands", "help.exits", "help.more", "help.eg")   # the headings, in rainbow_i18n like every word shown

# TOOL: [(command, the catalog key of what it does, an example)], [(exit code, the catalog key of its meaning)], where to read more.
# What the tool is for is the catalog's "help.TOOL".
H = {
    "browser-owner": {
        "commands": [
            ("list | names | status AGENT", "help.browser-owner.1", "browser-owner list"),
            ("start AGENT --by WHO", "help.browser-owner.2", "browser-owner start alpha --by alpha"),
            ("stop AGENT --by human [--allow-reopen]", "help.browser-owner.3", "browser-owner stop alpha --by human"),
            ("idle-stop | recover | front AGENT", "help.browser-owner.4", "browser-owner front alpha"),
            ("open AGENT URL", "help.browser-owner.5", "browser-owner open alpha https://example.com"),
            ("tabs [AGENT] [--apply] · job-start | job-end | job-keep | job-close AGENT", "help.browser-owner.6", "browser-owner job-start alpha"),
            ("mcp-config AGENT [--tool devtools|playwright] [--format json|claude]", "help.browser-owner.7", "browser-owner mcp-config alpha --format claude"),
            ("heal | human-theme | presence", "help.browser-owner.8", "browser-owner presence"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §3",
    },
    "port-owner": {
        "commands": [
            ("lease AGENT [--name NAME] [--prefer PORT]", "help.port-owner.1", "port-owner lease alpha --name web"),
            ("env AGENT [--name NAME] [--var VAR …]", "help.port-owner.2", "eval \"$(port-owner env alpha --name web) npm run dev\""),
            ("who PORT", "help.port-owner.3", "port-owner who 3000"),
            ("release AGENT [--name NAME | --all]", "help.port-owner.4", "port-owner release alpha --name web"),
            ("list [AGENT]", "help.port-owner.5", "port-owner list alpha"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §8",
    },
    "proc-owner": {
        "commands": [
            ("whose PID", "help.proc-owner.1", "proc-owner whose 4242"),
            ("kill PID --by WHO [--force]", "help.proc-owner.2", "proc-owner kill 4242 --by alpha"),
            ("list AGENT", "help.proc-owner.3", "proc-owner list alpha"),
            ("register AGENT", "help.proc-owner.4", "proc-owner register alpha"),
            ("reap AGENT [--session ID] [--dry-run]", "help.proc-owner.5", "proc-owner reap alpha --dry-run"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §9",
    },
    "office-owner": {
        "commands": [
            ("open | close | renew --agent NAME FILE", "help.office-owner.1", "office-owner open --agent alpha --app word ~/Reports/draft.docx"),
            ("pdf --agent NAME FILE.docx [--out FILE.pdf] [--force]", "help.office-owner.2", "office-owner pdf --agent alpha ~/Reports/draft.docx"),
            ("xlsx --agent NAME BOOK.xlsx [--out OTHER.xlsx] [--pdf SHEET.pdf]", "help.office-owner.3", "office-owner xlsx --agent alpha ~/Reports/book.xlsx"),
            ("sweep [--max-age-h 3] [--dry-run] · list · apps", "help.office-owner.4", "office-owner apps"),
        ],
        "exits": [(0, "help.office-owner.x0"), (3, "help.office-owner.x3"), (2, "help.office-owner.x2"), (1, "help.office-owner.x1")], "more": "docs/DESIGN.md §4",
    },
    "auth-owner": {
        "commands": [
            ("lease AGENT SITE [--minutes M] [--wait S]", "help.auth-owner.1", "auth-owner lease alpha accounts.example.com"),
            ("release AGENT SITE", "help.auth-owner.2", "auth-owner release alpha accounts.example.com"),
            ("code AGENT SITE [--why TEXT]", "help.auth-owner.3", "auth-owner code alpha accounts.example.com"),
            ("who SITE · list", "help.auth-owner.4", "auth-owner list"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §16",
    },
    "screen-owner": {
        "commands": [
            ("take AGENT [--minutes M] [--wait S]", "help.screen-owner.1", "screen-owner take alpha --minutes 5"),
            ("release AGENT", "help.screen-owner.2", "screen-owner release alpha"),
            ("takeover [--minutes M] · handback", "help.screen-owner.3", "screen-owner takeover"),
            ("who", "help.screen-owner.4", "screen-owner who"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §13",
    },
    "sim-owner": {
        "commands": [
            ("lease AGENT [--device \"iPhone 16\"]", "help.sim-owner.1", "sim-owner lease alpha"),
            ("who UDID", "help.sim-owner.2", "sim-owner who \"$UDID\""),
            ("release AGENT [--shutdown]", "help.sim-owner.3", "sim-owner release alpha"),
            ("list", "help.sim-owner.4", "sim-owner list"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §14",
    },
    "rainbowomma-approve": {
        "commands": [
            ("ask --agent NAME --why \"TEXT\" -- COMMAND …", "help.rainbowomma-approve.1", "rainbowomma-approve ask --agent alpha --why \"the weekly report\" -- osascript send.scpt"),
            ("list", "help.rainbowomma-approve.2", "rainbowomma-approve list"),
        ],
        "exits": [(0, "help.rainbowomma-approve.x0"), (2, "help.rainbowomma-approve.x2"), (1, "help.x.failed")], "more": "docs/DESIGN.md §13",
    },
    "rainbowomma-clip": {
        "commands": [
            ("copy AGENT [--name N]", "help.rainbowomma-clip.1", "echo text | rainbowomma-clip copy alpha"),
            ("paste AGENT [--name N]", "help.rainbowomma-clip.2", "rainbowomma-clip paste alpha"),
            ("clear AGENT", "help.rainbowomma-clip.3", "rainbowomma-clip clear alpha"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.x.refused"), (1, "help.x.failed")], "more": "docs/DESIGN.md §14",
    },
    "rainbowomma-pause": {
        "commands": [
            ("on | off | toggle", "help.rainbowomma-pause.1", "rainbowomma-pause on"),
            ("status", "help.rainbowomma-pause.2", "rainbowomma-pause status"),
        ],
        "exits": [(0, "help.x.ok"), (1, "help.x.failed")], "more": "docs/DESIGN.md §12",
    },
    "rainbowomma-doctor": {
        "commands": [
            ("[--json]", "help.rainbowomma-doctor.1", "rainbowomma-doctor"),
            ("status [--json]", "help.rainbowomma-doctor.2", "rainbowomma-doctor status"),
            ("logs [--since DATE] [-n N]", "help.rainbowomma-doctor.3", "rainbowomma-doctor logs --since 2026-11-01"),
        ],
        "exits": [(0, "help.rainbowomma-doctor.x0"), (1, "help.rainbowomma-doctor.x1")], "more": "README.md (Quick start)",
    },
    "rainbowomma-report": {
        "commands": [
            ("bug | feature --title TEXT --body-file FILE [--repo OWNER/NAME] [--dry-run]", "help.rainbowomma-report.1", "rainbowomma-report bug --title \"…\" --body-file bug.md --dry-run"),
            ("scan FILE…", "help.rainbowomma-report.2", "rainbowomma-report scan draft.md"),
        ],
        "exits": [(0, "help.rainbowomma-report.x0"), (2, "help.rainbowomma-report.x2"), (1, "help.x.failed")], "more": "docs/REPORTING.md",
    },
    "receipts": {
        "commands": [
            ("[--agent NAME] [--tool TOOL] [--since TIME] [-n 50]", "help.receipts.1", "receipts --agent alpha -n 20"),
            ("--export-otlp [URL]", "help.receipts.2", "receipts --export-otlp http://127.0.0.1:4318"),
        ],
        "exits": [(0, "help.x.ok"), (1, "help.x.failed")], "more": "docs/DESIGN.md §11",
    },
    "rainbowomma-guard": {
        "commands": [
            ("[--format exit2|cline] < payload.json", "help.rainbowomma-guard.1", "echo '{\"tool_input\":{\"command\":\"ls\"}}' | rainbowomma-guard"),
        ],
        "exits": [(0, "help.rainbowomma-guard.x0"), (2, "help.rainbowomma-guard.x2")], "more": "docs/DESIGN.md §5, docs/ISOLATION.md",
    },
    "rainbowomma-session-end": {
        "commands": [
            ("(no arguments)", "help.rainbowomma-session-end.1", "RAINBOW_AGENT=alpha rainbowomma-session-end"),
        ],
        "exits": [(0, "help.rainbowomma-session-end.x0")], "more": "docs/AGENTS.md",
    },
    "rainbowomma-mcp": {
        "commands": [
            ("--agent NAME", "help.rainbowomma-mcp.1", "rainbowomma-mcp --agent alpha"),
        ],
        "exits": [(0, "help.x.ok"), (1, "help.x.failed")], "more": "docs/DESIGN.md §10",
    },
    "rainbowomma-browser": {
        "commands": [
            ("URL", "help.rainbowomma-browser.1", "BROWSER=~/bin/rainbowomma-browser"),
        ],
        "exits": [(0, "help.rainbowomma-browser.x0")], "more": "docs/AGENTS.md",
    },
    "rainbowomma-menubar": {
        "commands": [
            ("(no arguments)", "help.rainbowomma-menubar.1", "rainbowomma-menubar"),
        ],
        "exits": [(0, "help.x.ok")], "more": "README.md (the menu bar)",
    },
    "cua-color-proxy": {
        "commands": [
            ("--agent NAME [--theme ID] [--reduced-motion on|auto|off] [--driver PATH] [-- DRIVER ARGS…]", "help.cua-color-proxy.1", "cua-color-proxy --agent alpha"),
        ],
        "exits": [(0, "help.x.ok"), (1, "help.x.failed")], "more": "docs/DESIGN.md §6",
    },
    "as-agent": {
        "commands": [
            ("NAME COMMAND [ARGS…]", "help.as-agent.1", "as-agent alpha claude"),
        ],
        "exits": [(0, "help.as-agent.x0"), (2, "help.as-agent.x2")], "more": "docs/AGENTS.md",
    },
    "desk-browser.sh": {
        "commands": [
            ("open | close AGENT", "help.desk-browser.sh.1", "desk-browser.sh open alpha"),
            ("open | close human · close agents", "help.desk-browser.sh.2", "desk-browser.sh close agents"),
        ],
        "exits": [(0, "help.x.ok"), (2, "help.desk-browser.sh.x2"), (1, "help.desk-browser.sh.x1")], "more": "README.md (One-click desktop controls)",
    },
    "human-chrome.sh": {
        "commands": [
            ("(no arguments)", "help.human-chrome.sh.1", "human-chrome.sh"),
        ],
        "exits": [(0, "help.x.ok"), (1, "help.human-chrome.sh.x1")], "more": "README.md (One-click desktop controls)",
    },
    "kill-chrome.sh": {
        "commands": [
            ("(no arguments)", "help.kill-chrome.sh.1", "kill-chrome.sh"),
            ("--all", "help.kill-chrome.sh.2", "kill-chrome.sh --all"),
        ],
        "exits": [(0, "help.x.ok")], "more": "README.md (One-click desktop controls)",
    },
    "rainbow-panel.sh": {
        "commands": [
            ("(no arguments)", "help.rainbow-panel.sh.1", "rainbow-panel.sh"),
        ],
        "exits": [(0, "help.x.ok"), (1, "help.rainbow-panel.sh.x1")], "more": "README.md (One-click desktop controls)",
    },
}
ALIAS = {"agent-office": "office-owner", "rainbow-panel": "rainbow-panel.sh", "rainbow_receipts": "receipts"}


def key(tool):
    """the catalog key for a file name in bin/ (with or without .py), or None"""
    name = Path(tool).name
    if name.endswith(".py"):
        name = name[:-3]
    name = ALIAS.get(name, name)
    return name if name in H else None


def text(tool, lg=None):
    lg = lg or lang()
    k = key(tool)
    h = H[k]
    w = lambda m: M[m].get(lg) or M[m]["en"]   # noqa: E731
    out = [f"{k} — {w('help.' + k)}", "", w("help.commands")]
    for cmd, what, eg in h["commands"]:
        prefix = "" if cmd.startswith("(") else f"{k} "
        out += [f"  {prefix}{cmd}", f"      {w(what)}", f"      {w('help.eg')} {eg}"]
    out += ["", w("help.exits")]
    out += [f"  {code}  {w(m)}" for code, m in h["exits"]]
    out += ["", f"{w('help.more')} {h['more']}"]
    return "\n".join(out)


def handle(tool, argv=None):
    """print the help and exit 0 when the first argument is -h or --help; otherwise return"""
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]) and key(tool):
        print(text(tool))
        sys.exit(0)


def main(argv):
    if len(argv) != 1 or not key(argv[0]):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    print(text(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

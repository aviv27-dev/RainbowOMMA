# 🌈 RainbowOMMA — One Mac, Many Agents

**Let a human and a whole team of AI agents share one Mac without stepping on each other.**

Your agents drive Chrome, open Word documents and fill in web portals, and you're still on the same Mac doing
your own work. RainbowOMMA keeps that arrangement civil: each agent gets **its own browser in its own color**,
one owner decides who may open or close it, and nothing an agent does can kill your browser or close a document
you're typing in.

![A shared Mac: the human's grey Chrome and three agent browsers, each in its own color with the agent's name written across the frame](docs/images/rainbow-desktop.png)

<sub>Illustration of the window frames RainbowOMMA paints. Today the UI text is Hebrew (RTL), and English/LTR is on the roadmap.</sub>

---

## Why

Put two or three agents on one machine and the same accidents keep happening:

- **Keystrokes land in the wrong window.** macOS sees every Chrome as one app, so typing meant for your browser can end up in an agent's.
- **Agents kill each other's browsers.** Each one writes its own "keep my browser alive" or "clean up" script. A `pkill -f chrome` in one agent logs another agent out mid-task, and sometimes kills the shell that was about to relaunch it.
- **Documents close under you.** An agent that "closes the active document" in Word can close the one *you* were editing, without saving.
- **You can't tell whose window is whose.** Four identical Chrome windows, and only one of them is yours.

## What it does

RainbowOMMA has one rule: **one owner per resource; everyone else asks it.**

| Resource | Owner | What it guarantees |
|---|---|---|
| Each agent's Chrome (its CDP port + profile) | `browser-owner` | One lock per agent. Starting twice never opens a second Chrome. Agents can't close each other's browser. |
| Documents agents open in Word / Excel / Acrobat / Preview | `agent-office` | Per-document leases. A document is closed only if *that agent* opened it and it's saved. Apps are never quit. |
| Your own Chrome | **you** | Nothing here ever touches it. |

### 🎨 A color for every agent
Each agent's browser wears a **real Chrome theme**: the whole frame is painted in the agent's color, with its name
written across it. One look at the screen tells you whose window is in front, and your own browser can be marked
"HUMAN · free to use".

### 🧑 The human comes first
- Only the human closes an agent's browser for good. After you close it, agent and keepalive restarts are `refused` until you reopen it.
- If you quit an agent's Chrome with ⌘Q, the tool remembers that and doesn't relaunch it behind your back (`closed-by-person`).
- A new agent window that takes focus hands it straight back to whatever you were using.
- Shared GUI apps are never quit, and an app that isn't running is never launched just to check on it.

### 🛑 If in doubt, do nothing
A port that answers but isn't the agent's own browser is reported as `blocked`, not "up". A profile open somewhere
else is `profile-busy`. If the process table changes during a check, nothing is killed. Before recovering a hung
browser, the tool probes it three times over 30 seconds or more, so a Mac deep in swap doesn't lose a logged-in session.

### 🤖 Made for agents to call
Every command prints **one JSON answer** with stable status words and exit codes (`browser-owner`: `0` ok · `2` refused · `1` failure;
`agent-office`: `0` done · `3` left open · `1` failure), so an agent can branch on the result instead of guessing.

![browser-owner in a terminal: start, already-up, an agent refused when it tries to close another agent's browser, and a refusal to reopen a browser the human closed](docs/images/browser-owner-terminal.png)

### 🖱️ One-click desktop controls
`install/make-desktop-apps.sh` puts colored open/close icons on the desktop: one pair per agent, one for your own
Chrome, and a "close all agents" button that asks for confirmation first.

![Colored desktop icons for opening and closing each agent's browser, the human's Chrome, and all agents](docs/images/desktop-icons.png)

---

## Quick start

```bash
git clone https://github.com/aviv27-dev/RainbowOMMA.git && cd RainbowOMMA
cp bin/* ~/bin/                                # the tools look for each other in the same folder
$EDITOR ~/bin/browsers.json                    # one row per agent: port, profile, color, label

~/bin/browser-owner start alpha --by alpha     # paints Alpha's browser and opens it in the background
~/bin/browser-owner list                       # who's up, blocked, hung, or closed by the human
~/bin/browser-owner stop alpha --by human      # only the human closes an agent's browser
install/make-desktop-apps.sh                   # optional: colored open/close icons on the desktop
```

A row in `browsers.json`:

```json
"alpha": { "label": "Alpha", "port": 9222, "profile": "~/agents/alpha-profile", "color": "#8E24AA" }
```

Then tell each agent, in its prompt, skill or rules, to open its browser **only** through
`browser-owner start <name> --by <name>`, and to stop when the answer is `refused`, `closed-by-person`, `blocked`
or `profile-busy`.

Documents work the same way:

```bash
~/bin/agent-office open  --agent alpha --app word ~/Reports/draft.docx
~/bin/agent-office close --agent alpha ~/Reports/draft.docx   # only if Alpha opened it and it's saved
```

## Guardrails for your agent framework

A guardrail stops an agent from going around the owner with its own `pkill`, `killall` or AppleScript `quit`:

- **Hermes Agent:** a ready-made deny list in [`adapters/hermes-approvals-deny.yaml`](adapters/hermes-approvals-deny.yaml).
- **Claude Code / Codex CLI:** the patterns are in [`docs/DESIGN.md`](docs/DESIGN.md#5-agent-adapters-the-guardrails). Ready-made adapters are on the roadmap.

Pattern rules only see the command an agent runs directly. The owner's own checks are the real protection.

## Requirements

macOS · Google Chrome · Python 3.9+ (standard library only) · `osascript` (built in). No dependencies to install.

## Tests

```bash
python3 tests/test_rainbowomma.py
```

The tests use a fake process table, a fake `osascript` and a fake Chrome. They never touch a real browser or app.

## Design

[`docs/DESIGN.md`](docs/DESIGN.md) covers the principles, every status word, and the Chrome behaviour the tools rely
on, which was measured rather than guessed: how ⌘Q is told apart from a reboot, why `open -g` isn't enough to keep
focus, and how a theme is installed through the DevTools pipe on Chrome 137+.

## Roadmap

- English + Hebrew message catalog (LTR + RTL frames)
- `install.sh`, launchd sweep with absolute paths, and one configurable state directory
- Ready-made Claude Code and Codex CLI guardrails
- A human-activity gate that waits while you're typing
- Per-agent tab claims, an auth/login lease, and a separate Chrome channel per agent

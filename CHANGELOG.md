# Changelog

All notable changes to RainbowOMMA. Versions follow [Semantic Versioning](https://semver.org/); JSON status words and
exit codes are an API and change only in a major version.

## [Unreleased]

### Added
- Homebrew: the repository is its own tap (`brew tap aviv27-dev/rainbowomma https://github.com/aviv27-dev/RainbowOMMA`,
  `brew install rainbowomma`); `rainbowomma-install` and `rainbowomma-uninstall` run the same installer into your folder.
- `browser-owner tabs` measures each agent browser's GPU process too (`SystemInfo.getProcessInfo`, `gpu` in its answer):
  it can't be pinned to one tab, so it is reported, with one notification when it stays above `gpuPercent` (15%) for
  `hotMinutes`.

### Fixed
- proc-owner: a recorded process mark holds only while the process is the same one — its command line and, now, its
  start time (a pid the system handed out again, to the same kind of command, is never the agent's). On macOS,
  `RAINBOW_AGENT=…` counts only in a process's environment, never as words in its own command line.

## [0.2.0] — 2026-10-24

### Added
- Tab housekeeping: `browser-owner tabs` measures the CPU of every tab in the agents' own browsers (through their CDP
  ports) and, for a stale tab hot for 30 minutes, reloads it, then closes it if it stays hot — never the last tab, one
  an agent drives, an excluded or `managedBy` browser, or the human's Chrome; nothing is killed. A dry run until
  `tabSweep.mode` is `apply`. `install.sh --with-tab-sweep`: every 15 minutes, a daily summary, a notification per close.

### Security
- A security review of the whole code (guard, owners, installer, CI) and its fixes. The guard now refuses: `kill -1`,
  `kill 0` and process groups; `xargs kill`; kill from inline code; commands hidden in heredocs, `| sh`, `<<<`,
  `env -S`, `find -exec`, `timeout`/`setsid`/`stdbuf`/`flock`/`script`, `sh -c --` and AppleScript's `do shell script`;
  an owner tool acting as another agent or the human (`--by`, its agent argument, `as-agent`); setting `RAINBOW_HOME`,
  `BROWSER_OWNER_REGISTRY`, `RAINBOW_AGENT` or `RAINBOW_TEST_*`; writing RainbowOMMA's state or `browsers.json` (shell
  and Write/Edit); the human's Chrome profile (shell and file tools); another agent's DevTools port on any host
  (`127.1`, `[::1]`, `0.0.0.0`); quitting or closing Chrome through AppleScript; `rm -r` of `~/.`, `~/Library`,
  `~/Documents` and the like; more ways to take a port (`php -S`, `nc -l`, `next -p`, `http.server -b`). An error while
  judging, or no python3, is a refusal (it was a pass).
- Every owner tool acts only as the caller (`RAINBOW_AGENT`): screen-owner, sim-owner, rainbowomma-clip, port-owner,
  proc-owner, office-owner, browser-owner. `human` and `human-*` are never an agent's name; screen leases last at most
  60 minutes.
- Approvals: no environment variable answers for the human (`RAINBOW_TEST_APPROVE` is gone); an approval is the asking
  agent's only and is used once even under parallel calls (locked); a command too long to read is refused, not cut; the
  reason is one short line.
- browser-owner: a link inside an agent's profile (to the human's) stops start, recover and heal; a theme folder with
  anything but the theme in it is rebuilt (the human's too); lock and log files never open through a link; a CDP message
  is capped at 32 MB; idle-stop needs a known start time; the browser MCP packages are pinned.
- proc-owner: a Python framework is its own root, and nothing at or above tmux, a login, a terminal or an editor ever is;
  a process under one agent's mark can't register as another.
- The menu bar strips newlines and `|` (no injected `bash=` items); a planted link at the pause flag counts as paused;
  receipts, approvals and state are yours only (0700/0600); an OTLP export to another URL keeps its own cursor; the
  cursor proxy holds batches, calls without an id and unreadable lines while paused.
- Installer: `--adapter` takes plain names only and paths are escaped; `uninstall.sh --purge` removes only a folder that is
  RainbowOMMA's (never your home); the Dock tray empties only a folder named RainbowOMMA; labels can't break out of
  AppleScript; the Claude Code adapter guards Write/Edit/Read too.
- CI: actions pinned by commit, no persisted credentials, tools pinned; releases only from main, with a write token
  only in the release job.

### Added
- `receipts --export-otlp`: receipts to an OpenTelemetry collector (OTLP/HTTP JSON logs, `gen_ai.agent.name`).
- Apps an agent never drives: `deniedApps` (default: terminals, System Settings, Keychain Access, Passwords, Activity
  Monitor) and per-agent `"apps"` allow/deny, for AppleScript, `open -a` and computer-use tools.
- `docs/ISOLATION.md`: separate macOS users, VMs, containers, virtual displays, credentials, and standards to watch.
- `sim-owner`: an iOS Simulator of each agent's own; the guard refuses `simctl … booted` and another agent's (or a
  shared) simulator. `rainbowomma-clip`: a clipboard of each agent's own; a named agent's `pbcopy`/`pbpaste` are refused.
- CI runs the test suite on Linux too.
- `screen-owner`: one lease for the screen (keyboard, mouse, the window in front). Foreground GUI actions take a short
  lease by themselves through the guard, so two agents never type into each other's windows; `takeover`/`handback`
  let the human stop every agent's GUI action and give it back (also in the menu bar).
- `rainbowomma-approve`: sending through Messages or Mail needs the human's "Allow once" for that exact command; no
  agent may click while the dialog is up. MCP tools: `take_screen`, `release_screen`, `ask_human_approval`.
- `browser-owner mcp-config`: a Chrome DevTools MCP or Playwright MCP entry on the agent's own browser; the guard refuses
  `--autoConnect`/`--extension` and another agent's CDP port.
- `sensitiveSites`: an agent's browser tools open them only while the human is at the Mac.
- `rainbowomma-pause` (the stop button for all agents) and `install.sh --with-menubar` (a SwiftBar item: agents as
  colored dots, open/front/close, pause with ⌘⌥⌃P, the latest receipts).
- `office-owner xlsx`: the real Excel recalculates every formula on its own copy, which then replaces the workbook (or
  goes to `--out`); `--pdf` exports the active sheet. A workbook open in Excel is never written under.
- `rainbowomma-doctor`: what's in place, what's missing and how to fix it (`--json` for agents); changes nothing.
- `uninstall.sh`, and `install.sh --adapter <framework>`: the adapter with your paths filled in, ready to merge.
- CI lints Python (ruff, real errors only) and every shell script (shellcheck, warnings and up).
- `"chrome"` per agent in `browsers.json` (`stable`, `beta`, `dev`, `canary`, `cft` or a path to a Chrome `.app`): the
  agent's browser runs as a separate app, so the human's ⌘Q and Chrome updates can't reach it. Every Chrome flavor is
  recognized as an agent's root process.
- Receipts: every acting command of every owner and every guard refusal leaves one JSON line in
  `$RAINBOW_HOME/logs/receipts.jsonl`; `bin/receipts` reads them back.
- The human at the keyboard comes first: GUI commands and MCP computer-use actions wait until the human has paused for
  5 seconds (the guard refuses them; the cursor proxy holds them, at most 30 s). The Claude Code adapter runs the guard
  before MCP computer-use actions too.
- The guard refuses `rm -r` of the home folder, the whole disk or a system folder.
- `port-owner`: a port range per agent (`"ports"` in `browsers.json`, by default 100 ports from 41000), leases inside
  it (`lease`, `env` for `eval`, `who`, `release`, `list`), and the usual dev ports kept for the human (`humanPorts`).
  The guardrail refuses `kill-port`, `fuser -k` and `lsof`/`ps` piped into `kill`, and holds an agent started with
  `RAINBOW_AGENT=<name>` to its own ports (`--port`, `PORT=`, `docker -p`, `http.server`).
- `proc-owner`: whose a process is (`RAINBOW_AGENT` in its environment, an ancestor, or the agent's Chrome; else the
  human's), `kill --by` that stops only your own, `list`, and `reap`, which stops a session's leftover servers and
  returns its idle port leases. The guardrail refuses a plain `kill <pid>` of another agent's (or, for a named agent,
  the human's) process.
- `as-agent NAME COMMAND`: runs any agent as NAME (`RAINBOW_AGENT`, `RAINBOW_SESSION`) and reaps when it exits;
  `rainbowomma-session-end`, the session-end hook for Claude Code, Gemini CLI, Factory Droid and Copilot CLI. The
  Claude Code adapter names its agent (`"env": {"RAINBOW_AGENT": "alpha"}`).
- `rainbowomma-mcp`: the owners as MCP tools (`lease_port`, `who_port`, `whose_process`, `stop_process`,
  `my_processes`, `browser_status`, `start_my_browser`, `recover_my_browser`), standard library only.
- Guardrail plug-ins for 17 agent frameworks (`docs/AGENTS.md`): Claude Code, Codex CLI, Gemini CLI, OpenCode, Kilo
  Code, Qwen Code, Factory Droid, Hermes Agent, Goose, Zed, GitHub Copilot (CLI and VS Code), Cursor, Cline, Continue,
  and drafts for Windsurf, Amp and OpenClaw. They share one hook, `bin/rainbowomma-guard`, which reads each
  framework's payload, and add the framework's own deny rules where it has them.
- `cua-color-proxy`: an MCP proxy in front of `cua-driver mcp` that gives every session of any MCP agent (Claude Code,
  OpenClaw, OpenCode, Codex CLI, Cursor, …) that agent's colored cursor, with no change to the agent.
- `CONTRIBUTING.md`, `SECURITY.md`, issue and pull request templates.
- A logo, real screenshots, and a branded social preview.

- `browser-owner front <agent>`: brings the agent's browser to the human's front, un-minimizing its windows through its
  own CDP port. `desk-browser.sh open` uses it for a browser that is already open.
- `install/make-dock-tray.sh`: the agents' browsers as one group in the Dock, right after Chrome, closed by the person's
  own Chrome in their color (`--remove` takes it out).
- `browser-owner heal` and `install.sh --with-heal`: every 30 minutes and at login, the colors Chrome Sync took come back
  (now for a closed browser; on the next start, with one notification, for an open one), and a Chrome update is noted.
- `ONLY=<agent> install/make-desktop-apps.sh`: one agent's icons, nothing archived.

### Changed
- The Claude Code guard moved to `bin/rainbowomma-guard` (installed with the other tools); the Hermes adapter files
  moved to `adapters/hermes/`.
- Desktop icons (`make-desktop-apps.sh`, `desk-browser.sh`) are made for every agent in `browsers.json`, in its own
  color, instead of three fixed agents. Every "close" icon asks for confirmation. `make-desktop-apps.sh --bin DIR`.
- The example registry uses orange, blue and green, like the screenshots and the logo.
- The English frame text reads "<label> · AI Agent · Do not touch". Existing English themes are rebuilt once.
- `bin/browsers.json` is no longer tracked: `install.sh` creates it from `examples/browsers.example.json`, and a missing
  registry gets a clear answer instead of a traceback.

### Fixed
- macOS 27 hides other processes' environments (`ps -E`), so `RAINBOW_AGENT` could no longer show whose a process was
  and the guard's `kill <pid>` rule failed open. Ownership now comes from marks the agents write: `as-agent` registers
  its shell (`proc-owner register`), the guard registers the agent framework above it and records its descendants
  (`$RAINBOW_HOME/state/proc-roots.json`, pid + command line). "Can't tell" is refused: a named agent may `kill` only
  what is provably its own, and an agent without a name no live process at all.
- An agent's theme comes back after Chrome Sync replaced it (signing in to Google inside the agent's profile).
- `office-owner` reports osascript's own reason for a failure instead of "exit 1".
- `desk-browser.sh` exits 1 with the reason on stderr when a browser didn't open or close.
- The test suite keeps all its state in a temporary folder, so it never shares a lock or lease with a live install.
- The guard reads the shell line instead of matching raw text. It now blocks `/usr/bin/pkill`, `\pkill`, wrappers
  (`sudo`, `env`, `nohup`, `xargs`), `sh -c` / `eval`, `ps | grep | xargs kill` and `lsof -ti :92xx | xargs kill`, and
  Chrome started with `open -a … --remote-debugging-port`. It no longer blocks a commit message, an `echo`, a search or
  a heredoc that only mentions `pkill`.
- The guard stops an agent from acting as the human: `--by human`, `LAUNCH_BY=human`, and the human's desktop scripts
  (`desk-browser.sh`, `kill-chrome.sh`, `human-chrome.sh`).
- `cua-color-proxy` no longer stops forwarding the agent's messages after one malformed tool call.
- `office-owner pdf` no longer replaces a PDF that is already there; `--force` replaces it on purpose.
- `office-owner` records that it launched an app only after the launch worked, and never takes over a Word the human
  opened later.
- `browser-owner idle-stop` refuses another agent (`--by` another agent's name) and a browser opened less than
  `idleMinutes` ago.
- A theme install no longer overwrites `lastStop`; it is recorded as `lastThemeInstall`.
- A theme install no longer leaks file descriptors, and sees at once when Chrome dies.
- The shell tools skip macOS's `python3` stub (it asks to install the developer tools) and look for Homebrew's Python
  first, like the wrappers.
- `office-owner close` reports a document left open even when the agent held more than one lease on it.
- Desktop icons escape the agent's label inside AppleScript.
- The example launcher no longer claims to be the human (`LAUNCH_BY`, default the agent), stops when browser-owner
  calls it (`BROWSER_OWNER_LAUNCH`), and allows only its own CDP origins instead of `*`.
- The shell tools find each other beside themselves, so `install.sh --bin DIR` works.
- Icon text shrinks to fit the circle.

### Known limitations
- `proc-owner` reads a process's environment with `ps -E` on macOS; that, `as-agent` and the session-end hooks are
  tested with fakes and on Linux, not yet with each real agent.
- `cua-color-proxy` is tested against a fake driver only; the left-to-right frame placement is not yet measured on a
  real Mac.

## [0.1.0] — 2026-10-14

First public release.

### Added
- `browser-owner`: one owner per agent Chrome (its CDP port + profile), with one lock per agent, human-only stop,
  ⌘Q detection, a careful `recover`, focus given back to the human, and a real Chrome theme in each agent's color.
- `office-owner` (= `agent-office`): per-document leases in Word / Excel / Acrobat / Preview, Word → PDF through the real
  Word, and an idle quit only for apps it launched itself.
- Colored CUA cursor per agent for Cua Driver computer use, with Hermes Agent adapters.
- **English and Hebrew** user interface: one message catalog (`bin/rainbow_i18n.py`), chosen by `RAINBOW_LANG`, the Mac's
  preferred language, or the locale. In English (LTR) the agent's name is drawn along the right part of the frame.
- `install.sh`: installs the tools, creates `browsers.json` from the example without ever overwriting yours, and with
  `--with-sweep` loads the launchd sweep with absolute paths.
- `RAINBOW_HOME`: one configurable root for logs, state and themes (default `~/.rainbowomma`).
- Claude Code guard (`adapters/claude-code/`): a PreToolUse hook that blocks pkill / killall / AppleScript-quit of Chrome /
  Chrome on a debug port, plus a settings example.
- Desktop open/close icons, the human's Chrome theme, and `kill-chrome.sh` that spares every agent browser.
- Tests on macOS in CI (fakes only — never a real browser or app).

[0.2.0]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.2.0
[0.1.0]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.1.0

# Changelog

All notable changes to RainbowOMMA. Versions follow [Semantic Versioning](https://semver.org/); JSON status words and
exit codes are an API and change only in a major version.
A release that asks something of you (a job to reinstall, a setting to add) lists it under `### Action needed`; an
upgrade prints those in full.

## [Unreleased]

### Added
- Every refusal and failure says what to do next: a `next` field beside `why` — a command to run, or "ask the human"
  (`port-owner list alpha` after a refused lease, `browser-owner recover alpha --by alpha` for a hung browser,
  `rainbowomma-doctor status` after a failure). An exception caught by a "one JSON answer, always" handler reads as an
  unexpected error in that tool, with a way to report it. Status words, the other keys and exit codes are unchanged. (#59)
- An upgrade ends with what changed: `install.sh` compares the release in place (`installed-version`) with the one it
  installs and prints every release in between, short (headings and the first line of each entry), then, in full,
  anything listed under `### Action needed` (a job to reinstall, a setting to add). `rainbowomma-doctor` shows the
  installed version and where it came from. (#60)
- Hermes works in the agent's own browser: `adapters/hermes/browser-cdp.yaml` (`browser.cdp_url` = the agent's port;
  `install.sh --adapter hermes` writes one per agent). Without it Hermes opened a throwaway browser and its credential
  vault filled passwords there. With `"hermesConfig"` in an agent's row, `rainbowomma-doctor` checks that `cdp_url` is on
  the agent's own port (not missing, not another agent's) and that no browser MCP under `mcp_servers` runs without
  `--cdp-endpoint` / `--browserUrl`, and prints the fix. (#78, #79)
- `rainbowomma-doctor status` lists every Chrome that is neither the human's nor an agent's (a browser MCP started
  without `--cdp-endpoint`, a test run): who started it, through which MCP, and the `browser-owner mcp-config` line to use
  instead. (#79)
- A tidy agent browser: per agent `restoreTabs` — `lastJob` (default: the last session, less the tabs a finished job
  left), `all` or `none` (no `--restore-last-session`) — and `maxTabs` (default 8). On `start` and before every idle-stop
  a tidy pass closes exact-duplicate URLs, blank and new-tab pages and the least recently used tabs past `maxTabs` —
  never an attached tab, the most recently used one or the last one; it follows `tabSweep.mode` (a dry run only reports).
  Idle-stop closes the job's own tabs first, without asking. (#76)

### Changed
- `--help` (and `-h`) has one shape for every tool in `bin/`: what it is for, the commands with an example each, the exit
  codes, where to read more — in English and Hebrew, from the catalog (`bin/rainbow_help.py`). A command's own options
  stay with argparse (`port-owner lease --help`). A test runs `--help` on every tool. (#58)
- The installer prints numbered steps, each with one result word (`[3/5] state in ~/.rainbowomma — done`; `kept`
  for your registry; `would` in a dry run), and counts the files instead of a line per file (new · updated · replaced,
  yours saved first · unchanged). `--dry-run` ends with a summary of the files, jobs, settings and adapters it would
  touch; a failure names the step it stopped at. (#61)

### Fixed
- `--help` never acts: `kill-chrome.sh --help` went on to look for Chrome processes to quit, `human-chrome.sh --help`
  opened Chrome, `rainbow-panel.sh --help` opened the panel, and the guard and the session-end hook read stdin. A test runs
  every tool's `--help` against stand-ins for `open`, `osascript`, `pkill`, `pgrep`, `ps` and checks none was called.

## [0.3.1] — 2026-11-07

One window for every browser (`rainbow-panel`), issues filed only after a privacy scan (`rainbowomma-report`), a
bring-to-front that needs no Automation grant, the release in place recorded on every install, `rainbowomma-doctor
status` for the running system on one screen, and the tests passing where macOS no longer shows other processes'
environments.

### Added
- `rainbowomma-doctor status [--json]`: the running system on one screen — each agent's browser, CDP mode, idle time and
  missing colors, presence, port leases, Office (who launched it, leftover temp copies), the last errors — and every
  problem with the command that fixes it; exit 1 when something needs attention, for scripts. (#57)
- `rainbow-panel` (`bin/rainbow-panel.sh`): one native window with every browser on the Mac — open, close, bring to
  front, an agent's color and name, and adding an agent to `browsers.json` through browser-owner's own validation. A
  local server on 127.0.0.1 with a key per launch and a Host check; English and Hebrew from the catalog.
- `rainbowomma-report bug|feature --title … --body-file …`: files an issue with `gh`, after a privacy scan of the title
  and body (e-mail addresses, home paths, private and Tailscale addresses, keys, phone numbers, this Mac's user, host and
  agent names, and your own `$RAINBOW_HOME/report-deny.txt`) and a check against the issue template. A finding stops it;
  `rainbowomma-report scan FILE…` only scans. See `docs/REPORTING.md`.

### Changed
- `browser-owner front` (and the focus give-back) brings a window forward through AppKit's `NSRunningApplication` first:
  no Apple Event, so no Automation grant — it works from a Dock icon, a panel or a launchd job that was never allowed to drive
  System Events (-1743). System Events stays as the fallback.
- `install.sh` records the release it put in place in `$RAINBOW_HOME/installed-version` (`VERSION`, and whether it came
  from Homebrew, a git checkout — `git describe` — or an archive), so a check can tell an install that lags the latest
  release. A release refuses to go out when `VERSION` doesn't match its tag.

### Fixed
- tests: the guard's `kill <pid>` check passes where the OS no longer shows another process's environment (macOS 27's
  `ps -E`): there it checks that every kill is refused (fail closed); root tracking covers ownership. The framework test's
  stopped `sleep` no longer prints "Terminated: 15" into the output.
- Examples and tests carry no real-looking dates, government domains or card words: `*.agency.example` in the
  `sensitiveSites` example, days built at run time in the tab-summary test, the MCP version compared to the one asked for.
  (A privacy scanner run over the repository found nine false positives there.)

## [0.3.0] — 2026-11-07

Word recovers from a blocking dialog and never stays open over a failed conversion; agents' sign-ins open in their
own browser, never the human's; idle browsers stop by themselves; a job's tabs close when it ends (after asking);
the working agent comes forward when nobody is at the Mac; an agent's Chrome can run with no open DevTools port;
one agent at a time signs in to a site; an agent can have a macOS user of its own; quiet, rotated logs; Homebrew; and
a move from a pre-release install that keeps a stopped browser stopped.

Pull requests since 0.2.0: #26 (process start time), #27 (Homebrew), #28 (GPU in tabs), #29 (`--agent-chrome`),
#30 (install manifest), #31 (auth-owner), #32 (file tools in every adapter), #33 (isolate-agent), #34 (cdp-broker),
#48 (Word recovery, #36–#38), #49 (`--migrate-from`, #41), #50 (auto idle-stop, missing colors, #44–#45),
#51 (logs, #46), #52 (sign-ins in the agent's browser, #42), #53 (a job's tabs, #43), #54 (presence, #35).

### Added
- `install.sh --agent-chrome beta|dev|canary|cft`: a new `browsers.json` gives every agent a Chrome of its own (the
  human's ⌘Q, ⌘-Tab and updates never reach it); the installer says when that Chrome isn't installed yet.
- Homebrew: the repository is its own tap (`brew tap aviv27-dev/rainbowomma https://github.com/aviv27-dev/RainbowOMMA`,
  `brew install rainbowomma`); `rainbowomma-install` and `rainbowomma-uninstall` run the same installer into your folder.
- `browser-owner tabs` measures each agent browser's GPU process too (`SystemInfo.getProcessInfo`, `gpu` in its answer):
  it can't be pinned to one tab, so it is reported, with one notification when it stays above `gpuPercent` (15%) for
  `hotMinutes`.
- `auth-owner` (optional — `"authSites"` in `browsers.json` turns it on): one agent at a time signs in to a listed site
  (`lease`, `release`, `who`, `list`; the guard keeps the others' browser tools off it), and `code` asks the human for the
  one-time code and hands it to that agent only. MCP tools `take_login`, `ask_login_code`, `release_login`.
- The guardrail reaches the file tools of Codex (`apply_patch`, read from the patch itself), Gemini CLI, Qwen Code,
  Factory Droid, Hermes (also its V4A patches), Cursor (`preToolUse`, `beforeReadFile`) and Windsurf (`pre_read_code`,
  `pre_write_code`), not only their shells; `docs/AGENTS.md` lists what each adapter matches.
- `install/isolate-agent.sh`: an agent of its own macOS user — `create` (a hidden standard user, a sudoers rule for you
  only, a shared work folder, RainbowOMMA in its home), `run AGENT -- COMMAND`, `status`, `remove`; a dry run unless
  `--apply`.
- `"cdp": "pipe"` per agent and `cdp-broker`: the agent's Chrome runs with `--remote-debugging-pipe`, no open DevTools
  port. RainbowOMMA reaches it through a socket only you can open; its MCP server through the port, but only at a
  WebSocket path with the agent's token (`mcp-config` emits it). Several clients share the pipe; the guard refuses
  another agent's token.
- `install.sh --migrate-from DIR` (`install/migrate.py`): a pre-release install's state is copied into `$RAINBOW_HOME` —
  never moved or overwritten; a legacy stop flag named after the person becomes `offByHuman`, and set or unreadable
  means stopped; locks, broker keys and Word's temp copies stay behind; rows of `browsers.json` still pointing into the
  old folder are named. `--dry-run` only reports. Until then browser-owner reads a legacy flag as stopped. (#41)
- Built-in idle-stop: an agent with `idleMinutes` whose browser has no client attached and no tab change for that long,
  and holds no auth-owner lease, is stopped by the heal job (`--by auto-idle`, with a receipt) — no private reaper
  needed. Anything that can't be read counts as busy. (#44)
- Sign-ins stay out of the human's browser: the guard refuses an agent's `open <url>` and `open -a <a browser>`
  (`"guardOpen": "report"` only records); `browser-owner open AGENT URL` opens it as a new tab in the agent's own
  browser (http(s) only, started first if down, an `authSites` site taken for the agent); `rainbowomma-browser` is a
  `BROWSER=` launcher for frameworks' `webbrowser.open`, which never falls back to the human's browser; MCP tool
  `open_in_my_browser`. (#42)
- A job's tabs: `browser-owner job-start` / `job-end` / `job-keep` / `job-close` (MCP `job_start`, `job_end`, `keep_tabs`,
  `close_job_tabs`) — the tabs a job opened are put to the agent at its end, kept ones (and the tabs they opened)
  stay, the rest close through CDP, or by the scheduled tab job a minute later; never the last tab, a tab another
  client drives, or one that was there before. (#43)
- `browser-owner presence` and `bin/rainbow_presence.py`: one "is the human at the Mac?" answer (recent input, a locked
  screen; unknown counts as present) shared by the guard, screen-owner, the cursor proxy and browser-owner. When nobody
  is, an agent's start or `open` brings its window to the front with that tab; when someone is, it stays in the
  background. (#35)

### Changed
- `install.sh` keeps a manifest (`$RAINBOW_HOME/installed.txt`) of what it put in place, and saves a file of yours it
  would replace (`$RAINBOW_HOME/backup/`). `uninstall.sh` removes only what it installed and you did not change since,
  then puts your files back; an older install without a manifest loses only files identical to RainbowOMMA's.
- Logs: the heal and sweep jobs print only what changed (stamped with `"at"`, a heartbeat once a day); logs in
  `$RAINBOW_HOME/logs` rotate weekly, kept 4 weeks (`receipts.jsonl` stays whole); `rainbowomma-doctor logs` merges every
  log into one timeline. Reinstall (or add `--scheduled` to the jobs) to get the quiet job output. (#46)

### Fixed
- proc-owner: a recorded process mark holds only while the process is the same one — its command line and, now, its
  start time (a pid the system handed out again, to the same kind of command, is never the agent's). On macOS,
  `RAINBOW_AGENT=…` counts only in a process's environment, never as words in its own command line.
- office-owner: a damaged .docx/.rtf/.doc is refused before Word opens it (exit 2); a dialog open in Word answers
  `blocked-by-dialog` at once instead of a run of -1708s; a stuck Word that office-owner launched is quit once
  (saving ask, at most every 10 minutes) and the conversion retried once. (#36)
- office-owner: temp copies a failed conversion leaves in Word or Excel are recorded and closed — in `finally`, and by the
  sweep before it decides whether the app may quit — so a failure no longer keeps Word open for days. (#37)
- office-owner: a failure never has an empty reason — an osascript timeout says so — and the AppleScript error number
  is returned as `errno`. (#38)
- heal: colors missing on an open browser are reported again after ~4 h with how long (at most once a day) and marked
  `themePending`; an idle stop in the same run puts them back. (#45)

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

[0.3.1]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.3.1
[0.3.0]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.3.0
[0.2.0]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.2.0
[0.1.0]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.1.0

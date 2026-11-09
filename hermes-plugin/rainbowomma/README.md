# RainbowOMMA for Hermes

**One Mac, one human, many agents — and none of them in each other's way.**

Run two or three Hermes profiles on the Mac you work on and they start to collide: one agent's `pkill Chrome` closes
your browser and the other agent's, a "free port 3000" kills your dev server, a Word document you had open gets closed
without saving, two agents type into the same window. A prompt can ask an agent to be careful. This plugin makes the
collisions impossible to cause by accident:

- **Its own browser.** Each profile gets a Chrome of its own — separate profile folder, its own debugging port, and a
  coloured window frame with the agent's name on it, so you always see whose window this is. Your Chrome is never used.
- **A guard on every tool call.** Commands that would hit you or another agent are refused before they run, with the
  safe way to do it: killing by pattern (`pkill`, `killall`, `kill $(pgrep …)`), quitting Chrome or Word through
  AppleScript, a port that isn't the agent's, your clipboard, your Chrome profile, typing while you are typing.
  Sending through Messages or Mail goes to Hermes's own approval prompt.
- **Leases instead of races.** Ports, the screen, sign-ins to a site, documents in Word / Excel / Acrobat / Preview:
  an agent takes a lease, and closes only what it leased. A document you already had open stays yours.
- **Cleanup after itself.** When a session ends, and while the agent is idle: the tabs its job opened close, hot tabs
  are reloaded, expired document leases are closed (only if saved), an Office app is quit only if an agent launched it
  and it sat empty for ten minutes, orphaned dev servers stop, unused ports go back, an idle browser is stopped.
- **`/rainbow`** — who holds what, in any Hermes surface. **`/rainbow pause`** stops every agent on the Mac at once;
  **`/rainbow resume`** lets them go on.

macOS only. Needs Google Chrome for the browser tools; Word / Excel / Acrobat only for the document tools.

## Install

```
hermes plugins install rainbowomma
```

Nothing to configure: the agent's name is the Hermes profile's name, and the first time it runs it gets a free colour
and a free port in the shared registry (`~/.rainbowomma/browsers.json`). Install it in every profile that works on the
same Mac — they find each other through that folder.

To make Hermes's **own browser tools** (navigate, click, snapshot, the CDP tools, the credential vault) drive the
agent's coloured Chrome instead of a throwaway Chromium, select the provider the plugin registers:

```
hermes config set browser.cloud_provider rainbowomma
```

Then, in a session: `/rainbow`, or ask the agent to "open example.com in your browser".

## What the agent gets (30 tools, toolset `rainbowomma`)

| | |
|---|---|
| Browser | `rainbow_start_browser` · `rainbow_browser_status` · `rainbow_recover_browser` · `rainbow_open_url` · `rainbow_job_start` · `rainbow_job_end` · `rainbow_keep_tabs` · `rainbow_close_job_tabs` · `rainbow_tidy_tabs` |
| Ports | `rainbow_lease_port` · `rainbow_release_port` · `rainbow_who_port` |
| Processes | `rainbow_whose_process` · `rainbow_stop_process` · `rainbow_my_processes` |
| Screen | `rainbow_take_screen` · `rainbow_release_screen` |
| Sign-ins | `rainbow_take_login` · `rainbow_release_login` |
| Documents | `rainbow_open_document` · `rainbow_close_document` · `rainbow_renew_document` · `rainbow_convert_to_pdf` · `rainbow_recalc_workbook` · `rainbow_documents` |
| Clipboard | `rainbow_clip_copy` · `rainbow_clip_paste` |
| iOS Simulator | `rainbow_sim_lease` · `rainbow_sim_release` |
| Overview | `rainbow_status` |

Every tool answers with one JSON object. `refused` is final: the agent is told to ask you.

## Settings (`plugins.entries.rainbowomma.settings`)

| key | default | |
|---|---|---|
| `agent_name` | the profile's name | this agent's name on the Mac |
| `color` | next free | frame colour, `#RRGGBB` (used when the agent is first registered) |
| `idle_minutes` | `30` | stop the agent's browser after this long with nobody driving it (`0`: never) |
| `tab_cleanup` | `apply` | `apply`, `dry-run` (report only) or `off` |
| `housekeeping_minutes` | `5` | how often the idle cleanup runs (`0`: only at session end) |
| `guard` | `true` | `false`: nothing is refused; the tools stay |
| `mark_commands` | `auto` | see "What it does on your machine" |
| `extra_apps` | `{}` | more document apps: `{textedit: {app: TextEdit, extensions: [.txt]}}` |
| `language` | `en` | `en`, `he` or `auto` — the owners' answers and the text on the frame |
| `word_folder` | | where Word converts temp copies (default: `word-convert` in the state folder) |
| `home` | `~/.rainbowomma` | shared state folder — the same one in every profile |
| `registry` | | path of the shared `browsers.json` (default: inside the state folder) |

The registry is yours to edit: colours, labels, ports, `humanPorts`, `deniedApps`, `sensitiveSites`, `authSites`.
The plugin adds a row for a new agent and never changes an existing one.

## What it does on your machine

Everything below is local. The plugin's only request is to `127.0.0.1` (the agent's own Chrome, to read its DevTools
address for Hermes's browser tools). It has no updater, reads no credential files and never approves
anything on your behalf.

- **Starts programs.** Google Chrome for the agent (its own `--user-data-dir` under `~/.rainbowomma/profiles/<agent>`,
  a DevTools port on `127.0.0.1` from the registry, and the frame theme, loaded as an unpacked theme extension through
  Chrome's own debugging pipe). `osascript` to talk to Word, Excel, Acrobat, Preview and System Events. `ps`, `pgrep`,
  `lsof`, `ioreg`, `sysctl`, `defaults read`, `open -g`, and `xcrun simctl` for the simulator tools.
- **Stops programs.** Only what is this agent's: a process the agent started (`rainbow_stop_process`, the orphan reap
  at session end), its own Chrome when it is idle, and an Office/PDF app that an agent launched and left empty. Never a
  process that is not provably the agent's; never an app that was already running.
- **Keeps a helper process.** One `guard_worker.py` per profile while Hermes runs (the guard), and a timer thread
  inside Hermes for the idle cleanup. Both stop when the plugin unloads.
- **Writes files** under `~/.rainbowomma/` only: the registry, leases and state, a receipts log of what was done and
  refused (`logs/receipts.jsonl`), the theme folders, the agent's Chrome profile, the agent's clipboard slots, temp
  copies for Word conversions.
- **Changes shell commands in one case.** When one Hermes process serves several profiles (a multiplexed gateway), a
  process started by a shell command can't be told apart by its ancestry, so the plugin prefixes the command with
  `export RAINBOW_AGENT=<agent> RAINBOW_HOME=… BROWSER_OWNER_REGISTRY=…;` (a `modify` directive). `mark_commands: never`
  turns it off, `always` does it in every process.
- **Asks you.** A Messages/Mail send becomes a Hermes approval prompt (`approve` directive). Under cron or a gateway
  with nobody to answer, Hermes's own approval timeout applies; the plugin never waits on a dialog of its own.
- **macOS prompts you may see once.** Automation permission the first time an app is driven; Word's "Grant access"
  for the folder it converts in. Until you answer, the tool reports `blocked-by-dialog` and stops.
- The vendored receipts module can export the log to an OpenTelemetry collector (`receipts --export-otlp URL`). The
  plugin never calls it.

What the guard is not: a sandbox. It reads the command text and closes the cheap ways to hurt a neighbour. A program
running as your user can still do anything your user can.

## How it is built

`vendor/` holds RainbowOMMA's owners — the same files as `bin/` in this repository, copied by
`hermes-plugin/tools/sync_vendor.py` (a test fails if they differ). Each tool is one call of one owner, run as this
profile's agent. The guard is the guard every other RainbowOMMA adapter uses, kept in a helper process because one
Hermes process may serve several profiles and the guard tells whose call it is from its environment.

Tests: `python3 hermes-plugin/tests/test_plugin.py` (no Hermes, Chrome or Office needed).

Apache-2.0. Part of [RainbowOMMA](https://github.com/aviv27-dev/RainbowOMMA), which does the same for Claude Code,
Codex, Cursor, Gemini CLI and a dozen other agent frameworks.

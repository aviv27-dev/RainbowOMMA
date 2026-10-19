# RainbowOMMA — design

## 1. Principles
1. **One owner per resource; everyone else asks it.** Owners: `browser-owner` (agent browsers), `office-owner` (= `agent-office`)
   (documents agents open), the human (their own Chrome).
2. **The human first.** Only the human closes an agent's browser for good (`stop --by human`); a person's ⌘Q is
   respected; a new window never stays in front of the human; an app the human launched is never quit (office-owner
   quits only apps it launched itself, after 10 idle minutes with no documents open).
3. **Unknown = do nothing.** A port that answers but is not the agent's browser is `blocked`, not "up". A profile in use
   is `profile-busy`. An app that cannot answer means "keep the lease". A process table that changed during the probes
   means "do not kill".
4. **One JSON answer, always** (exit 0 ok · 2 refused · 1 failure) — agents parse it; humans read the why in English or Hebrew (§7).

## 2. Components (repo layout)
| Path | What |
|---|---|
| `bin/browser-owner(.py)` | the owner. `list · names · status · start · stop [--allow-reopen] · idle-stop · recover · front · human-theme`, `--by WHO` |
| `browsers.json` (beside the tools; `install.sh` creates it from `examples/browsers.example.json`) | the registry: one row per agent — `port` (9222–9299, unique), `profile` (unique real path, no spaces, never a personal Chrome dir), `color`, `label`; optional `launcher`, `managedBy`, `idleMinutes`, `noTheme`, `ports` (`"41000-41099"`); top-level `humanPorts` |
| `bin/port-owner(.py)` | every agent's ports: a range per agent (`ports` in the registry, default 41000 + 100 × (CDP port − 9222)), leases inside it, `humanPorts` never leased: `lease · env · who · release · list` — §8 |
| `bin/proc-owner(.py)` | whose a process is (`RAINBOW_AGENT` in its environment, an ancestor that carries it, or the agent's Chrome tree; else the human's): `whose · kill --by · list · reap` — §9 |
| `bin/as-agent`, `bin/rainbowomma-session-end` | run any agent as a named agent (`RAINBOW_AGENT` + `RAINBOW_SESSION`, reap on exit) · the session-end hook adapters run — §9 |
| `bin/rainbowomma-mcp(.py)` | the owners as MCP tools for any MCP agent (stdio, standard library only) — §10 |
| `bin/theme-frame.js` | draws the agent's name onto the theme's frame image (AppKit via JXA — no image library) |
| `bin/office-owner` = `bin/agent-office(.py)` | document leases in Word/Excel/Acrobat/Preview, real-Word → PDF, quitting only the apps it launched: `open · close · renew · pdf · sweep · list · apps` |
| `bin/kill-chrome.sh` | the human's broom: closes their Chrome + headless leftovers, spares every agent browser; `--all` goes through the owner |
| `bin/desk-browser.sh`, `install/make-desktop-apps.sh` | colored desktop icons: open/close each agent, the human's Chrome, all agents (`ONLY=<agent>`: one agent's) |
| `install/make-dock-tray.sh`, `install/dock_tray.py`, `install/icon-lib.sh` | the agents' browsers as one group in the Dock after Chrome (`--remove`) · the Dock placement · the shared icon drawing |
| `examples/agent-shortcut` | `<agent>-browser <cmd>` = `browser-owner <cmd> <agent>` (kept for callers that know the old name) |
| `examples/agent-launcher.sh` | an agent with its own launcher; the owner calls it back with `<LAUNCHER_ENV>=1` |
| `bin/rainbowomma-guard(.py)` | the one pre-tool hook every guardrail adapter runs; reads each framework's hook payload — §5 |
| `adapters/<framework>/` | one folder per agent framework: hook wiring, native deny rules, plugins — see `docs/AGENTS.md` |
| `bin/cua-color-proxy(.py)` | MCP stdio proxy in front of `cua-driver mcp`: every session of an MCP agent wears that agent's cursor theme — §6 |
| `bin/rainbow_i18n.py` | the message catalog (English + Hebrew) and the language choice — §7 |
| `install.sh` | copies the tools, creates `browsers.json` from the example (never overwrites), the state folders, and with `--with-sweep` the launchd job with absolute paths |
| `bin/human-chrome.sh` | opens (or brings to front) the human's own Chrome, never an agent's |
| `bin/desk-browser.sh` | what the desktop icons run: `open\|close <agent>`, `open\|close human`, `close agents` |
| `tools/cursor-themes/build_cursor_themes.py`, `cua.default.lottie` | one Cua cursor theme per agent in its color — §6 |
| `adapters/hermes/cua-cursor-theme.patch`, `adapters/hermes/cursor-config.yaml` | Hermes Agent: select the agent's cursor theme per session — §6 |
| `install/com.rainbowomma.heal.plist` | the launchd heal template (every 30 min, at login); `install.sh --with-heal` writes it with absolute paths |
| `install/com.rainbowomma.agent-office-sweep.plist` | the launchd sweep template; `install.sh --with-sweep` writes it with absolute paths |
| `.github/workflows/tests.yml`, `release.yml` | tests on macOS for every push and PR · a release from a `v*` tag or by hand from the Actions tab |
| `tests/test_rainbowomma.py` | fake process table, fake osascript, fake Chrome — never touches a real browser |

## 3. browser-owner — behavior that was measured, not guessed
- **Identity.** An agent's browser = a root Chrome process with BOTH `--remote-debugging-port=<its port>` and
  `--user-data-dir=<its profile>` as whole argument values (`=92220` or `…-personal` are not it). Kills reach only that
  root and its descendants, re-validated right before the signal.
- **Status words.** `up` (its own root answers) · `blocked` (the port answers, not from its root — the listener is named
  via lsof) · `profile-busy` (its profile is open in a Chrome without its port) · `hung` · `down`.
- **"The human closed it."** `stop --by human` remembers `offByHuman`; agent/keepalive starts are `refused` until the
  human opens it. `--allow-reopen` closes without that memory. A stale flag (browser up again ≥2 min after the stop, its
  own root answering) is cleared — only under the lock, never by `status` (status never writes).
- **⌘Q.** Chrome writes `exit_type: Normal` for ⌘Q *and* for reboot/logout/AppleScript quit/our own SIGTERM. It counts as
  a person's quit only if the Preferences file was written after the last boot, ≤2 h ago, and not within ~3 min of an
  owner stop. Then agent starts answer `closed-by-person`.
- **Recover.** For anyone but the human: three probes over ≥30 s and one more look before any kill (a Mac deep in swap
  must not lose a logged-in session to one missed probe).
- **Focus.** `open -g` is NOT enough — Chrome activates itself when its window appears. The owner records the front app
  before the start and gives the front back once if the agent's window took it; never against a newer choice of the
  human (`user-moved`); no Automation consent → `no-permission`, recorded as such.
- **CDP origins.** New agents get `--remote-allow-origins=http://127.0.0.1:<port>,http://localhost:<port>`, not `*`.
  Python websocket-client sends that Origin; Node `ws`, urllib, Playwright and Vercel's agent-browser CLI send none.
- **Theme (the "rainbow").** Chrome's built-in profile color is always a pale tonal shade — useless at a glance. A real
  theme (an unpacked theme extension) paints the whole frame. Branded Chrome ≥137 ignores `--load-extension`, so the
  owner installs it through the DevTools **pipe**: Chrome with `--remote-debugging-pipe --enable-unsafe-extension-debugging
  --no-startup-window` (no window at all), `Extensions.loadUnpacked`, then **wait until the profile's Preferences record
  the theme id** (closing at once lost it — Chrome applies the theme asynchronously), then close that instance (recorded
  as an owner stop), then start normally. Pipe fds must be 3/4 in the child: dup the pipe ends above 4 first, use
  `close_fds=False`. A windowless Chrome does not exit when the pipe closes; a windowed one does. A failed install falls
  back to the profile color and records `themeError`. Rebuilt when `THEME_VERSION`, color or label changes.
- **Name collision.** Do NOT call any tool `agent-browser`: Hermes Agent looks up Vercel's `agent-browser` CLI on PATH.

- **Front for the human.** `front` un-minimizes first: activating an app never de-miniaturizes its windows, so through the
  agent's own CDP port (a standard-library WebSocket client, no package) every minimized window of its browser goes back
  to `normal`, and the tab already shown is activated, never another tab. No Automation grant is needed. Then the
  browser's root process is brought to the front. Local CDP calls never go through an `http_proxy`.
- **A theme Chrome Sync replaced.** Signing in to Google inside an agent profile lets Chrome Sync swap the agent's theme
  for the account's (`extensions.theme.id` emptied). The theme counts as installed only while the profile carries it, so
  the next start puts it back. `heal` (the `com.rainbowomma.heal` launchd job: every 30 minutes and at login) does it
  sooner for a closed browser, under its lock. An open browser is never restarted for its colors: `themeMissingSince`
  and one notification. A Chrome update (`CFBundleShortVersionString`, kept in `chrome-version.json`) gets one
  notification saying whether every agent still has its theme and, if the Dock tray was built, its applet.

## 4. agent-office
A document is identified by its full path (every spelling: `/var` vs `/private/var`). It is closed only if the agent
leased it, nobody had it open before (else the lease is born `shared`), and the app says it is saved — checked in the
SAME AppleScript that closes it. Never `tell application` an app that is not running (it would launch on the human's
screen). One lock for open/renew/close/sweep; the sweep re-reads each lease before closing; leases < 2 min are not
dropped (`open -g` returns before the app lists the document); leases of documents closed by hand are dropped.

**Word → PDF (`pdf`).** Always the real Word (LibreOffice renders complex Word layouts differently). The source is copied to a
uniquely named file (`ofc-pdf-<hex>`) inside ONE fixed work folder — Word's sandbox asks permission per folder, so a fixed
folder means one grant ever. Only documents with that name (or its PDF) are closed; `active document` is never used, so a
human typing in another Word window is never touched. Conversions run in parallel; a dialog or a hang ends in a timeout
(100 s), the copy is closed by name and the call fails clearly. Use LibreOffice only for spreadsheets and slides.

**Quitting apps (`sweep` → idle quit).** Every use records who launched the app: if it was already running when
office-owner first touched it, it is the human's and is never quit. An app office-owner launched is quit when it has been
idle ≥ 10 minutes, no lease or conversion is in flight on it, the SAME process is still running (a relaunch by someone else
makes it the human's), and — checked inside the quit AppleScript itself — it has no documents open. One window per agent
working in parallel is fine; the app is shared, the documents are not.

## 5. Agent adapters (the guardrails)
- **One guard, many frameworks.** `bin/rainbowomma-guard.py` splits the shell line into simple commands (through pipes,
  `;`/`&&`, `$( )`, backticks, `sh -c`, `eval`, and wrappers like `sudo`/`env`/`xargs`; heredoc bodies are data) and
  judges each command by its name (`/usr/bin/pkill` is `pkill`): `pkill`, `killall`, `kill` with a process search
  (`pgrep`, or `ps`/`lsof` on Chrome or a 92xx port), AppleScript quitting Chrome, Chrome on a debug port (its binary
  or `open -a`), and an agent acting as the human (`--by human`, `LAUNCH_BY=human`, the desktop scripts). It finds the command in each
  framework's payload (`tool_input.command`, Cursor's `command`, Windsurf's `tool_info.command_line`, Copilot CLI's
  `toolArgs` JSON text, Cline's `tool_call.input` / `preToolUse.parameters`) and refuses with exit 2 and the reason
  on stderr, or Cline's `{"cancel": true}` with `--format cline`. A payload it can't read is let through.
- **Native rules as a second layer** where a framework has them: Claude Code and Qwen `permissions.deny`, Codex exec
  policy `forbidden`, Gemini policy TOML, OpenCode / Kilo `permission.bash`, Factory `commandBlocklist`, Zed
  `always_deny`. Plugins where a framework only takes code: OpenCode / Kilo (`tool.execute.before`), OpenClaw
  (`before_tool_call`, draft).
- **Per-framework caveats** (Codex loads new hooks untrusted, Hermes needs hook consent, Copilot fails open on a hook
  timeout, Cline's refusal cancels the task, Warp's denylist only asks) are in `docs/AGENTS.md`.
Pattern rules only see the direct command — the owner-side checks stay the real protection.

## 6. The agent's CUA cursor (computer use)
Cua Driver draws an agent cursor overlay per session and supports installed cursor **themes** (dotLottie,
`cua.cursor-theme/2`: 12 action animations, 128×128 at 30 fps, vector shapes only). Its built-in default is tinted per session
name; an installed custom theme keeps its own colors.

- `tools/cursor-themes/build_cursor_themes.py` copies Cua's default source and swaps its single base color for each agent's
  color from `browsers.json`, giving `com.rainbowomma.cursor.<agent>`; `--install` runs `cua-driver cursor-theme
  validate / build / install`, so the driver itself checks every theme.
- Hermes Agent: apply `adapters/hermes/cua-cursor-theme.patch` (selects the profile's theme right after `start_session`) and
  add `adapters/hermes/cursor-config.yaml` to the profile. Reduced motion keeps the overlay from redrawing at rest.
- A theme is selected per session, because the driver has no global default. **`bin/cua-color-proxy`** handles this for
  every MCP client. It runs `cua-driver mcp` as a child and relays MCP stdio both ways unchanged. Before the first action on
  a session, it sends its own `start_session` (with `cursor_theme`) and `set_agent_cursor_theme`, and swallows their
  answers, so the agent never sees them and its request ids are untouched. Rules from the 0.21 session contract:
  - A call without `session` uses the transport's implicit session. The driver drops that session after 5 idle minutes or
    an `end_session`, so the proxy themes it again after 240 s without actions, or after the agent ends it.
  - A labelled session is themed once. A label the agent ended is never touched again, because `start_session` would
    revive it, and ordinary actions do not.
  - A failure, such as a theme that is not installed or no answer within 10 s, is logged to
    `$RAINBOW_HOME/logs/cua-color-proxy.log`, and the agent's call goes through as it came.
  - Tests drive it with a fake `cua-driver mcp`. *Not yet run against the real driver.*

```bash
python3 tools/cursor-themes/build_cursor_themes.py --registry ~/bin/browsers.json --install
cua-driver cursor-theme list            # com.rainbowomma.cursor.<agent> …
```

## 7. Language and the configurable root
- **One message catalog:** `bin/rainbow_i18n.py` holds every text a person sees, in `en` and `he`: `why`, notifications,
  desktop icon names, the profile and theme names, and the frame text. The Python tools import it, and the shell scripts
  call it (`rainbow_i18n.py KEY name=value`). The language is `RAINBOW_LANG`, else the Mac's first preferred language
  (`defaults read -g AppleLanguages`, checked before `LANG`, which the launchd job sets to `en_US`), else the locale, else
  English. Status words, exit codes and JSON keys are never translated.
- **Adding a language:** add its text to every entry in `M`, its code to `LANGS`, and to `RTL` if it reads right to
  left. A test checks that every message has every language.
- **Direction on the frame:** Chrome lays the frame image from the window's left edge. In RTL the tab strip grows from the
  right, so the name is drawn twice on the free left part. In LTR the tabs grow from the left, so the name repeats along
  the rest of the 3000 px image, and the right part of any window width carries it. The RTL theme key is unchanged, so
  existing Hebrew installs are not rebuilt. LTR has its own key, so switching language rebuilds the theme once. *The LTR
  placement is not yet measured on a real Mac.*
- **One root:** `RAINBOW_HOME` (default `~/.rainbowomma`) holds logs, state, themes and the Word work folder.

## 8. port-owner — ports have owners too
- **Ranges, not a free-for-all.** Each agent owns a contiguous range (default 100 ports from 41000 + 100 × (CDP port − 9222),
  all below macOS's ephemeral 49152+; overlapping ranges are refused by the registry). The human owns everything else;
  `humanPorts` (default 3000, 3001, 4200, 5000, 5173, 5432, 6379, 8000, 8080, 8888, 9000, 27017) is never leased.
- **A lease is a promise, checked twice.** `lease` picks the first port in the range that is not kept for the human, not
  leased, not listened on (`lsof`) and binds on every interface. A lease nobody listens on is dropped after 10 minutes,
  so a crashed agent's ports come back. One lock file serializes every change.
- **The guard.** `kill-port`, `fkill`, `fuser -k` and `kill` with `ps`/`lsof`/`pgrep` are refused for every agent. With
  `RAINBOW_AGENT=<name>` in the agent's environment, `--port N`, `--port=N`, `VAR_PORT=N`, `docker -p HOST:…` and
  `python -m http.server N` must name a port in that agent's range (or leased to it); without it, only ports another
  agent owns or holds are refused. A port that appears only in text (a commit message, an `echo`) is not a claim.

## 9. proc-owner — every process has an owner
- **Who.** `RAINBOW_AGENT=<name>` in a process's environment (Linux: `/proc/<pid>/environ`; macOS: `ps -E`, same user
  only) makes it that agent's, and so does an ancestor that carries it (a child whose environment was cleared) or being
  in the agent's Chrome tree (browser-owner's). Everything else is the human's. Set the name where the agent starts:
  `as-agent alpha claude`, or the framework's own env setting (Claude Code `"env"`).
- **Stop only your own.** `kill PID --by AGENT` sends TERM (`--force`: KILL after 5 s) only when the process is that
  agent's; `--by human` may stop any; pid 1 and the caller itself never. The guard applies the same rule to a plain
  `kill <pid>`: with `RAINBOW_AGENT` set, only the agent's own; without it, never another agent's. `kill $VAR` and
  `kill %1` can't be resolved from the text and are let through.
- **After a session.** `reap AGENT` stops the agent's servers that outlived their session: processes of that agent,
  re-parented to launchd (ppid 1) and listening on a port. Never its Chrome, never the caller or its ancestors (the
  agent running the hook), and with `--session ID` only that session's (`RAINBOW_SESSION`, set by `as-agent`). Then
  the agent's leases nobody listens on go back. `as-agent` reaps on exit; frameworks with a session-end hook run
  `rainbowomma-session-end`, which does nothing without `RAINBOW_AGENT`.

## 10. rainbowomma-mcp — the owners as MCP tools
- One stdio MCP server per agent (`--agent NAME` or `RAINBOW_AGENT`), standard library only, newline-delimited JSON-RPC:
  `initialize` (answers the client's protocol version), `tools/list`, `tools/call`, `ping`.
- Each tool runs the same command-line owner as the agent (`RAINBOW_AGENT` set) and returns its one JSON answer as
  `structuredContent` and text; a non-zero exit (refused or failed) is `isError`. Acting tools need the agent name;
  `who_port` and `whose_process` work without it.

## 11. Receipts and the human at the keyboard
- **Receipts.** `bin/rainbow_receipts.py` appends one JSON line per acting command (start, stop, idle-stop, recover, front,
  heal changes; lease and release; kill and reap; open, close, pdf and what the sweep closed or quit) and per guard
  refusal to `$RAINBOW_HOME/logs/receipts.jsonl`, under a lock. Read-only commands leave none; a receipt that can't be
  written never stops the tool. `bin/receipts` reads them back by agent, tool and time.
- **Wait for the human.** macOS's `HIDIdleTime` (`ioreg -c IOHIDSystem`) says how long ago the keyboard or mouse was
  used. Under `RAINBOW_HUMAN_IDLE_S` (5 s), the guard refuses GUI-driving commands (`osascript` to System Events with
  keystroke/click, `cliclick`) and MCP computer-use actions (any tool named `…cua…`/`…computer…` except screenshots,
  `get_*`, `list_*` and session calls), and the cursor proxy holds the action until the human pauses, at most
  `RAINBOW_HUMAN_WAIT_S` (30 s). Unknown idle time (not macOS, no `ioreg`) never blocks.
- **`rm -r` of home.** The guard refuses a recursive `rm` of `/`, `~`, `$HOME`, `/Users/<name>` or a system folder.


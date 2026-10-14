# RainbowOMMA — design

## 1. Principles
1. **One owner per resource; everyone else asks it.** Owners: `browser-owner` (agent browsers), `agent-office`
   (documents agents open), the human (their own Chrome).
2. **The human first.** Only the human closes an agent's browser for good (`stop --by human`); a person's ⌘Q is
   respected; a new window never stays in front of the human; shared GUI apps are never quit.
3. **Unknown = do nothing.** A port that answers but is not the agent's browser is `blocked`, not "up". A profile in use
   is `profile-busy`. An app that cannot answer means "keep the lease". A process table that changed during the probes
   means "do not kill".
4. **One JSON answer, always** (exit 0 ok · 2 refused · 1 failure) — agents parse it; humans read the Hebrew/English why.

## 2. Components (repo layout)
| Path | What |
|---|---|
| `bin/browser-owner(.py)` | the owner. `list · names · status · start · stop [--allow-reopen] · idle-stop · recover · human-theme`, `--by WHO` |
| `bin/browsers.json` | the registry: one row per agent — `port` (9222–9299, unique), `profile` (unique real path, no spaces, never a personal Chrome dir), `color`, `label`; optional `launcher`, `managedBy`, `idleMinutes`, `noTheme` |
| `bin/theme-frame.js` | draws the agent's name onto the theme's frame image (AppKit via JXA — no image library) |
| `bin/agent-office(.py)` | document leases in Word/Excel/Acrobat/Preview: `open · close · renew · sweep · list` |
| `bin/kill-chrome.sh` | the human's broom: closes their Chrome + headless leftovers, spares every agent browser; `--all` goes through the owner |
| `bin/desk-browser.sh`, `install/make-desktop-apps.sh` | colored desktop icons: open/close each agent, the human's Chrome, all agents |
| `examples/agent-shortcut` | `<agent>-browser <cmd>` = `browser-owner <cmd> <agent>` (kept for callers that know the old name) |
| `examples/agent-launcher.sh` | an agent with its own launcher; the owner calls it back with `<LAUNCHER_ENV>=1` |
| `adapters/hermes-approvals-deny.yaml` | Hermes guardrail: no pkill/killall/AppleScript-quit/Chrome-on-a-debug-port |
| `tests/test_rainbowomma.py` | fake process table, fake osascript, fake Chrome — never touches a real browser |

## 3. browser-owner — behaviour that was measured, not guessed
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

## 4. agent-office
A document is identified by its full path (every spelling: `/var` vs `/private/var`). It is closed only if the agent
leased it, nobody had it open before (else the lease is born `shared`), and the app says it is saved — checked in the
SAME AppleScript that closes it. Never `tell application` an app that is not running (it would launch on the human's
screen). One lock for open/renew/close/sweep; the sweep re-reads each lease before closing; leases < 2 min are not
dropped (`open -g` returns before the app lists the document); leases of documents closed by hand are dropped.

## 5. Agent adapters (the guardrails)
- **Hermes Agent:** `adapters/hermes-approvals-deny.yaml`.
- **Claude Code (todo):** a PreToolUse hook on Bash + `permissions.deny` with the same patterns.
- **Codex CLI (todo):** `prefix_rule(decision="forbidden", justification="use ~/bin/browser-owner")` with `match`/`not_match` self-tests.
Pattern rules only see the direct command — the owner-side checks stay the real protection.


#!/bin/bash
# An agent's own launcher, for an agent that already had one before browser-owner. Two ways it runs:
#  - browser-owner calls it to start the browser, with BROWSER_OWNER_LAUNCH=1 (or the variable named by
#    "launcherEnv" in browsers.json): then it only starts Chrome;
#  - anyone else runs it: then it asks browser-owner, and identifies itself as the agent.
#    Only a shortcut the human clicks may pass LAUNCH_BY=human (that is what lets a browser the human closed reopen).
set -u
BIN="${RAINBOW_BIN:-$HOME/bin}"
LAUNCH_BY="${LAUNCH_BY:-alpha}"

DATA_DIR="$HOME/agents/alpha-profile"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p "$DATA_DIR"

py() {   # the first python3 that works — never macOS's stub, which only asks to install the developer tools
  for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$p" ] || continue
    [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
    "$p" "$@"; return
  done
  return 127
}
msg() { py -I "$BIN/rainbow_i18n.py" "$@" 2>/dev/null || echo "$1"; }
notify() { osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' -e 'end run' \
  "$1" "$(msg al.title name=Alpha)" >/dev/null 2>&1; }

alive() { curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; }

if [ "${BROWSER_OWNER_LAUNCH:-0}" != "1" ] && [ "${ALPHA_BROWSER_OWNER:-0}" != "1" ] && [ -x "$BIN/browser-owner" ]; then
  OUT=$("$BIN/browser-owner" start alpha --by "$LAUNCH_BY" 2>&1); RC=$?
  case "$OUT" in
    *'"status": "already-up"'*) notify "$(msg al.already port=9222)" ;;
    *'"status": "started"'*) notify "$(msg al.up)" ;;
    *'no working python3'*) OWNER_DOWN=1 ;;
    *) notify "$(msg al.failed out="$OUT")" ;;
  esac
  if [ "${OWNER_DOWN:-0}" != "1" ]; then echo "$OUT"; exit $RC; fi
  notify "the owner (browser-owner) is not running — no python3; opening directly"   # no python3: no catalog either
fi

# Already running? Say so and stop. Starting a second copy on the same port would fail anyway,
# and killing the live one costs the logged-in session.
if alive; then
  notify "$(msg al.already port=9222)"
  echo "CDP already running on 9222"
  exit 0
fi

if [ ! -x "$CHROME" ]; then
  notify "$(msg al.no_chrome)"
  echo "Chrome not found at: $CHROME" >&2
  exit 1
fi

nohup "$CHROME" \
  --user-data-dir="$DATA_DIR" \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --disable-features=OptimizationGuideOnDeviceModel \
  --remote-debugging-port=9222 \
  --remote-allow-origins=http://127.0.0.1:9222,http://localhost:9222 \
  --no-first-run --no-default-browser-check \
  --restore-last-session \
  --hide-crash-restore-bubble \
  --window-name="Alpha-CDP" \
  >/dev/null 2>&1 &

for _ in $(seq 1 20); do
  alive && break
  sleep 1
done

if alive; then
  TABS=$(curl -s --max-time 3 http://127.0.0.1:9222/json 2>/dev/null \
         | grep -c '"type": "page"' || echo "?")
  notify "$(msg al.up_tabs tabs="$TABS")"
  echo "CDP up on 9222 ($TABS pages)"
else
  notify "$(msg al.port_silent port=9222)"
  echo "Chrome started but port 9222 never answered" >&2
  exit 1
fi

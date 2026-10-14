#!/bin/bash
set -u

DATA_DIR="$HOME/agents/alpha-profile"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p "$DATA_DIR"

msg() { /usr/bin/python3 -I "$HOME/bin/rainbow_i18n.py" "$@" 2>/dev/null || echo "$1"; }
notify() { osascript -e "display notification \"$1\" with title \"$(msg al.title name=Alpha)\"" >/dev/null 2>&1; }

alive() { curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; }

if [ "${ALPHA_BROWSER_OWNER:-0}" != "1" ] && [ -x "$HOME/bin/alpha-browser" ]; then
  OUT=$("$HOME/bin/alpha-browser" start --by human 2>&1); RC=$?
  case "$OUT" in
    *'"status": "already-up"'*) notify "$(msg al.already port=9222)" ;;
    *'"status": "started"'*) notify "$(msg al.up)" ;;
    *'no working python3'*) OWNER_DOWN=1 ;;
    *) notify "$(msg al.failed out="$OUT")" ;;
  esac
  if [ "${OWNER_DOWN:-0}" != "1" ]; then echo "$OUT"; exit $RC; fi
  notify "the owner (alpha-browser) is not running — no python3; opening directly"   # no python3: no catalog either
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
  --remote-allow-origins=* \
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

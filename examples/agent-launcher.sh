#!/bin/bash
set -u

DATA_DIR="$HOME/agents/alpha-profile"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p "$DATA_DIR"

notify() { osascript -e "display notification \"$1\" with title \"דפדפן אלפא (CDP)\"" >/dev/null 2>&1; }

alive() { curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; }

if [ "${ALPHA_BROWSER_OWNER:-0}" != "1" ] && [ -x "$HOME/bin/alpha-browser" ]; then
  OUT=$("$HOME/bin/alpha-browser" start --by human 2>&1); RC=$?
  case "$OUT" in
    *'"status": "already-up"'*) notify "כבר רץ (פורט 9222) — לא נפתח חלון חדש" ;;
    *'"status": "started"'*) notify "עלה — ערוץ CDP פעיל" ;;
    *'no working python3'*) OWNER_DOWN=1 ;;
    *) notify "הפתיחה נכשלה — $OUT" ;;
  esac
  if [ "${OWNER_DOWN:-0}" != "1" ]; then echo "$OUT"; exit $RC; fi
  notify "הבעלים (alpha-browser) לא רץ — אין python3; פותח ישירות"
fi

# Already running? Say so and stop. Starting a second copy on the same port would fail anyway,
# and killing the live one costs the logged-in session.
if alive; then
  notify "כבר רץ (פורט 9222) — לא נפתח חלון חדש"
  echo "CDP already running on 9222"
  exit 0
fi

if [ ! -x "$CHROME" ]; then
  notify "שגיאה: Google Chrome לא נמצא"
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
  notify "עלה — ערוץ CDP פעיל, $TABS טאבים שוחזרו"
  echo "CDP up on 9222 ($TABS pages)"
else
  notify "נפתח אבל ערוץ ה-CDP לא עלה על 9222 — הסוכן לא יוכל לשלוט בו"
  echo "Chrome started but port 9222 never answered" >&2
  exit 1
fi

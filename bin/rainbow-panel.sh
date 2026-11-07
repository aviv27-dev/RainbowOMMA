#!/bin/bash
# rainbow-panel.sh — what the panel icon runs: (re)start the panel's local server with a fresh key, then open its window.
# One panel at a time: an old server of ours (pid file) is closed first; it would end by itself a minute after its window.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
I18N="$DIR/rainbow_i18n.py"
RUN="${RAINBOW_HOME:-$HOME/.rainbowomma}/panel"; mkdir -p "$RUN"; chmod 700 "$RUN"
PORT="${RAINBOW_PANEL_PORT:-8790}"
PY=""
for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do   # never macOS's stub (it only asks for the developer tools)
  [ -x "$p" ] || continue
  [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
  PY="$p"; break
done
[ -n "$PY" ] || { echo "python3 is needed (macOS: xcode-select --install)" >&2; exit 1; }
msg() { "$PY" -I "$I18N" "$@" 2>/dev/null || echo "$1"; }

if [ -f "$RUN/pid" ] && kill -0 "$(cat "$RUN/pid")" 2>/dev/null && ps -o command= -p "$(cat "$RUN/pid")" | grep -q rainbow-panel.py; then
  kill "$(cat "$RUN/pid")" 2>/dev/null; sleep 0.5
fi
nohup "$PY" -I "$DIR/rainbow-panel.py" --port "$PORT" > "$RUN/out" 2> "$RUN/err" &
echo $! > "$RUN/pid"
URL=""
for _ in $(seq 1 30); do URL=$(sed -n 's/.*"url": *"\([^"]*\)".*/\1/p' "$RUN/out" 2>/dev/null); [ -n "$URL" ] && break; sleep 0.2; done
[ -n "$URL" ] || { msg panel.not_up why="$(tail -1 "$RUN/err" 2>/dev/null)" >&2; exit 1; }
nohup osascript -l JavaScript "$DIR/rainbow-panel.js" "$URL" "$(msg panel.title)" >/dev/null 2>&1 &
msg panel.opened

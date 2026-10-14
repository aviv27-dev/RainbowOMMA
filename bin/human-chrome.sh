#!/bin/bash
set -u

DATA_DIR="$HOME/Library/Application Support/Google/Chrome"
EXE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
I18N="$(cd "$(dirname "$0")" && pwd)/rainbow_i18n.py"
msg() { /usr/bin/python3 -I "$I18N" "$@"; }

notify() { osascript -e "display notification \"$1\" with title \"$(msg hc.title)\"" >/dev/null 2>&1; }

mine() {
  ps -axo pid=,command= | while read -r pid cmd; do
    case "$cmd" in
      "$EXE"*) ;;
      *) continue ;;
    esac
    case "$cmd" in
      *alpha-profile*|*remote-debugging-port*|*--headless*|*--type=*) continue ;;
    esac
    echo "$pid"
  done | head -1
}

pid=$(mine)
if [ -n "$pid" ]; then
  osascript -e "tell application \"System Events\" to set frontmost of (first process whose unix id is $pid) to true" >/dev/null 2>&1
  exit 0
fi

open -n -a "Google Chrome" --args --user-data-dir="$DATA_DIR" --no-first-run --no-default-browser-check
for _ in $(seq 1 20); do
  pid=$(mine); [ -n "$pid" ] && break
  sleep 0.5
done
if [ -n "$pid" ]; then
  osascript -e "tell application \"System Events\" to set frontmost of (first process whose unix id is $pid) to true" >/dev/null 2>&1
else
  notify "$(msg hc.not_up)"
  exit 1
fi

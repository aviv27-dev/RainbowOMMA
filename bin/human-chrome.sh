#!/bin/bash
case "${1:-}" in -h|--help)   # --help: one shape for every tool (bin/rainbow_help.py), and it never acts
  for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
    if [ -x "$p" ] && "$p" -I -V >/dev/null 2>&1; then exec "$p" -I "$(cd "$(dirname "$0")" && pwd)/rainbow_help.py" human-chrome.sh; fi
  done
  echo "human-chrome.sh: no working python3 found" >&2; exit 1 ;;
esac
set -u

DATA_DIR="$HOME/Library/Application Support/Google/Chrome"
EXE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
I18N="$(cd "$(dirname "$0")" && pwd)/rainbow_i18n.py"
py() {   # the first python3 that works — never macOS's stub, which only asks to install the developer tools
  for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$p" ] || continue
    [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
    "$p" "$@"; return
  done
  return 127
}
msg() { py -I "$I18N" "$@" 2>/dev/null || echo "$1"; }

notify() { osascript -e "display notification \"$1\" with title \"$(msg hc.title)\"" >/dev/null 2>&1; }

mine() {
  ps -axo pid=,command= | while read -r pid cmd; do
    case "$cmd" in
      "$EXE"*) ;;
      *) continue ;;
    esac
    case "$cmd" in
      *remote-debugging-port*|*remote-debugging-pipe*|*--headless*|*--type=*) continue ;;
      *--user-data-dir="$DATA_DIR"|*--user-data-dir="$DATA_DIR"\ *) ;;
      *--user-data-dir=*) continue ;;      # a Chrome on another profile (an agent's) is never "your Chrome"
    esac
    echo "$pid"
  done | head -1
}

# a click that "does nothing": the human's Chrome was running with every window
# minimized, and activating a process never un-minimizes. A "reopen" Apple Event to THIS pid is what a Dock click sends: Chrome
# restores a minimized window, or opens a new one when it has none. Sent to a pid it needs no Automation grant (kAENeverInteract:
# never a dialog); then AppKit brings that pid forward, System Events stays the fallback.
front() {
  local r
  r=$(osascript -l JavaScript -e "ObjC.import('AppKit');
const t = \$.NSAppleEventDescriptor.descriptorWithProcessIdentifier($1);
\$.NSAppleEventDescriptor.appleEventWithEventClassEventIDTargetDescriptorReturnIDTransactionID(0x61657674, 0x72617070, t, -1, 0)
  .sendEventWithOptionsTimeoutError(3 | 0x10, 5, Ref());
const a = \$.NSRunningApplication.runningApplicationWithProcessIdentifier($1);
a.isNil() ? 'none' : String(a.activateWithOptions(\$.NSApplicationActivateAllWindows))" 2>/dev/null)
  [ "$r" = "true" ] || osascript -e "tell application \"System Events\" to set frontmost of (first process whose unix id is $1) to true" >/dev/null 2>&1
}

pid=$(mine)
if [ -n "$pid" ]; then
  front "$pid"
  exit 0
fi

# closed: its color from human.json goes on first (Chrome reads it at start; never while it runs) — then open it
OWNER="$(cd "$(dirname "$0")" && pwd)/browser-owner"
[ -x "$OWNER" ] && "$OWNER" human-paint >/dev/null 2>&1
open -n -a "Google Chrome" --args --user-data-dir="$DATA_DIR" --no-first-run --no-default-browser-check
for _ in $(seq 1 20); do
  pid=$(mine); [ -n "$pid" ] && break
  sleep 0.5
done
if [ -n "$pid" ]; then
  front "$pid"
else
  notify "$(msg hc.not_up)"
  exit 1
fi

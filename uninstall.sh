#!/bin/bash
# RainbowOMMA uninstaller — takes out what install.sh put in, and nothing else.
#
#   ./uninstall.sh [--bin DIR] [--purge] [--dry-run]
#
#   --bin DIR    where install.sh put the tools (default: ~/bin)
#   --purge      also browsers.json and $RAINBOW_HOME (logs, state, themes, receipts)
#   --dry-run    print what would happen, change nothing
#
# Never touched: the agents' Chrome profiles (they hold their logins — delete them yourself if you want), your own
# Chrome, and any agent settings you merged an adapter into. The Dock group and desktop icons have their own way out:
# install/make-dock-tray.sh --remove, and dragging the icons to the Trash.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/bin"
PURGE=0
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bin) BIN="${2:?--bin needs a folder}"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case "$BIN" in /*) ;; *) BIN="$(pwd)/$BIN" ;; esac
ROOT="${RAINBOW_HOME:-$HOME/.rainbowomma}"
AGENTS_DIR="${RAINBOW_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"

run() { if [ "$DRY" = 1 ]; then echo "would: $*"; else "$@"; fi; }

for label in com.rainbowomma.agent-office-sweep com.rainbowomma.heal com.rainbowomma.tabs; do
  plist="$AGENTS_DIR/$label.plist"
  [ -e "$plist" ] || continue
  echo "→ job $label"
  if [ "$DRY" = 1 ]; then
    echo "would: unload and remove $plist"
  else
    [ "${RAINBOW_INSTALL_NO_LAUNCHCTL:-0}" = "1" ] || launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
    rm -f "$plist"
  fi
done

echo "→ tools in $BIN (only the ones RainbowOMMA ships)"
for f in "$HERE"/bin/*; do
  name="$(basename "$f")"
  case "$name" in browsers.json|__pycache__) continue ;; esac
  [ -e "$BIN/$name" ] && run rm -f "$BIN/$name"
done
[ -d "$BIN/__pycache__" ] && run rm -rf "$BIN/__pycache__"

if [ "$PURGE" = 1 ]; then
  [ -e "$BIN/browsers.json" ] && { echo "→ $BIN/browsers.json"; run rm -f "$BIN/browsers.json"; }
  if [ -d "$ROOT" ]; then
    # only a real folder that is RainbowOMMA's: never /, your home, a symlink, or a folder without its state or logs
    R="$(cd "$ROOT" && pwd -P)"
    if [ -L "$ROOT" ] || [ "$R" = / ] || [ "$R" = "$(cd "$HOME" && pwd -P)" ] || { [ ! -d "$R/state" ] && [ ! -d "$R/logs" ]; }; then
      echo "not removing $ROOT: it doesn't look like RainbowOMMA's folder (no state/ or logs/, or it is / or your home) — delete it yourself" >&2
    else
      echo "→ $ROOT (logs, state, themes, receipts)"; run rm -rf "$R"
    fi
  fi
else
  echo "kept: $BIN/browsers.json and $ROOT (--purge removes them)"
fi
echo "Done. The agents' Chrome profiles were not touched."

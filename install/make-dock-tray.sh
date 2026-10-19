#!/bin/bash
# make-dock-tray.sh — the agents' browsers as ONE group in the Dock. Every Chrome shares one Dock icon (one app, many
# profiles), so each agent in browsers.json gets a small applet: a circle in its color with its name. A click runs
# `desk-browser.sh open <agent>`: closed → it opens; open or minimized → it comes to the front. Only a failure shows a dialog.
# The group sits right after the last Chrome in the Dock, between two small spacers; re-running replaces it in place and
# the rest of the Dock is never touched. The Dock reloads once.
#
#   install/make-dock-tray.sh [--bin DIR]             build the applets (~/Applications/RainbowOMMA) and put them in the Dock
#   install/make-dock-tray.sh [--bin DIR] --no-dock   build the applets only
#   install/make-dock-tray.sh --remove                take the group out of the Dock (the applets stay)
set -eu
BIN="$HOME/bin"; DOCK=1; REMOVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bin) BIN="${2:?--bin needs a folder}"; shift 2 ;;
    --no-dock) DOCK=0; shift ;;
    --remove) REMOVE=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${RAINBOW_DOCK_APPS:-$HOME/Applications/RainbowOMMA}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
I18N="$BIN/rainbow_i18n.py"; [ -f "$I18N" ] || I18N="$HERE/../bin/rainbow_i18n.py"
. "$HERE/icon-lib.sh"
py() {   # the first python3 that works — never macOS's stub, which only asks to install the developer tools
  for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$p" ] || continue
    [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
    "$p" "$@"; return
  done
  return 127
}
msg() { py -I "$I18N" "$@" 2>/dev/null || echo "$1"; }

if [ "$REMOVE" = 1 ]; then
  defaults export com.apple.dock "$WORK/dock.plist"
  py -I "$HERE/dock_tray.py" "$WORK/dock.plist" "$OUT" --remove
  defaults import com.apple.dock "$WORK/dock.plist"
  killall Dock
  echo "ok — the agents' group is out of the Dock (the applets stay in $OUT)"
  exit 0
fi

# the agents this owner knows, in the registry's order: name<TAB>label<TAB>color
AGENTS=$("$BIN/browser-owner" list 2>/dev/null | py -I -c '
import json, sys
for a in json.load(sys.stdin).get("agents", []):
    print("\t".join((a["agent"], a["label"], a["color"])))') || AGENTS=""
[ -n "$AGENTS" ] || { echo "no agents: is $BIN/browser-owner installed and browsers.json filled in?" >&2; exit 1; }

mkdir -p "$OUT"
rm -rf "$OUT"/*.app
CLOSE="$(asq "$(msg desk.btn_close)")"; QB="$(asq "$BIN/desk-browser.sh")"
LIST="$WORK/apps.txt"; : > "$LIST"
i=0
while IFS=$'\t' read -r who label color; do
  [ -n "$who" ] || continue
  i=$((i + 1))
  name="$(msg dock.app_name n="$i" name="$label")"
  app="$OUT/$name.app"; qn="$(asq "$name")"
  cat > "$WORK/a.applescript" <<AS
-- $qn — made by RainbowOMMA/make-dock-tray.sh; the work is desk-browser.sh open $who
on run
  try
    do shell script quoted form of "$QB" & " open $who"
  on error e
    activate
    display dialog e with title "$qn" buttons {"$CLOSE"} default button 1 giving up after 8
  end try
end run
AS
  osacompile -o "$app" "$WORK/a.applescript"
  icon "$WORK/applet.icns" "$color" "$label" 40 300          # a larger circle and name than the desktop icons: readable in the Dock
  cp "$WORK/applet.icns" "$app/Contents/Resources/applet.icns"
  rm -f "$app/Contents/Resources/Assets.car"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$app/Contents/Info.plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$app/Contents/Info.plist" 2>/dev/null || true   # no 2nd Dock icon while it runs
  codesign --force --deep -s - "$app" >/dev/null 2>&1 || true
  touch "$app"
  echo "$app" >> "$LIST"
done <<< "$AGENTS"

if [ "$DOCK" = 0 ]; then echo "ok — $i applets in $OUT (the Dock was not touched)"; exit 0; fi
defaults export com.apple.dock "$WORK/dock.plist"
py -I "$HERE/dock_tray.py" "$WORK/dock.plist" "$OUT" "$LIST"
defaults import com.apple.dock "$WORK/dock.plist"
killall Dock
echo "ok — $i agents side by side in the Dock (applets in $OUT)"

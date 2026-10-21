#!/bin/bash
# Colored open/close icons on the desktop: one pair per agent in browsers.json, the human's own Chrome, and
# "close all agents". Each icon runs desk-browser.sh from the folder the tools were installed into.
#
#   install/make-desktop-apps.sh [--bin DIR]      DIR: where install.sh put the tools (default ~/bin)
#   ONLY=<agent> install/make-desktop-apps.sh     only that agent's two icons (a new agent): nothing is archived
set -eu
BIN="$HOME/bin"
[ "${1:-}" = "--bin" ] && BIN="${2:?--bin needs a folder}"
DESK="$HOME/Desktop"
ARCH="$DESK/Archive/browser-shortcuts-$(date +%Y%m%d-%H%M)"
WORK="$(mktemp -d)"
HERE="$(cd "$(dirname "$0")" && pwd)"
I18N="$BIN/rainbow_i18n.py"; [ -f "$I18N" ] || I18N="$HERE/../bin/rainbow_i18n.py"
py() {   # the first python3 that works — never macOS's stub, which only asks to install the developer tools
  for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$p" ] || continue
    [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
    "$p" "$@"; return
  done
  return 127
}
msg() { py -I "$I18N" "$@" 2>/dev/null || echo "$1"; }
CANCEL="$(msg desk.btn_cancel)"; CLOSE="$(msg desk.btn_close)"; ERR="$(msg desk.error)"

ONLY="${ONLY:-}"
if [ -z "$ONLY" ]; then
  mkdir -p "$ARCH"
  for f in "$DESK"/[0-9]\ ·\ *.app "$DESK"/[0-9][0-9]\ ·\ *.app; do
    [ -e "$f" ] && mv "$f" "$ARCH/"
  done
fi

. "$HERE/icon-lib.sh"

app() {   # app <name> <hex> <icon text> <act> <who> [confirm text]
  local name="$1" hex="$2" txt="$3" act="$4" who="$5" confirm="${6:-}" src="$WORK/a.applescript" out="$DESK/$1.app"
  [ -n "$ONLY" ] && [ "$who" != "$ONLY" ] && return 0
  local qn qc qb qcancel qclose qerr
  qn="$(asq "$name")"; qc="$(asq "$confirm")"; qb="$(asq "$BIN/desk-browser.sh")"
  qcancel="$(asq "$CANCEL")"; qclose="$(asq "$CLOSE")"; qerr="$(asq "$ERR")"
  {
    echo "-- $qn — made by RainbowOMMA/make-desktop-apps.sh; the work is $BIN/desk-browser.sh $act $who"
    echo "on run"
    if [ -n "$confirm" ]; then
      echo "  display dialog \"$qc\" with title \"$qn\" buttons {\"$qcancel\", \"$qclose\"} default button \"$qcancel\" cancel button \"$qcancel\" with icon caution"
    fi
    echo "  try"
    echo "    set r to do shell script quoted form of \"$qb\" & \" $act $who\""
    echo "  on error e"
    echo "    set r to \"$qerr\" & e"
    echo "  end try"
    echo "  display notification r with title \"$qn\""
    echo "end run"
  } > "$src"
  rm -rf "$out"
  osacompile -o "$out" "$src"
  icon "$WORK/applet.icns" "$hex" "$txt"
  cp "$WORK/applet.icns" "$out/Contents/Resources/applet.icns"
  rm -f "$out/Contents/Resources/Assets.car"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$out/Contents/Info.plist" 2>/dev/null || true
  codesign --force --deep -s - "$out" >/dev/null 2>&1 || true
  touch "$out"
}

# the agents this owner may stop, with their label and color, from browsers.json
AGENTS=$("$BIN/browser-owner" list 2>/dev/null | py -I -c '
import json, sys
names = set(sys.argv[1].split())
for a in json.load(sys.stdin).get("agents", []):
    if a["agent"] in names:
        print("\t".join((a["agent"], a["label"], a["color"])))' "$("$BIN/browser-owner" names 2>/dev/null)") || AGENTS=""
[ -n "$AGENTS" ] || { echo "no agents: is $BIN/browser-owner installed and browsers.json filled in?" >&2; exit 1; }

H="$(msg desk.name.human)"
n=1
app "$n · $(msg desk.app.open_human)" "#B0BEC5" "$H" open human; n=$((n + 1))
while IFS=$'\t' read -r who label hex; do
  app "$n · $(msg desk.app.open_agent name="$label")" "$hex" "$label" open "$who"; n=$((n + 1))
done <<< "$AGENTS"
app "$n · ✖ $(msg desk.app.close_human)" "#B0BEC5" "✖ $H" close human; n=$((n + 1))
LABELS=""
while IFS=$'\t' read -r who label hex; do
  app "$n · ✖ $(msg desk.app.close_agent name="$label")" "$hex" "✖ $label" close "$who" "$(msg desk.confirm_one name="$label")"; n=$((n + 1))
  LABELS="${LABELS:+$LABELS, }$label"
done <<< "$AGENTS"
app "$n · ✖ $(msg desk.app.close_all)" "#757575" "✖ $(msg desk.name.all)" close agents "$(msg desk.confirm_all names="$LABELS")"
rm -rf "$WORK"
if [ -n "$ONLY" ]; then echo "ok — the icons of $ONLY on the desktop"; else echo "ok — $n icons on the desktop; the old ones in $ARCH"; fi

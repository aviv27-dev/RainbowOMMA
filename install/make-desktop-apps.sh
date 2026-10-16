#!/bin/bash
# Colored open/close icons on the desktop: one pair per agent in browsers.json, the human's own Chrome, and
# "close all agents". Each icon runs desk-browser.sh from the folder the tools were installed into.
#
#   install/make-desktop-apps.sh [--bin DIR]      DIR: where install.sh put the tools (default ~/bin)
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

mkdir -p "$ARCH"
for f in "$DESK"/[0-9]\ ·\ *.app "$DESK"/[0-9][0-9]\ ·\ *.app; do
  [ -e "$f" ] && mv "$f" "$ARCH/"
done

icon() {   # icon <out.icns> <hex> <text>
  local png="$WORK/i.png" set="$WORK/i.iconset"
  osascript -l JavaScript - "$png" "$2" "$3" <<'JS'
ObjC.import('AppKit');
function run(argv) {
  const [out, hex, text] = argv; const v = parseInt(hex.slice(1), 16);
  const r = ((v >> 16) & 255) / 255, g = ((v >> 8) & 255) / 255, b = (v & 255) / 255;
  const light = (0.299 * r + 0.587 * g + 0.114 * b) > 0.65;
  const S = 1024;
  const rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(null, S, S, 8, 4, true, false, $.NSDeviceRGBColorSpace, 0, 0);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));
  $.NSColor.colorWithDeviceRedGreenBlueAlpha(r, g, b, 1).setFill;
  $.NSBezierPath.bezierPathWithOvalInRect($.NSMakeRect(64, 64, S - 128, S - 128)).fill;
  const attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey(light ? $.NSColor.colorWithDeviceRedGreenBlueAlpha(0.15, 0.12, 0, 1) : $.NSColor.whiteColor, $.NSForegroundColorAttributeName);
  const s = $.NSString.alloc.initWithUTF8String(text);
  // the largest bold size whose text fits inside the circle — English names are longer than Hebrew ones
  let size = 260, sz;
  do {
    attrs.setObjectForKey($.NSFont.boldSystemFontOfSize(size), $.NSFontAttributeName);
    sz = s.sizeWithAttributes(attrs);
    size -= 10;
  } while (sz.width > (S - 128) * 0.74 && size >= 80);
  s.drawAtPointWithAttributes($.NSMakePoint((S - sz.width) / 2, (S - sz.height) / 2), attrs);
  $.NSGraphicsContext.restoreGraphicsState;
  rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $()).writeToFileAtomically(out, true);
  return 'ok';
}
JS
  rm -rf "$set"; mkdir -p "$set"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$png" --out "$set/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$png" --out "$set/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$set" -o "$1"
}

asq() { local s="${1//\\/\\\\}"; printf '%s' "${s//\"/\\\"}"; }   # text safe inside an AppleScript "string" (a label may hold " or \)

app() {   # app <name> <hex> <icon text> <act> <who> [confirm text]
  local name="$1" hex="$2" txt="$3" act="$4" who="$5" confirm="${6:-}" src="$WORK/a.applescript" out="$DESK/$1.app"
  local qn qc qb qcancel qclose qerr
  qn="$(asq "$name")"; qc="$(asq "$confirm")"; qb="$(asq "$BIN/desk-browser.sh")"
  qcancel="$(asq "$CANCEL")"; qclose="$(asq "$CLOSE")"; qerr="$(asq "$ERR")"
  {
    echo "-- $name — made by RainbowOMMA/make-desktop-apps.sh; the work is $BIN/desk-browser.sh $act $who"
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
echo "ok — $n icons on the desktop; the old ones in $ARCH"

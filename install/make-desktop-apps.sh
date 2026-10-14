#!/bin/bash
set -eu
DESK="$HOME/Desktop"
ARCH="$DESK/Archive/browser-shortcuts-$(date +%Y%m%d-%H%M)"
WORK="$(mktemp -d)"
HERE="$(cd "$(dirname "$0")" && pwd)"
I18N="$HERE/../bin/rainbow_i18n.py"; [ -f "$I18N" ] || I18N="$HOME/bin/rainbow_i18n.py"
msg() { /usr/bin/python3 -I "$I18N" "$@"; }
CANCEL="$(msg desk.btn_cancel)"; CLOSE="$(msg desk.btn_close)"; ERR="$(msg desk.error)"

mkdir -p "$ARCH"
for f in "$DESK"/*Chrome*.app "$DESK"/*דפדפן*.app "$DESK"/[1-9]\ ·\ *.app; do
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
  attrs.setObjectForKey($.NSFont.boldSystemFontOfSize(text.length > 7 ? 150 : text.length > 4 ? 200 : 260), $.NSFontAttributeName);
  attrs.setObjectForKey(light ? $.NSColor.colorWithDeviceRedGreenBlueAlpha(0.15, 0.12, 0, 1) : $.NSColor.whiteColor, $.NSForegroundColorAttributeName);
  const s = $.NSString.alloc.initWithUTF8String(text);
  const sz = s.sizeWithAttributes(attrs);
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

app() {   # app <name> <hex> <icon text> <act> <who> [confirm text]
  local name="$1" hex="$2" txt="$3" act="$4" who="$5" confirm="${6:-}" src="$WORK/a.applescript" out="$DESK/$1.app"
  {
    echo "-- $name — made by RainbowOMMA/make-desktop-apps.sh; the work is ~/bin/desk-browser.sh $act $who"
    echo "on run"
    if [ -n "$confirm" ]; then
      echo "  display dialog \"$confirm\" with title \"$name\" buttons {\"$CANCEL\", \"$CLOSE\"} default button \"$CANCEL\" cancel button \"$CANCEL\" with icon caution"
    fi
    echo "  try"
    echo "    set r to do shell script quoted form of ((POSIX path of (path to home folder)) & \"bin/desk-browser.sh\") & \" $act $who\""
    echo "  on error e"
    echo "    set r to \"$ERR\" & e"
    echo "  end try"
    echo "  display notification r with title \"$name\""
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

H="$(msg desk.name.human)"; A="$(msg desk.name.alpha)"; B="$(msg desk.name.bravo)"; C="$(msg desk.name.charlie)"
app "1 · ⚪ $(msg desk.app.open_human)"            "#B0BEC5" "$H"   open  human
app "2 · 🟣 $(msg desk.app.open_agent name="$A")"  "#8E24AA" "$A"   open  alpha
app "3 · 🟢 $(msg desk.app.open_agent name="$B")"  "#00897B" "$B"   open  bravo
app "4 · 🟠 $(msg desk.app.open_agent name="$C")"  "#F4511E" "$C"   open  charlie
app "5 · ✖ $(msg desk.app.close_human)"            "#B0BEC5" "✖ $H" close human
app "6 · ✖ $(msg desk.app.close_agent name="$A")"  "#8E24AA" "✖ $A" close alpha "$(msg desk.confirm_one name="$A")"
app "7 · ✖ $(msg desk.app.close_agent name="$B")"  "#00897B" "✖ $B" close bravo
app "8 · ✖ $(msg desk.app.close_agent name="$C")"  "#F4511E" "✖ $C" close charlie
app "9 · ✖ $(msg desk.app.close_all)"              "#757575" "✖ $(msg desk.name.all)" close agents "$(msg desk.confirm_all names="$A, $B, $C")"
rm -rf "$WORK"
echo "ok — 9 icons on the desktop; the old ones in $ARCH"

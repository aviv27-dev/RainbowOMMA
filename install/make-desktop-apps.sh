#!/bin/bash
set -eu
DESK="$HOME/Desktop"
ARCH="$DESK/Archive/browser-shortcuts-$(date +%Y%m%d-%H%M)"
WORK="$(mktemp -d)"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$ARCH"
for f in "$DESK"/*Chrome*.app "$DESK"/*דפדפן*.app; do
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
  attrs.setObjectForKey($.NSFont.boldSystemFontOfSize(text.length > 4 ? 200 : 260), $.NSFontAttributeName);
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
      echo "  display dialog \"$confirm\" with title \"$name\" buttons {\"ביטול\", \"סגור\"} default button \"ביטול\" cancel button \"ביטול\" with icon caution"
    fi
    echo "  try"
    echo "    set r to do shell script quoted form of ((POSIX path of (path to home folder)) & \"bin/desk-browser.sh\") & \" $act $who\""
    echo "  on error e"
    echo "    set r to \"שגיאה: \" & e"
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

app "1 · ⚪ האדם — פתח Chrome"            "#B0BEC5" "האדם"   open  human
app "2 · 🟣 אלפא — פתח דפדפן"              "#8E24AA" "אלפא"   open  alpha
app "3 · 🟢 בראבו — פתח דפדפן"              "#00897B" "בראבו"   open  bravo
app "4 · 🟠 צ׳רלי — פתח דפדפן"              "#F4511E" "צ׳רלי"   open  charlie
app "5 · ✖ האדם — סגור Chrome (לא סוכנות)" "#B0BEC5" "✖ האדם" close human
app "6 · ✖ אלפא — סגור דפדפן"       "#8E24AA" "✖ אלפא" close alpha "לסגור את הדפדפן של אלפא? ההתחברות של הסוכן תתנתק, והוא לא ייפתח לבד עד לפתיחה ידנית מהקיצור."
app "7 · ✖ בראבו — סגור דפדפן"              "#00897B" "✖ בראבו" close bravo
app "8 · ✖ צ׳רלי — סגור דפדפן"              "#F4511E" "✖ צ׳רלי" close charlie
app "9 · ✖ כל הסוכנים — סגור ⚠️"           "#757575" "✖ הכל"  close agents "לסגור את הדפדפנים של כל הסוכנים (אלפא, בראבו, צ׳רלי)? ההתחברויות של הסוכנים יתנתקו, ואף אחד מהם לא ייפתח לבד עד לפתיחה ידנית."
rm -rf "$WORK"
echo "ok — 9 icons on the desktop; the old ones in $ARCH"

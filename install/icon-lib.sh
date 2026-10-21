# shellcheck shell=bash
# icon-lib.sh — sourced by make-desktop-apps.sh and make-dock-tray.sh: icon() draws the colored circle with a name in it as an
# .icns; asq() makes text safe inside an AppleScript string
icon() {   # icon <out.icns> <hex> <text> [inset px of 1024] [largest font size] — needs $WORK
  local png="$WORK/i.png" set="$WORK/i.iconset"
  osascript -l JavaScript - "$png" "$2" "$3" "${4:-64}" "${5:-260}" <<'JS'
ObjC.import('AppKit');
function run(argv) {
  const [out, hex, text] = argv; const inset = +argv[3], top = +argv[4]; const v = parseInt(hex.slice(1), 16);
  const r = ((v >> 16) & 255) / 255, g = ((v >> 8) & 255) / 255, b = (v & 255) / 255;
  const light = (0.299 * r + 0.587 * g + 0.114 * b) > 0.65;
  const S = 1024;
  const rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(null, S, S, 8, 4, true, false, $.NSDeviceRGBColorSpace, 0, 0);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));
  $.NSColor.colorWithDeviceRedGreenBlueAlpha(r, g, b, 1).setFill;
  $.NSBezierPath.bezierPathWithOvalInRect($.NSMakeRect(inset, inset, S - 2 * inset, S - 2 * inset)).fill;
  const attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey(light ? $.NSColor.colorWithDeviceRedGreenBlueAlpha(0.15, 0.12, 0, 1) : $.NSColor.whiteColor, $.NSForegroundColorAttributeName);
  const s = $.NSString.alloc.initWithUTF8String(text);
  // the largest bold size whose text fits inside the circle — English names are longer than Hebrew ones
  let size = top, sz;
  do {
    attrs.setObjectForKey($.NSFont.boldSystemFontOfSize(size), $.NSFontAttributeName);
    sz = s.sizeWithAttributes(attrs);
    size -= 10;
  } while (sz.width > (S - 2 * inset) * 0.74 && size >= 80);
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

asq() { local s="${1//[$'\r\n\t']/ }"; s="${s//\\/\\\\}"; printf '%s' "${s//\"/\\\"}"; }   # text safe inside an AppleScript "string" (a label may hold " or \; a newline would end it)

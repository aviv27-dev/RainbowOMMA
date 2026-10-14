ObjC.import('AppKit');
function run(argv) {
  const [out, label, r, g, b] = [argv[0], argv[1], +argv[2], +argv[3], +argv[4]];
  const W = 3000, H = 110;
  const rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
    null, W, H, 8, 4, true, false, $.NSDeviceRGBColorSpace, 0, 0);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));
  $.NSColor.colorWithDeviceRedGreenBlueAlpha(r / 255, g / 255, b / 255, 1).setFill;
  $.NSRectFill($.NSMakeRect(0, 0, W, H));
  const attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey($.NSFont.boldSystemFontOfSize(19), $.NSFontAttributeName);
  const ink = argv[5] === 'dark' ? [0.15, 0.12, 0, 0.85] : [1, 1, 1, 0.8];
  attrs.setObjectForKey($.NSColor.colorWithDeviceRedGreenBlueAlpha(ink[0], ink[1], ink[2], ink[3]), $.NSForegroundColorAttributeName);
  const s = $.NSString.alloc.initWithUTF8String(label);
  for (const x of [40, 470]) s.drawAtPointWithAttributes($.NSMakePoint(x, H - 50), attrs);
  $.NSGraphicsContext.restoreGraphicsState;
  rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $()).writeToFileAtomically(out, true);
  return 'ok';
}

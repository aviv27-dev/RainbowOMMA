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
  // Chrome lays the frame image from the window's left edge. RTL: the tabs grow from the right, so the name sits on the free
  // left part. LTR: the tabs grow from the left, so the name repeats along the rest of the frame, and whatever the window's
  // width, its right part carries it.
  const xs = argv[6] === 'ltr' ? [470, 900, 1330, 1760, 2190, 2620] : [40, 470];
  for (const x of xs) s.drawAtPointWithAttributes($.NSMakePoint(x, H - 50), attrs);
  $.NSGraphicsContext.restoreGraphicsState;
  rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $()).writeToFileAtomically(out, true);
  return 'ok';
}

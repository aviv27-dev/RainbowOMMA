// rainbow-panel.js — the panel's window: a native AppKit window with a web view on the panel's local server, so no browser
// profile (the human's or an agent's) is opened just to show it. Closing the window ends it.
// Usage: osascript -l JavaScript rainbow-panel.js <url> [title]
ObjC.import('Cocoa'); ObjC.import('WebKit');
function run(argv) {
  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyRegular);
  const vis = $.NSScreen.mainScreen.visibleFrame;
  const W = 600, H = 560;
  const win = $.NSWindow.alloc.initWithContentRectStyleMaskBackingDefer(
    $.NSMakeRect(vis.origin.x + (vis.size.width - W) / 2, vis.origin.y + (vis.size.height - H) / 2, W, H), 15, $.NSBackingStoreBuffered, false);
  win.title = argv[1] || 'RainbowOMMA';
  win.releasedWhenClosed = false;
  const wv = $.WKWebView.alloc.initWithFrameConfiguration($.NSMakeRect(0, 0, W, H), $.WKWebViewConfiguration.alloc.init);
  wv.autoresizingMask = $.NSViewWidthSizable | $.NSViewHeightSizable;
  wv.loadRequest($.NSURLRequest.requestWithURL($.NSURL.URLWithString(argv[0])));
  win.contentView = wv;
  win.makeKeyAndOrderFront(null);
  app.activateIgnoringOtherApps(true);
  // the red button hides the window; when it is gone, the process (and so the panel) ends
  $.NSTimer.scheduledTimerWithTimeIntervalRepeatsBlock(1, true, () => { if (!win.isVisible) app.terminate(null); });
  app.run;
}

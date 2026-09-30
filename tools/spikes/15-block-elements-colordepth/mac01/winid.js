// osascript -l JavaScript winid.js <OwnerName>
// Prints the CGWindowNumber of the first on-screen layer-0 window owned by <OwnerName>
// (empty string when none). CGWindowList needs no Automation grant.
ObjC.import('CoreGraphics');
function run(argv) {
  const owner = argv[0] || 'iTerm2';
  const ref = $.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, $.kCGNullWindowID);
  const wins = ObjC.deepUnwrap(ObjC.castRefToObject(ref)) || [];
  for (let i = 0; i < wins.length; i++) {
    const w = wins[i];
    if (w.kCGWindowOwnerName === owner && w.kCGWindowLayer === 0) return String(w.kCGWindowNumber);
  }
  return '';
}

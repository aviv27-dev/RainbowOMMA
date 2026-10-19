#!/usr/bin/env python3
"""dock_tray.py — put the agents' applets in the Dock as one group, or take the group out. Used by make-dock-tray.sh.

    dock_tray.py DOCK.plist APPLET_FOLDER LIST_FILE      the group goes right after the last Chrome in the Dock (else at the end)
    dock_tray.py DOCK.plist APPLET_FOLDER --remove       only the group goes

The group is the applets (one path per line in LIST_FILE) between two small spacers tagged "rainbowomma". Re-running
replaces the group in place; nothing else in the Dock is touched.
"""
import plistlib
import sys
import urllib.parse
import uuid


def _url(tile):
    return urllib.parse.unquote((((tile.get("tile-data") or {}).get("file-data") or {}).get("_CFURLString") or ""))


def _ours(tile, folder):
    return folder.rstrip("/") + "/" in _url(tile) or bool((tile.get("tile-data") or {}).get("rainbowomma"))


def _guid():
    return int(uuid.uuid4().int % 2 ** 31)


def _spacer():
    return {"GUID": _guid(), "tile-type": "small-spacer-tile", "tile-data": {"rainbowomma": True}}


def place(dock, folder, apps=None):
    """→ the Dock dict with our group (re)placed; apps=None takes the group out"""
    tiles = [t for t in dock.get("persistent-apps", []) if not _ours(t, folder)]
    if apps:
        chrome = [i + 1 for i, t in enumerate(tiles) if "/Google Chrome.app" in _url(t)]
        pos = max(chrome) if chrome else len(tiles)
        group = [_spacer()] + [{"GUID": _guid(), "tile-type": "file-tile", "tile-data": {
            "file-data": {"_CFURLString": "file://" + urllib.parse.quote(p.rstrip("/")) + "/", "_CFURLStringType": 15},
            "file-label": p.rstrip("/").rsplit("/", 1)[-1][:-4], "file-type": 41}} for p in apps] + [_spacer()]
        tiles = tiles[:pos] + group + tiles[pos:]
    return dict(dock, **{"persistent-apps": tiles})


def main(argv):
    path, folder, what = argv[1:4]
    with open(path, "rb") as fh:
        dock = plistlib.load(fh)
    if what == "--remove":
        apps = None
    else:
        with open(what, encoding="utf-8") as fh:
            apps = [ln.strip() for ln in fh if ln.strip()]
    with open(path, "wb") as fh:
        plistlib.dump(place(dock, folder, apps), fh)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

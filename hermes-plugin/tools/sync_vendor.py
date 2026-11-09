#!/usr/bin/env python3
"""sync_vendor — copy the owners the Hermes plugin runs from bin/ into hermes-plugin/rainbowomma/vendor/.

    python3 hermes-plugin/tools/sync_vendor.py            copy
    python3 hermes-plugin/tools/sync_vendor.py --check    exit 1 when a vendored file differs from bin/

The plugin is installed from the catalog as its own folder, so the code it runs has to live inside it. bin/ stays the
source: change a file there, run this, commit both. Left out on purpose: the menu bar, the web panel, the cursor proxy,
the doctor and the GitHub reporter (the plugin has its own status view and sends nothing anywhere).
"""
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN, VENDOR = ROOT / "bin", ROOT / "hermes-plugin" / "rainbowomma" / "vendor"
FILES = ["agent-office.py", "auth-owner.py", "browser-owner.py", "cdp-broker.py", "port-owner.py", "proc-owner.py",
         "screen-owner.py", "sim-owner.py", "rainbow_help.py", "rainbow_i18n.py", "rainbow_next.py", "rainbow_presence.py",
         "rainbow_receipts.py", "rainbow_tabs.py", "rainbowomma-approve.py", "rainbowomma-clip.py", "rainbowomma-guard.py",
         "rainbowomma-pause.py", "theme-frame.js"]


def main(argv):
    check = "--check" in argv
    VENDOR.mkdir(parents=True, exist_ok=True)
    stale = [f for f in FILES if not (VENDOR / f).exists() or not filecmp.cmp(BIN / f, VENDOR / f, shallow=False)]
    extra = sorted(p.name for p in VENDOR.iterdir() if p.is_file() and p.name not in FILES)
    if check:
        for f in stale:
            print(f"differs from bin/: {f}")
        for f in extra:
            print(f"not in the list: {f}")
        return 1 if stale or extra else 0
    for f in stale:
        shutil.copy2(BIN / f, VENDOR / f)
        print(f"copied {f}")
    for f in extra:
        (VENDOR / f).unlink()
        print(f"removed {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

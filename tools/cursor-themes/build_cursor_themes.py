#!/usr/bin/env python3
"""build_cursor_themes.py — each agent's CUA cursor in its color.

Copies Cua Driver's default cursor theme source (cua.default.lottie, MIT — see third_party/NOTICE-cua.md), swaps its one
base color for each agent's color from browsers.json, and gives every theme its own id (com.rainbowomma.cursor.<agent>).

    python3 build_cursor_themes.py [--registry ~/bin/browsers.json] [--out DIR] [--install] [--only AGENT ...]

validate → build → (install) run through the real `cua-driver cursor-theme`, so the driver checks every theme.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "cua.default.lottie"
CUA = "/Applications/CuaDriver.app/Contents/MacOS/cua-driver"
BASE = (0.369, 0.753, 0.91)          # Cua blue in the default source


def rgb01(hex_rgb: str) -> list:
    v = int(hex_rgb.lstrip("#"), 16)
    return [round(((v >> 16) & 255) / 255, 4), round(((v >> 8) & 255) / 255, 4), round((v & 255) / 255, 4)]


def recolor(obj, to):
    n = 0
    if isinstance(obj, dict):
        if obj.get("ty") in ("fl", "st") and isinstance(obj.get("c"), dict):
            k = obj["c"].get("k")
            if isinstance(k, list) and len(k) >= 3 and not isinstance(k[0], dict) and all(abs(k[i] - BASE[i]) < 0.01 for i in range(3)):
                obj["c"]["k"] = to + list(k[3:])
                n += 1
        for v in obj.values():
            n += recolor(v, to)
    elif isinstance(obj, list):
        for v in obj:
            n += recolor(v, to)
    return n


def theme_id(agent: str) -> str:
    return f"com.rainbowomma.cursor.{agent}"


def make(agent: str, label: str, color: str, out: Path) -> tuple[Path, int]:
    to = rgb01(color)
    buf, swapped = io.BytesIO(), 0
    with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("a/") and info.filename.endswith(".json"):
                j = json.loads(data)
                swapped += recolor(j, to)
                data = json.dumps(j, separators=(",", ":")).encode()
            elif info.filename == "cua/theme.json":
                j = json.loads(data)
                j.update({"id": theme_id(agent), "name": f"RainbowOMMA — {label}", "version": "1.0.0", "author": "RainbowOMMA (from Cua Default)"})
                data = json.dumps(j, separators=(",", ":"), ensure_ascii=False).encode()
            zout.writestr(info.filename, data)
    p = out / f"{agent}.lottie"
    p.write_bytes(buf.getvalue())
    return p, swapped


def run(*args):
    r = subprocess.run([CUA, "cursor-theme", *args], capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(Path.home() / "bin" / "browsers.json"))
    ap.add_argument("--out", default=str(Path.home() / ".rainbowomma" / "cursor-themes"))
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    out = Path(os.path.expanduser(a.out)); out.mkdir(parents=True, exist_ok=True)
    agents = json.loads(Path(os.path.expanduser(a.registry)).read_text(encoding="utf-8"))["agents"]
    report = {}
    for name, row in agents.items():
        if a.only and name not in a.only:
            continue
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,30}", name):        # it becomes a file name under --out
            report[name] = {"status": "invalid", "why": "not an agent name (a-z, 0-9, -)"}; continue
        src, swapped = make(name, row.get("label", name), row["color"], out)
        code, msg = run("validate", str(src))
        if code != 0:
            report[name] = {"status": "invalid", "why": msg[-300:]}; continue
        built = out / f"{name}.cua-theme"
        code, msg = run("build", str(src), "--output", str(built))
        if code != 0:
            report[name] = {"status": "build-failed", "why": msg[-300:]}; continue
        res = {"status": "built", "theme_id": theme_id(name), "color": row["color"], "swapped": swapped, "file": str(built)}
        if a.install:
            code, msg = run("install", str(built))
            res["status"] = "installed" if code == 0 else "install-failed"
            if code != 0:
                res["why"] = msg[-300:]
        report[name] = res
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if all(v["status"] in ("built", "installed") for v in report.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/check_drift.py — FW(XBMヘッダ) と PC(inkart.js) のアート同期チェック.

背景: 実機の表示は src/display/art/*.h のXBM、PCミラーは pc-companion/inkart.js の
フレームを使う。inkart.js は tools/make_artjs.cjs が .h から自動生成するが、
生成忘れ・手編集・退避コピー等で静かにズレると「PCと実機で絵が違う」事故になる
(これまでに何度も発生)。このツールはCI/手元で1コマンド検証する。

使い方:
  python tools/check_drift.py            # 検査 (差分があれば exit 1)
  python tools/check_drift.py --regen    # 差分があれば make_artjs で再生成して再検査
"""
from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "src", "display", "art")
JS = os.path.join(ROOT, "pc-companion", "inkart.js")
# make_artjs.cjs が削除するレガシー素体 (species別 art_ink_m*.h を使うため)
LEGACY = {"ink_idle", "ink_happy", "ink_eat", "ink_sleep", "ink_sad"}


def parse_headers() -> dict:
    """art_*.h (art_parts.h除く) の static const unsigned char NAME_xbm[1152] を回収"""
    frames = {}
    for fn in sorted(os.listdir(ART)):
        if not re.match(r"^art_.*\.h$", fn) or fn in ("art_parts.h", "art_sheet_gear.h", "art_sheet_hud.h"):
            continue  # parts/sheetは別形式 (bmp+mask+anchors) で後段が検査する
        src = open(os.path.join(ART, fn), encoding="utf-8", errors="replace").read()
        m = re.search(r"static const unsigned char (\w+)_xbm\[(\d+)\][\s\S]*?PROGMEM\s*=\s*\{([\s\S]*?)\};", src)
        if not m:
            print(f"[warn] no xbm in {fn}")
            continue
        name, size = m.group(1), int(m.group(2))
        b = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(3)))
        if len(b) != size:
            print(f"[FAIL] {fn}: byte count {len(b)} != declared {size}")
        frames[name] = b.hex()
    for k in list(frames):
        if k in LEGACY:
            del frames[k]
    return frames


def parse_js() -> dict:
    src = open(JS, encoding="utf-8").read()
    frames = {}
    for m in re.finditer(r'"([a-z0-9_]+)"\s*:\s*"([0-9a-fA-F]+)"', src):
        if m.group(1) in ("bmp", "mask"):  # parts配列側のキーは除外
            continue
        if len(m.group(2)) == 2304:  # 1152B=96x96 XBMのみ (sheet icons等は対象外)
            frames[m.group(1)] = m.group(2).lower()
    return frames


def parse_parts_headers() -> list:
    """art_parts.h の PART_ROWS を (gear,w,h,bmp_hex,mask_hex) で返す"""
    src = open(os.path.join(ART, "art_parts.h"), encoding="utf-8", errors="replace").read()
    syms = {}
    for m in re.finditer(r"static const uint8_t (\w+)\[\] PROGMEM = \{([\s\S]*?)\};", src):
        syms[m.group(1)] = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(2))).hex()
    dims = {}
    for m in re.finditer(r"(?:#define|static const uint8_t)\s+(PART_\w+_[WH])\b[^0-9]*(\d+)", src):
        dims[m.group(1)] = int(m.group(2))
    rows = re.search(r"static constexpr PartRow PART_ROWS\[\] = \{([\s\S]*?)\n\};", src)
    if not rows:
        return []
    out = []
    for row in re.finditer(r"\{\s*(\d+),\s*(\w+),\s*(\w+),\s*(PART_\w+_W),\s*(PART_\w+_H),", rows.group(1)):
        gear = int(row.group(1))
        bmp_hex = syms.get(row.group(2), "")
        mask_hex = None if row.group(3) == "nullptr" else syms.get(row.group(3), "")
        out.append((gear, dims.get(row.group(4), 0), dims.get(row.group(5), 0), bmp_hex, mask_hex))
    return out


def parse_js_parts() -> list:
    src = open(JS, encoding="utf-8").read()
    block = re.search(r'"parts":\[(.*)\]\};', src, re.S)
    if not block:
        return []
    out = []
    for m in re.finditer(r'\{"gear":(\d+),"w":(\d+),"h":(\d+),"bmp":"([0-9a-f]*)","mask":(null|"[0-9a-f]*")', block.group(1)):
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4),
                    None if m.group(5) == "null" else m.group(5).strip('"')))
    return out


def regen() -> None:
    node = "node"
    script = os.path.join(ROOT, "tools", "make_artjs.cjs")
    subprocess.run([node, script], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true", help="差分時に inkart.js を再生成して再検査")
    a = ap.parse_args()

    fw = parse_headers()
    js = parse_js()
    bad = []
    for name in sorted(set(fw) | set(js)):
        if name not in js:
            bad.append(f"missing in inkart.js: {name}")
        elif name not in fw:
            bad.append(f"stale in inkart.js (not in art/): {name}")
        elif fw[name] != js[name]:
            bad.append(f"BYTES DIFFER: {name} (fw {len(fw[name])//2}B / js {len(js[name])//2}B)")
    fw_parts = parse_parts_headers()
    js_parts = parse_js_parts()
    if len(fw_parts) != len(js_parts):
        bad.append(f"parts row count: fw {len(fw_parts)} vs js {len(js_parts)}")
    else:
        for i, (p, q) in enumerate(zip(fw_parts, js_parts)):
            if p[:4] != q[:4] or (p[4] or "") != (q[4] or ""):
                bad.append(f"parts row {i} differ: gear{p[0]} {p[1]}x{p[2]}")

    print(f"== art drift check ==  fw frames={len(fw)}  js frames={len(js)}  parts={len(fw_parts)}")
    if not bad:
        print("OK: FW(XBM) と PC(inkart.js) は完全一致")
        return 0
    for b in bad[:40]:
        print(" - " + b)
    if len(bad) > 40:
        print(f" ... 他 {len(bad)-40} 件")
    if a.regen:
        print("-- regenerating inkart.js (node tools/make_artjs.cjs) --")
        regen()
        return main()
    print(f"NG: {len(bad)} 件のズレ (--regen で自動修復)")
    return 1


if __name__ == "__main__":
    sys.exit(main())

# assets/parts — シートマスタ

純2値 (黒 #000000 / 白 #FFFFFF のみ) のピクセルアート・スプライトシート置き場。
グレー・アンチエイリアス・グラデーション禁止 (1-bit E-Ink直結のため)。

| シート | 構成 | 用途 |
|---|---|---|
| `sheet_gear.png` | 1024x1024, 2x2 | ギアID 0/4/8/11 (まる水滴・しま縞・うず渦・ほし星) |
| `sheet_hud.png` | 1024x256, 1x4 | HP/SAT/EN/HA ステータスアイコン |

セル内訳 (左上起点):

- gear: TL=ID11ほし / TR=ID8うず / BL=ID0まる / BR=ID4しま
- hud: 左から HP心・SAT肉・EN雷・HA笑顔

## 再生成

```bash
python tools/gen_sheets.py          # src/display/art_sheet_*.h を生成
python tools/gen_sheets.py --check  # ASCII確認のみ
```

- gear: 24x24 bmp+mask (maskは水滴ハイライト等の内側白抜き再現用シルエット)
- hud: 16x16 bmpのみ (白背景に黒点描画)
- 配置は `src/display/screen.h` の `gear()` / `draw()` と1:1対応。
  PCミラーは `pc-companion/virtual_eink.py` と `voxel_art.py` が同座標で再現する。

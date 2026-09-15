# pc-companion/virtual_eink.py
"""
InkLife バーチャル E-Ink レンダラー (296x128 ピクセル完全再現)
ファームウェア (src/display/screen.h) の E-Ink 画面レイアウト・フォント・
標本窓・プログレスバー・現象盤ミニ窓・ログ表示をピクセル単位で再現し、
Raylib テクスチャとして画面上にリアルタイム描画します。
"""

import math
from typing import List, Tuple
import pyray as rl
from inkparser import CreatureState, base_morph_of, fuse_shown_gears, normalize_action, sleep_head_off, zone_of
from voxel_art import ART_DB

EPD_W = 296
EPD_H = 128

# レトロな電子ペーパーの紙色とインク色
COLOR_PAPER = rl.Color(238, 240, 235, 255)  # ほんのり温かみのある電子ペーパー白
COLOR_INK   = rl.Color(20, 22, 26, 255)     # くっきりとした電子インク黒
COLOR_FRAME = rl.Color(45, 52, 64, 255)     # ベゼルフレーム色

class VirtualEInk:
    def __init__(self):
        # 296x128 の 1bit ピクセルバッファ (True=黒, False=白)
        self.buffer = [[False for _ in range(EPD_W)] for _ in range(EPD_H)]
        # Raylib テクスチャ
        img = rl.gen_image_color(EPD_W, EPD_H, COLOR_PAPER)
        self.texture = rl.load_texture_from_image(img)
        rl.unload_image(img)
        self.pixels_rgba = bytearray(EPD_W * EPD_H * 4)

        # ログバッファ (最新2件)
        self.logs: List[str] = ["SYSTEM READY", "WAITING FOR SYNC..."]
        self.last_age: int = 0

    def push_log(self, text: str, age_sec: int):
        h = min(age_sec // 3600, 99)
        m = (age_sec // 60) % 60
        s = age_sec % 60
        line = f">T+{h:02d}:{m:02d}:{s:02d} {text}"
        self.logs.insert(0, line)
        if len(self.logs) > 2:
            self.logs.pop()

    def clear(self):
        for y in range(EPD_H):
            for x in range(EPD_W):
                self.buffer[y][x] = False

    def draw_pixel(self, x: int, y: int, black: bool = True):
        if 0 <= x < EPD_W and 0 <= y < EPD_H:
            self.buffer[y][x] = black

    def draw_line(self, x0: int, y0: int, x1: int, y1: int):
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.draw_pixel(x0, y0, True)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def draw_rect(self, x: int, y: int, w: int, h: int):
        self.draw_line(x, y, x + w - 1, y)
        self.draw_line(x, y + h - 1, x + w - 1, y + h - 1)
        self.draw_line(x, y, x, y + h - 1)
        self.draw_line(x + w - 1, y, x + w - 1, y + h - 1)

    def fill_rect(self, x: int, y: int, w: int, h: int, black: bool = True):
        for cy in range(y, y + h):
            for cx in range(x, x + w):
                self.draw_pixel(cx, cy, black)

    def draw_pbar(self, x: int, y: int, w: int, val: int):
        """ステータスミニバー (高さ6px)"""
        self.draw_rect(x, y, w, 6)
        val = max(0, min(100, val))
        fw = int((w - 2) * val / 100)
        if fw > 0:
            self.fill_rect(x + 1, y + 1, fw, 4, True)

    def draw_text_simple(self, x: int, y: int, text: str):
        """組み込み 5x7 ビットマップフォント簡易描画 (英数字/記号)"""
        # Raylib テクスチャ更新後に DrawText で重ねるアプローチも可能だが、
        # E-Ink 完全再現のためにピクセル上にラスタライズ
        pass

    def render(self, state: CreatureState):
        """実機 screen.h の draw() ロジックを完全エミュレート"""
        self.clear()

        # 外枠
        self.draw_rect(0, 0, EPD_W, EPD_H)

        # 標本窓 L字ブラケット (4,16), (100,16), (4,112), (100,112)
        self.draw_line(4, 16, 12, 16);  self.draw_line(4, 16, 4, 24)
        self.draw_line(100, 16, 92, 16); self.draw_line(100, 16, 100, 24)
        self.draw_line(4, 112, 12, 112); self.draw_line(4, 112, 4, 104)
        self.draw_line(100, 112, 92, 112); self.draw_line(100, 112, 100, 104)

        # 縦区切り線
        self.draw_line(108, 4, 108, 124)

        # 96x96 キメラドット絵の描画 (標本窓の中央: x=5, y=16 付近)
        self._render_creature_art(state)

        # 右側ステータスバー群 (x=162〜232)
        tx_bar = 162
        self.draw_pbar(tx_bar, 19, 70, state.health)
        self.draw_pbar(tx_bar, 31, 70, 100 - state.hunger)
        self.draw_pbar(tx_bar, 43, 70, state.energy)
        self.draw_pbar(tx_bar, 55, 70, state.happiness)

        # 現象盤ミニ窓 (ACT行右側の 48x12 盤: x=240, y=60)。実盤面のみ (FIELDB同期前は空白)
        self.draw_rect(240, 60, 50, 14)
        self.fill_rect(241, 61, 48, 12, False)  # 白下地
        for fy in range(12):
            for fx in range(48):
                v = state.field_grid[fy][fx]
                if v == 1:
                    self.draw_pixel(241 + fx, 61 + fy, True)
                elif v == 2 and ((fx + fy) & 1) == 0:
                    self.draw_pixel(241 + fx, 61 + fy, True)

        # バッファをテクスチャへ転送
        self._update_texture()

    def _render_creature_art(self, state: CreatureState):
        """標本窓内にキメラの 2D ドット絵を描画 (idle12独立、動作5基幹)"""
        raw = state.species_id % 12
        mid = base_morph_of(state.species_id)
        frame_name = self._resolve_frame_name(raw, mid, state.action, state.mood)
        frame_bytes = ART_DB.get_frame_bytes(frame_name)
        if not frame_bytes or len(frame_bytes) < 1152:
            return

        # 成長サイズ: 64px〜96px (標本窓 ox=4, oy=16 に中央寄せ。FWと同一式)
        dst = min(96, 64 + state.age_sec // 270)
        ox = 4 + (96 - dst) // 2
        oy = 16 + (96 - dst) // 2

        # スケーリング転送
        for dy in range(dst):
            sy = (dy * 96) // dst
            row_idx = sy * 12
            for dx in range(dst):
                sx = (dx * 96) // dst
                byte = frame_bytes[row_idx + (sx >> 3)]
                if (byte >> (sx & 7)) & 1:
                    self.draw_pixel(ox + dx, oy + dy, True)

        # キメラパーツの追加 (睡眠時はHEAD装備だけ追従オフセット。FW sprite()と同一)
        asleep = (normalize_action(state.action) == "SLEEP" or state.mood == "SLEEPY")
        effective_gears = fuse_shown_gears(state.fuse, mid, raw)
        for gid in effective_gears:
            if gid in (0, 4, 8, 11):
                # 手続き型
                self._draw_gear_proc(ox, oy, dst, gid, state.happiness)
            else:
                for row in ART_DB.parts:
                    if row["gear"] != gid:
                        continue
                    anch = None
                    for a in row["anchors"]:
                        if a[0] == mid or a[0] == 255:
                            anch = a; break
                    if not anch:
                        continue
                    ax, ay = anch[1], anch[2]
                    if asleep and zone_of(gid) == 0:
                        dx, dy = sleep_head_off(mid)
                        ax, ay = ax + dx, ay + dy
                    pw, ph = row["w"], row["h"]
                    stride = (pw + 7) >> 3
                    bmp = row["bmp"]
                    msk = row.get("mask")
                    for py in range(ph):
                        sy = (ay + py) * dst // 96
                        for px in range(pw):
                            sx = (ax + px) * dst // 96
                            if msk and (msk[py * stride + (px >> 3)] >> (px & 7)) & 1:
                                self.draw_pixel(ox + sx, oy + sy, False)
                            if (bmp[py * stride + (px >> 3)] >> (px & 7)) & 1:
                                self.draw_pixel(ox + sx, oy + sy, True)
                    # breakしない: ペア物 (耳L/R・髭L/R) は同gearで2行ある

    def _draw_gear_proc(self, ox, oy, dst, gid, ha):
        SC = lambda v: (v * dst) // 96
        if gid == 0:  # まる (ハイライト水玉 5x5)
            for (bx, by) in ((14, 76), (78, 76)):
                self.fill_rect(ox + SC(bx), oy + SC(by), max(1, SC(5)), max(1, SC(5)), True)
        elif gid == 4:  # しま (トラ猫の縞 14x3)
            for (bx, by) in ((12, 70), (70, 70)):
                self.fill_rect(ox + SC(bx), oy + SC(by), max(1, SC(14)), max(1, SC(3)), True)
        elif gid == 8:  # うず (渦巻き r=3,6 outline。半径もSC変換)
            cx0, cy0 = SC(48), SC(66)
            for r in (3, 6):
                rs = max(1, SC(r))
                for dy in range(-rs, rs + 1):
                    for dx in range(-rs, rs + 1):
                        d2 = dx * dx + dy * dy
                        if (rs - 1) * (rs - 1) <= d2 <= rs * rs:
                            self.draw_pixel(ox + cx0 + dx, oy + cy0 + dy, True)
        elif gid == 11:  # ほし (四隅 9x3+3x9 plus)
            corners = [(14, 14), (82, 14), (14, 82), (82, 82)]
            n = min(4, 2 + ha * 2 // 100)
            for i in range(n):
                cx, cy = corners[i][0], corners[i][1]
                # firmware dot()そのまま: 位置・寸法ともSC変換
                self.fill_rect(ox + SC(cx - 4), oy + SC(cy - 1), max(1, SC(9)), max(1, SC(3)), True)
                self.fill_rect(ox + SC(cx - 1), oy + SC(cy - 4), max(1, SC(3)), max(1, SC(9)), True)

    def _resolve_frame_name(self, raw: int, mid: int, action: str, mood: str) -> str:
        # 全12形態 (0〜11) が専用アクション絵を完全保持 (FW表記ゆれ対応)
        act = normalize_action(action)
        if act == "SLEEP" or mood == "SLEEPY": return f"ink_m{raw:02d}_sleep"
        if act == "EAT": return f"ink_m{raw:02d}_eat"
        if act == "PLAY" or mood == "HAPPY": return f"ink_m{raw:02d}_happy"
        if mood in ("SAD", "SICK"): return f"ink_m{raw:02d}_sad"
        # P0 FW統一: COMMは全形態自前IDLE (実機はアンテナ波紋オーバーレイ)。旧raw==2 greet特例廃止
        return f"ink_m{raw:02d}_idle"

    def _update_texture(self):
        # RGBA バイト列の生成
        idx = 0
        pr, pg, pb, pa = COLOR_PAPER.r, COLOR_PAPER.g, COLOR_PAPER.b, COLOR_PAPER.a
        ir, ig, ib, ia = COLOR_INK.r, COLOR_INK.g, COLOR_INK.b, COLOR_INK.a

        for y in range(EPD_H):
            row = self.buffer[y]
            for x in range(EPD_W):
                if row[x]:
                    self.pixels_rgba[idx]     = ir
                    self.pixels_rgba[idx + 1] = ig
                    self.pixels_rgba[idx + 2] = ib
                    self.pixels_rgba[idx + 3] = ia
                else:
                    self.pixels_rgba[idx]     = pr
                    self.pixels_rgba[idx + 1] = pg
                    self.pixels_rgba[idx + 2] = pb
                    self.pixels_rgba[idx + 3] = pa
                idx += 4
        # pyray (CFFI) の void* ポインタへゼロコピーで変換して渡す
        cdata_pixels = rl.ffi.cast("void *", rl.ffi.from_buffer(self.pixels_rgba))
        rl.update_texture(self.texture, cdata_pixels)

    def draw_on_screen(self, dest_x: int, dest_y: int, scale: float, state: CreatureState):
        """画面上にベゼルフレームと高精細文字付きで描画"""
        dw = int(EPD_W * scale)
        dh = int(EPD_H * scale)

        # 外枠のベゼル (高級感のあるマットブラックケース)
        pad = 8
        rl.draw_rectangle_rounded(
            rl.Rectangle(dest_x - pad, dest_y - pad, dw + pad * 2, dh + pad * 2),
            0.08, 6, COLOR_FRAME
        )
        rl.draw_rectangle_rounded_lines(
            rl.Rectangle(dest_x - pad, dest_y - pad, dw + pad * 2, dh + pad * 2),
            0.08, 6, rl.Color(70, 80, 100, 255)
        )

        # E-Ink テクスチャの描画
        src_rec = rl.Rectangle(0, 0, EPD_W, EPD_H)
        dst_rec = rl.Rectangle(dest_x, dest_y, dw, dh)
        rl.draw_texture_pro(self.texture, src_rec, dst_rec, rl.Vector2(0, 0), 0.0, rl.WHITE)

        # HUD テキストを Raylib で鮮明にオーバーレイ描画
        S = scale
        tx = dest_x + int(114 * S)
        fs = int(10 * S)  # フォントサイズ

        hms = f"{min(state.age_sec // 3600, 99):02d}:{(state.age_sec // 60) % 60:02d}:{state.age_sec % 60:02d}"

        # 標本窓ラベル (実機 screen.h:565-566 と同一座標。T+は右上 x=236)
        rl.draw_text("SPECIMEN", dest_x + int(6 * S), dest_y + int(4 * S), fs, COLOR_INK)
        rl.draw_text(f"T+{hms}", dest_x + int(236 * S) - rl.measure_text(f"T+{hms}", fs), dest_y + int(4 * S), fs, COLOR_INK)
        rl.draw_text(f"G{state.generation:02d} {state.base_name}-{state.species_id%12:02d}",
                     dest_x + int(6 * S), dest_y + int(116 * S), fs, COLOR_INK)

        # 右側ステータス
        peers_cnt = len(state.peers)
        p_str = f" P{peers_cnt}" if peers_cnt > 0 else ""
        rl.draw_text(f"ID {state.device_id:08X} G{state.generation:02d}{p_str}", tx, dest_y + int(4 * S), fs, COLOR_INK)
        rl.draw_text(f"HP  {state.health:03d}", tx, dest_y + int(16 * S), fs, COLOR_INK)
        rl.draw_text(f"SAT {100 - state.hunger:03d}", tx, dest_y + int(28 * S), fs, COLOR_INK)
        rl.draw_text(f"EN  {state.energy:03d}", tx, dest_y + int(40 * S), fs, COLOR_INK)
        rl.draw_text(f"HA  {state.happiness:03d}", tx, dest_y + int(52 * S), fs, COLOR_INK)
        rl.draw_text(f"ACT {state.action}", tx, dest_y + int(64 * S), fs, COLOR_INK)
        rl.draw_text(f"FLD {state.field_activity:3d}", dest_x + int(200 * S), dest_y + int(64 * S), fs, COLOR_INK)

        # 形質コード + 状態コード (FW traitLabel準拠: 最大形質1項目) + 概日
        m_val, m_code = state.curiosity, "CUR"
        if state.sociability > m_val: m_val, m_code = state.sociability, "SOC"
        if state.intelligence > m_val: m_val, m_code = state.intelligence, "INT"
        if state.aggression > m_val: m_val, m_code = state.aggression, "AGG"
        trt = f"{m_code} {m_val:03d}"
        state_code = {"HAPPY": "OPTIMAL", "SAD": "STRESSED", "SLEEPY": "REST",
                      "SICK": "CRITICAL"}.get(state.mood, "NOMINAL")
        rl.draw_text(f"ST {state_code} TRT {trt}", tx, dest_y + int(76 * S), fs, COLOR_INK)
        is_night = ((state.age_sec % 86400) >= 57600)
        day_str = "NGT" if is_night else "DAY"
        rl.draw_text(f"STG {state.stage_name} {hms} {day_str}", tx, dest_y + int(88 * S), fs, COLOR_INK)

        # イベントログ 2行
        log0 = self.logs[0] if len(self.logs) > 0 else ""
        log1 = self.logs[1] if len(self.logs) > 1 else ""
        rl.draw_text(log0[:26], tx, dest_y + int(101 * S), int(9 * S), COLOR_INK)
        rl.draw_text(log1[:26], tx, dest_y + int(112 * S), int(9 * S), COLOR_INK)

    def unload(self):
        rl.unload_texture(self.texture)

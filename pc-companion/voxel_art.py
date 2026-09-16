# pc-companion/voxel_art.py
"""
InkLife 3D Voxel 描画 & キメラ合成エンジン (高精細ソリッド・ボクセルレリーフ)
=======================================================================
2D ドット絵 (96x96 XBM) を解析し、外側 Flood-Fill によるボディ肉付け、
ボリューメトリックな厚み付け、インクラインのエンボス加工、
およびキメラ遺伝パーツの境界合成を行うことで、
愛着の湧くリッチな 3D ソリッド・ボクセルフィギュアを生成します。
"""

import os
import re
import json
import math
from collections import deque
from typing import Dict, List, Tuple, Optional
import pyray as rl
from inkparser import ANCHOR_BASE_MAP, fuse_shown_gears, zone_of, normalize_action, sleep_head_off

# 形態ごとのベースカラーパレット (本体基本色, ハイライト色, 影色, インクライン色)
MORPH_COLORS = {
    0: (rl.Color(64, 205, 225, 255),  rl.Color(160, 245, 255, 255), rl.Color(30, 130, 160, 255), rl.Color(18, 48, 56, 255)),   # スライム: マリンシアン
    1: (rl.Color(48, 195, 140, 255),  rl.Color(120, 235, 180, 255), rl.Color(24, 110, 75, 255),  rl.Color(16, 45, 34, 255)),   # ドラゴン: 翡翠エメラルド
    2: (rl.Color(225, 160, 85, 255),  rl.Color(255, 215, 150, 255), rl.Color(160, 100, 45, 255), rl.Color(55, 32, 20, 255)),   # 柴犬: キャラメルゴールド
    3: (rl.Color(110, 95, 210, 255),  rl.Color(175, 165, 255, 255), rl.Color(70, 60, 160, 255),  rl.Color(30, 28, 70, 255)),   # とげ: スパインパープル
    4: (rl.Color(240, 140, 90, 255),  rl.Color(255, 195, 160, 255), rl.Color(170, 85, 50, 255),  rl.Color(56, 28, 18, 255)),   # トラ猫: コーラルオレンジ
    5: (rl.Color(255, 225, 95, 255),  rl.Color(255, 240, 160, 255), rl.Color(190, 165, 50, 255), rl.Color(70, 60, 22, 255)),   # わっか: ハローゴールド
    6: (rl.Color(95, 185, 235, 255),  rl.Color(165, 225, 255, 255), rl.Color(55, 120, 170, 255), rl.Color(24, 52, 75, 255)),   # ひれ: フィンブルー
    7: (rl.Color(110, 205, 65, 255),  rl.Color(180, 245, 120, 255), rl.Color(65, 130, 30, 255),  rl.Color(25, 52, 16, 255)),   # カエル: フレッシュライム
    8: (rl.Color(170, 120, 220, 255), rl.Color(210, 175, 255, 255), rl.Color(110, 75, 170, 255), rl.Color(48, 32, 74, 255)),   # うず: スパイラル
    9: (rl.Color(190, 145, 95, 255),  rl.Color(235, 200, 160, 255), rl.Color(135, 95, 55, 255),  rl.Color(56, 38, 22, 255)),   # あし: レッグ
    10: (rl.Color(210, 210, 215, 255), rl.Color(245, 245, 250, 255), rl.Color(145, 145, 155, 255), rl.Color(62, 62, 68, 255)),  # ひげ: ウィスカー
    11: (rl.Color(255, 240, 110, 255), rl.Color(255, 250, 175, 255), rl.Color(190, 175, 60, 255), rl.Color(72, 66, 24, 255)),  # ほし: スター
}

# キメラ遺伝パーツの固有カラー (角、耳、王冠、トゲなど部位ごとのアクセントカラー)
GEAR_COLORS = {
    0: rl.Color(140, 240, 255, 255),  # まる: 水滴ハイライト
    1: rl.Color(80, 225, 240, 255),   # つの: クリスタルシアン
    2: rl.Color(245, 185, 90, 255),   # みみ: 柴犬ゴールド
    3: rl.Color(245, 75, 75, 255),    # とげ: クリムゾンレッド
    4: rl.Color(60, 45, 40, 255),     # しま: トラ縞ダーク
    5: rl.Color(255, 220, 100, 255),  # わっか: エンジェルリング
    6: rl.Color(70, 200, 240, 255),   # ひれ: アクアブルー
    7: rl.Color(255, 215, 0, 255),    # おうかん: ピュアゴールド 👑
    8: rl.Color(180, 110, 240, 255),  # うず: ミスティックパープル
    9: rl.Color(50, 160, 110, 255),   # あし: ドラゴンクロー
    10: rl.Color(240, 240, 240, 255), # ひげ: ピュアホワイト
    11: rl.Color(255, 235, 80, 255),  # ほし: スターゴールド ★
}

class Voxel:
    __slots__ = ('x', 'y', 'z', 'w', 'h', 'd', 'color', 'gear_id')
    def __init__(self, x: float, y: float, z: float, w: float, h: float, d: float, color: rl.Color, gear_id: int = -1):
        self.x = x
        self.y = y
        self.z = z
        self.w = w
        self.h = h
        self.d = d
        self.color = color
        self.gear_id = gear_id

class ArtDataManager:
    def __init__(self):
        self.frames: Dict[str, bytes] = {}
        self.parts: List[dict] = []
        self.sheet_gear: Dict[str, dict] = {}  # art_sheet_gear.h (24x24 bmp+mask)
        self.sheet_hud: Dict[str, dict] = {}   # art_sheet_hud.h (16x16 bmp)
        self._load()

    def _load_sheet(self, fname: str) -> Dict[str, dict]:
        """gen_sheets.py生成ヘッダ (VAR_W/H + var_bmp/var_mask) を読む。"""
        disp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "src", "display", "art")
        out: Dict[str, dict] = {}
        try:
            with open(os.path.join(disp, fname), "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"[VoxelArt] WARNING: {fname} load failed ({e})")
            return out
        dims = {}
        for m in re.finditer(r"#define\s+(\w+_[WH])\s+(\d+)", text):
            dims[m.group(1)] = int(m.group(2))
        for m in re.finditer(
                r"static const unsigned char (\w+)_bmp\[(\d+)\][\s\S]*?PROGMEM\s*=\s*\{([\s\S]*?)\};",
                text):
            var, _decl, body = m.group(1), m.group(2), m.group(3)
            bmp = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", body))
            mm = re.search(r"static const unsigned char " + re.escape(var) +
                           r"_mask\[(\d+)\][\s\S]*?PROGMEM\s*=\s*\{([\s\S]*?)\};", text)
            mask = (bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", mm.group(2)))
                    if mm else None)
            w = dims.get(var.upper() + "_W", 0)
            h = dims.get(var.upper() + "_H", 0)
            if w > 0 and len(bmp) == ((w + 7) // 8) * h:
                out[var] = {"w": w, "h": h, "bmp": bmp, "mask": mask}
            else:
                print(f"[VoxelArt] WARNING: {fname}:{var} size mismatch")
        return out

    def _load(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        js_path = os.path.join(base_dir, "inkart.js")
        try:
            with open(js_path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"var InkArt = ({.*?});\s*if", text, re.DOTALL)
            if not m:
                raise ValueError("InkArt block not found")
            data = json.loads(m.group(1))
            for name, hex_str in data.get("frames", {}).items():
                self.frames[name] = bytes.fromhex(hex_str)
            for row in data.get("parts", []):
                self.parts.append({
                    "gear": row["gear"],
                    "w": row["w"],
                    "h": row["h"],
                    "bmp": bytes.fromhex(row["bmp"]),
                    "mask": bytes.fromhex(row["mask"]) if row.get("mask") else None,
                    "anchors": row["anchors"]
                })
            print(f"[VoxelArt] Loaded {len(self.frames)} frames and {len(self.parts)} parts from inkart.js")
            self.sheet_gear = self._load_sheet("art_sheet_gear.h")
            self.sheet_hud = self._load_sheet("art_sheet_hud.h")
            print(f"[VoxelArt] Loaded {len(self.sheet_gear)} sheet-gear and "
                  f"{len(self.sheet_hud)} sheet-hud icons")
            return
        except Exception as e:
            print(f"[VoxelArt] WARNING: inkart.js load failed ({e}), fallback to placeholder")

    def get_frame_bytes(self, name: str) -> Optional[bytes]:
        hit = self.frames.get(name)
        if hit is None:
            # 同期ずれの隠蔽防止: フォールバック時は警告して検出可能にする
            print(f"[VoxelArt] WARNING: frame '{name}' missing, fallback to ink_m01_idle")
            hit = self.frames.get("ink_m01_idle")
        return hit

# グローバルアートデータ
ART_DB = ArtDataManager()

class ChimeraVoxelModel:
    """96x96 キメラアートを立体ボクセル化したソリッド 3D モデル"""
    def __init__(self):
        self.voxels: List[Voxel] = []
        self.stars: List[Tuple[float, float, float, float]] = []  # (x, y, z, phase)
        self.cache_key: str = ""
        self.base_color: rl.Color = rl.Color(48, 195, 140, 255)

    def build(self, species_id: int, action: str, mood: str, fuse: List[int], happiness: int = 70, age_sec: int = 999999):
        raw = species_id % 12
        mid = ANCHOR_BASE_MAP[raw]
        # 早期形態 (タマゴ/幼生) は純血固定でパーツなし (FW sprite()早期returnと同一)
        effective_gears = [] if age_sec < 7200 else fuse_shown_gears(fuse, mid, raw)
        # FW表記ゆれ対策: 正規化後の行動で鍵を作り、同一絵の無駄再ビルドを防ぐ
        act = normalize_action(action)
        early = 0 if age_sec >= 7200 else (1 if age_sec >= 600 else 2 + age_sec // 200)
        key = f"{species_id}_{mid}_{act}_{mood}_{','.join(map(str, effective_gears))}_{happiness // 25}_{early}"
        if key == self.cache_key and self.voxels:
            return

        self.cache_key = key
        self.voxels.clear()
        self.stars.clear()

        # 1. フレーム名の決定 (idleは12独立、動作は5基幹にフォールバック)
        frame_name = self._resolve_frame_name(raw, mid, action, mood, age_sec)
        frame_bytes = ART_DB.get_frame_bytes(frame_name)
        if not frame_bytes or len(frame_bytes) < 1152:
            return

        # 2. 96x96 グリッドの構築 (0=背景, 1=黒インク, 2=キメラパーツ)
        grid = [[0 for _ in range(96)] for _ in range(96)]
        gear_grid = [[-1 for _ in range(96)] for _ in range(96)]
        cleared = set()  # マスク消去済み画素 (肉体判定から除外。FWの白抜き相当)

        # 黒インクピクセルの展開
        for y in range(96):
            row_idx = y * 12
            for x in range(96):
                byte = frame_bytes[row_idx + (x >> 3)]
                if (byte >> (x & 7)) & 1:
                    grid[y][x] = 1

        # 3. 外側 Flood-Fill による体内(Body)の識別
        # 外枠の四辺からBFSを行い、黒インク壁に遮られて到達できない白ピクセルを「肉体」として判定
        visited = [[False]*96 for _ in range(96)]
        q = deque()
        for x in range(96):
            if not grid[0][x]: q.append((x, 0)); visited[0][x] = True
            if not grid[95][x]: q.append((x, 95)); visited[95][x] = True
        for y in range(96):
            if not grid[y][0] and not visited[y][0]: q.append((0, y)); visited[y][0] = True
            if not grid[y][95] and not visited[y][95]: q.append((95, y)); visited[y][95] = True

        while q:
            cx, cy = q.popleft()
            for dx, dy in ((-1,0), (1,0), (0,-1), (0,1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < 96 and 0 <= ny < 96 and not visited[ny][nx] and grid[ny][nx] == 0:
                    visited[ny][nx] = True
                    q.append((nx, ny))

        # 4. キメラパーツの展開 & マスク合成
        # 睡眠時はHEAD装備だけ追従オフセット (FW sprite()と同一条件)
        asleep = (normalize_action(action) == "SLEEP" or mood == "SLEEPY")
        for gid in effective_gears:
            if gid in (0, 4, 8, 11):
                self._apply_procedural_gear(grid, gear_grid, gid, happiness)
            else:
                self._apply_bitmap_gear(grid, gear_grid, gid, mid, asleep, cleared)

        # 5. 3D ボクセル (立体レリーフ) の生成
        base_c, high_c, shad_c, line_c = MORPH_COLORS.get(raw, MORPH_COLORS.get(mid, MORPH_COLORS[1]))
        self.base_color = base_c
        voxel_scale = 1.9 / 96.0  # 全体サイズ約 1.9 ユニット
        box_wh = voxel_scale * 1.04

        for y in range(96):
            wy = (48.0 - y) * voxel_scale
            for x in range(96):
                val = grid[y][x]
                is_ink = (val == 1)
                is_part = (val == 2)
                is_body = (not visited[y][x] and val == 0 and (x, y) not in cleared)

                if not is_ink and not is_part and not is_body:
                    continue

                wx = (x - 48.0) * voxel_scale
                gid = gear_grid[y][x]

                # 体のふっくらとした本格的3D厚み (中心が厚く、外周が薄い球状・楕円体ドーム構造)
                dx_norm = (x - 48.0) / 40.0
                dy_norm = (y - 50.0) / 42.0
                dist_c = math.sqrt(dx_norm * dx_norm + dy_norm * dy_norm)
                base_thick = max(0.16, 0.58 * math.cos(min(1.0, dist_c) * math.pi * 0.46))

                if is_part and gid >= 0:
                    # キメラパーツ (角、耳、トゲ、王冠など): 前面や背面に立体的に突出
                    part_c = GEAR_COLORS.get(gid, high_c)
                    z_offset = self._gear_z_depth(gid) * 1.8
                    thick = base_thick * 0.95 + 0.08
                    self.voxels.append(Voxel(wx, wy, z_offset, box_wh, box_wh, thick, part_c, gid))
                elif is_ink:
                    # 黒インク線 (輪郭・目・口・鱗・模様): 表面に少し浮き彫り (エンボス)
                    thick = base_thick + 0.035
                    self.voxels.append(Voxel(wx, wy, 0.02, box_wh, box_wh, thick, line_c, -1))
                else:
                    # 体内 (ソリッドな肉体): 形態ごとのベースカラー
                    self.voxels.append(Voxel(wx, wy, 0.0, box_wh, box_wh, base_thick, base_c, -1))

        # ほし (gid=11) がある場合は浮遊星屑オーラを登録
        if 11 in effective_gears:
            for i in range(8):
                ang = i * (math.pi * 2 / 8)
                self.stars.append((math.cos(ang) * 0.9, 0.8 + (i % 3) * 0.3, math.sin(ang) * 0.9, i * 0.8))

    def _apply_bitmap_gear(self, grid: List[List[int]], gear_grid: List[List[int]], gid: int, mid: int, asleep: bool = False, cleared=None):
        # FW drawPartと同一: マスク消去 (肉体のみ。線画はcleared記録で肉体化を防ぐ) → 黒描画
        if cleared is None:
            cleared = set()
        for row in ART_DB.parts:
            if row["gear"] != gid:
                continue
            target_anch = None
            for anch in row["anchors"]:
                if anch[0] == mid or anch[0] == 255:
                    target_anch = anch
                    break
            if not target_anch:
                continue

            ax, ay = target_anch[1], target_anch[2]
            if asleep and zone_of(gid) == 0:
                dx, dy = sleep_head_off(mid)
                ax, ay = ax + dx, ay + dy
            pw, ph = row["w"], row["h"]
            stride = (pw + 7) >> 3
            bmp = row["bmp"]
            msk = row.get("mask")
            for py in range(ph):
                sy = ay + py
                if sy < 0 or sy >= 96:
                    continue
                for px in range(pw):
                    sx = ax + px
                    if sx < 0 or sx >= 96:
                        continue
                    if msk and (msk[py * stride + (px >> 3)] >> (px & 7)) & 1:
                        if grid[sy][sx] == 1:  # 線画のみ消去 (肉体は温存)
                            grid[sy][sx] = 0
                            cleared.add((sx, sy))
                    if (bmp[py * stride + (px >> 3)] >> (px & 7)) & 1:
                        grid[sy][sx] = 2
                        gear_grid[sy][sx] = gid
            # breakしない: ペア物 (耳L/R・髭L/R) は同gearで2行ある

    def _blit_sheet_gear(self, grid: List[List[int]], gear_grid: List[List[int]],
                           var: str, ax: int, ay: int, gid: int) -> bool:
        """シート型ギアの転写 (FW screen.h gear() と同一配置。穴は素体色のまま)。"""
        icon = ART_DB.sheet_gear.get(var)
        if not icon:
            return False
        w, h, bmp = icon["w"], icon["h"], icon["bmp"]
        stride = (w + 7) >> 3
        for py in range(h):
            for px in range(w):
                if (bmp[py * stride + (px >> 3)] >> (px & 7)) & 1:
                    x, y = ax + px, ay + py
                    if 0 <= y < 96 and 0 <= x < 96:
                        grid[y][x] = 2
                        gear_grid[y][x] = gid
        return True

    def _apply_procedural_gear(self, grid: List[List[int]], gear_grid: List[List[int]], gid: int, happiness: int):
        # シート型 (FW screen.h gear() と同一座標。art_sheet_gear.h駆動。
        # ヘッダ不在時のみ旧手続き型へフォールバック)
        if gid == 0:  # まる (シート水滴×2)
            if "gear0_drop" in ART_DB.sheet_gear:
                self._blit_sheet_gear(grid, gear_grid, "gear0_drop", 6, 64, gid)
                self._blit_sheet_gear(grid, gear_grid, "gear0_drop", 66, 64, gid)
                return
            for (ox, oy) in ((14, 76), (78, 76)):  # フォールバック旧水玉
                for dy in range(5):
                    for dx in range(5):
                        grid[oy + dy][ox + dx] = 2; gear_grid[oy + dy][ox + dx] = gid
            return
        if gid == 4:  # しま (シート縞×2)
            if "gear4_stripe" in ART_DB.sheet_gear:
                self._blit_sheet_gear(grid, gear_grid, "gear4_stripe", 4, 66, gid)
                self._blit_sheet_gear(grid, gear_grid, "gear4_stripe", 68, 66, gid)
                return
            for y_off in (70, 71, 72):  # フォールバック旧縞
                for x in list(range(12, 26)) + list(range(70, 84)):
                    grid[y_off][x] = 2; gear_grid[y_off][x] = gid
            return
        if gid == 8:  # うず (シート渦巻き)
            if self._blit_sheet_gear(grid, gear_grid, "gear8_swirl", 36, 54, gid):
                return
            self._draw_circle(grid, gear_grid, 48, 66, 3, gid, hollow=True)  # フォールバック旧渦
            self._draw_circle(grid, gear_grid, 48, 66, 6, gid, hollow=True)
            return
        if gid == 11:  # ほし (シート星屑。四隅、数は幸福度で2〜4)
            n = min(4, 2 + int(happiness * 2 / 100))
            if "gear11_star" in ART_DB.sheet_gear:
                for cx, cy in [(0, 0), (72, 0), (0, 72), (72, 72)][:n]:
                    self._blit_sheet_gear(grid, gear_grid, "gear11_star", cx, cy, gid)
                return
            corners = [(14, 14), (82, 14), (14, 82), (82, 82)]  # フォールバック旧星屑
            for i in range(n):
                cx, cy = corners[i]
                for dy in range(3):
                    for dx in range(9):
                        grid[cy + dy - 1][cx + dx - 4] = 2; gear_grid[cy + dy - 1][cx + dx - 4] = gid
                for dy in range(9):
                    for dx in range(3):
                        grid[cy + dy - 4][cx + dx - 1] = 2; gear_grid[cy + dy - 4][cx + dx - 1] = gid
            return

    def _draw_circle(self, grid, gear_grid, cx, cy, r, gid, hollow=False):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                d2 = dx * dx + dy * dy
                if hollow:
                    if (r - 1) * (r - 1) <= d2 <= r * r:
                        y, x = cy + dy, cx + dx
                        if 0 <= y < 96 and 0 <= x < 96:
                            grid[y][x] = 2; gear_grid[y][x] = gid
                else:
                    if d2 <= r * r:
                        y, x = cy + dy, cx + dx
                        if 0 <= y < 96 and 0 <= x < 96:
                            grid[y][x] = 2; gear_grid[y][x] = gid

    def _gear_z_depth(self, gid: int) -> float:
        z = zone_of(gid)
        if z == 0:  # HEAD (角・耳・王冠): 前面に突出
            return 0.04
        if z == 1:  # BACK (トゲ・翼・背びれ): 背面へ突出
            return -0.04
        if z == 2:  # BELLY (しま・うず): お腹の前面に貼られる
            return 0.03
        return 0.05  # AURA (星・ハイライト): 前面で浮遊

    def _resolve_frame_name(self, raw: int, mid: int, action: str, mood: str, age_sec: int = 999999) -> str:
        # FW screen.h sprite() と同一: 600s未満=タマゴ3段階、7200s未満=幼生5感情
        if age_sec < 600:
            if age_sec < 200: return "ink_egg_idle"
            if age_sec < 400: return "ink_egg_crack"
            return "ink_egg_hatch"
        if age_sec < 7200:
            act = normalize_action(action)
            if act == "SLEEP" or mood == "SLEEPY": return "ink_larva_sleep"
            if act == "EAT": return "ink_larva_eat"
            if act == "PLAY" or mood == "HAPPY": return "ink_larva_happy"
            if mood in ("SAD", "SICK"): return "ink_larva_sad"
            return "ink_larva_idle"
        # 全12形態 (0〜11) が専用アクション絵を完全保持
        # FWは STANDBY/FEED/UPLINK 表記、PC内部は IDLE/EAT/COMM。両方受ける。
        act = normalize_action(action)
        if act == "SLEEP" or mood == "SLEEPY":
            return f"ink_m{raw:02d}_sleep"
        if act == "EAT":
            return f"ink_m{raw:02d}_eat"
        if act == "PLAY" or mood == "HAPPY":
            return f"ink_m{raw:02d}_happy"
        if mood in ("SAD", "SICK"):
            return f"ink_m{raw:02d}_sad"
        # P0 FW統一: COMMは全形態自前IDLE。旧raw==2 greet特例廃止
        return f"ink_m{raw:02d}_idle"

    def draw(self, pos: rl.Vector3, scale: float, rot_y: float = 0.0, breathe: float = 0.0,
             squash_x: float = 1.0, squash_y: float = 1.0, rot_z: float = 0.0):
        """Raylib 3D 空間にソリッド・ボクセルキメラを描画 (MF2アニメーション対応)"""
        if not self.voxels:
            return

        # 呼吸モーション (ぷにっとした伸縮) + 外的 squash/stretch
        breathe_scale_y = (1.0 + math.sin(breathe * 3.0) * 0.04) * squash_y
        breathe_scale_x = (1.0 - math.sin(breathe * 3.0) * 0.02) * squash_x

        rad_y = math.radians(rot_y)
        cos_y = math.cos(rad_y)
        sin_y = math.sin(rad_y)

        rad_z = math.radians(rot_z)
        cos_z = math.cos(rad_z)
        sin_z = math.sin(rad_z)

        for v in self.voxels:
            # 呼吸と伸縮
            lx = v.x * scale * breathe_scale_x
            ly = v.y * scale * breathe_scale_y
            lz = v.z * scale

            # Z軸回転 (roll: 横倒れ・ズコー)
            zx = lx * cos_z - ly * sin_z
            zy = lx * sin_z + ly * cos_z
            zz = lz

            # Y軸回転 (yaw)
            rx = zx * cos_y - zz * sin_y
            rz = zx * sin_y + zz * cos_y
            ry = zy

            world_x = pos.x + rx
            world_y = pos.y + ry
            world_z = pos.z + rz

            # 立体ボクセルキューブの描画
            rl.draw_cube(
                rl.Vector3(world_x, world_y, world_z),
                v.w * scale * breathe_scale_x,
                v.h * scale * breathe_scale_y,
                v.d * scale,
                v.color
            )

        # 浮遊星屑オーラの描画 (ほしパーツ装着時)
        if self.stars:
            star_col = rl.Color(255, 235, 80, 220)
            star_size = 0.05 * scale
            for sx, sy, sz, ph in self.stars:
                cur_ang = breathe * 1.5 + ph
                orbit_r = 0.95
                cur_x = pos.x + math.cos(cur_ang) * orbit_r
                cur_z = pos.z + math.sin(cur_ang) * orbit_r
                cur_y = pos.y + sy - 0.82 + math.sin(breathe * 4.0 + ph) * 0.08
                rl.draw_cube(rl.Vector3(cur_x, cur_y, cur_z), star_size, star_size, star_size, star_col)


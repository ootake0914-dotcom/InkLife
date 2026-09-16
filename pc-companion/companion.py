# pc-companion/companion.py
"""
InkLife 3D Companion Station (Raylib 6.0 Native 3D Engine)
============================================================
ESP32-S3 E-Ink サイバー生命体「InkLife」のための、
本格的ネイティブ 3D デスクトップ・コンパニオン＆観測ステーション。

- 3D Voxel テラリウム & キメラ生息空間 (呼吸・感情モーション・マウス触れ合い)
- Core 0 現象盤 (Brian's Brain 48x12) の足元ホログラム
- 実機 296x128 E-Ink 完全再現バーチャルディスプレイ
- LoRa メッシュ知人帳レーダー & ソーシャルモニター
- 自動 COM ポート検出・双方向シリアル通信 & オフライン鑑賞モード
"""

import sys
import os
import time
import math
import random
import threading
from typing import Optional, List
from enum import Enum, auto
import pyray as rl

# 自作モジュール
from inkparser import (
    CreatureState, InkProtocolParser, MORPH_NAMES, GEAR_NAMES, GEAR_NAMES_EN,
    stat_rank, condition_label, MORPH_TRAIT_APTITUDE, FW_STAT_TO_DISPLAY,
    hab_gain, GROWTH_SEC_PER_PX, EVO_TABLE, EVO_RANK_NAMES, EVO_TRAIT_ORDER
)
from voxel_art import ChimeraVoxelModel, ART_DB
from virtual_eink import VirtualEInk
from sound_effects import SoundManager
from tournament import Fighter, TournamentManager, TournamentUI

class AppMode(Enum):
    FARM = auto()        # 既存の3Dテラリウム生息空間
    TOURNAMENT = auto()  # モンスターファーム２風 トーナメント大会


try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# 画面定数
WIN_W = 1280
WIN_H = 760

# テーマカラー (サイバーパンク・テラリウム)
COL_BG_DARK   = rl.Color(16, 20, 28, 255)
COL_PANEL_BG  = rl.Color(23, 28, 38, 245)
COL_ACCENT    = rl.Color(80, 220, 240, 255)
COL_ACCENT_AMB= rl.Color(255, 190, 80, 255)
COL_TXT_MAIN  = rl.Color(230, 238, 248, 255)
COL_TXT_DIM   = rl.Color(120, 135, 155, 255)
COL_LINE      = rl.Color(42, 52, 70, 255)
COL_BTN       = rl.Color(35, 45, 62, 255)
COL_BTN_HOVER = rl.Color(55, 70, 95, 255)

class TrainCutin:
    """MF2風 トレーニング結果 3Dカットイン & パーティクル演出"""
    def __init__(self):
        self.active = False
        self.timer = 0.0
        self.duration = 2.4
        self.res = ""       # "GREAT", "SUCCESS", "FAIL", "SLACK", "OVERWORK"
        self.stat = ""      # "INT", "AGGR", "CURIO", "SOC"
        self.gain = 0
        self.particles: List[dict] = []

    def trigger(self, res: str, stat: str, gain: int, sound_mgr: SoundManager):
        self.active = True
        self.timer = self.duration
        self.res = res
        self.stat = stat
        self.gain = gain
        self.particles.clear()

        # サウンド & パーティクル生成
        if res == "PERFECT":
            sound_mgr.play("perfect_fanfare")
            for _ in range(60):
                ang = random.uniform(0, math.pi * 2)
                spd = random.uniform(1.5, 4.0)
                self.particles.append({
                    "x": 0.0, "y": 1.2, "z": 0.0,
                    "vx": math.cos(ang) * spd,
                    "vy": random.uniform(2.0, 5.0),
                    "vz": math.sin(ang) * spd,
                    "col": rl.Color(255, random.choice([215, 235, 255]), random.choice([80, 150, 255]), 255),
                    "life": 1.0, "size": random.uniform(0.05, 0.09)
                })
        elif res == "FLYING":
            sound_mgr.play("flying_buzz")
        elif res == "GREAT":
            sound_mgr.play("train_great")
            for _ in range(40):
                ang = random.uniform(0, math.pi * 2)
                spd = random.uniform(1.2, 3.5)
                self.particles.append({
                    "x": 0.0, "y": 1.2, "z": 0.0,
                    "vx": math.cos(ang) * spd,
                    "vy": random.uniform(1.5, 4.0),
                    "vz": math.sin(ang) * spd,
                    "col": rl.Color(255, random.choice([200, 220, 240]), random.choice([50, 100, 220]), 255),
                    "life": 1.0, "size": random.uniform(0.04, 0.08)
                })
        elif res == "SUCCESS":
            sound_mgr.play("train_success")
            for _ in range(16):
                ang = random.uniform(0, math.pi * 2)
                spd = random.uniform(0.8, 2.0)
                self.particles.append({
                    "x": 0.0, "y": 1.0, "z": 0.0,
                    "vx": math.cos(ang) * spd,
                    "vy": random.uniform(1.0, 2.5),
                    "vz": math.sin(ang) * spd,
                    "col": rl.Color(80, 240, 150, 255),
                    "life": 1.0, "size": 0.05
                })
        elif res == "FAIL":
            sound_mgr.play("train_fail")
            for _ in range(10):
                self.particles.append({
                    "x": random.uniform(-0.3, 0.3), "y": 1.3, "z": 0.2,
                    "vx": random.uniform(-0.3, 0.3), "vy": random.uniform(-0.2, 0.4), "vz": 0.0,
                    "col": rl.Color(120, 200, 255, 230),
                    "life": 1.0, "size": 0.06
                })
        elif res == "SLACK":
            sound_mgr.play("train_slack")
        elif res == "OVERWORK":
            sound_mgr.play("overwork_alarm")

    def update(self, dt: float):
        if not self.active:
            return
        self.timer -= dt
        if self.timer <= 0:
            self.active = False
            self.particles.clear()
            return
        for p in self.particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["z"] += p["vz"] * dt
            p["vy"] -= 5.5 * dt
            p["life"] = max(0.0, p["life"] - dt * 0.7)

# ---- オフライン簡易シミュレーション (FW creatureTick/doRebirth/applyInspectの移植) ----
# 実機なしでも育成が進むよう、1実秒=30ゲーム秒で生理を回す。AI行動変化はなし (単純化)。

def offline_tick(state):
    """30ゲーム秒分の生理変化。FW creatureTick()と同一式"""
    state.age_sec += 30
    old = state.age_sec > 259200
    state.hunger = min(100, state.hunger + (3 if old else 2))
    for k in range(3):
        state.habit[k] = max(0, state.habit[k] - 8)
    if state.action == "SLEEP":
        state.energy = min(100, state.energy + 10)
    else:
        state.energy = max(0, state.energy - 2)
    if state.action == "FEED":
        state.hunger = max(0, state.hunger - 12)
    if state.action == "PLAY":
        state.happiness = min(100, state.happiness + 8)
        state.energy = max(0, state.energy - 4)
    else:
        state.happiness = max(0, state.happiness - 1)
    if ((state.age_sec // 30) % 2) == 0 and state.cleanliness > 0:
        state.cleanliness -= 1
    if state.hunger >= 95 or state.energy == 0:
        if state.health > 0:
            state.health -= 1
    elif state.hunger < 50 and state.happiness > 50 and state.cleanliness >= 30 and state.health < 100:
        state.health += 1
    if state.cleanliness < 30 and state.happiness > 0:
        state.happiness -= 1
    state.update_mood()


def offline_pick_target(state):
    raw = state.species_id % 12
    best = MORPH_TRAIT_APTITUDE[raw] if 0 <= raw < 12 else (0, 1)
    return best[0] if random.random() < 0.7 else best[1]


def offline_inspect_apply(state, grade):
    """FW applyInspectと同一経済。戻り値はイベント文"""
    if state.energy < 15:
        state.health = max(1, state.health - 5)
        state.happiness = max(0, state.happiness - 10)
        state.action = "STANDBY"
        return "OVERWORK"
    state.energy = max(0, state.energy - 15)
    state.hunger = min(100, state.hunger + 12)
    state.happiness = max(0, state.happiness - 5)
    if grade == 4:
        state.happiness = max(0, state.happiness - 3)
        state.action = "STANDBY"
        return "TR:FLYING"
    if grade == 3:
        state.action = "STANDBY"
        return "TR:FAIL"
    target = offline_pick_target(state)
    gain = 5 if grade == 0 else (4 + random.randrange(2) if grade == 1 else 2 + random.randrange(2))
    if grade <= 1:
        state.happiness = min(100, state.happiness + 15)
    if target == 0:
        state.intelligence = min(100, state.intelligence + gain)
    elif target == 1:
        state.aggression = min(100, state.aggression + gain)
    elif target == 2:
        state.curiosity = min(100, state.curiosity + gain)
    else:
        state.sociability = min(100, state.sociability + gain)
    state.habit[1] = min(100, state.habit[1] + 20)
    state.action = "PLAY"
    return ("TR:PERFECT!", "TR:GREAT!", "TR:SUCCESS")[grade]


def offline_rebirth(state):
    """FW doRebirthの簡易版 (遺伝なし。能力微変動＋世代+1＋新生値)"""
    state.generation = min(255, state.generation + 1)
    for attr in ("intelligence", "curiosity", "aggression", "sociability"):
        setattr(state, attr, max(0, min(100, getattr(state, attr) + random.randint(-3, 3))))
    state.age_sec = 0
    state.health = 90
    state.hunger = 20
    state.energy = 90
    state.happiness = 70
    state.cleanliness = 80
    state.habit = [0, 0, 0]
    state.action = "STANDBY"
    state.update_mood()


class SerialWorker:
    """バックグラウンドで ESP32-S3 とのシリアル通信を維持・自動再接続するスレッド"""
    def __init__(self, parser: InkProtocolParser, eink: VirtualEInk):
        self.parser = parser
        self.eink = eink
        self.ser: Optional[serial.Serial] = None
        self.connected = False
        self.running = True
        self.port_name = "AUTO"
        # TIME送信済みか (VirtualEInkの昼夜表示用。実機rtcUnixと一致する前提)
        self.time_synced = False
        # RLock: send()保持中に_add_log()が同ロックを取るため再入可能にする
        self.lock = threading.RLock()
        # 状態共有ロック (CreatureState/field_grid/peers/logsは両スレッドで触る)。
        # 無ロックだと辞書リサイズ中のRuntimeErrorや盤面行ちぎれが起きる。
        self.state_lock = threading.Lock()
        self.tx_queue: List[str] = []
        self.log_lines: List[str] = []
        self.event_queue: List[dict] = []

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def send(self, cmd: str):
        with self.lock:
            self.tx_queue.append(cmd.strip() + "\n")
            self._add_log(f"> {cmd.strip()}")

    def pop_events(self) -> List[dict]:
        with self.lock:
            evts = list(self.event_queue)
            self.event_queue.clear()
            return evts

    def _add_log(self, text: str):
        # 描画スレッドと共有するためロック下で操作 (行ちぎれ防止)
        with self.lock:
            self.log_lines.append(text)
            if len(self.log_lines) > 50:
                self.log_lines.pop(0)

    def get_logs(self, n: int) -> List[str]:
        with self.lock:
            return list(self.log_lines[-n:])

    def _find_port(self) -> Optional[str]:
        if not SERIAL_AVAILABLE:
            return None
        # 明示指定が最優先 (--port=COM24 / 環境変数 INKLIFE_PORT)。誤爆防止。
        for arg in sys.argv:
            if arg.startswith("--port=") and len(arg) > 7:
                return arg[7:]
        forced = os.environ.get("INKLIFE_PORT")
        if forced:
            return forced
        ports = list(serial.tools.list_ports.comports())
        # 1. COM24 を優先 (開発機既定)
        for p in ports:
            if p.device.upper() == "COM24":
                return p.device
        # 2. ESP32-S3 / USB-JTAG-CDC を検索
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if "esp32" in desc or "jtag" in desc or "usb serial" in desc or "303a" in hwid:
                return p.device
            # CP210x / CH340 / FTDI 等の汎用USB-UARTも実機の可能性がある
            if "cp210" in desc or "ch340" in desc or "ch341" in desc or "ftdi" in desc or "usb" in desc:
                # Bluetooth SPP は除外 (誤爆送信防止)
                if "bluetooth" not in desc and "bth" not in hwid:
                    return p.device
        # 3. フォールバック: Bluetooth以外の最初のCOMを試す (実機取りこぼし防止)
        #    以前はNoneを返してOFFLINE固定になっていたため、狐実機でも
        #    デモのスライム (species 24) が表示され続けるバグがあった。
        for p in ports:
            desc = (p.description or "").lower()
            if "bluetooth" in desc:
                continue
            if "standard serial over bluetooth" in desc:
                continue
            return p.device
        return None

    def _run(self):
        while self.running:
            if not self.connected:
                target_port = self._find_port()
                if target_port and SERIAL_AVAILABLE:
                    try:
                        # write_timeout必須: USB抜去・リセット中のWriteFile無限ブロックで
                        # ワーカがlock保持のまま固まり、描画スレッドがpop_eventsで
                        # 一緒に固まるデッドロックを防ぐ (白画面の犯人)。
                        s = serial.Serial(target_port, 115200, timeout=0.1, write_timeout=1)
                        self.ser = s
                        self.port_name = target_port
                        self.connected = True
                        self._add_log(f"[ONLINE] Connected to {target_port}")
                        with self.lock:
                            self.event_queue.append({"type": "dock", "port": target_port})
                        # 初期同期コマンドの送信 (古い滞留コマンドは破棄)
                        with self.lock:
                            self.tx_queue.clear()
                        time.sleep(0.3)
                        now_unix = int(time.time())
                        self.send(f"TIME {now_unix}")
                        self.time_synced = True
                        self.send("FZ")
                        self.send("SP")
                        self.send("ID")
                        self.send("AFF")
                    except Exception as e:
                        self.connected = False
                        self.ser = None
                        time.sleep(1.0)
                else:
                    time.sleep(1.0)
            else:
                # 受信ループ
                try:
                    if self.ser and self.ser.is_open:
                        # 送信キューの処理
                        with self.lock:
                            while self.tx_queue:
                                msg = self.tx_queue.pop(0)
                                self.ser.write(msg.encode("utf-8"))

                        # 受信行の読み出し (状態更新はstate_lock下で一括)
                        # in_waitingがある限り一括ドレインしてPC側の読み遅れによるFW Txバッファ溢れを防止
                        while self.ser and self.ser.is_open and self.ser.in_waiting > 0:
                            line_bytes = self.ser.readline()
                            if not line_bytes:
                                break
                            line = line_bytes.decode("utf-8", errors="replace").strip()
                            if line:
                                # FIELDBは12行/分でログを埋めてイベントを押し流すため畳む
                                # (盤面はE-Inkミニ窓とラボのAct/Symに反映済み。解析はINK_FELDB=1で生表示)
                                if line.startswith("+FIELDB "):
                                    if os.environ.get("INK_FELDB") == "1":
                                        self._add_log(line)
                                    elif line[8:9] == "0":
                                        self._add_log("+FIELDB x12 (board updated)")
                                else:
                                    self._add_log(line)
                                with self.state_lock:
                                    r = self.parser.parse_line(line)
                                    if r and r.get("type") == "event":
                                        self.eink.push_log(r["event"], self.parser.state.age_sec)
                                if r:
                                    with self.lock:
                                        self.event_queue.append(r)
                    else:
                        self.connected = False
                        self.ser = None
                except Exception as e:
                    self._add_log(f"[OFFLINE] Disconnected: {e}")
                    self.connected = False
                    self.ser = None
                    time.sleep(1.0)

            time.sleep(0.01)

def draw_morph_dex(state: CreatureState):
    """形態図鑑オーバーレイ (Mキー)。12形態のアート・名前・得意形質と進化表を一覧する。
    進化先の見通しが立つので「あと30分で何になるか」の楽しみが増える (アートはFWと同一XBM)"""
    rl.draw_rectangle(0, 0, WIN_W, WIN_H, rl.Color(8, 10, 16, 236))
    rl.draw_text("MORPH ENCYCLOPEDIA", 24, 12, 20, COL_ACCENT)
    rl.draw_text("M: close   |   gold frame = current form   |   A/B = training aptitude",
                 24, 38, 11, COL_TXT_DIM)

    cur_raw = state.raw_morph
    cw, ch = 150, 196
    x0, y0 = 24, 60
    for i in range(12):
        cx = x0 + (i % 4) * 156
        cy = y0 + (i // 4) * 204
        is_cur = (i == cur_raw)
        rl.draw_rectangle_rounded(rl.Rectangle(cx, cy, cw, ch), 0.08, 4,
                                  rl.Color(30, 42, 60, 255) if is_cur else rl.Color(17, 23, 33, 255))
        rl.draw_rectangle_rounded_lines(rl.Rectangle(cx, cy, cw, ch), 0.08, 4,
                                        rl.Color(255, 215, 0, 255) if is_cur else rl.Color(50, 65, 90, 255))
        px = _dex_pixels(f"ink_m{i:02d}_idle")
        sc = 84.0 / 96.0
        ax = cx + (cw - 84) / 2
        ay = cy + 6
        col = rl.Color(230, 238, 248, 255)
        for (dx, dy) in px:
            rl.draw_rectangle(int(ax + dx * sc), int(ay + dy * sc), 1, 1, col)
        nm = MORPH_NAMES.get(i, "?")
        rl.draw_text(f"{i:02d} {nm}", int(cx + 8), int(cy + 98), 13,
                     rl.Color(255, 215, 0, 255) if is_cur else COL_TXT_MAIN)
        apt = MORPH_TRAIT_APTITUDE[i]
        d0 = FW_STAT_TO_DISPLAY[EVO_TRAIT_ORDER[apt[0]]]
        d1 = FW_STAT_TO_DISPLAY[EVO_TRAIT_ORDER[apt[1]]]
        rl.draw_text(f"A:{d0}  B:{d1}", int(cx + 8), int(cy + 118), 11, COL_ACCENT)

    # 進化表 (rank x 得意形質 -> morph)
    ty = y0 + 3 * 204 + 4
    rl.draw_text("EVOLUTION TABLE  (care rank x dominant trait)", 24, ty, 13, COL_ACCENT_AMB)
    for r in range(4):
        row = EVO_TABLE[r]
        names = "  ".join(f"{EVO_TRAIT_ORDER[t][:3]}:{MORPH_NAMES.get(row[t], '?')[:7]}" for t in range(4))
        rl.draw_text(f"{EVO_RANK_NAMES[r]}  {names}", 24, ty + 20 + r * 16, 12,
                     rl.Color(255, 215, 0, 255) if r == 0 else COL_TXT_MAIN)


DEX_PIXEL_CACHE = {}


def _dex_pixels(frame_name: str):
    """XBMフレームの黒画素リスト (初回走査をキャッシュ)"""
    px = DEX_PIXEL_CACHE.get(frame_name)
    if px is None:
        b = ART_DB.get_frame_bytes(frame_name)
        px = []
        if b and len(b) >= 1152:
            for y in range(96):
                row = y * 12
                for x in range(96):
                    if (b[row + (x >> 3)] >> (x & 7)) & 1:
                        px.append((x, y))
        DEX_PIXEL_CACHE[frame_name] = px
    return px


def draw_mf2_status_panel(state: CreatureState, x: int, y: int):
    """左上 3Dテラリウム内 MF2能力値パネル (POW, INT, SPD, SKI & ランク & コンディション)"""
    w = 230
    h = 188
    # 半透明サイバーパネル
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.08, 4, rl.Color(16, 22, 32, 225))
    rl.draw_rectangle_rounded_lines(rl.Rectangle(x, y, w, h), 0.08, 4, rl.Color(50, 68, 95, 255))

    # ヘッダー
    rl.draw_text("MONSTER STATUS", x + 12, y + 10, 13, COL_ACCENT)

    # コンディション判定 (MF2風)
    cond_text, cond_type = condition_label(state.energy, state.health, state.happiness)
    if cond_type == "DANGER":
        cond_col = rl.Color(255, 75, 75, 255)
    elif cond_type == "WARN":
        cond_col = rl.Color(255, 190, 60, 255)
    elif cond_type == "PEAK":
        cond_col = rl.Color(255, 225, 70, 255)
    elif cond_type == "GOOD":
        cond_col = rl.Color(90, 240, 150, 255)
    else:
        cond_col = COL_TXT_MAIN

    rl.draw_text(cond_text, x + 12, y + 28, 12, cond_col)

    # 適性情報 (現在の形態)
    raw_species = state.species_id % 12
    best_traits = MORPH_TRAIT_APTITUDE[raw_species] if 0 <= raw_species < 12 else (0, 1)

    # 4大パラメータ (POW, INT, SPD, SKI)。Raylib既定フォントはASCIIのみのため英語表記。
    traits = [
        ("Power (POW)", state.aggression, 1, rl.Color(255, 100, 100, 255)),
        ("Smart (INT)", state.intelligence, 0, rl.Color(100, 190, 255, 255)),
        ("Speed (SPD)", state.curiosity, 2, rl.Color(100, 255, 180, 255)),
        ("Charm (SKI)", state.sociability, 3, rl.Color(255, 220, 100, 255)),
    ]

    for i, (label, val, tid, bar_col) in enumerate(traits):
        row_y = y + 52 + i * 32
        rank = stat_rank(val)

        # ランク色
        if rank == "S": r_col = rl.Color(255, 215, 0, 255)
        elif rank == "A": r_col = rl.Color(255, 110, 70, 255)
        elif rank == "B": r_col = rl.Color(80, 190, 255, 255)
        elif rank == "C": r_col = rl.Color(80, 220, 120, 255)
        elif rank == "D": r_col = rl.Color(180, 210, 230, 255)
        else: r_col = COL_TXT_DIM

        # ラベル & 適性マーク [A] [B]
        apt_mark = " [A]" if tid == best_traits[0] else (" [B]" if tid == best_traits[1] else "")
        rl.draw_text(f"{label}{apt_mark}", x + 12, row_y, 11, COL_TXT_MAIN)

        # バー背景
        bar_x = x + 12
        bar_y = row_y + 14
        bar_w = 145
        bar_h = 7
        rl.draw_rectangle(bar_x, bar_y, bar_w, bar_h, rl.Color(35, 45, 60, 255))

        # ゲージ
        fill_w = int(bar_w * (min(100, max(0, val)) / 100.0))
        rl.draw_rectangle(bar_x, bar_y, fill_w, bar_h, bar_col)

        # 数値 & ランク
        rl.draw_text(f"{val:3d}", x + 165, row_y + 9, 12, COL_TXT_MAIN)
        rl.draw_text(rank, x + 198, row_y + 8, 14, r_col)

def draw_cutin_banner(cutin: TrainCutin):
    """3D領域上部にポップアップする MF2風カットインリザルトバナー"""
    if not cutin.active:
        return
    progress = (cutin.duration - cutin.timer) / cutin.duration
    alpha = 1.0 if progress < 0.75 else max(0.0, (1.0 - progress) / 0.25)
    a_int = int(alpha * 255)

    bx = 90
    by = 180
    bw = 470
    bh = 80

    if cutin.res == "GREAT":
        title = "★ GREAT SUCCESS !! ★"
        sub = f"{cutin.stat} +{cutin.gain} UP ! (Tremendous Growth!)"
        col_border = rl.Color(255, 215, 0, a_int)
        col_txt = rl.Color(255, 235, 120, a_int)
    elif cutin.res == "SUCCESS":
        title = "SUCCESS !"
        sub = f"{cutin.stat} +{cutin.gain} UP !"
        col_border = rl.Color(80, 240, 150, a_int)
        col_txt = rl.Color(120, 255, 180, a_int)
    elif cutin.res == "FAIL":
        title = "FAIL..."
        sub = "Wasted effort... (0 gain)"
        col_border = rl.Color(100, 160, 240, a_int)
        col_txt = rl.Color(160, 200, 255, a_int)
    elif cutin.res == "SLACK":
        title = "SLACK... (Playing Hooky)"
        sub = "Took a little nap instead~"
        col_border = rl.Color(255, 180, 80, a_int)
        col_txt = rl.Color(255, 205, 120, a_int)
    else:  # OVERWORK
        title = "⚠ OVERWORK WARNING !! ⚠"
        sub = "Dangerously exhausted! Rest immediately!"
        col_border = rl.Color(255, 60, 60, a_int)
        col_txt = rl.Color(255, 100, 100, a_int)

    # バナー背景
    rl.draw_rectangle_rounded(rl.Rectangle(bx, by, bw, bh), 0.2, 4, rl.Color(14, 18, 26, int(a_int * 0.92)))
    rl.draw_rectangle_rounded_lines(rl.Rectangle(bx, by, bw, bh), 0.2, 4, col_border)

    tw1 = rl.measure_text(title, 22)
    rl.draw_text(title, bx + (bw - tw1) // 2, by + 16, 22, col_txt)
    tw2 = rl.measure_text(sub, 15)
    rl.draw_text(sub, bx + (bw - tw2) // 2, by + 46, 15, COL_TXT_MAIN)

def main():
    # 1. Raylib ウィンドウ初期化
    rl.set_config_flags(rl.FLAG_MSAA_4X_HINT | rl.FLAG_VSYNC_HINT)
    rl.init_window(WIN_W, WIN_H, "InkLife 3D Companion — サイバー生命体観測ステーション")
    rl.set_target_fps(60)

    # 2. 状態・モデル・E-Ink・シリアル初期化
    state = CreatureState()
    parser = InkProtocolParser(state)
    voxel_model = ChimeraVoxelModel()
    eink = VirtualEInk()
    serial_worker = SerialWorker(parser, eink)
    serial_worker.start()

    # 8-bit サウンドマネージャ & MF2カットイン演出
    sound_mgr = SoundManager()
    sound_mgr.init_audio()
    train_cutin = TrainCutin()

    # デモ用の初期設定 (OFFLINE時のみ表示。ONLINEで即 +SP/+FZ 上書きされる)
    # BUG修正: 24 % 12 == 0 スライムになっていた (意図はちびドラゴン %12==1)。
    # 25 % 12 == 1 でドラゴン正。fuse [2,3,11] は耳/トゲ/星で全ゾーン別 = 全表示。
    state.species_id = 25  # 第24世代ちびドラゴン (柴犬ピン耳 + 背中トゲ + 星屑)
    state.generation = 24
    state.fuse = [2, 3, 11, 255]  # 耳、トゲ、星屑
    state.last_event = "WAKE_OK"
    state.speech_bubble = "InkLife 3D Online! Welcome back!"

    # 3. 3D カメラ設定 (Orbit カメラ)
    cam = rl.Camera3D()
    cam.position = rl.Vector3(0.0, 1.8, 3.8)
    cam.target = rl.Vector3(0.0, 0.75, 0.0)
    cam.up = rl.Vector3(0.0, 1.0, 0.0)
    cam.fovy = 45.0
    cam.projection = rl.CAMERA_PERSPECTIVE

    cam_angle = 0.0
    cam_pitch = 0.35
    cam_dist = 3.6
    mouse_dragging = False
    last_mouse_pos = rl.Vector2(0, 0)

    # アニメーション用クロック
    sim_time = 0.0
    click_bounce = 0.0
    bubble_alpha = 1.0
    # 反応速度検査ミニゲームの状態 (None or dict)。G開始・SPACE回答。
    inspect_game = None
    # 形態図鑑オーバーレイ (Mトグル)
    show_dex = False
    # REBORN二度押し確認 (誤クリックで世代が飛ぶのを防ぐ)
    reborn_armed_until = 0.0
    # オフライン生理tick用アキュムレータ (1実秒=30ゲーム秒)
    offline_acc = 0.0

    # ボタン矩形定義
    btn_feed = rl.Rectangle(930, 680, 100, 36)
    btn_play = rl.Rectangle(1040, 680, 100, 36)
    btn_time = rl.Rectangle(1150, 680, 100, 36)
    btn_train = rl.Rectangle(930, 634, 100, 36)
    btn_reborn = rl.Rectangle(1040, 634, 100, 36)
    btn_photo = rl.Rectangle(1150, 634, 100, 36)
    # 588行は4列 (幅74)。CUREは病時専用の小さな薬ボタン
    btn_tourney = rl.Rectangle(930, 588, 74, 36)  # トーナメント大会エントリーボタン
    btn_clean = rl.Rectangle(1010, 588, 74, 36)  # 掃除 (FW同時押しと同一)
    btn_bench = rl.Rectangle(1090, 588, 74, 36)
    btn_cure = rl.Rectangle(1170, 588, 74, 36)  # お薬 (FW CUREと同一。SICK圏外は無効)

    # アプリケーションモード (FARM <-> TOURNAMENT)
    # 引数に --tourney または -t がある場合は直接トーナメント大会から開始
    if "--tourney" in sys.argv or "-t" in sys.argv:
        with serial_worker.state_lock:
            my_fighter = Fighter.from_creature_state(state)
            peers_list = list(state.peers.values())
        tourney_mgr = TournamentManager(my_fighter, peers_list)
        tourney_ui: Optional[TournamentUI] = TournamentUI(tourney_mgr, sound_mgr)
        app_mode = AppMode.TOURNAMENT
    else:
        app_mode = AppMode.FARM
        tourney_ui: Optional[TournamentUI] = None


    screenshot_msg = ""
    screenshot_timer = 0.0

    # E-Ink再描画ゲート (内容変化時のみ。毎フレーム37kループ回避)
    eink_key = None
    # 現象盤要求の追跡 (+LIFE更新ごとにFIELDBを1回)
    last_field_age = -1
    # 種・融合の定期再同期 (+SP/+FZ応答ロスでスライム固定化するのを防止。10秒毎)
    last_sync_time = 0.0

    # 3D シーン用ライティングシェーダー (Key + Fill + Ambient)
    vs_code = """#version 330
in vec3 vertexPosition;
in vec3 vertexNormal;
in vec4 vertexColor;
uniform mat4 mvp;
uniform mat4 matModel;
out vec3 fragNormal;
out vec4 fragColor;
out vec3 fragPosition;
void main() {
    fragPosition = vec3(matModel * vec4(vertexPosition, 1.0));
    fragNormal = normalize(vec3(matModel * vec4(vertexNormal, 0.0)));
    fragColor = vertexColor;
    gl_Position = mvp * vec4(vertexPosition, 1.0);
}
"""
    fs_code = """#version 330
in vec3 fragNormal;
in vec4 fragColor;
out vec4 finalColor;
void main() {
    vec3 keyDir = normalize(vec3(0.55, 1.0, 0.75));
    float diffKey = max(dot(fragNormal, keyDir), 0.0);
    vec3 fillDir = normalize(vec3(-0.7, 0.25, -0.6));
    float diffFill = max(dot(fragNormal, fillDir), 0.0) * 0.35;
    vec3 ambient = vec3(0.38, 0.42, 0.48);
    vec3 light = ambient + vec3(0.9, 0.88, 0.82) * diffKey + vec3(0.25, 0.5, 0.75) * diffFill;
    finalColor = vec4(light * fragColor.rgb, fragColor.a);
}
"""
    lighting_shader = rl.load_shader_from_memory(vs_code, fs_code)

    # 3D 専用レンダーテクスチャ (650x760 ピクセル完全分離 & 理想的アスペクト比)
    rt_3d_w = 650
    rt_3d_h = WIN_H
    rt_3d = rl.load_render_texture(rt_3d_w, rt_3d_h)

    # アンビエント浮遊パーティクル (テラリウム内のエネルギー微粒子)
    ambient_particles = []
    for i in range(24):
        ambient_particles.append({
            "ang": i * (math.pi * 2 / 24),
            "rad": 0.5 + (i % 5) * 0.22,
            "y": 0.1 + (i % 7) * 0.28,
            "speed": 0.18 + (i % 4) * 0.06,
        })

    # 4. メインループ
    while not rl.window_should_close():
        dt = rl.get_frame_time()
        sim_time += dt
        if click_bounce > 0:
            click_bounce = max(0.0, click_bounce - dt * 4.0)

        # オフライン生理tick (実機なしでも育成が進む。FW creatureTick移植)
        if not serial_worker.connected:
            offline_acc += dt
            while offline_acc >= 1.0:
                offline_acc -= 1.0
                with serial_worker.state_lock:
                    offline_tick(state)

        # シリアルイベントの受信・ディスパッチ (状態に触るためstate_lock下)
        with serial_worker.state_lock:
            pending_evts = serial_worker.pop_events()
            for ev in pending_evts:
                etype = ev.get("type")
                if etype == "dock":
                    sound_mgr.play("dock")
                    state.speech_bubble = f"PocketStation Docked! [{ev.get('port', 'COM')}]"
                    state.speech_timer = 4.0
                elif etype == "train":
                    res = ev.get("res", "SUCCESS")
                    # FWは AGGR/CURIO/SOC、PC表示は POW/SPD/SKI。統一して表示する。
                    raw_stat = ev.get("stat", "INT")
                    stat = FW_STAT_TO_DISPLAY.get(raw_stat, raw_stat)
                    gain = ev.get("gain", 0)
                    train_cutin.trigger(res, stat, gain, sound_mgr)
                elif etype == "inspect":
                    # FW検査結果 (INSPECT target/grade)。カットイン語彙に寄せる。
                    grade = ev.get("grade", 3)
                    res = ("PERFECT", "GREAT", "SUCCESS", "FAIL")[grade] if 0 <= grade <= 3 else "FAIL"
                    raw_stat = ev.get("target", "INT")
                    stat = FW_STAT_TO_DISPLAY.get(raw_stat, raw_stat)
                    train_cutin.trigger(res, stat, 0, sound_mgr)
                elif etype == "evolve":
                    train_cutin.trigger("GREAT", "INT", 0, sound_mgr)
                    sound_mgr.play("evolve_shine")
                    state.speech_bubble = f"Evolution! Rank {ev.get('rank', '?')}!"
                    state.speech_timer = 5.0
                elif etype == "event":
                    evt = ev.get("event", "")
                    # イベント→効果音 (旧: OHAYO/掃除/薬の3種のみで残りは無音だった)
                    _sfx = {
                        "FEED_OK": "eat_crunch", "STUFFED": "eat_crunch",
                        "PLAY_OK": "play_chirp",
                        "CLEAN_OK": "clean_scrub", "SPOTLESS": "clean_scrub",
                        "CURE_OK": "cure_chime",
                        "OHAYO": "ohayo_birds",
                        "ENTER_REST": "sleep_soft",
                        "WAKE_OK": "wake_yawn",
                        "FATIGUE": "fatigue_thud",
                        "OVERWORK": "overwork_alarm",
                        "BONDED": "bond_twinkle",
                        "RIVAL": "rival_growl",
                        "PEER_FOUND": "peer_ping",
                        "FOOD_TX": "packet_zip", "FOOD_RX": "packet_zip",
                        "COMBAT_WIN": "combat_hit", "COMBAT_LOSS": "combat_hit",
                        "TRADE_OK": "trade_swap", "TRADE_REFUSE": "trade_swap",
                        "BIRTH_RX": "peer_fanfare", "EVOLVE_RX": "peer_fanfare",
                        "GETWELL_RX": "heal_bell",
                        "NIGHTFALL": "night_fall", "DAYBREAK": "day_break",
                    }.get(evt)
                    if _sfx:
                        sound_mgr.play(_sfx)

        train_cutin.update(dt)

        # トーナメント大会モードの更新 & 描画
        if app_mode == AppMode.TOURNAMENT and tourney_ui is not None:
            should_exit = tourney_ui.update(dt, serial_worker)
            rl.begin_drawing()
            tourney_ui.draw(WIN_W, WIN_H)
            rl.end_drawing()
            if should_exit:
                app_mode = AppMode.FARM
                tourney_ui = None
            continue

        # マウス入力 & 3D カメラ制御
        mouse_pos = rl.get_mouse_position()
        if show_dex:
            mouse_pos = rl.Vector2(-9999.0, -9999.0)  # 図鑑表示中はUI入力を無効化
        in_3d_area = (mouse_pos.x < 650)  # 左側 3D 領域

        # 撫で判定は上部UI(タイトル/MF2パネル/吹き出し/カットイン帯 y<270)を除外。
        # ドラッグ回転・ズームは全域で有効のまま。
        pet_zone = in_3d_area and mouse_pos.y > 270

        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT) and in_3d_area:
            mouse_dragging = True
            last_mouse_pos = mouse_pos
            if pet_zone:
                # キメラクリック判定 (跳ねるリアクション)
                click_bounce = 1.0
                # FW側で幸福+1 (30秒クールダウン)。旧: PCローカル+2は次の+LIFEで上書きされ消えていた
                serial_worker.send("PET")
                with serial_worker.state_lock:
                    state.speech_bubble = "*purr* So happy to see you!"
                    state.speech_timer = 3.5

        if rl.is_mouse_button_released(rl.MOUSE_BUTTON_LEFT):
            mouse_dragging = False

        if mouse_dragging:
            dx = mouse_pos.x - last_mouse_pos.x
            dy = mouse_pos.y - last_mouse_pos.y
            cam_angle -= dx * 0.008
            cam_pitch = max(0.05, min(1.2, cam_pitch + dy * 0.008))
            last_mouse_pos = mouse_pos

        # ホイールズーム
        wheel = rl.get_mouse_wheel_move()
        if in_3d_area and wheel != 0:
            cam_dist = max(2.0, min(6.5, cam_dist - wheel * 0.3))

        # カメラ座標更新
        cam.position.x = math.sin(cam_angle) * math.cos(cam_pitch) * cam_dist
        cam.position.y = math.sin(cam_pitch) * cam_dist + 0.5
        cam.position.z = math.cos(cam_angle) * math.cos(cam_pitch) * cam_dist
        cam.target = rl.Vector3(0.0, 0.75, 0.0)

        # 形態図鑑 (M: 12形態のアート・得意形質・進化表。開いている間は入力を殺す)
        if rl.is_key_pressed(rl.GLFW_KEY_M):
            show_dex = not show_dex
            mouse_dragging = False
            sound_mgr.play("click")

        # 反応速度検査ミニゲーム (G開始・SPACE回答。FW runInspectGameと同一経済)
        # E-Ink実機はLED合図、PCは画面カウントダウン。GO前のSPACEはお手つき失格。
        if rl.is_key_pressed(rl.GLFW_KEY_G) and inspect_game is None and not show_dex:
            sound_mgr.play("click")
            inspect_game = {"phase": "COUNT", "t0": sim_time,
                            "go_at": sim_time + 1.8 + random.uniform(0.5, 1.5),
                            "shown": 0, "flying": False,
                            "result": 3, "until": 0.0}
            with serial_worker.state_lock:
                state.speech_bubble = "Reaction test... steady..."
                state.speech_timer = 3.0
        if inspect_game is not None:
            ig = inspect_game
            el = sim_time - ig["t0"]
            if ig["phase"] == "COUNT":
                count = 3 - int(el / 0.6)
                if count != ig["shown"] and count >= 1:
                    ig["shown"] = count
                    sound_mgr.play("click")
                if rl.is_key_pressed(rl.GLFW_KEY_SPACE):
                    ig["flying"] = True
                if el >= ig["go_at"]:
                    if not ig["flying"]:
                        ig["phase"] = "GO"
                        ig["go_mark"] = sim_time
                        sound_mgr.play("dock")
                    else:
                        # お手つき失格。FWに符号がないため送らず、 offline時のみ自前処理。
                        ig["phase"] = "DONE"
                        ig["result"] = 4
                        ig["until"] = sim_time + 1.5
                        if serial_worker.connected:
                            with serial_worker.state_lock:
                                state.speech_bubble = "TR:FLYING"
                                state.speech_timer = 3.0
                        else:
                            with serial_worker.state_lock:
                                ev = offline_inspect_apply(state, 4)
                                train_cutin.trigger("FLYING", "INT", 0, sound_mgr)
                                state.speech_bubble = ev
                                state.speech_timer = 3.0
            elif ig["phase"] == "GO":
                grade = None
                if rl.is_key_pressed(rl.GLFW_KEY_SPACE):
                    dt_ms = int((sim_time - ig["go_mark"]) * 1000)
                    grade = 0 if dt_ms <= 150 else (1 if dt_ms <= 400 else (2 if dt_ms <= 800 else 3))
                elif sim_time - ig["go_mark"] >= 2.0:
                    grade = 3
                if grade is not None:
                    if serial_worker.connected:
                        serial_worker.send(f"INSPECT {grade}")  # FWが経済処理 (結果行でカットイン)
                    else:
                        with serial_worker.state_lock:
                            ev = offline_inspect_apply(state, grade)
                            res = {"TR:PERFECT!": "PERFECT", "TR:GREAT!": "GREAT",
                                   "TR:SUCCESS": "SUCCESS", "TR:FAIL": "FAIL"}.get(ev, "FAIL")
                            train_cutin.trigger(res, "INT", 0, sound_mgr)
                            state.speech_bubble = ev
                            state.speech_timer = 3.0
                    ig["phase"] = "DONE"
                    ig["result"] = grade
                    ig["until"] = sim_time + 1.5
            elif ig["phase"] == "DONE":
                if sim_time >= ig["until"]:
                    inspect_game = None

        # ボタン入力判定 (FW実効値と一致させる。旧楽観値はhabGain無視で乖離)
        if rl.check_collision_point_rec(mouse_pos, btn_feed) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            serial_worker.send("FEED")
            with serial_worker.state_lock:
                if state.hunger == 0:
                    state.happiness = min(100, state.happiness + hab_gain(2, state.habit[0]))
                else:
                    state.hunger = max(0, state.hunger - 30)
                    state.happiness = min(100, state.happiness + hab_gain(5, state.habit[0]))
                    state.habit[0] = min(100, state.habit[0] + 25)
                    state.cleanliness = max(0, state.cleanliness - 15)  # FW ui::feedと同一 (食ったら出す)
                state.action = "FEED"  # FW表記 (E-Ink一致。art解決は正規化)
                state.speech_bubble = "*munch munch* Delicious snack!"
                state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_play) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            serial_worker.send("PLAY")
            with serial_worker.state_lock:
                if state.energy < 10:
                    state.speech_bubble = "Tired... need sleep..."
                else:
                    state.happiness = min(100, state.happiness + hab_gain(25, state.habit[1]))
                    state.habit[1] = min(100, state.habit[1] + 25)
                    state.energy = max(0, state.energy - 10)
                    state.action = "PLAY"
                    state.speech_bubble = "Yay! Playing games is awesome!"
                state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_clean) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            serial_worker.send("CLEAN")
            with serial_worker.state_lock:
                if state.cleanliness >= 100:
                    state.speech_bubble = "Already spotless!"
                else:
                    state.cleanliness = 100
                    state.happiness = min(100, state.happiness + 3)
                    state.action = "STANDBY"  # FWのIDLE相当 (PC表記)
                    state.speech_bubble = "*scrub scrub* All clean!"
                state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_cure) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            serial_worker.send("CURE")
            with serial_worker.state_lock:
                if state.health >= 50:
                    state.speech_bubble = "Healthy! No medicine needed."
                else:
                    state.health = min(100, state.health + 30)
                    state.happiness = max(0, state.happiness - 5)
                    state.action = "STANDBY"  # FWのIDLE相当 (PC表記)
                    state.speech_bubble = "*gulp* Bitter... but effective!"
                state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_train) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            serial_worker.send("TRAIN")
            # オフライン時 (シミュレータ時) はPC側でMF2ダイスロール & 即時カットイン
            # FW ui::train() と同一式 (エネルギー/幸福度依存の可変確率 + 幸福度増減)。
            if not serial_worker.connected:
                with serial_worker.state_lock:
                    raw_sp = state.species_id % 12
                    best_t = MORPH_TRAIT_APTITUDE[raw_sp] if 0 <= raw_sp < 12 else (0, 1)
                    target = best_t[0] if random.random() < 0.7 else best_t[1]
                    t_names = ["INT", "POW", "SPD", "SKI"]
                    target_name = t_names[target]

                    if state.energy < 15:
                        state.health = max(1, state.health - 5)
                        state.happiness = max(0, state.happiness - 10)
                        state.action = "STANDBY"  # FW表記 (ui::train OVERWORK)
                        train_cutin.trigger("OVERWORK", target_name, 0, sound_mgr)
                        state.speech_bubble = "Too exhausted... Overworked!"
                    else:
                        # FW ui::train と同一コスト (15。旧18から緩和に追従)
                        state.energy = max(0, state.energy - 15)
                        state.hunger = min(100, state.hunger + 12)
                        state.happiness = max(0, state.happiness - 5)
                        # FW準拠: サボり→大成功→成功→失敗の順に残り確率で判定
                        slack_chance = (50 - state.happiness) / 3 + 3 if state.happiness < 50 else 3
                        r100 = random.uniform(0, 100)
                        if r100 < slack_chance:
                            state.happiness = min(100, state.happiness + 8)
                            state.action = "PLAY"
                            train_cutin.trigger("SLACK", target_name, 0, sound_mgr)
                            state.speech_bubble = "Played hooky today~ (SLACK)"
                        else:
                            r100 -= slack_chance
                            great_chance = 20 if (state.happiness >= 70 and state.energy >= 50) else 6
                            if r100 < great_chance:
                                gain = random.choice([4, 5])
                                if target == 0: state.intelligence = min(100, state.intelligence + gain)
                                elif target == 1: state.aggression = min(100, state.aggression + gain)
                                elif target == 2: state.curiosity = min(100, state.curiosity + gain)
                                elif target == 3: state.sociability = min(100, state.sociability + gain)
                                state.happiness = min(100, state.happiness + 15)
                                state.action = "PLAY"
                                train_cutin.trigger("GREAT", target_name, gain, sound_mgr)
                                state.speech_bubble = f"GREAT SUCCESS !! {target_name} +{gain} UP!"
                            else:
                                r100 -= great_chance
                                success_chance = 40 + (state.energy * 4 / 10)
                                if r100 < success_chance:
                                    gain = random.choice([2, 3])
                                    if target == 0: state.intelligence = min(100, state.intelligence + gain)
                                    elif target == 1: state.aggression = min(100, state.aggression + gain)
                                    elif target == 2: state.curiosity = min(100, state.curiosity + gain)
                                    elif target == 3: state.sociability = min(100, state.sociability + gain)
                                    state.action = "PLAY"
                                    train_cutin.trigger("SUCCESS", target_name, gain, sound_mgr)
                                    state.speech_bubble = f"Training complete! {target_name} +{gain} UP!"
                                else:
                                    state.action = "STANDBY"  # FW表記
                                    train_cutin.trigger("FAIL", target_name, 0, sound_mgr)
                                    state.speech_bubble = "Couldn't make it this time... (FAIL)"
                    state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_time) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            now_u = int(time.time())
            serial_worker.send(f"TIME {now_u}")
            serial_worker.time_synced = True
            state.speech_bubble = f"Host time synced: {now_u}"
            state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_reborn) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            if sim_time < reborn_armed_until:
                # 二度押しで確定 (旧: ワンクリック即REBORNで誤爆すると世代が飛んでいた)
                reborn_armed_until = 0.0
                serial_worker.send("REBORN")
                state.speech_bubble = "Rebirth command sent! New generation awaits..."
                state.speech_timer = 3.5
                if not serial_worker.connected:
                    with serial_worker.state_lock:
                        offline_rebirth(state)
                        state.speech_bubble = f"Reborn as Gen {state.generation}! (offline sim)"
            else:
                reborn_armed_until = sim_time + 3.0
                state.speech_bubble = "REBORN: click again within 3s to confirm"
                state.speech_timer = 3.0

        if rl.check_collision_point_rec(mouse_pos, btn_photo) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            fn = f"inklife_snap_{int(time.time())}.png"
            rl.take_screenshot(fn)
            screenshot_msg = f"Snapshot saved: {fn}"
            screenshot_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_bench) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            serial_worker.send("BENCH")

        if rl.check_collision_point_rec(mouse_pos, btn_tourney) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            sound_mgr.play("click")
            with serial_worker.state_lock:
                my_fighter = Fighter.from_creature_state(state)
                peers_list = list(state.peers.values())
            tourney_mgr = TournamentManager(my_fighter, peers_list)
            tourney_ui = TournamentUI(tourney_mgr, sound_mgr)
            app_mode = AppMode.TOURNAMENT


        # 3Dモデル・盤面要求・E-Ink更新は多欄一貫読みのためstate_lock下
        with serial_worker.state_lock:
            # 3D ボクセルモデルのビルド (キャッシュにより変化時のみ再生成)
            voxel_model.build(
                state.species_id,
                state.action,
                state.mood,
                state.fuse,
                state.happiness,
                state.age_sec
            )

            # 現象盤の実盤面を要求 (+LIFE更新ごと。FIELDB 12行で返る。接続中のみ)
            if state.age_sec != last_field_age:
                last_field_age = state.age_sec
                if serial_worker.connected:
                    serial_worker.send("FIELDB")

        # 種・融合の定期再同期 (初回応答ロス対策。接続中10秒毎にSP/FZ/AFF/ID再要求)
            if serial_worker.connected and (sim_time - last_sync_time) > 10.0:
                last_sync_time = sim_time
                serial_worker.send("SP")
                serial_worker.send("FZ")
                serial_worker.send("ID")
                serial_worker.send("AFF")

            # バーチャル E-Ink の更新 (内容変化時のみ再構築＋転送。盤面到着も含む)
            # FW dispHash相当: 分丸め・成長段で秒ゆらぎ再構築を抑止、4形質でTRAIN直後 staleを防止
            ekey = (state.age_sec // 60, state.age_sec // GROWTH_SEC_PER_PX, state.action, state.mood,
                    tuple(state.fuse), state.last_event, len(state.peers),
                    state.health, state.hunger, state.energy, state.happiness,
                    state.intelligence, state.curiosity, state.aggression,
                    state.sociability, state.generation, state.species_id,
                    state.field_seq)
            if ekey != eink_key:
                eink_key = ekey
                eink.render(state, wall_synced=serial_worker.time_synced)

        # セリフ吹き出しタイマー
        if state.speech_timer > 0:
            state.speech_timer -= dt
            bubble_alpha = min(1.0, state.speech_timer)
        else:
            bubble_alpha = 0.0

        if screenshot_timer > 0:
            screenshot_timer -= dt

        # -----------------------------------------------------------------
        # 1. 3D シーン描画 (専用 650x760 レンダーテクスチャへ)
        # -----------------------------------------------------------------
        rl.begin_texture_mode(rt_3d)
        rl.clear_background(COL_BG_DARK)
        rl.begin_mode_3d(cam)

        # 3D シーン用ライティングシェーダー適用
        rl.begin_shader_mode(lighting_shader)

        # 浮遊テラリウム台座 (高級感のある二段サイバーポディウム)
        pedestal_base_pos = rl.Vector3(0.0, -0.08, 0.0)
        rl.draw_cylinder(pedestal_base_pos, 1.52, 1.62, 0.14, 36, rl.Color(28, 35, 48, 255))
        pedestal_top_pos = rl.Vector3(0.0, 0.01, 0.0)
        rl.draw_cylinder(pedestal_top_pos, 1.34, 1.34, 0.04, 36, rl.Color(44, 56, 78, 255))

        # 足元に広がる現象盤 (Brian's Brain 48x12) の 3D ホログラムセル
        # 実盤面 (FIELDB同期。未同期は空白)。1=発火シアン、2=減衰バイオレット
        cell_w = 0.052
        start_x = -24 * cell_w
        start_z = -6 * cell_w
        for fz in range(12):
            row = state.field_grid[fz]
            for fx in range(48):
                v = row[fx]
                if v == 0:
                    continue
                cx = start_x + fx * cell_w
                cz = start_z + fz * cell_w
                cell_col = rl.Color(0, 220, 240, 210) if v == 1 else rl.Color(160, 100, 255, 150)
                rl.draw_cube(rl.Vector3(cx, 0.035, cz), cell_w * 0.82, 0.015, cell_w * 0.82, cell_col)

        # キメラの 3D ボクセル描画
        # モーション計算: 呼吸、感情、クリック時のバウンド
        bounce_y = math.sin(click_bounce * math.pi) * 0.35
        if state.mood == "HAPPY" or state.action == "PLAY":
            hop_y = abs(math.sin(sim_time * 5.0)) * 0.18
            rot_y = math.sin(sim_time * 2.5) * 12.0
        elif state.mood == "SLEEPY" or state.action == "SLEEP":
            hop_y = -0.15
            rot_y = 0.0
        elif state.mood == "SICK":
            hop_y = math.sin(sim_time * 30.0) * 0.02  # ブルブル震え
            rot_y = math.sin(sim_time * 20.0) * 4.0
        else:
            hop_y = math.sin(sim_time * 2.0) * 0.04
            rot_y = math.sin(sim_time * 0.9) * 8.0

        chimera_pos = rl.Vector3(0.0, 0.82 + hop_y + bounce_y, 0.0)
        # MF2 トレーニング・カットイン演出のモーション合成
        cut_jump_y = 0.0
        cut_squash_x = 1.0
        cut_squash_y = 1.0
        cut_rot_z = 0.0
        if train_cutin.active:
            prog = (train_cutin.duration - train_cutin.timer) / train_cutin.duration
            if train_cutin.res == "GREAT":
                # 大ジャンプ + 宙返りスピン
                cut_jump_y = math.sin(prog * math.pi) * 1.65
                rot_y += prog * 720.0
                cut_squash_x = 1.0 - math.sin(prog * math.pi) * 0.18
                cut_squash_y = 1.0 + math.sin(prog * math.pi) * 0.28
            elif train_cutin.res == "SUCCESS":
                # リズミカルな小ジャンプ
                cut_jump_y = abs(math.sin(prog * math.pi * 3.0)) * 0.45
            elif train_cutin.res == "FAIL":
                # 前のめりにペタンと潰れる
                cut_jump_y = -0.22
                cut_squash_y = 0.52
                cut_squash_x = 1.38
            elif train_cutin.res == "SLACK":
                # 横を向いてゴロンと寝る
                cut_jump_y = -0.26
                cut_rot_z = 75.0
            elif train_cutin.res == "OVERWORK":
                # 力尽きてガクッと倒れる
                cut_jump_y = -0.32
                cut_squash_y = 0.65
                cut_rot_z = 40.0

        chimera_pos = rl.Vector3(0.0, 0.82 + hop_y + bounce_y + cut_jump_y, 0.0)
        voxel_model.draw(
            chimera_pos, scale=1.0, rot_y=rot_y, breathe=sim_time,
            squash_x=cut_squash_x, squash_y=cut_squash_y, rot_z=cut_rot_z
        )

        # MF2 カットイン・パーティクル (星屑 / 汗)
        for p in train_cutin.particles:
            p_col = rl.Color(p["col"].r, p["col"].g, p["col"].b, int(p["life"] * 255))
            rl.draw_cube(rl.Vector3(p["x"], p["y"], p["z"]), p["size"], p["size"], p["size"], p_col)

        rl.end_shader_mode()

        # 台座上の動的ドロップシャドウ (高さ連動でふんわり減衰)
        cur_h = hop_y + bounce_y + cut_jump_y
        shadow_scale = max(0.4, 0.85 - cur_h * 0.6)
        shadow_alpha = int(max(40, 160 - cur_h * 180))
        rl.draw_circle_3d(rl.Vector3(0, 0.032, 0), shadow_scale, rl.Vector3(1, 0, 0), 90.0, rl.Color(12, 16, 24, shadow_alpha))

        # テラリウムのサイバー発光リング
        ring_pulse = 0.85 + math.sin(sim_time * 3.0) * 0.15
        rl.draw_circle_3d(rl.Vector3(0, 0.034, 0), 1.35, rl.Vector3(1, 0, 0), 90.0, rl.Color(0, int(220 * ring_pulse), 240, 200))
        rl.draw_circle_3d(rl.Vector3(0, 0.034, 0), 1.53, rl.Vector3(1, 0, 0), 90.0, rl.Color(70, 100, 180, 150))

        # アンビエント浮遊パーティクル (光のエネルギー微粒子)
        for p in ambient_particles:
            p["y"] += p["speed"] * dt
            if p["y"] > 2.0:
                p["y"] = 0.1
                p["ang"] = (p["ang"] + 1.2) % (math.pi * 2)
            px = math.cos(p["ang"] + sim_time * 0.2) * p["rad"]
            pz = math.sin(p["ang"] + sim_time * 0.2) * p["rad"]
            p_alpha = int(min(1.0, math.sin((p["y"] - 0.1) / 1.9 * math.pi)) * 210)
            rl.draw_cube(rl.Vector3(px, p["y"], pz), 0.025, 0.025, 0.025, rl.Color(80, 220, 240, p_alpha))

        # 睡眠中の「Zzz」パーティクル
        if state.mood == "SLEEPY" or state.action == "SLEEP":
            for zi in range(3):
                z_phase = (sim_time * 0.4 + zi * 0.33) % 1.0
                zx = 0.5 + z_phase * 0.4
                zy = 1.3 + z_phase * 0.8
                zz = 0.2
                z_alpha = int((1.0 - z_phase) * 220)
                rl.draw_cube(rl.Vector3(zx, zy, zz), 0.08, 0.08, 0.08, rl.Color(160, 200, 255, z_alpha))

        rl.end_mode_3d()
        rl.end_texture_mode()

        # -----------------------------------------------------------------
        # 2. メイン画面描画 (3Dテクスチャ合成 & 2D UI)
        # -----------------------------------------------------------------
        rl.begin_drawing()
        rl.clear_background(COL_BG_DARK)

        # 3D RenderTexture を左側エリアに転送 (OpenGL Y反転)
        src_rec = rl.Rectangle(0, 0, rt_3d_w, -rt_3d_h)
        dst_rec = rl.Rectangle(0, 0, rt_3d_w, rt_3d_h)
        rl.draw_texture_pro(rt_3d.texture, src_rec, dst_rec, rl.Vector2(0, 0), 0.0, rl.WHITE)

        # 3D ビュー外枠
        rl.draw_line(650, 0, 650, WIN_H, COL_LINE)

        # 左上: タイトル & ステータスインジケーター
        rl.draw_text("InkLife 3D Companion", 24, 20, 22, COL_TXT_MAIN)
        rl.draw_text("Cybernetic Chimera Observation Station", 24, 46, 12, COL_TXT_DIM)

        # オンライン／オフライン表示
        conn_col = rl.Color(80, 240, 130, 255) if serial_worker.connected else rl.Color(240, 160, 60, 255)
        conn_label = f"ONLINE ({serial_worker.port_name})" if serial_worker.connected else "OFFLINE (SIMULATOR)"
        rl.draw_rectangle_rounded(rl.Rectangle(24, 68, 185, 24), 0.4, 4, rl.Color(25, 32, 45, 200))
        rl.draw_circle(36, 80, 4, conn_col)
        rl.draw_text(conn_label, 46, 74, 11, conn_col)

        # 3D領域 右上: MF2風 能力値ステータスパネル (POW, INT, SPD, SKI & ランク & コンディション)
        draw_mf2_status_panel(state, 395, 18)

        # キメラの吹き出し (Speech Bubble: カットイン中は非表示)
        # 右端は3D領域内 (x<345) に収める (MF2パネルへの被り防止)
        if bubble_alpha > 0.05 and not train_cutin.active:
            bub_text = state.speech_bubble
            tw = rl.measure_text(bub_text, 16)
            bw = tw + 32
            bx = max(30, min(345 - bw, 325 - tw // 2))
            by = 120
            bh = 40
            alpha_int = int(bubble_alpha * 255)
            rl.draw_rectangle_rounded(
                rl.Rectangle(bx, by, bw, bh), 0.3, 6,
                rl.Color(255, 255, 255, alpha_int)
            )
            # 下向き三角 (吹き出し内に収める)
            # 頂点は裏面カリング回避のため下頂点を2番目に置く (実測: 逆順は描画されない)
            px = max(bx + 16, min(bx + bw - 16, 325))
            rl.draw_triangle(
                rl.Vector2(px - 8, by + bh),
                rl.Vector2(px, by + bh + 10),
                rl.Vector2(px + 8, by + bh),
                rl.Color(255, 255, 255, alpha_int)
            )
            rl.draw_text(bub_text, bx + 16, by + 12, 16, rl.Color(20, 24, 32, alpha_int))

        # MF2 トレーニング・カットインバナー (画面中央ポップアップ)
        draw_cutin_banner(train_cutin)

        # 左下: 3D 操作ヒント
        rl.draw_text("L-Drag: Orbit Camera | Wheel: Zoom | Click Chimera: Pet | G: Reaction Game", 24, WIN_H - 28, 11, COL_TXT_DIM)

        # ===== 3. 右側: バーチャル E-Ink ディスプレイ (296x128 -> 592x256) =====
        eink_x = 668
        eink_y = 20
        eink.draw_on_screen(eink_x, eink_y, scale=2.0, state=state,
                            wall_synced=serial_worker.time_synced,
                            connected=serial_worker.connected)

        # ===== 4. 右側中段: 知人帳 (LoRa Mesh) レーダー & ソーシャルモニター =====
        panel_radar_y = 300
        rl.draw_rectangle_rounded(
            rl.Rectangle(660, panel_radar_y, 600, 160), 0.04, 6, COL_PANEL_BG
        )
        rl.draw_rectangle_rounded_lines(
            rl.Rectangle(660, panel_radar_y, 600, 160), 0.04, 6, COL_LINE
        )

        rl.draw_text("LoRa MESH RADAR / PEERS", 676, panel_radar_y + 12, 14, COL_ACCENT)
        with serial_worker.state_lock:
            peers_list = list(state.peers.values())
        rl.draw_text(f"Registered Peers: {len(peers_list)} / 6", 880, panel_radar_y + 12, 12, COL_TXT_DIM)

        if not peers_list:
            rl.draw_text("No peers detected. Listening for LoRa packets...", 676, panel_radar_y + 45, 13, COL_TXT_DIM)
            rl.draw_text("(When another InkLife device broadcasts, affinity & traits appear here)", 676, panel_radar_y + 72, 11, COL_TXT_DIM)
        else:
            # 知人カード描画
            for pi, peer in enumerate(peers_list[:4]):
                card_x = 676 + (pi % 2) * 290
                card_y = panel_radar_y + 42 + (pi // 2) * 52
                rl.draw_rectangle_rounded(rl.Rectangle(card_x, card_y, 280, 46), 0.15, 4, rl.Color(30, 38, 52, 255))
                # DID & 種族
                rl.draw_text(f"DID: {peer.did}", card_x + 10, card_y + 8, 12, COL_TXT_MAIN)
                # 好感度バー
                aff_col = rl.Color(255, 110, 130, 255) if peer.aff > 30 else (rl.Color(110, 180, 255, 255) if peer.aff < -20 else COL_ACCENT_AMB)
                rl.draw_text(f"AFF: {peer.aff:+d}", card_x + 120, card_y + 8, 12, aff_col)
                # RSSI
                rl.draw_text(f"RSSI: {peer.rssi} dBm", card_x + 10, card_y + 26, 10, COL_TXT_DIM)
                tag = "BONDED" if peer.aff >= 50 else ("RIVAL" if peer.aff <= -50 else "ACQUAINT")
                rl.draw_text(tag, card_x + 120, card_y + 26, 10, COL_TXT_DIM)

        # ===== 5. 右側下段: シリアルログ & ラボコントロール =====
        panel_lab_y = 475
        rl.draw_rectangle_rounded(
            rl.Rectangle(660, panel_lab_y, 600, 265), 0.04, 6, COL_PANEL_BG
        )
        rl.draw_rectangle_rounded_lines(
            rl.Rectangle(660, panel_lab_y, 600, 265), 0.04, 6, COL_LINE
        )

        # 左側: リアルタイムシリアルログミニビュー
        rl.draw_text("FIRMWARE SERIAL TELEMETRY", 676, panel_lab_y + 12, 12, COL_ACCENT)
        rl.draw_rectangle(676, panel_lab_y + 32, 230, 218, rl.Color(14, 17, 24, 255))
        rl.draw_rectangle_lines(676, panel_lab_y + 32, 230, 218, COL_LINE)

        # 最新ログ表示
        recent_logs = serial_worker.get_logs(13)
        for li, log_t in enumerate(recent_logs):
            l_col = COL_ACCENT if log_t.startswith("+EVT") else (rl.Color(110, 240, 140, 255) if log_t.startswith("+BORN") else COL_TXT_DIM)
            rl.draw_text(log_t[:30], 682, panel_lab_y + 38 + li * 16, 10, l_col)

        # 右側: お世話 & 実験ボタン群
        ctrl_x = 920
        rl.draw_text("LAB CONTROL / COMMANDS", ctrl_x, panel_lab_y + 12, 13, COL_ACCENT_AMB)

        # 形質レーダーグラフ風テキスト
        rl.draw_text(f"Intellect (IN): {state.intelligence:2d}   Curiosity (CU): {state.curiosity:2d}", ctrl_x, panel_lab_y + 38, 12, COL_TXT_MAIN)
        rl.draw_text(f"Aggress   (AG): {state.aggression:2d}   Sociable  (SO): {state.sociability:2d}", ctrl_x, panel_lab_y + 58, 12, COL_TXT_MAIN)
        gears_str = ", ".join([GEAR_NAMES_EN[g] for g in state.effective_gears if g < len(GEAR_NAMES_EN)]) or "None"
        rl.draw_text(f"Equipped Gears: {gears_str}", ctrl_x, panel_lab_y + 80, 11, COL_ACCENT)
        rl.draw_text(f"Brian's Brain CA: Act {state.field_activity} / Sym {state.field_symmetry}", ctrl_x, panel_lab_y + 96, 11, COL_TXT_DIM)

        # ボタン描画ヘルパー
        def draw_button(rec: rl.Rectangle, label: str, col_acc: rl.Color):
            hover = rl.check_collision_point_rec(mouse_pos, rec)
            bg = COL_BTN_HOVER if hover else COL_BTN
            rl.draw_rectangle_rounded(rec, 0.2, 4, bg)
            rl.draw_rectangle_rounded_lines(rec, 0.2, 4, col_acc if hover else COL_LINE)
            tw = rl.measure_text(label, 12)
            tx = int(rec.x + (rec.width - tw) / 2)
            ty = int(rec.y + (rec.height - 12) / 2)
            rl.draw_text(label, tx, ty, 12, col_acc if hover else COL_TXT_MAIN)

        draw_button(btn_train, "TRAIN", rl.Color(255, 180, 50, 255))
        draw_button(btn_reborn, "CONFIRM?" if sim_time < reborn_armed_until else "REBORN",
                    rl.Color(255, 110, 220, 255))
        draw_button(btn_photo, "SNAPSHOT", COL_ACCENT_AMB)
        draw_button(btn_tourney, "TOURNEY", rl.Color(255, 215, 0, 255))
        draw_button(btn_clean, "CLEAN", rl.Color(140, 220, 255, 255))
        draw_button(btn_bench, "BENCH", COL_ACCENT)
        draw_button(btn_cure, "CURE", rl.Color(150, 255, 170, 255))

        draw_button(btn_feed, "FEED", rl.Color(255, 140, 90, 255))
        draw_button(btn_play, "PLAY", rl.Color(100, 240, 160, 255))
        draw_button(btn_time, "SYNC TIME", COL_ACCENT)

        # スクリーンショット通知
        if screenshot_timer > 0:
            rl.draw_rectangle(676, panel_lab_y + 215, 568, 30, rl.Color(40, 120, 70, 230))
            rl.draw_text(screenshot_msg, 690, panel_lab_y + 222, 13, rl.WHITE)

        # 検査ゲームオーバーレイ (カウントダウン・GO・結果)
        if inspect_game is not None:
            ig = inspect_game
            rl.draw_rectangle(0, 0, WIN_W, WIN_H, rl.Color(8, 10, 16, 140))
            cx, cy = WIN_W // 2, WIN_H // 2 - 40
            if ig["phase"] == "COUNT":
                n = max(1, 3 - int((sim_time - ig["t0"]) / 0.6))
                rl.draw_text(str(n), cx - 30, cy - 60, 120, rl.WHITE)
                rl.draw_text("SPACE at GO!! (early = foul)", cx - 170, cy + 80, 16, COL_TXT_DIM)
            elif ig["phase"] == "GO":
                blink = (int(sim_time * 6) % 2 == 0)
                rl.draw_text("GO!!", cx - 90, cy - 60, 120,
                             rl.Color(100, 255, 150, 255) if blink else rl.WHITE)
                rl.draw_text("SPACE NOW!", cx - 80, cy + 80, 20, rl.Color(255, 220, 90, 255))
            else:
                names = ("PERFECT!", "GREAT!", "GOOD", "FAIL", "FLYING (foul)")
                g = ig.get("result", 3)
                rl.draw_text(names[g] if 0 <= g <= 4 else "FAIL",
                             cx - 110, cy - 50, 64, rl.Color(255, 215, 0, 255))

        # 形態図鑑オーバーレイ (Mトグル) は最前面
        if show_dex:
            draw_morph_dex(state)

        rl.end_drawing()

    # 5. 終了処理
    serial_worker.running = False
    sound_mgr.close()
    rl.unload_shader(lighting_shader)
    rl.unload_render_texture(rt_3d)
    eink.unload()
    rl.close_window()

if __name__ == "__main__":
    main()

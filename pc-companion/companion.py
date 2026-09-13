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
import threading
from typing import Optional, List
import pyray as rl

# 自作モジュール
from inkparser import CreatureState, InkProtocolParser, MORPH_NAMES, GEAR_NAMES, GEAR_NAMES_EN
from voxel_art import ChimeraVoxelModel
from virtual_eink import VirtualEInk

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

class SerialWorker:
    """バックグラウンドで ESP32-S3 とのシリアル通信を維持・自動再接続するスレッド"""
    def __init__(self, parser: InkProtocolParser, eink: VirtualEInk):
        self.parser = parser
        self.eink = eink
        self.ser: Optional[serial.Serial] = None
        self.connected = False
        self.running = True
        self.port_name = "AUTO"
        self.lock = threading.Lock()
        self.tx_queue: List[str] = []
        self.log_lines: List[str] = []

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def send(self, cmd: str):
        with self.lock:
            self.tx_queue.append(cmd.strip() + "\n")
            self._add_log(f"> {cmd.strip()}")

    def _add_log(self, text: str):
        self.log_lines.append(text)
        if len(self.log_lines) > 50:
            self.log_lines.pop(0)

    def _find_port(self) -> Optional[str]:
        if not SERIAL_AVAILABLE:
            return None
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
        # 3. 該当なし (無関係BTポート等への誤爆送信を避けるためNone)
        return None

    def _run(self):
        while self.running:
            if not self.connected:
                target_port = self._find_port()
                if target_port and SERIAL_AVAILABLE:
                    try:
                        s = serial.Serial(target_port, 115200, timeout=0.1)
                        self.ser = s
                        self.port_name = target_port
                        self.connected = True
                        self._add_log(f"[ONLINE] Connected to {target_port}")
                        # 初期同期コマンドの送信 (古い滞留コマンドは破棄)
                        with self.lock:
                            self.tx_queue.clear()
                        time.sleep(0.3)
                        now_unix = int(time.time())
                        self.send(f"TIME {now_unix}")
                        self.send("FZ")
                        self.send("SP")
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

                        # 受信行の読み出し
                        line_bytes = self.ser.readline()
                        if line_bytes:
                            line = line_bytes.decode("utf-8", errors="replace").strip()
                            if line:
                                self._add_log(line)
                                r = self.parser.parse_line(line)
                                if r and r.get("type") == "event":
                                    self.eink.push_log(r["event"], self.parser.state.age_sec)
                    else:
                        self.connected = False
                        self.ser = None
                except Exception as e:
                    self._add_log(f"[OFFLINE] Disconnected: {e}")
                    self.connected = False
                    self.ser = None
                    time.sleep(1.0)

            time.sleep(0.01)

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

    # デモ用の初期設定
    state.species_id = 24  # 第24世代ちびドラゴン (柴犬ピン耳 + 背中トゲ)
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

    # ボタン矩形定義
    btn_feed = rl.Rectangle(930, 680, 100, 36)
    btn_play = rl.Rectangle(1040, 680, 100, 36)
    btn_time = rl.Rectangle(1150, 680, 100, 36)
    btn_train = rl.Rectangle(930, 634, 100, 36)
    btn_reborn = rl.Rectangle(1040, 634, 100, 36)
    btn_photo = rl.Rectangle(1150, 634, 100, 36)
    btn_bench = rl.Rectangle(1150, 588, 100, 36)

    screenshot_msg = ""
    screenshot_timer = 0.0

    # E-Ink再描画ゲート (内容変化時のみ。毎フレーム37kループ回避)
    eink_key = None
    # 現象盤要求の追跡 (+LIFE更新ごとにFIELDBを1回)
    last_field_age = -1

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

        # マウス入力 & 3D カメラ制御
        mouse_pos = rl.get_mouse_position()
        in_3d_area = (mouse_pos.x < 650)  # 左側 3D 領域

        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT) and in_3d_area:
            mouse_dragging = True
            last_mouse_pos = mouse_pos
            # キメラクリック判定 (跳ねるリアクション)
            click_bounce = 1.0
            state.speech_bubble = "*purr* So happy to see you!"
            state.happiness = min(100, state.happiness + 2)
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

        # ボタン入力判定
        if rl.check_collision_point_rec(mouse_pos, btn_feed) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            serial_worker.send("FEED")
            state.hunger = max(0, state.hunger - 30)
            state.happiness = min(100, state.happiness + 10)
            state.action = "EAT"
            state.speech_bubble = "*munch munch* Delicious snack!"
            state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_play) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            serial_worker.send("PLAY")
            state.happiness = min(100, state.happiness + 15)
            state.energy = max(0, state.energy - 10)
            state.action = "PLAY"
            state.speech_bubble = "Yay! Playing games is awesome!"
            state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_train) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            serial_worker.send("TRAIN")
            state.energy = max(0, state.energy - 18)
            state.hunger = min(100, state.hunger + 12)
            state.action = "PLAY"
            state.speech_bubble = "Push it to the limit! Training hard!"
            state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_time) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            now_u = int(time.time())
            serial_worker.send(f"TIME {now_u}")
            state.speech_bubble = f"Host time synced: {now_u}"
            state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_reborn) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            serial_worker.send("REBORN")
            state.speech_bubble = "Rebirth command sent! New generation awaits..."
            state.speech_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_photo) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            # スクリーンショット撮影
            fn = f"inklife_snap_{int(time.time())}.png"
            rl.take_screenshot(fn)
            screenshot_msg = f"Snapshot saved: {fn}"
            screenshot_timer = 3.5

        if rl.check_collision_point_rec(mouse_pos, btn_bench) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            serial_worker.send("BENCH")

        # 3D ボクセルモデルのビルド (キャッシュにより変化時のみ再生成)
        voxel_model.build(
            state.species_id,
            state.action,
            state.mood,
            state.fuse,
            state.happiness
        )

        # 現象盤の実盤面を要求 (+LIFE更新ごと。FIELDB 12行で返る。接続中のみ)
        if state.age_sec != last_field_age:
            last_field_age = state.age_sec
            if serial_worker.connected:
                serial_worker.send("FIELDB")

        # バーチャル E-Ink の更新 (内容変化時のみ再構築＋転送。盤面到着も含む)
        ekey = (state.age_sec, state.action, state.mood, tuple(state.fuse),
                state.last_event, len(state.peers), state.health, state.hunger,
                state.energy, state.happiness, state.generation, state.species_id,
                state.field_seq)
        if ekey != eink_key:
            eink_key = ekey
            eink.render(state)

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
        voxel_model.draw(chimera_pos, scale=1.0, rot_y=rot_y, breathe=sim_time)

        rl.end_shader_mode()

        # 台座上の動的ドロップシャドウ (高さ連動でふんわり減衰)
        cur_h = hop_y + bounce_y
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

        # キメラの吹き出し (Speech Bubble)
        if bubble_alpha > 0.05:
            bub_text = state.speech_bubble
            tw = rl.measure_text(bub_text, 16)
            bx = max(30, min(500 - tw, 325 - tw // 2))
            by = 120
            bw = tw + 32
            bh = 40
            alpha_int = int(bubble_alpha * 255)
            rl.draw_rectangle_rounded(
                rl.Rectangle(bx, by, bw, bh), 0.3, 6,
                rl.Color(255, 255, 255, alpha_int)
            )
            # 下向き三角
            rl.draw_triangle(
                rl.Vector2(325 - 8, by + bh),
                rl.Vector2(325 + 8, by + bh),
                rl.Vector2(325, by + bh + 10),
                rl.Color(255, 255, 255, alpha_int)
            )
            rl.draw_text(bub_text, bx + 16, by + 12, 16, rl.Color(20, 24, 32, alpha_int))

        # 左下: 3D 操作ヒント
        rl.draw_text("L-Drag: Orbit Camera | Wheel: Zoom | Click Chimera: Pet", 24, WIN_H - 28, 11, COL_TXT_DIM)

        # ===== 3. 右側: バーチャル E-Ink ディスプレイ (296x128 -> 592x256) =====
        eink_x = 668
        eink_y = 20
        eink.draw_on_screen(eink_x, eink_y, scale=2.0, state=state)

        # ===== 4. 右側中段: 知人帳 (LoRa Mesh) レーダー & ソーシャルモニター =====
        panel_radar_y = 300
        rl.draw_rectangle_rounded(
            rl.Rectangle(660, panel_radar_y, 600, 160), 0.04, 6, COL_PANEL_BG
        )
        rl.draw_rectangle_rounded_lines(
            rl.Rectangle(660, panel_radar_y, 600, 160), 0.04, 6, COL_LINE
        )

        rl.draw_text("LoRa MESH RADAR / PEERS", 676, panel_radar_y + 12, 14, COL_ACCENT)
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
        recent_logs = serial_worker.log_lines[-13:]
        for li, log_t in enumerate(recent_logs):
            l_col = COL_ACCENT if log_t.startswith("+EVT") else (rl.Color(110, 240, 140, 255) if log_t.startswith("+BORN") else COL_TXT_DIM)
            rl.draw_text(log_t[:30], 682, panel_lab_y + 38 + li * 16, 10, l_col)

        # 右側: お世話 & 実験ボタン群
        ctrl_x = 920
        rl.draw_text("LAB CONTROL / COMMANDS", ctrl_x, panel_lab_y + 12, 13, COL_ACCENT_AMB)

        # 形質レーダーグラフ風テキスト
        rl.draw_text(f"Intellect (IN): {state.intelligence:2d}   Curiosity (CU): {state.curiosity:2d}", ctrl_x, panel_lab_y + 40, 12, COL_TXT_MAIN)
        rl.draw_text(f"Aggress   (AG): {state.aggression:2d}   Sociable  (SO): {state.sociability:2d}", ctrl_x, panel_lab_y + 60, 12, COL_TXT_MAIN)
        gears_str = ", ".join([GEAR_NAMES_EN[g] for g in state.effective_gears if g < len(GEAR_NAMES_EN)]) or "None"
        rl.draw_text(f"Equipped Gears: {gears_str}", ctrl_x, panel_lab_y + 84, 11, COL_ACCENT)
        rl.draw_text(f"Brian's Brain CA: Act {state.field_activity} / Sym {state.field_symmetry}", ctrl_x, panel_lab_y + 104, 11, COL_TXT_DIM)

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
        draw_button(btn_reborn, "REBORN", rl.Color(255, 110, 220, 255))
        draw_button(btn_photo, "SNAPSHOT", COL_ACCENT_AMB)
        draw_button(btn_bench, "BENCH", COL_ACCENT)

        draw_button(btn_feed, "FEED", rl.Color(255, 140, 90, 255))
        draw_button(btn_play, "PLAY", rl.Color(100, 240, 160, 255))
        draw_button(btn_time, "SYNC TIME", COL_ACCENT)

        # スクリーンショット通知
        if screenshot_timer > 0:
            rl.draw_rectangle(676, panel_lab_y + 215, 568, 30, rl.Color(40, 120, 70, 230))
            rl.draw_text(screenshot_msg, 690, panel_lab_y + 222, 13, rl.WHITE)

        rl.end_drawing()

    # 5. 終了処理
    serial_worker.running = False
    rl.unload_shader(lighting_shader)
    rl.unload_render_texture(rt_3d)
    eink.unload()
    rl.close_window()

if __name__ == "__main__":
    main()

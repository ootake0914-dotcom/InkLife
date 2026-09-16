# pc-companion/sound_effects.py
"""
InkLife 8-Bit Retro Sound Synthesizer (Zero-Asset In-Memory Sound Engine)
========================================================================
外部 WAV/MP3 ファイルに一切依存せず、Python 標準ライブラリ (wave, io, struct, math)
のみでメモリ上に直接 8-bit レトロ波形を合成し、Raylib オーディオで即座に再生します。
"""

import io
import wave
import struct
import math
from typing import Optional, Dict
import pyray as rl


def _synth_wav(
    notes: list,  # [(freq_or_tuple, duration_ms, wave_type, volume)]
    sample_rate: int = 44100
) -> bytes:
    """複数の周波数・音長シーケンスから 16-bit PCM WAV バイト列を合成 (ピッチスライド対応)"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)

        all_data = bytearray()
        for note in notes:
            freq_spec, dur_ms, wtype, vol = note
            n_samples = max(1, int(sample_rate * dur_ms / 1000))
            phase = 0.0

            f_start, f_end = (freq_spec, freq_spec) if isinstance(freq_spec, (int, float)) else freq_spec

            for i in range(n_samples):
                t_rel = i / n_samples
                cur_freq = f_start + (f_end - f_start) * t_rel
                phase_inc = 2.0 * math.pi * cur_freq / sample_rate

                # エンベロープ (急速アタック、自然減衰)
                if t_rel < 0.06:
                    env = t_rel / 0.06
                else:
                    env = max(0.0, 1.0 - (t_rel - 0.06) / 0.94)

                # 波形生成
                if wtype == 'square':  # ファミコン風矩形波 (Duty 50%)
                    raw = 1.0 if (phase % (2.0 * math.pi)) < math.pi else -1.0
                elif wtype == 'pulse':  # 細いパルス波 (Duty 25%)
                    raw = 1.0 if (phase % (2.0 * math.pi)) < (math.pi * 0.5) else -1.0
                elif wtype == 'triangle':  # ベース三角波
                    p = (phase % (2.0 * math.pi)) / (2.0 * math.pi)
                    raw = 4.0 * abs(p - 0.5) - 1.0
                elif wtype == 'noise':  # レトロノイズ
                    raw = ((i * 1103515245 + 12345) & 0x7FFF) / 16384.0 - 1.0
                else:  # サイン波
                    raw = math.sin(phase)

                phase += phase_inc
                sample = int(raw * env * vol * 28000)
                sample = max(-32767, min(32767, sample))
                all_data.extend(struct.pack('<h', sample))

        w.writeframes(all_data)
    return buf.getvalue()


class SoundManager:
    """8-bit レトロサウンド管理マネージャ"""
    
    def __init__(self):
        self.sounds: Dict[str, rl.Sound] = {}
        self.waves: Dict[str, rl.Wave] = {}
        self.audio_ready = False
        self.enabled = True

    def init_audio(self):
        """Raylib オーディオデバイスの初期化 & SE のインメモリプリロード"""
        try:
            if not rl.is_audio_device_ready():
                rl.init_audio_device()
            self.audio_ready = rl.is_audio_device_ready()
            if self.audio_ready:
                self._build_all_sounds()
                print("[SoundManager] 8-Bit Retro Audio Engine Initialized Successfully")
        except Exception as e:
            print(f"[SoundManager] WARNING: Audio initialization failed ({e})")
            self.audio_ready = False

    def _register(self, name: str, wav_bytes: bytes):
        try:
            wave_obj = rl.load_wave_from_memory(".wav", wav_bytes, len(wav_bytes))
            snd = rl.load_sound_from_wave(wave_obj)
            self.waves[name] = wave_obj
            self.sounds[name] = snd
        except Exception as e:
            print(f"[SoundManager] Failed to load sound {name}: {e}")

    def _build_all_sounds(self):
        # 1. ピッ (ボタン決定音: 1200Hz パルス波 40ms)
        self._register("click", _synth_wav([
            (1200, 40, 'pulse', 0.55)
        ]))

        # 2. テレレレーン！ (MF2式 特訓・大成功ファンファーレ: C5 -> E5 -> G5 -> C6 アルペジオ)
        self._register("train_great", _synth_wav([
            (523.25, 70, 'square', 0.65),   # C5
            (659.25, 70, 'square', 0.70),   # E5
            (783.99, 80, 'square', 0.75),   # G5
            (1046.50, 260, 'pulse', 0.85),  # C6 (キーンと響く)
        ]))

        # 3. ピロリン！ (特訓・成功: 660Hz -> 880Hz)
        self._register("train_success", _synth_wav([
            (659.25, 80, 'square', 0.60),
            (880.00, 160, 'pulse', 0.75),
        ]))

        # 4. ズコー… (特訓・失敗: 下降三角波 400Hz -> 200Hz)
        self._register("train_fail", _synth_wav([
            (440.00, 90, 'triangle', 0.60),
            (330.00, 90, 'triangle', 0.65),
            (220.00, 180, 'triangle', 0.70),
        ]))

        # 5. ポケ〜 (サボり: 脱力ピロピロ)
        self._register("train_slack", _synth_wav([
            (349.23, 100, 'pulse', 0.55),
            (293.66, 180, 'pulse', 0.50),
        ]))

        # 6. 警告ブザー！ (過労警告: 激しい矩形波パルス)
        self._register("overwork_alarm", _synth_wav([
            (880, 60, 'square', 0.85),
            (440, 60, 'square', 0.85),
            (880, 60, 'square', 0.85),
            (440, 120, 'square', 0.90),
        ]))

        # 7. ピリリッ！ (ポケステ接続・ドッキング音)
        self._register("dock", _synth_wav([
            (880.0, 45, 'pulse', 0.55),
            (1174.7, 50, 'pulse', 0.65),
            (1760.0, 90, 'pulse', 0.75),
        ]))

        # 16. パパパパーン！ (検査・PERFECT王冠ファンファーレ: G5 -> C6 -> E6 -> G6)
        self._register("perfect_fanfare", _synth_wav([
            (783.99, 70, 'square', 0.70),    # G5
            (1046.50, 70, 'square', 0.75),   # C6
            (1318.51, 70, 'square', 0.75),   # E6
            (1567.98, 300, 'pulse', 0.85),   # G6 (キーンと響く)
        ]))

        # 17. ブッブー！ (検査・お手つき失格: 低い矩形波2連)
        self._register("flying_buzz", _synth_wav([
            (196.00, 140, 'square', 0.70),
            (155.56, 220, 'square', 0.70),
        ]))

        # 18. キュッキュッ！ (掃除: 短い摩擦パルス3連)
        self._register("clean_scrub", _synth_wav([
            (1200, 35, 'pulse', 0.45),
            (1500, 35, 'pulse', 0.45),
            (1200, 35, 'pulse', 0.45),
        ]))

        # 19. ポロン♪ (お薬: 優しい回復アルペジオ A5 -> D6)
        self._register("cure_chime", _synth_wav([
            (880.00, 90, 'triangle', 0.60),
            (1174.66, 200, 'triangle', 0.65),
        ]))

        # 20. キラーン！ (進化: 上昇グリッサンド C6 -> C7)
        self._register("evolve_shine", _synth_wav([
            ((1046.50, 2093.00), 420, 'pulse', 0.75),
        ]))

        # 21. ピヨピヨ！ (おはよう: 小鳥のさえずり2連)
        self._register("ohayo_birds", _synth_wav([
            ((1567.98, 2093.00), 90, 'pulse', 0.55),
            ((1760.00, 2349.32), 130, 'pulse', 0.55),
        ]))

        # 8. 試合開始ゴング (ノイズ+矩形波 240Hz→75Hz 下降スライド 800ms)
        self._register("battle_gong", _synth_wav([
            ((240, 75), 800, 'square', 0.80),
        ]))

        # 9. 技発動(近接) (440Hz 矩形波 80ms)
        self._register("move_melee", _synth_wav([
            (440, 80, 'square', 0.65),
        ]))

        # 10. 技発動(遠距離) (300Hz→900Hz 三角波 220ms)
        self._register("move_ranged", _synth_wav([
            ((300, 900), 220, 'triangle', 0.70),
        ]))

        # 11. 打撃ヒット音 (ノイズ+低音パルス 70ms)
        self._register("hit_punch", _synth_wav([
            (120, 70, 'noise', 0.90),
        ]))

        # 12. 遠距離ヒット爆発音 (ノイズ+低周波減衰 280ms)
        self._register("hit_magic", _synth_wav([
            ((200, 60), 280, 'noise', 0.95),
        ]))

        # 13. 回避スライド音 (600Hz→200Hz 140ms)
        self._register("evade", _synth_wav([
            ((600, 200), 140, 'triangle', 0.55),
        ]))

        # 14. K.O.音 (500Hz→40Hz急降下 650ms)
        self._register("battle_ko", _synth_wav([
            ((500, 40), 650, 'square', 0.90),
        ]))

        # 15. 大会優勝ファンファーレ (C5-E5-G5-C6 華やかな和音アルペジオ 700ms)
        self._register("tourney_win", _synth_wav([
            (523.25, 120, 'square', 0.70),
            (659.25, 120, 'square', 0.75),
            (783.99, 140, 'square', 0.80),
            (1046.50, 320, 'pulse', 0.90),
        ]))

        # 22. もぐもぐ (FEED_OK: 低めの粒状パルス4連)
        self._register("eat_crunch", _synth_wav([
            (180, 45, 'noise', 0.55),
            (150, 45, 'noise', 0.50),
            (200, 45, 'noise', 0.55),
            (140, 70, 'noise', 0.45),
        ]))

        # 23. うれしい鳴き (PLAY_OK: 上昇2連チャープ)
        self._register("play_chirp", _synth_wav([
            ((700, 1100), 90, 'pulse', 0.55),
            ((900, 1500), 120, 'pulse', 0.60),
        ]))

        # 24. すやすや (ENTER_REST: 柔らかい下降2音)
        self._register("sleep_soft", _synth_wav([
            (523.25, 200, 'triangle', 0.45),
            (392.00, 320, 'triangle', 0.40),
        ]))

        # 25. おはよ (WAKE_OK: 短い上昇3音)
        self._register("wake_yawn", _synth_wav([
            (440.00, 90, 'triangle', 0.50),
            (554.37, 90, 'triangle', 0.55),
            (659.25, 160, 'triangle', 0.60),
        ]))

        # 26. バタン (FATIGUE: 脱力して倒れる低音)
        self._register("fatigue_thud", _synth_wav([
            ((320, 90), 220, 'square', 0.70),
            (90, 200, 'noise', 0.65),
        ]))

        # 27. きらきら (BONDED: 高音の粒3連)
        self._register("bond_twinkle", _synth_wav([
            (1318.51, 70, 'pulse', 0.45),
            (1567.98, 70, 'pulse', 0.50),
            (2093.00, 160, 'pulse', 0.55),
        ]))

        # 28. うなる (RIVAL: 低くざらつく2連)
        self._register("rival_growl", _synth_wav([
            (160, 160, 'noise', 0.60),
            (110, 240, 'square', 0.65),
        ]))

        # 29. ピコン (PEER_FOUND: レーダー反応)
        self._register("peer_ping", _synth_wav([
            (1046.50, 60, 'pulse', 0.50),
            (1568.00, 120, 'pulse', 0.45),
        ]))

        # 30. シュルッ (FOOD_TX/FOOD_RX: パケット送受信)
        self._register("packet_zip", _synth_wav([
            ((1800, 600), 160, 'triangle', 0.45),
        ]))

        # 31. ドン (COMBAT_WIN/LOSS: 決着の一撃)
        self._register("combat_hit", _synth_wav([
            (200, 80, 'noise', 0.85),
            ((260, 80), 240, 'square', 0.70),
        ]))

        # 32. ポン (TRADE_OK: 交換成立)
        self._register("trade_swap", _synth_wav([
            (880.00, 70, 'pulse', 0.50),
            (1174.66, 140, 'pulse', 0.55),
        ]))

        # 33. ファンファーレ小 (BIRTH_RX/EVOLVE_RX: 仲間の祝事)
        self._register("peer_fanfare", _synth_wav([
            (659.25, 90, 'square', 0.60),
            (880.00, 90, 'square', 0.65),
            (1318.51, 220, 'pulse', 0.70),
        ]))

        # 34. ちりん (GETWELL_RX: 回復の鈴)
        self._register("heal_bell", _synth_wav([
            (1760.00, 140, 'triangle', 0.50),
            (2093.00, 260, 'triangle', 0.45),
        ]))

        # 35. 夜のしじま (NIGHTFALL) / 36. 朝の光 (DAYBREAK)
        self._register("night_fall", _synth_wav([
            ((600, 300), 420, 'triangle', 0.45),
        ]))
        self._register("day_break", _synth_wav([
            ((400, 900), 300, 'triangle', 0.50),
            (1046.50, 200, 'pulse', 0.45),
        ]))

    def play(self, name: str):
        """サウンドの再生"""
        if not self.enabled or not self.audio_ready:
            return
        snd = self.sounds.get(name)
        if snd:
            rl.play_sound(snd)

    def close(self):
        """リソースの解放"""
        if self.audio_ready:
            for snd in self.sounds.values():
                try:
                    rl.unload_sound(snd)
                except:
                    pass
            for wav in self.waves.values():
                try:
                    rl.unload_wave(wav)
                except:
                    pass
            try:
                rl.close_audio_device()
            except:
                pass
            self.audio_ready = False

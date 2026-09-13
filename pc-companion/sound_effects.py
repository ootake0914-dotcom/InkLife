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
    notes: list,  # [(freq, duration_ms, wave_type, volume)]
    sample_rate: int = 44100
) -> bytes:
    """複数の周波数・音長シーケンスから 16-bit PCM WAV バイト列を合成"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        
        all_data = bytearray()
        for note in notes:
            freq, dur_ms, wtype, vol = note
            n_samples = int(sample_rate * dur_ms / 1000)
            phase = 0.0
            phase_inc = 2.0 * math.pi * freq / sample_rate
            
            for i in range(n_samples):
                t_rel = i / n_samples
                # エンベロープ (急速アタック、自然減衰)
                if t_rel < 0.08:
                    env = t_rel / 0.08
                else:
                    env = max(0.0, 1.0 - (t_rel - 0.08) / 0.92)
                
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

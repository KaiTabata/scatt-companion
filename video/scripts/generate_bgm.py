"""シネマティック ambient BGM を numpy で合成生成する (60 秒)。

権利完全クリア (このスクリプト = 私たちの著作物)。
構成:
  0-15s: 低音ドローン + スパース arpeggio (intro)
  15-30s: 中音 pad 重ね
  30-45s: 全レイヤー + ソフトな脈動
  45-60s: ドローン アウト
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 44100
DURATION = 60.0
OUT_WAV = Path(__file__).parent.parent / "public" / "bgm.wav"
OUT_MP3 = Path(__file__).parent.parent / "public" / "bgm.mp3"


def sine(freq: float, t: np.ndarray, phase: float = 0.0) -> np.ndarray:
    return np.sin(2 * np.pi * freq * t + phase)


def saw(freq: float, t: np.ndarray) -> np.ndarray:
    """三角に近い緩やかなサウンド (ハーモニクス 3 つ重ね)。"""
    return (sine(freq, t)
            + 0.45 * sine(freq * 2, t)
            + 0.18 * sine(freq * 3, t)) / 1.63


def lfo(rate: float, t: np.ndarray, depth: float = 1.0, offset: float = 0.0) -> np.ndarray:
    return offset + depth * np.sin(2 * np.pi * rate * t)


def adsr(t: np.ndarray, attack: float, hold: float, release: float) -> np.ndarray:
    """attack/hold/release で 0→1→0 のエンベロープ。"""
    out = np.zeros_like(t)
    a_mask = t < attack
    h_mask = (t >= attack) & (t < attack + hold)
    r_mask = (t >= attack + hold) & (t < attack + hold + release)
    out[a_mask] = t[a_mask] / attack
    out[h_mask] = 1.0
    out[r_mask] = 1.0 - (t[r_mask] - attack - hold) / release
    return out


def soft_clip(x: np.ndarray, amount: float = 1.5) -> np.ndarray:
    """tanh によるソフトクリッピング (歪みを少し)。"""
    return np.tanh(amount * x) / np.tanh(amount)


def main() -> None:
    n = int(SR * DURATION)
    t = np.linspace(0, DURATION, n, endpoint=False)

    # === レイヤー 1: 低音ドローン (A1 = 55Hz) ===
    drone_lfo = lfo(0.07, t, depth=0.06, offset=0.94)
    drone = (saw(55, t) + 0.6 * saw(82.5, t)) * drone_lfo  # A1 + E2 (1.5x)
    drone *= np.linspace(0, 1, n) ** 0.5  # fade in slowly
    fade_out = np.ones(n)
    fade_out[int(n * 0.85):] = np.linspace(1, 0, n - int(n * 0.85)) ** 1.5
    drone *= fade_out
    drone *= 0.20

    # === レイヤー 2: ミッド pad (A3 / C4 / E4 マイナーコード) ===
    pad_t = t.copy()
    pad_env = np.zeros_like(pad_t)
    # 15-50 秒のあいだ pad が鳴る
    pad_start = int(SR * 15.0)
    pad_end = int(SR * 50.0)
    pad_env[pad_start:pad_end] = 1.0
    # smooth fade
    pad_env = np.convolve(pad_env, np.ones(int(SR * 1.5)) / int(SR * 1.5), mode="same")
    pad_lfo = lfo(0.13, t, depth=0.12, offset=0.88)
    pad = (
        0.55 * saw(220.0, t)   # A3
        + 0.40 * saw(261.63, t) # C4
        + 0.35 * saw(329.63, t) # E4
    ) * pad_env * pad_lfo
    pad *= 0.10

    # === レイヤー 3: 高音アルペジオ (ぽつぽつ) ===
    arp = np.zeros_like(t)
    # シンプルな A minor のアルペジオ: A4 / C5 / E5 / A4 ...
    arp_notes = [440.0, 523.25, 659.25, 880.0, 659.25, 523.25]
    note_duration = 0.85
    for i, idx_start in enumerate(np.arange(5.0, 55.0, note_duration)):
        note = arp_notes[i % len(arp_notes)]
        note_t = idx_start
        # ADSR 風: 20ms attack, 0.4s hold, 0.4s release
        env_n = int(SR * 1.0)
        env_t = np.linspace(0, 1.0, env_n)
        env = adsr(env_t, attack=0.02, hold=0.30, release=0.65)
        start_n = int(SR * note_t)
        end_n = min(n, start_n + env_n)
        seg = sine(note, env_t[:end_n - start_n]) * env[:end_n - start_n]
        arp[start_n:end_n] += seg
    # 強度
    arp_env_global = np.zeros_like(t)
    arp_env_global[int(SR * 5):int(SR * 55)] = np.linspace(0.4, 1.0, int(SR * 50))
    arp *= arp_env_global * 0.05

    # === レイヤー 4: 微かなパーカッション (ソフトキック模倣) ===
    kick = np.zeros_like(t)
    kick_period = 1.2  # 秒
    for beat_t in np.arange(20.0, 45.0, kick_period):
        kick_env_n = int(SR * 0.4)
        kick_env = np.exp(-np.linspace(0, 6, kick_env_n))
        kick_freq_sweep = np.linspace(120, 50, kick_env_n)
        kick_sound = np.sin(2 * np.pi * np.cumsum(kick_freq_sweep) / SR) * kick_env
        start_n = int(SR * beat_t)
        end_n = min(n, start_n + kick_env_n)
        kick[start_n:end_n] += kick_sound[:end_n - start_n]
    kick *= 0.07

    # === ミックス + ソフトクリップ ===
    mix = drone + pad + arp + kick
    mix = soft_clip(mix, amount=1.3)
    # 最大値を 0.85 に
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix *= 0.85 / peak

    # ステレオに広げる (左右で微妙に位相をずらす)
    left = mix * 0.95
    right = np.roll(mix, int(SR * 0.005)) * 0.95
    stereo = np.stack([left, right], axis=1)

    # WAV 書き出し (16-bit PCM)
    stereo_i16 = (stereo * 32767).astype(np.int16)
    import wave
    with wave.open(str(OUT_WAV), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo_i16.tobytes())
    print(f"Saved WAV: {OUT_WAV} ({OUT_WAV.stat().st_size // 1024} KB)")

    # ffmpeg で MP3 化
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(OUT_WAV), "-codec:a", "libmp3lame",
         "-b:a", "192k", str(OUT_MP3)],
        check=True,
        capture_output=True,
    )
    print(f"Saved MP3: {OUT_MP3} ({OUT_MP3.stat().st_size // 1024} KB)")
    OUT_WAV.unlink()


if __name__ == "__main__":
    main()

"""SCATT データの分析関数群。伏射(prone)主軸 + 他姿勢対応。

各 trace を numpy で受け取り、射撃理論に基づく指標を計算する。

主要な前提:
  - samples: shape (N, 3) の np.ndarray (x_mm, y_mm, cant_rad)
  - sample_rate: Hz (典型 120)
  - trace_offset: shots テーブル由来の発射サンプル番号
    * samples[:trace_offset]    = pre-trigger (狙い・トリガープル中)
    * samples[trace_offset]     = 発射の瞬間
    * samples[trace_offset+1:]  = 反動・フォロースルー

伏射重視の指標:
  - last_window_quality (発射前 0.5 秒の R95、tremor power)
  - hold_time (速度が低い連続時間)
  - steadiness_score (合成スコア)
  - cant_drift (shot 間)
  - approach_pattern (狙いの近づき方)
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass
class TraceArrays:
    """生サンプルを numpy に整形して保持。"""
    samples: np.ndarray         # (N, 3)
    sample_rate: float
    trace_offset: int | None    # 発射サンプル番号 (なければ None)

    @property
    def n(self) -> int:
        return len(self.samples)

    @property
    def x(self) -> np.ndarray:
        return self.samples[:, 0]

    @property
    def y(self) -> np.ndarray:
        return self.samples[:, 1]

    @property
    def cant(self) -> np.ndarray:
        return self.samples[:, 2]

    @property
    def t(self) -> np.ndarray:
        """各サンプルの時刻 (秒、trace 内相対)。発射時刻を 0 にする。"""
        idx = np.arange(self.n) / self.sample_rate
        if self.trace_offset is not None:
            idx -= self.trace_offset / self.sample_rate
        return idx

    def pre(self) -> "TraceArrays":
        """pre-trigger 部分のみのビュー。"""
        if self.trace_offset is None:
            return self
        return TraceArrays(self.samples[:self.trace_offset], self.sample_rate, None)

    def post(self) -> "TraceArrays":
        """発射後(反動)部分のみのビュー。"""
        if self.trace_offset is None:
            return TraceArrays(self.samples[:0], self.sample_rate, None)
        return TraceArrays(self.samples[self.trace_offset:], self.sample_rate, None)


def to_trace_arrays(samples: list[tuple[float, float, float]],
                    sample_rate: float,
                    trace_offset: int | None) -> TraceArrays:
    return TraceArrays(np.asarray(samples, dtype=np.float32), float(sample_rate), trace_offset)


# ----- 速度 -----

def velocity(t: TraceArrays) -> np.ndarray:
    """各サンプル間の速度 (mm/s)、長さ n-1。"""
    if t.n < 2:
        return np.zeros(0)
    dx = np.diff(t.x)
    dy = np.diff(t.y)
    return np.hypot(dx, dy) * t.sample_rate


def velocity_stats(v: np.ndarray) -> dict:
    if len(v) == 0:
        return {"mean": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "mean": float(np.mean(v)),
        "max": float(np.max(v)),
        "p50": float(np.percentile(v, 50)),
        "p95": float(np.percentile(v, 95)),
    }


# ----- 周波数解析 (FFT) -----

def spectrum(signal: np.ndarray, sample_rate: float,
             detrend: bool = True, hann: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """単側 FFT。返り値 (freq_hz, magnitude)。"""
    n = len(signal)
    if n < 16:
        return np.zeros(0), np.zeros(0)
    x = signal.astype(np.float64)
    if detrend:
        x = x - np.mean(x)
    if hann:
        x = x * np.hanning(n)
    spec = np.fft.rfft(x)
    mag = np.abs(spec) / n
    freq = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    return freq, mag


def tremor_band(freq: np.ndarray, mag: np.ndarray,
                low: float = 8.0, high: float = 12.0) -> float:
    """指定帯域のパワー合計を返す(振戦帯域のエネルギー)。"""
    if len(freq) == 0:
        return 0.0
    mask = (freq >= low) & (freq <= high)
    return float(np.sum(mag[mask] ** 2))


def breathing_band(freq: np.ndarray, mag: np.ndarray,
                   low: float = 0.15, high: float = 0.5) -> float:
    """呼吸帯域のパワー合計(0.15-0.5 Hz)。"""
    return tremor_band(freq, mag, low, high)


# ----- Pre-trigger 安定度 -----

def stability_window(t: TraceArrays, seconds: float) -> dict:
    """発射の seconds 秒前 〜 発射の瞬間 までの軌跡安定度を返す。"""
    if t.trace_offset is None or t.trace_offset <= 0:
        return {}
    n_samples = int(round(seconds * t.sample_rate))
    end = t.trace_offset
    start = max(0, end - n_samples)
    if end - start < 2:
        return {}
    seg = t.samples[start:end]
    cx, cy = float(np.mean(seg[:, 0])), float(np.mean(seg[:, 1]))
    rx = seg[:, 0] - cx
    ry = seg[:, 1] - cy
    r = np.hypot(rx, ry)
    return {
        "window_s": seconds,
        "n_samples": int(end - start),
        "center_x": cx, "center_y": cy,
        "std_x": float(np.std(seg[:, 0])),
        "std_y": float(np.std(seg[:, 1])),
        "r_mean": float(np.mean(r)),
        "r_max": float(np.max(r)),
        "r95": float(np.percentile(r, 95)),  # 95% を含む円の半径
        "area_r95_mm2": float(np.pi * np.percentile(r, 95) ** 2),
    }


def stability_multi(t: TraceArrays, windows=(0.5, 1.0, 2.0, 3.0)) -> list[dict]:
    return [s for s in (stability_window(t, w) for w in windows) if s]


# ----- Hold / Aim / Trigger フェーズ分解 -----

def segment_phases(t: TraceArrays,
                   hold_thresh: float = 60.0,
                   aim_thresh: float = 20.0) -> dict:
    """速度ベースで pre-trigger を Hold/Aim/Trigger に大別。

    Hold:    粗い狙い(>= hold_thresh mm/s)
    Aim:     精密な狙い(aim_thresh ~ hold_thresh)
    Trigger: 最終ホールド(< aim_thresh)

    戻り値: 各フェーズの (duration, fraction, mean_velocity)
    """
    if t.trace_offset is None or t.trace_offset < 2:
        return {}
    pre = t.pre()
    v = velocity(pre)
    if len(v) == 0:
        return {}
    holds = v >= hold_thresh
    triggers = v < aim_thresh
    aims = ~holds & ~triggers
    dt = 1.0 / t.sample_rate
    out = {}
    for name, mask in (("hold", holds), ("aim", aims), ("trigger", triggers)):
        n = int(np.sum(mask))
        out[name] = {
            "n_samples": n,
            "duration_s": n * dt,
            "fraction": float(n / len(v)) if len(v) else 0.0,
            "mean_velocity": float(np.mean(v[mask])) if n else 0.0,
        }
    out["pre_trigger_duration_s"] = len(v) * dt
    return out


# ----- shot 間ドリフト -----

def group_drift(shots: list[dict]) -> dict:
    """複数 shot の発射点 (x,y) と Cant の系列から、重心ドリフトと相関を返す。

    shots: [{"x": .., "y": .., "cant": ..(rad), "shot_id": ..}, ...]
    """
    if len(shots) < 2:
        return {}
    xs = np.array([s["x"] for s in shots])
    ys = np.array([s["y"] for s in shots])
    cants = np.array([s["cant"] for s in shots])
    cx, cy = float(np.mean(xs)), float(np.mean(ys))
    rs = np.hypot(xs - cx, ys - cy)
    drift = float(np.sum(np.hypot(np.diff(xs), np.diff(ys))) / max(1, len(shots) - 1))
    return {
        "n_shots": len(shots),
        "center_x": cx, "center_y": cy,
        "r_mean": float(np.mean(rs)),
        "r_max": float(np.max(rs)),
        "r95": float(np.percentile(rs, 95)),
        "mean_drift_per_shot_mm": drift,
        "cant_mean_rad": float(np.mean(cants)),
        "cant_std_rad": float(np.std(cants)),
        "corr_cant_x": float(np.corrcoef(cants, xs)[0, 1]) if len(shots) >= 3 else 0.0,
        "corr_cant_y": float(np.corrcoef(cants, ys)[0, 1]) if len(shots) >= 3 else 0.0,
    }


# ----- 伏射特化指標 -----

def hold_time(t: TraceArrays, vel_thresh: float = 15.0,
              min_duration_s: float = 0.5) -> dict:
    """速度 < vel_thresh が連続している区間の最長時間 (= 最終ホールド時間)。

    伏射では発射直前に「速度 15mm/s 以下が 0.5〜2 秒継続」が理想とされる。
    """
    if t.trace_offset is None or t.trace_offset < 2:
        return {"hold_s": 0.0, "longest_hold_s": 0.0}
    pre = t.pre()
    v = velocity(pre)
    if len(v) == 0:
        return {"hold_s": 0.0, "longest_hold_s": 0.0}
    is_hold = v < vel_thresh
    # 発射直前から遡って連続している長さ
    tail_run = 0
    for b in is_hold[::-1]:
        if b:
            tail_run += 1
        else:
            break
    # 全体での最長連続区間
    longest = 0
    cur = 0
    for b in is_hold:
        if b:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    dt = 1.0 / t.sample_rate
    return {
        "hold_s": tail_run * dt,
        "longest_hold_s": longest * dt,
        "vel_thresh": vel_thresh,
    }


def last_window_quality(t: TraceArrays, window_s: float = 0.5) -> dict:
    """発射直前 window_s 秒の品質指標(伏射では 0.5 秒が最重要)。"""
    if t.trace_offset is None or t.trace_offset < 2:
        return {}
    n_w = max(2, int(round(window_s * t.sample_rate)))
    end = t.trace_offset
    start = max(0, end - n_w)
    seg = t.samples[start:end]
    if len(seg) < 2:
        return {}
    cx, cy = float(np.mean(seg[:, 0])), float(np.mean(seg[:, 1]))
    r = np.hypot(seg[:, 0] - cx, seg[:, 1] - cy)
    vx = np.diff(seg[:, 0]) * t.sample_rate
    vy = np.diff(seg[:, 1]) * t.sample_rate
    v = np.hypot(vx, vy)
    freq, mag = spectrum(seg[:, 0] - cx, t.sample_rate)
    return {
        "window_s": window_s,
        "r_mean": float(np.mean(r)),
        "r95": float(np.percentile(r, 95)),
        "v_mean": float(np.mean(v)),
        "v_max": float(np.max(v)),
        "cant_std_rad": float(np.std(seg[:, 2])),
        "tremor_power": tremor_band(freq, mag),
    }


def steadiness_score(t: TraceArrays) -> dict:
    """伏射向けの合成安定度スコア (0〜100、高いほど良い)。

    式: 100 - (R95(1s) [mm] × 10 + tremor_power × 1000 + |cant_drift| × 100)
    伏射では:
      - R95(1s) 1mm 以下 = 上級者
      - tremor_power 0.01 以下 = 安定
    """
    lq = last_window_quality(t, 1.0)
    if not lq:
        return {"score": None}
    score = 100.0 - (
        lq["r95"] * 10.0
        + lq["tremor_power"] * 1000.0
        + abs(lq.get("cant_std_rad", 0.0)) * 100.0
    )
    return {
        "score": float(max(0.0, min(100.0, score))),
        "r95_1s": lq["r95"],
        "tremor_power": lq["tremor_power"],
        "cant_std": lq.get("cant_std_rad", 0.0),
    }


def approach_pattern(t: TraceArrays, window_s: float = 2.0) -> dict:
    """狙いの近づき方: 発射前 window_s 秒で R(中心距離) がどう変化するか。

    - 単調減少 = まっすぐ収束 (理想)
    - 振動 = 狙い直しが多い
    """
    if t.trace_offset is None or t.trace_offset < 4:
        return {}
    n_w = int(round(window_s * t.sample_rate))
    start = max(0, t.trace_offset - n_w)
    end = t.trace_offset
    if end - start < 4:
        return {}
    seg = t.samples[start:end]
    fx, fy = float(t.samples[t.trace_offset, 0]), float(t.samples[t.trace_offset, 1])
    r_to_fire = np.hypot(seg[:, 0] - fx, seg[:, 1] - fy)
    # 単調減少度: |diff < 0 のサンプル数| / 全体
    diffs = np.diff(r_to_fire)
    monotonic_frac = float(np.sum(diffs < 0) / len(diffs))
    # 振動数: 符号反転数 / 秒
    sign_changes = int(np.sum(np.diff(np.sign(diffs)) != 0))
    return {
        "window_s": window_s,
        "r_initial_mm": float(r_to_fire[0]),
        "r_final_mm": float(r_to_fire[-1]),
        "monotonic_fraction": monotonic_frac,
        "sign_changes_per_s": float(sign_changes / window_s),
    }


def ten_a_percent(t: TraceArrays, window_s: float, ring_radius_mm: float) -> dict:
    """発射前 window_s 秒、ターゲット中心から半径 ring_radius_mm 以内に
    照準があった時間の割合 (%)。SCATT の "10a" / "10a5" 互換指標。

    50m ライフル基準:
      - 10 ring 半径   = 5.2 mm  → "10a"
      - Inner 10 半径  = 2.5 mm  → "10a5" (10.5 相当)
    """
    if t.trace_offset is None or t.trace_offset < 2:
        return {}
    n_w = max(1, int(round(window_s * t.sample_rate)))
    end = t.trace_offset
    start = max(0, end - n_w)
    seg = t.samples[start:end]
    if len(seg) < 1:
        return {}
    r = np.hypot(seg[:, 0], seg[:, 1])
    pct = float(np.sum(r <= ring_radius_mm) / len(seg) * 100.0)
    return {"window_s": window_s, "ring_radius_mm": ring_radius_mm, "percent": pct}


def recovery_dispersion(t: TraceArrays, window_s: float = 1.0) -> dict:
    """発射後 window_s 秒の軌跡の R95(反動からの戻り具合)。"""
    if t.trace_offset is None or t.trace_offset >= t.n - 2:
        return {}
    n_w = int(round(window_s * t.sample_rate))
    start = t.trace_offset
    end = min(t.n, start + n_w)
    seg = t.samples[start:end]
    if len(seg) < 2:
        return {}
    fx, fy = float(seg[0, 0]), float(seg[0, 1])
    r = np.hypot(seg[:, 0] - fx, seg[:, 1] - fy)
    return {
        "window_s": window_s,
        "r_max_mm": float(np.max(r)),
        "r_final_mm": float(r[-1]),
        "recovery_ratio": float(r[-1] / max(np.max(r), 1e-6)),
    }


def recoil_detailed(t: TraceArrays, window_s: float = 1.0,
                    settle_threshold_mm: float = 5.0) -> dict:
    """発射後の反動を詳細に分析。発射点を原点とした相対挙動。

    返り値:
      peak_r_mm        : 発射後の最大変位 (反動の振幅)
      peak_t_s         : 最大変位までの時間
      direction_deg    : 反動初期 (50ms) の方向 (atan2、0°=右、90°=上)
      impulse_mm       : 50ms 時点の変位
      settle_time_s    : 半径 settle_threshold_mm 以内に戻る時間 (None=戻らず)
      final_r_mm       : window 終端での残存ズレ
      post_05_r95_mm   : 発射後 0.5 秒の照準ブレ円 (フォロースルー安定度)
      post_v_mean      : 発射後の平均速度 (mm/s)
      direction_std_deg: 発射後 100-500ms の動きベクトル方向の標準偏差 (低い=単方向反動)
    """
    if t.trace_offset is None or t.trace_offset >= t.n - 2:
        return {}
    n_w = int(round(window_s * t.sample_rate))
    start = t.trace_offset
    end = min(t.n, start + n_w)
    seg = t.samples[start:end]
    if len(seg) < 3:
        return {}
    fx, fy = float(seg[0, 0]), float(seg[0, 1])
    rx = seg[:, 0] - fx
    ry = seg[:, 1] - fy
    r = np.hypot(rx, ry)
    peak_idx = int(np.argmax(r))

    # 反動方向: 発射後 50ms の動きベクトル
    impulse_n = max(1, int(round(0.05 * t.sample_rate)))
    idx_imp = min(impulse_n, len(seg) - 1)
    impulse_dx = float(rx[idx_imp])
    impulse_dy = float(ry[idx_imp])
    direction_deg = float(np.degrees(np.arctan2(impulse_dy, impulse_dx)))
    impulse_mm = float(np.hypot(impulse_dx, impulse_dy))

    # 戻り時間: peak 後に settle_threshold 以内に最初に戻るまで
    settle_idx = None
    for i in range(peak_idx + 1, len(r)):
        if r[i] <= settle_threshold_mm:
            settle_idx = i
            break
    settle_time = (settle_idx / t.sample_rate) if settle_idx is not None else None

    # 発射後 0.5 秒の R95 (フォロースルー安定)
    n_05 = min(len(seg), max(2, int(round(0.5 * t.sample_rate))))
    post_seg = seg[:n_05]
    pcx = float(np.mean(post_seg[:, 0]))
    pcy = float(np.mean(post_seg[:, 1]))
    post_r = np.hypot(post_seg[:, 0] - pcx, post_seg[:, 1] - pcy)
    post_r95 = float(np.percentile(post_r, 95))

    # 反動方向の標準偏差 (100ms 〜 500ms の動きベクトルの atan2 散らばり)
    n_lo = int(round(0.1 * t.sample_rate))
    n_hi = int(round(0.5 * t.sample_rate))
    n_lo = min(n_lo, len(seg) - 1)
    n_hi = min(n_hi, len(seg) - 1)
    if n_hi > n_lo + 2:
        dxs = np.diff(seg[n_lo:n_hi, 0])
        dys = np.diff(seg[n_lo:n_hi, 1])
        angs = np.arctan2(dys, dxs)
        # 円形統計: 平均方向の周りの分散
        mean_x = np.mean(np.cos(angs))
        mean_y = np.mean(np.sin(angs))
        R = np.hypot(mean_x, mean_y)
        circ_std = np.sqrt(-2.0 * np.log(R)) if R > 1e-6 else np.pi
        direction_std_deg = float(np.degrees(circ_std))
    else:
        direction_std_deg = 0.0

    # 平均速度
    if len(rx) > 1:
        v = np.hypot(np.diff(seg[:, 0]), np.diff(seg[:, 1])) * t.sample_rate
        post_v_mean = float(np.mean(v))
    else:
        post_v_mean = 0.0

    return {
        "window_s": window_s,
        "peak_r_mm": float(r[peak_idx]),
        "peak_t_s": float(peak_idx / t.sample_rate),
        "direction_deg": direction_deg,
        "impulse_mm": impulse_mm,
        "settle_time_s": settle_time,
        "final_r_mm": float(r[-1]),
        "post_05_r95_mm": post_r95,
        "post_v_mean": post_v_mean,
        "direction_std_deg": direction_std_deg,
    }


# ----- 1 trace 全指標まとめ -----

def summarize(t: TraceArrays) -> dict:
    """trace + shot から伏射向け全指標を一括算出。GUI 表示の中心。"""
    v_pre = velocity(t.pre())
    v_post = velocity(t.post())
    freq, mag = spectrum(t.pre().x - np.mean(t.pre().x), t.sample_rate) if t.pre().n > 16 else (np.zeros(0), np.zeros(0))
    return {
        "n_samples": t.n,
        "trace_offset": t.trace_offset,
        "duration_s": t.n / t.sample_rate,
        "pre_duration_s": (t.trace_offset or 0) / t.sample_rate,
        "post_duration_s": ((t.n - (t.trace_offset or t.n)) / t.sample_rate),
        "v_pre": velocity_stats(v_pre),
        "v_post": velocity_stats(v_post),
        "stability": stability_multi(t, (0.5, 1.0, 2.0, 3.0)),
        "last_05s": last_window_quality(t, 0.5),
        "last_10s": last_window_quality(t, 1.0),
        "phases": segment_phases(t),
        "hold": hold_time(t),
        "approach": approach_pattern(t),
        "recovery": recovery_dispersion(t),
        "recoil": recoil_detailed(t),
        "steadiness": steadiness_score(t),
        # SCATT 互換: 10a-1.0 / 10a-0.5 (どちらも 10-ring R≤5.2mm)
        # 10b-1.0 / 10b-0.5 (inner-10 R≤2.5mm)
        # 9c / 9d は 9-ring 系 (R≤13.2mm)
        "ten_a_1s":   ten_a_percent(t, 1.0, 5.2),   # 本家 "10a"
        "ten_a_05s":  ten_a_percent(t, 0.5, 5.2),   # 本家 "10a-0.5" (= 10a5 表記)
        "ten_b_1s":   ten_a_percent(t, 1.0, 2.5),   # 本家 "10b" (inner-10)
        "ten_b_05s":  ten_a_percent(t, 0.5, 2.5),
        "nine_c_1s":  ten_a_percent(t, 1.0, 13.2),  # 本家 "9c"
        "nine_c_05s": ten_a_percent(t, 0.5, 13.2),
        "tremor_power_pre": tremor_band(freq, mag),
        "breathing_power_pre": breathing_band(freq, mag),
        "spectrum_peak_hz": float(freq[int(np.argmax(mag))]) if len(mag) > 0 else 0.0,
    }

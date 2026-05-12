"""scatt_analysis: 合成データに対する summarize() の sanity チェック。"""

import math

import numpy as np
import pytest

import scatt_analysis as A
import scatt_target as T


def make_trace(n=240, fs=120.0, fire_at=180, amp=2.0):
    """単純な周期動きを持つ合成 trace を生成。"""
    t = np.arange(n) / fs
    x = amp * np.sin(2 * math.pi * 1.5 * t)   # 1.5Hz, 心拍由来の帯域
    y = amp * 0.3 * np.cos(2 * math.pi * 1.5 * t)
    cant = np.zeros(n)
    samples = np.stack([x, y, cant], axis=1).astype(np.float32)
    return A.TraceArrays(samples, fs, fire_at)


def test_summarize_basic_keys():
    """summarize() が期待されるキーをすべて返す。"""
    tr = make_trace()
    s = A.summarize(tr)
    expected_keys = {
        "n_samples", "trace_offset", "duration_s",
        "v_pre", "v_post", "stability",
        "ten_a_1s", "ten_a_05s", "ten_b_1s", "ten_b_05s",
        "nine_c_1s", "nine_c_05s",
        "recoil", "hold", "approach", "recovery", "steadiness",
    }
    missing = expected_keys - set(s.keys())
    assert not missing, f"missing keys: {missing}"


def test_ten_a_uses_current_discipline():
    """50m と 10m エアライフルで 10a の半径が異なれば結果も変わる。"""
    tr = make_trace(amp=0.3)  # 大きく動かない trace
    T.set_current("rifle_50m")
    a50 = A.summarize(tr)["ten_a_1s"]["ring_radius_mm"]
    T.set_current("rifle_10m")
    a10 = A.summarize(tr)["ten_a_1s"]["ring_radius_mm"]
    T.set_current("rifle_50m")
    assert a50 == 5.2
    assert a10 == 0.25


def test_zero_motion_perfect_ten_a():
    """完全に中心 (0,0) 静止なら 10a = 100%。"""
    n = 240
    samples = np.zeros((n, 3), dtype=np.float32)
    tr = A.TraceArrays(samples, 120.0, n - 1)
    s = A.summarize(tr)
    assert s["ten_a_1s"]["percent"] == pytest.approx(100.0, abs=0.1)


def test_velocity_pre_post():
    """発射前後の velocity 統計が辞書として返る。"""
    tr = make_trace()
    s = A.summarize(tr)
    assert "mean" in s["v_pre"] and "max" in s["v_pre"]
    assert s["v_pre"]["mean"] >= 0

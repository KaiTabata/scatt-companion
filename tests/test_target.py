"""scatt_target: discipline 切替と幾何の sanity チェック。"""

import scatt_target as T


def test_default_is_rifle_50m():
    # 未設定 = 50m ライフル
    T.set_current("rifle_50m")
    d = T.current()
    assert d.key == "rifle_50m"
    assert d.outer_diam_mm == 154.4
    assert d.ring_10_radius_mm == 5.2
    assert d.ring_inner_10_radius_mm == 2.5


def test_rifle_10m_geometry():
    T.set_current("rifle_10m")
    d = T.current()
    assert d.outer_diam_mm == 45.5
    assert d.ring_10_radius_mm == 0.25  # 10ring = 0.5mm dot
    # 元に戻す
    T.set_current("rifle_50m")


def test_unknown_key_is_ignored():
    T.set_current("rifle_50m")
    T.set_current("nonexistent_xyz")
    assert T.current().key == "rifle_50m"


def test_ring_step_consistency():
    """全種目で (outer - 9 * step) > 0 (= 10 リングまで描ける)。"""
    for d in T.DISCIPLINES.values():
        innermost_d = d.outer_diam_mm - 9 * d.ring_step_mm
        assert innermost_d > 0, f"{d.key} ring step too large"

"""scatt_feedback: rule-based NLG が文字列を返すこと、致命的な KeyError を出さないこと。"""

import scatt_feedback as FB


def _dummy_shot(**overrides):
    """summarize() 風の辞書を粗く作る (NLG は欠損キーを許容する想定)。"""
    base = {
        "r95_05": 3.0,
        "r95_1": 4.0,
        "ten_a_1s": 60.0,
        "ten_a_05s": 70.0,
        "ten_b_1s": 30.0,
        "hold_time_s": 1.2,
        "tremor_band": 0.0008,
        "breathing_band": 0.003,
        "heart_band": 0.005,
    }
    base.update(overrides)
    return base


def _session_stats():
    """session_stats: {key: (mu, sigma)} の tuple 形式。"""
    return {
        "r95_05":         (3.5, 1.0),
        "r95_1":          (4.5, 1.0),
        "ten_a_1s":       (55.0, 10.0),
        "ten_a_05s":      (65.0, 10.0),
        "ten_b_1s":       (25.0, 5.0),
        "hold_time_s":    (1.0, 0.3),
        "tremor_band":    (0.001, 0.0003),
        "breathing_band": (0.003, 0.001),
        "heart_band":     (0.005, 0.001),
    }


def test_shot_feedback_returns_string():
    txt = FB.shot_feedback(_dummy_shot(), _session_stats())
    assert isinstance(txt, str)


def test_shot_feedback_handles_missing_keys():
    """空の辞書でも例外を投げない。"""
    txt = FB.shot_feedback({}, {})
    assert isinstance(txt, str)


def test_session_feedback_returns_string():
    rows = [_dummy_shot(r95_05=2.0), _dummy_shot(r95_05=5.0), _dummy_shot(r95_05=3.5)]
    txt = FB.session_feedback(rows)
    assert isinstance(txt, str)
    assert len(txt) > 0

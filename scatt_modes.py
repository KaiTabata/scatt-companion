"""射撃モード — Prone / AR / ホールド練習。

各モードは Dashboard のレイアウト (KPI 4 枠 + デフォルトグラフ枠 + 表示要素)
を一括設定するプリセット。ホーム画面で選択 → SETTINGS の layout/* を一括書換。

discipline (rifle_50m / rifle_10m / pistol_10m) と独立した「使い方」軸。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    description: str
    # 推奨 discipline (rifle_50m / rifle_10m / pistol_10m)
    suggested_discipline: str
    # 主役 KPI 4 枚 (METRICS の key)
    hero_kpis: tuple[str, ...]
    # デフォルトグラフ 9 枠 (GRAPH_KINDS の key)
    default_graphs: tuple[str, ...]
    # 大型「撃発時速度」ウィジェットの表示
    show_velocity_hero: bool = False
    # Live ステータスバーに 速度 + 心拍 + 銃傾き
    enhanced_status_bar: bool = False
    # ホールド練習モード: ターゲット精度指標を隠す
    hide_target_metrics: bool = False


MODES: dict[str, Mode] = {
    "prone": Mode(
        key="prone",
        label="伏射 (Prone) — 既存",
        description=(
            "50m スポーツライフル伏射向け。SCATT 互換指標 (10a/S1) 中心、"
            "反動の詳細分析、心拍 / HRV 連携を活用。"
        ),
        suggested_discipline="rifle_50m",
        hero_kpis=("ten_a_1s", "ten_a_05s", "s1_mm_s", "r95_05"),
        default_graphs=(
            "velocity", "scatter", "r95_history", "r95_bars",
            "cant_history", "spectrum",
            "trace_xy", "timing_history", "hold_history",
        ),
    ),
    "ar": Mode(
        key="ar",
        label="AR (10m エアライフル立射)",
        description=(
            "立射特化。撃発時速度・S1・心拍・フォロースルー安定 を主軸。"
            "反動の振幅でなくフォロースルーの一貫性を重視。"
        ),
        suggested_discipline="rifle_10m",
        hero_kpis=("timing_v", "s1_mm_s", "hr_at_fire", "recoil_post05_r95"),
        default_graphs=(
            "velocity", "timing_history", "cant_history", "spectrum",
            "recoil_xy", "hr_time", "r95_history", "trace_xy",
            "hr_vs_r95",
        ),
        show_velocity_hero=True,
        enhanced_status_bar=True,
    ),
    "hold_practice": Mode(
        key="hold_practice",
        label="ホールド練習 (ターゲット非依存)",
        description=(
            "黒点を狙いに行かず、銃そのものの静止度だけを評価。"
            "重心 R95 + 平均速度 + 力み のみ。10a 等のターゲット中心指標は隠す。"
        ),
        suggested_discipline="rifle_10m",
        hero_kpis=("timing_v", "s1_mm_s", "tremor", "cant_sd_deg"),
        default_graphs=(
            "velocity", "cant_time", "spectrum", "cant_history",
            "timing_history", "hold_history", "trace_xy",
            "cant_sd_history", "recoil_speed",
        ),
        show_velocity_hero=True,
        enhanced_status_bar=True,
        hide_target_metrics=True,
    ),
}

_DEFAULT_MODE = "prone"
_current_key = _DEFAULT_MODE


def set_current(key: str) -> bool:
    global _current_key
    if key in MODES:
        _current_key = key
        return True
    return False


def current() -> Mode:
    return MODES[_current_key]


def current_key() -> str:
    return _current_key


def apply_to_settings(mode_key: str, settings) -> bool:
    """モード切替: settings の hero_kpi_* / graph_default_* / discipline を更新。

    GUI 側で discipline 切替に伴うリロードを呼ぶ。
    """
    if mode_key not in MODES:
        return False
    m = MODES[mode_key]
    set_current(mode_key)
    settings.set("mode", mode_key)
    # discipline
    settings.set("discipline", m.suggested_discipline)
    # KPI 4 枚
    for i, k in enumerate(m.hero_kpis, 1):
        settings.set(f"layout/hero_kpi_{i}", k)
    # デフォルトグラフ 9 枠
    for i, g in enumerate(m.default_graphs, 1):
        settings.set(f"layout/graph_default_{i}", g)
    return True

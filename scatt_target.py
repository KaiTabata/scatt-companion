"""射撃種目 (discipline) ごとのターゲット幾何と解析半径。

50m ライフル既存挙動を変えないため、デフォルトは "rifle_50m"。
Settings から切り替え可能。

設計方針:
  - 描画と解析の両方が共通の値を参照する
  - グローバル current() でアクセス、起動時に set_current()
  - ten_a_percent() の半径 (10/inner-10/9 ring) も discipline 依存
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Discipline:
    key: str
    label: str
    # 描画用 (見た目)
    outer_diam_mm: float       # 一番外側 (= 1 リング外周)
    ring_step_mm: float        # リング直径の差 (1 リング進む = 直径 -ring_step_mm)
    black_diam_mm: float       # 黒地の直径 (照準黒丸)
    inner_ten_diam_mm: float   # inner-10 の表示用直径 (破線)
    # 解析用 (SCATT 互換指標)
    ring_10_radius_mm: float          # 10a, 10a-0.5 の判定半径
    ring_inner_10_radius_mm: float    # 10b, 10b-0.5 の判定半径
    ring_9_radius_mm: float           # 9c, 9c-0.5 の判定半径


# ISSF ターゲット仕様より
DISCIPLINES: dict[str, Discipline] = {
    # 既存 (50m スポーツライフル)
    "rifle_50m": Discipline(
        key="rifle_50m",
        label="50m ライフル",
        outer_diam_mm=154.4, ring_step_mm=16.0,
        black_diam_mm=112.4, inner_ten_diam_mm=5.0,
        ring_10_radius_mm=5.2, ring_inner_10_radius_mm=2.5, ring_9_radius_mm=13.2,
    ),
    # ISSF 10m エアライフル: 10ring=0.5mm dot, ring step 2.5mm radius
    # inner-10 (SCATT 概念) は中心ドット内の更に半分相当を割り当て
    "rifle_10m": Discipline(
        key="rifle_10m",
        label="10m エアライフル",
        outer_diam_mm=45.5, ring_step_mm=5.0,
        black_diam_mm=30.5, inner_ten_diam_mm=0.5,
        ring_10_radius_mm=0.25, ring_inner_10_radius_mm=0.125, ring_9_radius_mm=2.75,
    ),
    # ISSF 10m エアピストル
    "pistol_10m": Discipline(
        key="pistol_10m",
        label="10m エアピストル",
        outer_diam_mm=155.5, ring_step_mm=16.0,
        black_diam_mm=59.5, inner_ten_diam_mm=5.0,
        ring_10_radius_mm=5.75, ring_inner_10_radius_mm=2.5, ring_9_radius_mm=13.75,
    ),
}

_DEFAULT_KEY = "rifle_50m"
_current_key = _DEFAULT_KEY


def set_current(key: str) -> None:
    """起動時に Settings から読んで呼ぶ。未知の key は無視。"""
    global _current_key
    if key in DISCIPLINES:
        _current_key = key


def current() -> Discipline:
    return DISCIPLINES[_current_key]


def current_key() -> str:
    return _current_key

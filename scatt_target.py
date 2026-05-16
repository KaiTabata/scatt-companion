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
    # 解析・判定の閾値 (種目別に大きく違うのでハードコードしない)
    # hold_time:  「速度がこれ未満なら静止」
    hold_v_thr_mm_s: float
    # segment_phases:  hold/aim/trigger 区切り (v >= hold_mm_s → hold、< aim_mm_s → trigger)
    phase_hold_mm_s: float
    phase_aim_mm_s: float
    # recoil_detailed: 反動が「収まった」と判定する円の半径
    recoil_settle_mm: float
    # r95 色判定 (グラフバーの「良 / 中 / 要改善」境界)
    r95_good_mm: float                # ≤ これなら緑
    r95_bad_mm: float                 # ≥ これなら赤
    # 誤反応 shot とみなす中心からの距離 (Sessions タブの threshold_spin デフォルト)
    suspicious_radius_mm: float


# ISSF ターゲット仕様より
# 閾値は射撃理論の典型値 + 実データの分布から経験的に設定。
# 50m と 10m AR ではホールド速度・R95 のレンジが 5〜10 倍違うため、種目で揃える。
DISCIPLINES: dict[str, Discipline] = {
    "rifle_50m": Discipline(
        key="rifle_50m",
        label="50m ライフル",
        outer_diam_mm=154.4, ring_step_mm=16.0,
        black_diam_mm=112.4, inner_ten_diam_mm=5.0,
        ring_10_radius_mm=5.2, ring_inner_10_radius_mm=2.5, ring_9_radius_mm=13.2,
        hold_v_thr_mm_s=15.0,
        phase_hold_mm_s=60.0, phase_aim_mm_s=20.0,
        recoil_settle_mm=5.0,
        r95_good_mm=2.0, r95_bad_mm=5.0,
        suspicious_radius_mm=200.0,
    ),
    # 10m AR: 10ring=0.5mm dot, ring step 2.5mm 半径 → 50m の約 1/20 スケール
    "rifle_10m": Discipline(
        key="rifle_10m",
        label="10m エアライフル",
        outer_diam_mm=45.5, ring_step_mm=5.0,
        black_diam_mm=30.5, inner_ten_diam_mm=0.5,
        ring_10_radius_mm=0.25, ring_inner_10_radius_mm=0.125, ring_9_radius_mm=2.75,
        hold_v_thr_mm_s=3.0,
        phase_hold_mm_s=10.0, phase_aim_mm_s=4.0,
        recoil_settle_mm=1.0,
        r95_good_mm=0.5, r95_bad_mm=1.5,
        suspicious_radius_mm=25.0,
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


# fitInView 用の視野半径 (mm)。
# 全種目「外径 × 1.05」に統一: 50m / 10m AR どちらもターゲット全体が
# わずかな余白付きで収まるスケール。軌跡の見た目サイズが種目間で一貫し、
# mode 切替後の再 fit でも同じ式が走るのでサイズがブレない。
_VIEW_MARGIN = 1.05


def view_radius_mm(disc: Discipline | None = None) -> float:
    """ターゲット view の fitInView 半径。全種目で外径 × 1.05/2。"""
    d = disc or current()
    return d.outer_diam_mm / 2.0 * _VIEW_MARGIN

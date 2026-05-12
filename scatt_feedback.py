"""ローカル(オフライン)動作の自然言語フィードバック生成。

ネット接続・LLM ファイル不要。z-score とテンプレートから所見を組み立てる。
- shot_feedback(cur, stats): 単発 shot の所見
- session_feedback(session_shots): セッション全体の所見

設計方針:
- 各文がどの指標から来てるか追跡可能
- ヒント文は射撃理論の典型的アドバイス
- 文の数は最大 4〜5 個 (過剰説明を避ける)
"""

from __future__ import annotations
from typing import Optional
import numpy as np


# 各指標の方向 (low_good = 値が低いほど良い、high_good = 高いほど良い、abs_low_good = 絶対値小)
METRIC_DIRECTIONS = {
    "timing_v":         "low_good",
    "r95_05":           "low_good",
    "r95_1":            "low_good",
    "r95_2":            "low_good",
    "r95_3":            "low_good",
    "cant_at_fire_deg": "abs_low_good",
    "cant_sd_deg":      "low_good",
    "hold_s":           "high_good",
    "aim_s":            "info",
    "tremor":           "low_good",
    "breath":           "low_good",
    "heart_band":       "low_good",
    "total_power":      "low_good",
    "approach_mono":    "high_good",
    "approach_signs":   "low_good",
    "hr_at_fire":       "low_good",
    "rmssd_30s":        "high_good",
    "ten_a_1s":         "high_good",
    "ten_a_05s":        "high_good",
    "ten_b_1s":         "high_good",
    "ten_b_05s":        "high_good",
    "nine_c_1s":        "high_good",
    "recoil_peak":      "low_good",
    "recoil_settle":    "low_good",
    "recoil_post05_r95": "low_good",
    "recoil_dir_std":   "low_good",
}


def _z_score(value, mu, sigma, direction: str) -> Optional[float]:
    """z-score を計算。high_good なら反転して "悪い側が正" に統一。"""
    if value is None or sigma is None or sigma <= 0:
        return None
    if direction == "abs_low_good":
        z = (abs(value) - abs(mu)) / sigma
    else:
        z = (value - mu) / sigma
    if direction == "high_good":
        z = -z
    return float(z)


def _describe_bad(key: str, val: float, z: float) -> Optional[str]:
    """普段より悪い指標を 1 文で表現。"""
    sev = "顕著に" if z >= 2.0 else "やや"
    if key == "timing_v":
        return f"撃発タイミングが{sev}速く {val:.0f}mm/s でした (普段より {z:+.1f}σ)。"
    if key == "r95_05":
        return f"S2 (最終 0.5s 照準ブレ) が{sev}大きく {val:.2f}mm でした (z={z:+.1f}σ)。"
    if key == "r95_1":
        return f"S1 (最終 1s 照準ブレ) が{sev}大きく {val:.2f}mm でした (z={z:+.1f}σ)。"
    if key in ("r95_2", "r95_3"):
        return f"長窓 R95 が{sev}大きく {val:.2f}mm でした。"
    if key == "ten_a_1s":
        return f"10a (10-ring 滞在 1s) が{sev}短く {val:.0f}% でした (z={z:+.1f}σ)。"
    if key == "ten_a_05s":
        return f"10a-0.5 (10-ring 滞在 0.5s) が{sev}短く {val:.0f}% でした。"
    if key == "ten_b_1s":
        return f"10b (inner-10 滞在) が{sev}短く {val:.0f}% でした。"
    if key == "cant_at_fire_deg":
        return f"撃発時 cant が普段と{sev}ズレ {val:+.2f}° でした (z={z:+.1f}σ)。"
    if key == "cant_sd_deg":
        return f"発射前 0.5s の cant 変動が{sev}大きく σ={val:.2f}° でした。"
    if key == "hold_s":
        return f"最終ホールド時間が{sev}短く {val:.2f}s でした。"
    if key == "tremor":
        return f"力み (8-12Hz) が{sev}大きく {val:.4f} でした。"
    if key == "breath":
        return f"呼吸帯のパワーが{sev}大きく {val:.3f} (息止め失敗の兆候) でした。"
    if key == "heart_band":
        return f"心拍由来のゆれが{sev}大きく {val:.3f} でした。"
    if key == "total_power":
        return f"サイト全体のゆれが{sev}大きく {val:.3f} でした。"
    if key == "approach_signs":
        return f"狙い直しの振動が{sev}多く {val:.1f} 回/秒 でした。"
    if key == "approach_mono":
        return f"approach 単調率が{sev}低く {val:.2f} でした。"
    if key == "hr_at_fire":
        return f"発射時 HR が{sev}高く {val:.0f} bpm でした。"
    if key == "rmssd_30s":
        return f"HRV (RMSSD) が{sev}低く {val:.0f}ms (緊張・疲労の兆候) でした。"
    if key == "recoil_peak":
        return f"反動 peak が{sev}大きく {val:.1f}mm でした。"
    if key == "recoil_settle":
        return f"反動からの復元時間が{sev}長く {val:.2f}s でした。"
    if key == "recoil_post05_r95":
        return f"フォロースルー (発射後 0.5s R95) が{sev}大きく {val:.1f}mm でした。"
    return None


def _describe_good(key: str, val: float, z: float) -> Optional[str]:
    """普段より良い指標を 1 文で表現。"""
    if key == "timing_v":
        return f"撃発タイミング {val:.0f}mm/s は普段より良く、止まって撃てています。"
    if key == "r95_05":
        return f"S2 {val:.2f}mm は普段より良く、最終ホールドが安定。"
    if key == "r95_1":
        return f"S1 {val:.2f}mm は普段より良いです。"
    if key == "ten_a_1s":
        return f"10a {val:.0f}% は普段より高く、10 リングへ長く留まれています。"
    if key == "hold_s":
        return f"最終ホールド {val:.2f}s は普段より長く、止めの時間が確保できています。"
    if key == "cant_sd_deg":
        return f"発射前の cant 変動が普段より小さく ({val:.2f}°)、姿勢が一貫しています。"
    if key == "tremor":
        return f"力み (8-12Hz) が普段より少なく ({val:.4f})、落ち着いた撃発でした。"
    if key == "breath":
        return f"呼吸の影響が少なく ({val:.3f})、息止めが効いています。"
    if key == "recoil_peak":
        return f"反動 peak {val:.1f}mm は普段より小さく、銃の保持が良好。"
    if key == "rmssd_30s":
        return f"HRV {val:.0f}ms は普段より高く、リラックスできていました。"
    return None


def _improvement_tip(key: str) -> Optional[str]:
    """改善ヒント (各指標が悪いときに添えるアドバイス)。"""
    tips = {
        "timing_v":         "→ ヒント: タイミングが速い時は、追加で 0.3 秒待つ意識を。",
        "r95_05":           "→ ヒント: 最終 0.5s が散る時は息止めのタイミングを揃え、姿勢の最終固定を見直し。",
        "r95_1":            "→ ヒント: 最終 1s が散る時は approach phase を短くせず、ゆっくり中心に収束させる。",
        "ten_a_1s":         "→ ヒント: 10a が低いのは approach が不安定。狙い直しを減らす。",
        "ten_a_05s":        "→ ヒント: 10a-0.5 が低い時は最終ホールドが弱い。引きの判断を遅らせる。",
        "cant_at_fire_deg": "→ ヒント: cant が普段と違う時はグリップやストックの当て方を再確認。",
        "cant_sd_deg":      "→ ヒント: 狙い中の肩の力みや銃の保持を見直し。",
        "hold_s":           "→ ヒント: 最終ホールドが短い。発射判断を 0.3〜0.5 秒遅らせる練習を。",
        "tremor":           "→ ヒント: 力みが大きい時は呼吸前のリラックス、脱力を意識。",
        "breath":           "→ ヒント: 呼吸の影響が出ている。完全息止めまたは半呼気の習慣化。",
        "heart_band":       "→ ヒント: 心拍由来のゆれは避けられないが、撃発タイミングを心拍の合間に置く意識を。",
        "total_power":      "→ ヒント: サイト全体のゆれが大きい。姿勢の固定、グリップの安定を見直し。",
        "approach_signs":   "→ ヒント: 狙い直しを減らす。最初の狙いで決める意識。",
        "approach_mono":    "→ ヒント: approach をまっすぐ収束させる練習を。",
        "hr_at_fire":       "→ ヒント: HR が高い時はリラックス、呼吸でクールダウン。",
        "rmssd_30s":        "→ ヒント: HRV 低下は疲労・緊張の兆候。1 分間の深呼吸で持ち直し。",
        "recoil_peak":      "→ ヒント: 反動が大きい時はトリガープルでの引き込み、保持の緩みを確認。",
        "recoil_settle":    "→ ヒント: 復元が遅い時は銃の保持力と肩への当て方を見直し。",
        "recoil_post05_r95": "→ ヒント: フォロースルーがぶれている。発射後 1 秒は構えを維持。",
    }
    return tips.get(key)


def shot_feedback(cur_metrics: dict, session_stats: dict, *, min_z: float = 1.0) -> str:
    """単発 shot の所見を生成。

    cur_metrics: {key: value} 現在 shot の指標値
    session_stats: {key: (mu, sigma)} 過去 shot の統計
    min_z: 言及する z-score 閾値 (これ未満は "普段通り")
    """
    z_map: dict[str, float] = {}
    for key, val in cur_metrics.items():
        if val is None or key not in session_stats:
            continue
        direction = METRIC_DIRECTIONS.get(key, "info")
        if direction == "info":
            continue
        mu, sigma = session_stats[key]
        z = _z_score(val, mu, sigma, direction)
        if z is not None:
            z_map[key] = z

    if not z_map:
        return "(過去履歴が少ないため比較できません)"

    # 悪い側 top 2、良い側 top 1
    bad_sorted = sorted(z_map.items(), key=lambda x: -x[1])
    good_sorted = sorted(z_map.items(), key=lambda x: x[1])

    sentences: list[str] = []
    mentioned: set[str] = set()

    # 悪い側 top 2 (z >= min_z のもの)
    for key, z in bad_sorted[:2]:
        if z < min_z:
            break
        s = _describe_bad(key, cur_metrics.get(key), z)
        if s:
            sentences.append(s)
            mentioned.add(key)

    # 良い側 (1 個まで、z <= -min_z)
    for key, z in good_sorted[:1]:
        if z > -min_z or key in mentioned:
            continue
        s = _describe_good(key, cur_metrics.get(key), z)
        if s:
            sentences.append(s)
            mentioned.add(key)

    if not sentences:
        sentences.append("今回の shot は全体的に普段通りでした。")

    # 一番悪い指標についてヒント (z >= 1.5 のみ)
    if bad_sorted and bad_sorted[0][1] >= 1.5:
        tip = _improvement_tip(bad_sorted[0][0])
        if tip:
            sentences.append(tip)

    return "\n".join(sentences)


def session_feedback(session_shots: list[dict]) -> str:
    """セッション全体の所見。集計、特徴値、前半 vs 後半トレンド、改善ポイント。"""
    n = len(session_shots)
    if n < 3:
        return "shot 数が少ないため評価できません (最低 3 shots)。"

    # 全体集計
    s1_vals: list[float] = []
    s2_vals: list[float] = []
    ten_a_vals: list[float] = []
    ten_a05_vals: list[float] = []
    cant_vals: list[float] = []
    timing_vals: list[float] = []
    peak_vals: list[float] = []
    hold_vals: list[float] = []
    hr_vals: list[float] = []
    for s in session_shots:
        summ = s.get("summary") or {}
        for st in (summ.get("stability") or []):
            if st.get("window_s") == 1.0: s1_vals.append(st["r95"])
            if st.get("window_s") == 0.5: s2_vals.append(st["r95"])
        v = (summ.get("ten_a_1s") or {}).get("percent")
        if v is not None: ten_a_vals.append(v)
        v = (summ.get("ten_a_05s") or {}).get("percent")
        if v is not None: ten_a05_vals.append(v)
        if s.get("fire_cant") is not None:
            cant_vals.append(np.degrees(s["fire_cant"]))
        if s.get("timing_v") is not None: timing_vals.append(s["timing_v"])
        pk = (summ.get("recoil") or {}).get("peak_r_mm")
        if pk is not None: peak_vals.append(pk)
        h = (summ.get("hold") or {}).get("hold_s")
        if h is not None: hold_vals.append(h)
        if s.get("hr_at_fire") is not None: hr_vals.append(s["hr_at_fire"])

    sentences: list[str] = []
    sentences.append(f"このセッションでは {n} shot を撃ちました。")

    # S2 (最終 0.5s) 評価
    if s2_vals:
        mu_s2 = float(np.mean(s2_vals))
        if mu_s2 < 2:
            sentences.append(f"S2 平均 {mu_s2:.2f}mm — 上級者レベルの安定したホールド。")
        elif mu_s2 < 4:
            sentences.append(f"S2 平均 {mu_s2:.2f}mm — 標準的。最後の止めを 0.2 秒長くする余地。")
        else:
            sentences.append(f"S2 平均 {mu_s2:.2f}mm — 最終ホールドが散らばっています。呼吸停止と姿勢固定を見直し。")

    # 10a 評価
    if ten_a_vals:
        mu_ten = float(np.mean(ten_a_vals))
        if mu_ten >= 70:
            sentences.append(f"10a 平均 {mu_ten:.0f}% — 10-ring 滞在時間 良好。")
        elif mu_ten >= 30:
            sentences.append(f"10a 平均 {mu_ten:.0f}% — 標準。approach の安定を伸ばす余地。")
        else:
            sentences.append(f"10a 平均 {mu_ten:.0f}% — 10-ring に長く留まれていません。狙いの収束に課題。")

    # Cant ばらつき
    if cant_vals and len(cant_vals) >= 3:
        sd = float(np.std(cant_vals))
        if sd < 0.5:
            sentences.append(f"Cant ばらつき σ={sd:.2f}° — 銃の保持が一貫しています。")
        elif sd > 1.5:
            sentences.append(f"Cant ばらつき σ={sd:.2f}° — shot 間で cant が変動。グリップを統一すべき。")

    # 前半 vs 後半トレンド
    if len(s2_vals) >= 6:
        half = len(s2_vals) // 2
        first = float(np.mean(s2_vals[:half]))
        second = float(np.mean(s2_vals[half:]))
        diff = second - first
        if diff > 0.5:
            sentences.append(f"後半 S2 が +{diff:.2f}mm 悪化 — 疲労や集中切れの兆候。休憩を挟むか練習量を見直し。")
        elif diff < -0.5:
            sentences.append(f"後半 S2 が {diff:.2f}mm 改善 — 体が温まってきた。前半のアップを充実させると更に良い。")

    if len(peak_vals) >= 6:
        half = len(peak_vals) // 2
        f = float(np.mean(peak_vals[:half]))
        s = float(np.mean(peak_vals[half:]))
        if s - f > 5:
            sentences.append(f"後半に反動 peak が +{s-f:.1f}mm 増加 — 銃の保持が緩んでいる可能性。")

    # 心拍トレンド
    if len(hr_vals) >= 5:
        mu_hr = float(np.mean(hr_vals))
        sd_hr = float(np.std(hr_vals))
        if sd_hr > 8:
            sentences.append(f"心拍ばらつき σ={sd_hr:.0f} bpm — shot 間の状態差が大きい。呼吸・リズム統一を意識。")
        elif mu_hr > 90:
            sentences.append(f"発射時平均 HR {mu_hr:.0f} bpm — やや高め。リラックスのルーティンを。")

    # ベスト shot 抽出
    if s2_vals:
        idx_best = int(np.argmin(s2_vals))
        sentences.append(f"ベスト shot は #{idx_best + 1} (S2={s2_vals[idx_best]:.2f}mm) — その時の感覚を再現。")

    return "\n".join(sentences)

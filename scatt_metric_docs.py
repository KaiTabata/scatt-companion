"""指標・グラフの計算式を 1 箇所に集約。

UI から right-click → 「計算式」で開ける。
Help タブからも参照される。

エントリ構造:
  key: {
    "name":    "10a",
    "summary": "1 文の要約",
    "formula": "<HTML>",
    "why":     "何のために見るか",
    "range":   "典型値の幅 (任意)",
    "notes":   "実装上の注意点 (任意)",
  }
"""

from __future__ import annotations

# ----- 指標 (METRICS) -----

METRIC_DOCS: dict[str, dict] = {
    # ==== SCATT 互換 (10 圏内・安定度) ====
    "ten_a_1s": {
        "name": "10a (10-ring 1 秒滞在率)",
        "summary": "発射直前 1 秒のうち、照準が 10 点圏内 (R≤R₁₀) にいた時間の割合",
        "formula":
            "10a = Σ<sub>k: t[k] ∈ [t<sub>fire</sub>−1, t<sub>fire</sub>]</sub> "
            "<b>1</b>[ r[k] ≤ R<sub>10</sub> ] / N<sub>window</sub> × 100  [%]<br>"
            "r[k] = √(x[k]² + y[k]²)  (中心からの距離 mm)<br>"
            "R<sub>10</sub> = 5.2mm (50m ライフル) / 0.25mm (10m エアライフル) / 5.75mm (10m エアピストル)",
        "why": "本家 SCATT の主役指標。値が高いほど狙いが安定して 10 点圏に入っている。",
        "range": "60–95% (50m prone 上級者)",
    },
    "ten_a_05s": {
        "name": "10a-0.5 (10-ring 0.5 秒滞在率)",
        "summary": "10a と同じだが窓を発射直前 0.5 秒に絞ったもの",
        "formula":
            "10a-0.5 = Σ<sub>k: t[k] ∈ [t<sub>fire</sub>−0.5, t<sub>fire</sub>]</sub> "
            "<b>1</b>[ r[k] ≤ R<sub>10</sub> ] / N<sub>window</sub> × 100  [%]",
        "why": "短い窓ほど発射の瞬間の狙いに近い。10a より厳しい指標。",
    },
    "ten_b_1s": {
        "name": "10b (inner-10 滞在率)",
        "summary": "10 点中央 (R≤R<sub>inner-10</sub>) の滞在率",
        "formula":
            "10b = Σ<sub>k</sub> <b>1</b>[ r[k] ≤ R<sub>inner-10</sub> ] / N × 100  [%]<br>"
            "R<sub>inner-10</sub> = 2.5mm (50m ライフル) / 0.125mm (10m エアライフル) / 2.5mm (10m エアピストル)",
        "why": "10a より中央寄り。1.0 点増加に直結する評価。",
    },
    "ten_b_05s": {
        "name": "10b-0.5",
        "summary": "inner-10 滞在率を直前 0.5 秒で",
        "formula": "10b-0.5 = Σ 1[r[k] ≤ R<sub>inner-10</sub>] / N (k ∈ 直前 0.5 秒) × 100",
        "why": "発射の瞬間に内 10 に入っていたかをほぼ直接見られる。",
    },
    "nine_c_1s": {
        "name": "9c (9-ring 滞在率)",
        "summary": "9 点圏内 (R≤R₉) の滞在率",
        "formula": "9c = Σ 1[r[k] ≤ R<sub>9</sub>] / N × 100  (R<sub>9</sub> = 13.2mm for 50m)",
        "why": "外しの絶対数を見るときの目安。10 点圏より広い。",
    },
    "r95_1": {
        "name": "S1 (直前 1 秒の R95)",
        "summary": "発射前 1 秒間に照準が散らばった範囲。値が小さいほど安定。",
        "formula":
            "S1 = percentile<sub>95%</sub>({ r[k] : k ∈ [t<sub>fire</sub>−1, t<sub>fire</sub>] })  [mm]<br>"
            "= 95% のサンプルが収まる円の半径 (中心 = 着弾点)",
        "why": "本家 SCATT の S1 と同等。1 秒尺度の落ち着き。",
        "range": "良 ≤ 2mm / 普通 2–5mm / 要改善 > 5mm (50m prone)",
    },
    "r95_05": {
        "name": "S2 (直前 0.5 秒の R95)",
        "summary": "発射前 0.5 秒の R95。短期安定度",
        "formula": "S2 = percentile<sub>95%</sub>({ r[k] : k ∈ 直前 0.5 秒 })",
        "why": "撃発の瞬間に最も近い指標。S1 より厳しい。",
    },
    "r95_2": {
        "name": "R95 直前 2 秒",
        "summary": "中期スパンの安定度",
        "formula": "R95-2s = percentile<sub>95%</sub>({ r[k] : k ∈ 直前 2 秒 })",
        "why": "長めの構えのうちブレた範囲を見る。アプローチが粗いかどうか。",
    },
    "r95_3": {
        "name": "R95 直前 3 秒",
        "summary": "長期スパンの安定度",
        "formula": "R95-3s = percentile<sub>95%</sub>({ r[k] : k ∈ 直前 3 秒 })",
        "why": "アプローチ全体のスケール感。",
    },

    # ==== 撃発タイミング・速度系 ====
    "timing_v": {
        "name": "撃発タイミング (発射時の動き)",
        "summary": "発射の瞬間の照準速度。小さいほど良い (止まっている時に撃てている)",
        "formula":
            "v[k] = √((x[k+1]−x[k])² + (y[k+1]−y[k])²) × f<sub>s</sub>  [mm/s]<br>"
            "撃発タイミング = v[k<sub>fire</sub>]  (発射サンプル時点の速度)",
        "why": "停止状態で撃発できているかの直接指標。3 mm/s 以下なら静止状態。",
        "range": "理想 < 3mm/s、要改善 > 15mm/s",
    },

    # ==== 銃の傾き ====
    "cant_at_fire_deg": {
        "name": "銃の傾き (撃発時)",
        "summary": "撃発の瞬間の銃身傾き角",
        "formula":
            "cant_at_fire_deg = degrees(cant[k<sub>fire</sub>])  [°]<br>"
            "cant[k] は SCATT センサが記録した銃身ロール角 (radians)",
        "why": "弾道に直接影響。常に同じ角度に統一できると 着弾分布の左右ブレが減る。",
    },
    "cant_sd_deg": {
        "name": "銃傾きの揺れ (0.5 秒)",
        "summary": "発射前 0.5 秒の cant 角の標準偏差",
        "formula":
            "cant_sd_deg = std({ degrees(cant[k]) : k ∈ 直前 0.5 秒 })  [°]",
        "why": "発射直前にバランスが揺れていないか。値が大きいと反動方向のばらつきも増える。",
    },

    # ==== ホールド時間 ====
    "hold_s": {
        "name": "静止時間 (hold time)",
        "summary": "発射直前で速度が hold threshold 以下だった連続時間",
        "formula":
            "v_thr = thresh/hold_velocity_mm_s  (デフォルト 15 mm/s, Settings で可変)<br>"
            "hold_s = max(continuous duration where v[k] < v_thr) [s]<br>"
            "発射直前から遡って測る",
        "why": "短いと「焦って撃った」、長すぎると「粘りすぎて疲労」。0.5–2 秒が目安。",
    },
    "aim_s": {
        "name": "構え時間 (aim time)",
        "summary": "1 trace の発射前の総時間",
        "formula": "aim_s = (t<sub>fire</sub> − t<sub>0</sub>) [s]  (pre-trigger 全体)",
        "why": "1 発にかかった時間。長すぎると疲労、短すぎると粗い。",
    },

    # ==== スペクトラム由来 ====
    "total_power": {
        "name": "サイト全体のゆれ (total power)",
        "summary": "発射前 速度の全周波数帯のエネルギー",
        "formula":
            "1) v[k] = (x[k+1]−x[k]) × f<sub>s</sub>  (X 軸速度)<br>"
            "2) FFT(v) → magnitude[m]<br>"
            "3) total_power = Σ<sub>m</sub> magnitude[m]²",
        "why": "狙い全体のざわつき。大きいと「全部が大きく動いている」状態。",
    },
    "heart_band": {
        "name": "心拍由来のゆれ (0.8–2 Hz)",
        "summary": "心拍周波数帯のスペクトルエネルギー",
        "formula":
            "heart_band = Σ<sub>m: f[m] ∈ [0.8, 2.0]</sub> magnitude[m]²  "
            "(速度ベース FFT)",
        "why": "伏射では心拍由来の上下動が支配的。値が大きい時は撃発のタイミング工夫が要る。",
    },
    "tremor": {
        "name": "力み (8–12 Hz)",
        "summary": "生理的振戦帯のスペクトルエネルギー",
        "formula":
            "tremor = Σ<sub>m: f[m] ∈ [8, 12]</sub> magnitude[m]²",
        "why": "肩・指の力みや疲労で増える。リラックスできているかの指標。",
    },
    "breath": {
        "name": "呼吸 (0.15–0.5 Hz)",
        "summary": "呼吸由来の低周波エネルギー",
        "formula":
            "breath = Σ<sub>m: f[m] ∈ [0.15, 0.5]</sub> magnitude[m]²",
        "why": "息止め失敗の検出。0 が理想だが、わずかに残るのが自然。",
    },

    # ==== 軌跡分析 ====
    "approach_mono": {
        "name": "狙いの直線度 (monotonicity)",
        "summary": "アプローチ中、中心に近づき続けた割合",
        "formula":
            "Δr[k] = r[k+1] − r[k]<br>"
            "approach_mono = #{k : Δr[k] < 0, k ∈ pre} / #{k ∈ pre}",
        "why": "1.0 に近いほどスムーズに中心へ向かった。低いと寄せたり離したり繰り返してる。",
    },
    "approach_signs": {
        "name": "狙い直し回数 / 秒",
        "summary": "アプローチ中、中心への移動方向が反転した回数の頻度",
        "formula":
            "sign[k] = sign(Δr[k])<br>"
            "approach_signs = #{k : sign[k] ≠ sign[k−1]} / pre_duration  [/s]",
        "why": "高いほど狙いがブレている。3 回/秒以上は粗い。",
    },

    # ==== 心拍 / HRV ====
    "hr_at_fire": {
        "name": "心拍 (撃発時)",
        "summary": "BLE で受信した、発射時点に最も近い HR 値",
        "formula":
            "hr_at_fire = HR(t<sub>fire</sub>) [bpm]<br>"
            "(直近 1 秒以内に受信した値を採用、なければ NULL)",
        "why": "発射時の心拍位相がスコアに影響するかを後で相関分析できる。",
    },
    "rmssd_30s": {
        "name": "HRV (RMSSD 30 秒)",
        "summary": "心拍変動の代表値",
        "formula":
            "RR[n] = 心拍間隔 [ms]<br>"
            "RMSSD = √( mean( (RR[n+1] − RR[n])² ) )  over 直近 30 秒  [ms]",
        "why": "副交感神経活動の強さ。リラックスできていると高くなる。20–50ms が一般的。",
    },

    # ==== 反動受け ====
    "recoil_peak": {
        "name": "反動の振幅 (peak amplitude)",
        "summary": "発射後 1 秒のうち中心から最も遠ざかった距離",
        "formula":
            "recoil_peak = max( r[k] : k ∈ [t<sub>fire</sub>, t<sub>fire</sub>+1s] )  [mm]<br>"
            "r[k] = √(x[k]² + y[k]²)",
        "why": "反動の大きさを定量化。銃のフィットや当て方によって変わる。",
    },
    "recoil_settle": {
        "name": "反動の戻り時間 (settle time)",
        "summary": "ピークから戻ってきて、peak/4 以下に最初に達するまでの時間",
        "formula":
            "settle = (最初に r[k] < recoil_peak / 4 になる k) − k<sub>peak</sub>  [s]<br>"
            "(発射後 1 秒以内に戻らなければ NULL)",
        "why": "短いほど復元が速い = 銃のホールドが効いている。",
    },
    "recoil_post05_r95": {
        "name": "フォロースルー安定 (post-0.5s R95)",
        "summary": "発射後 0.5 秒以降の R95",
        "formula":
            "recoil_post05_r95 = percentile<sub>95%</sub>"
            "({ r[k] : k ∈ [t<sub>fire</sub>+0.5s, t<sub>fire</sub>+1s] })",
        "why": "反動を受け切った後の姿勢が安定しているか。フォロースルーの質。",
    },
    "recoil_direction": {
        "name": "反動方向 (peak の角度)",
        "summary": "ピーク時点の中心から見た方向角",
        "formula":
            "recoil_direction = atan2(y[k<sub>peak</sub>], x[k<sub>peak</sub>]) [°]<br>"
            "0° = 右, 90° = 上 (画面座標)",
        "why": "毎回同じ方向に反動が出ていれば持ち方が一貫している。",
    },
    "recoil_dir_std": {
        "name": "反動方向のばらつき (circular σ)",
        "summary": "反動方向の円形標準偏差。shot 間の持ち方一貫性",
        "formula":
            "R = | mean(exp(i · θ[shot])) | (各 shot の方向の円平均)<br>"
            "circ_std = √( −2 · ln(R) )  [rad → deg に変換]",
        "why": "0° に近いほど反動方向が揃っている = 持ち方が安定。30°以上は要改善。",
    },
}

# ----- グラフ (GRAPH_KINDS) -----

GRAPH_DOCS: dict[str, dict] = {
    "velocity": {
        "name": "速度 時系列",
        "summary": "発射前後の照準速度 |v(t)|",
        "formula":
            "|v(t)|[k] = √((x[k+1]−x[k])² + (y[k+1]−y[k])²) × f<sub>s</sub>  [mm/s]<br>"
            "横軸は発射の瞬間を 0 とした相対時刻",
        "why": "ホールド (低速の谷) と撃発時の動き (v[t_fire]) が一目で見える。",
    },
    "spectrum": {
        "name": "FFT スペクトル",
        "summary": "発射前の照準速度の周波数スペクトル (X / Y 軸別)",
        "formula":
            "v[k] = Δx[k] × f<sub>s</sub>  → Hanning 窓 → rfft → /N<br>"
            "帯域別エネルギー = Σ magnitude²<br>"
            "  呼吸 (0.15–0.5 Hz) / 心拍 (0.8–2 Hz) / 力み (8–12 Hz)",
        "why": "「何が原因でブレているか」を周波数で分離する。Sessions タブで X/Y 別表示。",
    },
    "scatter": {
        "name": "発射点 散布図",
        "summary": "session 全 shot の着弾点を target 座標にプロット",
        "formula":
            "各 shot の (x[k<sub>fire</sub>], y[k<sub>fire</sub>]) をそのまま描画<br>"
            "重心 = (mean(x_fire), mean(y_fire)), R95 = percentile<sub>95</sub>(distances)",
        "why": "集弾の癖 (左右流れ・上下流れ) を視覚化。",
    },
    "trace_xy": {
        "name": "現 trace の軌跡 (X-Y)",
        "summary": "現在選択中 shot の照準軌跡 (X 横軸, Y 縦軸)",
        "formula":
            "samples[:, 0] = X 軌跡, samples[:, 1] = Y 軌跡<br>"
            "発射前 = 青、発射後 = 赤、撃発点 = 黄",
        "why": "1 発の動き方を直接見る。アプローチの形状とフォロースルーが分かる。",
    },
    "r95_history": {
        "name": "安定度 推移",
        "summary": "S2 (0.5s) / S1 (1s) / R95-2s を shot 順に",
        "formula": "各 shot で stability[window=0.5/1.0/2.0] の R95 を抽出してプロット",
        "why": "セッション内で疲労・集中力の波が見える。",
    },
    "r95_bars": {
        "name": "直近 5 発の S2 棒グラフ",
        "summary": "最後の 5 shot の S2 を棒で",
        "formula": "棒の高さ = 各 shot の r95_05 (mm)",
        "why": "最近の調子をぱっと見で確認。色は閾値判定。",
    },
    "cant_time": {
        "name": "銃の傾き 時系列",
        "summary": "現 trace の cant 角の時間変化",
        "formula": "degrees(cant[k]) for k ∈ [0, N), 横軸 = 発射からの相対時刻",
        "why": "発射前にどう傾きが揺れたか。発射時点で安定していたかを確認。",
    },
    "cant_history": {
        "name": "発射時 銃の傾き 推移",
        "summary": "各 shot の cant_at_fire を shot 順に",
        "formula": "y[shot_idx] = degrees(cant[k<sub>fire</sub>])",
        "why": "shot 毎の傾きが揃っているか。trend があるなら姿勢の問題。",
    },
    "timing_history": {
        "name": "撃発タイミング 推移",
        "summary": "各 shot の v[t_fire] (撃発時の速度) を shot 順に",
        "formula": "y[shot_idx] = timing_v (mm/s)",
        "why": "撃発のキレ。低いほど止まって撃てている。",
    },
    "hold_history": {
        "name": "静止時間 推移",
        "summary": "各 shot の hold time を shot 順に",
        "formula": "y[shot_idx] = hold_s (秒)",
        "why": "粘り時間の一貫性。極端に短いと焦り、長すぎは疲労の兆候。",
    },
    "hr_time": {
        "name": "心拍 時系列",
        "summary": "shot ごとの hr_at_fire を shot 順に",
        "formula": "y[shot_idx] = hr_at_fire (bpm)",
        "why": "心拍が下がる前半 vs 上がる後半など、状態の流れを見る。",
    },
    "hr_vs_r95": {
        "name": "心拍 vs S2 (相関)",
        "summary": "shot ごとの (HR, S2) を散布図",
        "formula":
            "X[shot] = hr_at_fire, Y[shot] = r95_05<br>"
            "相関 r = Pearson 相関係数",
        "why": "心拍と安定度の関係。心拍が高いほどブレるかどうか個人で確認できる。",
    },
    "rmssd_vs_r95": {
        "name": "HRV vs S2 (相関)",
        "summary": "shot ごとの (RMSSD, S2) を散布図",
        "formula":
            "X[shot] = rmssd_30s, Y[shot] = r95_05<br>"
            "相関 r = Pearson 相関係数",
        "why": "リラックス度と安定度の相関。HRV が高い方が S2 良ければ「整っている時の方が撃てる」。",
    },
    "session_overview": {
        "name": "セッション概観 (S2 + 心拍)",
        "summary": "shot 順に S2 と HR を 2 軸プロット",
        "formula": "左軸 = S2 mm, 右軸 = HR bpm",
        "why": "セッション中の状態と精度の同時推移。山谷の対応を見る。",
    },
    "timing_vs_r95": {
        "name": "撃発タイミング vs S2 (相関)",
        "summary": "shot ごとの (timing_v, S2) 散布図",
        "formula": "X = timing_v, Y = r95_05, 相関係数表示",
        "why": "「止まっていれば撃てる」が個人で成り立つかの検証。",
    },
    "recoil_xy": {
        "name": "反動軌跡 オーバーレイ",
        "summary": "全 shot の発射後 1 秒 (x,y) を重ね描き",
        "formula": "shot ごとに samples[t<sub>fire</sub>:t<sub>fire</sub>+1s, 0:2] を半透明で重ねる",
        "why": "反動の形状一貫性。同じ軌跡が重なるほど持ち方が一定。",
    },
    "recoil_dir_amp": {
        "name": "反動方向 × 振幅",
        "summary": "極座標的に shot ごとに (方向, 振幅) をプロット",
        "formula": "X = recoil_direction (°), Y = recoil_peak (mm)",
        "why": "持ち方の一貫性。同じ方向に同じ大きさの反動が出るのが理想。",
    },
    "recoil_settle": {
        "name": "反動の戻り時間 推移",
        "summary": "shot ごとの settle_time の遷移",
        "formula": "y[shot] = recoil_settle (秒)",
        "why": "復元時間の trend。疲労で遅くなることがある。",
    },
    "recoil_peak_hist": {
        "name": "反動の振幅 推移",
        "summary": "shot ごとの peak_amplitude の遷移",
        "formula": "y[shot] = recoil_peak (mm)",
        "why": "振幅が一定なら銃のフィットが安定。",
    },
    "recoil_speed": {
        "name": "発射後速度 (現 trace)",
        "summary": "現在 shot の発射後 1 秒の |v(t)|",
        "formula": "|v(t)| over k ∈ [t<sub>fire</sub>, t<sub>fire</sub>+1s]",
        "why": "反動の速度プロファイル。peak 後にどう減衰するか。",
    },
    "cant_sd_history": {
        "name": "発射前 銃傾きの揺れ 推移",
        "summary": "shot ごとの cant_sd_deg",
        "formula": "y[shot] = std(degrees(cant[k]) for k ∈ 直前 0.5 秒)",
        "why": "発射直前のバランスの揺らぎが一貫しているか。",
    },
    "best_vs_worst": {
        "name": "ベスト 5 vs ワースト 5 比較",
        "summary": "session を S2 順に上位 / 下位 5 shot を選んで指標比較",
        "formula":
            "best  = top 5 shots by smallest r95_05<br>"
            "worst = bottom 5 shots by largest r95_05<br>"
            "両群で各指標の mean を比較表示",
        "why": "「良い時と悪い時で何が違うか」を直接見る。",
    },
    "condition_map": {
        "name": "コンディションマップ (心拍×HRV×S2)",
        "summary": "心拍を X, HRV を Y, S2 を色で 1 shot 1 点プロット",
        "formula":
            "X = hr_at_fire, Y = rmssd_30s, 色 = r95_05 (cmap)<br>"
            "サイズ = shot 順 (古→新)",
        "why": "心拍状態と安定度の 2 次元マップ。自分のスイートスポット領域が分かる。",
    },
}


def get_metric_doc(key: str) -> dict | None:
    return METRIC_DOCS.get(key)


def get_graph_doc(key: str) -> dict | None:
    return GRAPH_DOCS.get(key)


def render_doc_html(doc: dict) -> str:
    """ダイアログ表示用の HTML を組み立て。"""
    parts = [f"<h3>{doc['name']}</h3>"]
    if doc.get("summary"):
        parts.append(f"<p style='color:#444'>{doc['summary']}</p>")
    parts.append("<h4>計算式</h4>")
    parts.append(f"<p style='font-family:Menlo,monospace;font-size:13px'>{doc['formula']}</p>")
    if doc.get("why"):
        parts.append("<h4>何のために見るか</h4>")
        parts.append(f"<p>{doc['why']}</p>")
    if doc.get("range"):
        parts.append(f"<p><b>典型値:</b> {doc['range']}</p>")
    if doc.get("notes"):
        parts.append("<h4>注意点</h4>")
        parts.append(f"<p style='color:#666'>{doc['notes']}</p>")
    return "\n".join(parts)

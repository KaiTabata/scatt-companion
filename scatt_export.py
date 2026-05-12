"""shots / sessions データを CSV / JSON にエクスポートする。

外部解析(Excel、R、pandas 等)で使えるよう、フラットな構造で出力。
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from typing import Iterable, Optional


def _shot_to_row(s: dict) -> dict:
    """セッション内 shot dict から、CSV/JSON 用のフラットな dict を生成。"""
    summ = s.get("summary") or {}
    stab = {st.get("window_s"): st for st in (summ.get("stability") or [])}
    rec = summ.get("recoil") or {}
    last05 = summ.get("last_05s") or {}
    return {
        "shot_id":         s.get("shot_id"),
        "trace_id":        s.get("trace_id"),
        "session_id":      s.get("session_id"),
        "timer_ms":        s.get("timer_ms"),
        "trace_offset":    s.get("trace_offset"),
        "match_shot":      s.get("match_shot"),
        "missed":          s.get("missed"),
        "favorite":        s.get("favorite"),
        "fire_x_mm":       s.get("fire_x"),
        "fire_y_mm":       s.get("fire_y"),
        "fire_cant_rad":   s.get("fire_cant"),
        # SCATT 互換指標
        "ten_a_1s_pct":    (summ.get("ten_a_1s") or {}).get("percent"),
        "ten_a_05s_pct":   (summ.get("ten_a_05s") or {}).get("percent"),
        "ten_b_1s_pct":    (summ.get("ten_b_1s") or {}).get("percent"),
        "ten_b_05s_pct":   (summ.get("ten_b_05s") or {}).get("percent"),
        "nine_c_1s_pct":   (summ.get("nine_c_1s") or {}).get("percent"),
        # R95 (stability)
        "r95_05s_mm":      (stab.get(0.5) or {}).get("r95"),
        "r95_1s_mm":       (stab.get(1.0) or {}).get("r95"),
        "r95_2s_mm":       (stab.get(2.0) or {}).get("r95"),
        "r95_3s_mm":       (stab.get(3.0) or {}).get("r95"),
        # last 0.5s
        "cant_sd_last_05s_rad": last05.get("cant_std_rad"),
        "tremor_pre":      summ.get("tremor_power_pre"),
        "breath_pre":      summ.get("breathing_power_pre"),
        "spectrum_peak_hz": summ.get("spectrum_peak_hz"),
        # フェーズ / hold / aim / approach
        "pre_duration_s":  summ.get("pre_duration_s"),
        "post_duration_s": summ.get("post_duration_s"),
        "hold_s":          (summ.get("hold") or {}).get("hold_s"),
        "approach_monotonic": (summ.get("approach") or {}).get("monotonic_fraction"),
        "approach_signs_per_s": (summ.get("approach") or {}).get("sign_changes_per_s"),
        "timing_v":        s.get("timing_v"),
        # 反動
        "recoil_peak_mm":     rec.get("peak_r_mm"),
        "recoil_settle_s":    rec.get("settle_time_s"),
        "recoil_direction_deg": rec.get("direction_deg"),
        "recoil_post05_r95_mm": rec.get("post_05_r95_mm"),
        # 心拍 (extra.db から補完済)
        "hr_at_fire_bpm":  s.get("hr_at_fire"),
        "rmssd_30s_ms":    s.get("rmssd_30s"),
    }


def export_shots_csv(session_shots: Iterable[dict], path: str) -> int:
    """shot 群を CSV に出力。session_shots は fetch_session_shots 系の戻り値。"""
    rows = [_shot_to_row(s) for s in session_shots]
    if not rows:
        # 空でもヘッダだけ書く
        rows = [_shot_to_row({})]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def export_shots_json(session_shots: Iterable[dict], path: str,
                       include_samples: bool = False,
                       db_path: Optional[str] = None) -> int:
    """shot 群を JSON で出力。include_samples=True なら trace data も含める(重い)。"""
    out = []
    for s in session_shots:
        row = _shot_to_row(s)
        if include_samples and db_path:
            try:
                import zlib, struct
                XOR_KEY = bytes([
                    0xe3, 0x00, 0xe9, 0x00, 0x34, 0x85, 0x1d, 0x04,
                    0xf0, 0x95, 0xc0, 0x70, 0x0e, 0x1e, 0xb9, 0xf3,
                ])
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
                blob = conn.execute("SELECT data FROM traces WHERE trace_id = ?",
                                    (s.get("trace_id"),)).fetchone()
                conn.close()
                if blob and blob[0]:
                    body = blob[0][1:]
                    o = bytearray(len(body)); prev = 0
                    for i, c in enumerate(body):
                        o[i] = prev ^ c ^ XOR_KEY[i % 16]; prev = c
                    raw = zlib.decompress(bytes(o[1:])[2:][4:])
                    n = struct.unpack(">H", raw[12:14])[0]
                    samples = [
                        list(struct.unpack(">fff", raw[15+i*12:15+(i+1)*12]))
                        for i in range(n)
                    ]
                    row["samples"] = samples
            except Exception:
                pass
        out.append(row)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return len(out)


def export_session_summary_csv(sessions_data: Iterable[dict], path: str) -> int:
    """各 session の集計を 1 行ずつ CSV 出力。

    sessions_data: [{"session_id", "meta": {...}, "shots": [...]}]
    """
    import numpy as np
    rows = []
    for entry in sessions_data:
        sid = entry["session_id"]
        meta = entry.get("meta") or {}
        shots = entry.get("shots") or []
        ten_a_vals = []; s1_vals = []; s2_vals = []
        cant_vals = []; peak_vals = []; hr_vals = []
        for s in shots:
            summ = s.get("summary") or {}
            v = (summ.get("ten_a_1s") or {}).get("percent")
            if v is not None: ten_a_vals.append(v)
            for st in (summ.get("stability") or []):
                if st.get("window_s") == 1.0: s1_vals.append(st["r95"])
                if st.get("window_s") == 0.5: s2_vals.append(st["r95"])
            pk = (summ.get("recoil") or {}).get("peak_r_mm")
            if pk is not None: peak_vals.append(pk)
            if s.get("fire_cant") is not None: cant_vals.append(s["fire_cant"])
            if s.get("hr_at_fire") is not None: hr_vals.append(s["hr_at_fire"])
        def m(vs): return float(np.mean(vs)) if vs else None
        def sd(vs): return float(np.std(vs)) if vs else None
        rows.append({
            "session_id":   sid,
            "distance_m":   meta.get("distance"),
            "position":     meta.get("position_name"),
            "n_shots":      len(shots),
            "ten_a_1s_mean":  m(ten_a_vals),
            "s1_mean_mm":    m(s1_vals),
            "s2_mean_mm":    m(s2_vals),
            "s2_std_mm":     sd(s2_vals),
            "recoil_peak_mean_mm": m(peak_vals),
            "cant_mean_rad": m(cant_vals),
            "hr_mean_bpm":   m(hr_vals),
        })
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)

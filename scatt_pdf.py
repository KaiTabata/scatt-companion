"""セッション 1 件を PDF レポートとして書き出す。

QTextDocument + QPdfWriter で HTML テンプレを A4 PDF に変換。
グラフ画像は同梱せず、テキスト統計と shot テーブルが中心の軽量レポート。
"""

from __future__ import annotations

import datetime
import os
from typing import Optional

import numpy as np
from PyQt6.QtCore import QSizeF, QMarginsF, Qt
from PyQt6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument


POSITION_NAMES_JP = {0: "伏射", 1: "立射", 2: "膝射", 3: "その他"}


def _shot_table_row(idx: int, s: dict) -> str:
    summ = s.get("summary") or {}
    stab = {st.get("window_s"): st for st in (summ.get("stability") or [])}
    def get_r95(w): return stab.get(w, {}).get("r95")
    def pct(k): return (summ.get(k) or {}).get("percent")
    t_str = datetime.datetime.fromtimestamp(s["timer_ms"] / 1000).strftime("%H:%M:%S")
    flags = []
    if s.get("match_shot"): flags.append("M")
    if s.get("favorite"): flags.append("★")
    if s.get("missed"): flags.append("X")
    cant = np.degrees(s["fire_cant"]) if s.get("fire_cant") is not None else None
    fx, fy = s.get("fire_x"), s.get("fire_y")
    dist = (fx * fx + fy * fy) ** 0.5 if (fx is not None and fy is not None) else None

    def fmt(v, digits=2, suffix=""):
        return f"{v:.{digits}f}{suffix}" if v is not None else "—"

    return (
        f"<tr>"
        f"<td>{idx}</td>"
        f"<td>{t_str}</td>"
        f"<td>{fmt(dist, 0)}</td>"
        f"<td>{fmt(pct('ten_a_1s'), 1)}</td>"
        f"<td>{fmt(pct('ten_a_05s'), 1)}</td>"
        f"<td>{fmt(get_r95(1.0), 2)}</td>"
        f"<td>{fmt(get_r95(0.5), 2)}</td>"
        f"<td>{(f'{cant:+.2f}' if cant is not None else '—')}</td>"
        f"<td>{' '.join(flags)}</td>"
        f"</tr>"
    )


def _session_summary_table(shots: list[dict]) -> str:
    """セッション集計テーブル。"""
    s2s, s1s, ten_a_s, ten_a05_s = [], [], [], []
    cants, hrs, peaks, hold_s = [], [], [], []
    for s in shots:
        summ = s.get("summary") or {}
        for st in (summ.get("stability") or []):
            if st.get("window_s") == 0.5: s2s.append(st["r95"])
            if st.get("window_s") == 1.0: s1s.append(st["r95"])
        v = (summ.get("ten_a_1s") or {}).get("percent")
        if v is not None: ten_a_s.append(v)
        v = (summ.get("ten_a_05s") or {}).get("percent")
        if v is not None: ten_a05_s.append(v)
        if s.get("fire_cant") is not None: cants.append(np.degrees(s["fire_cant"]))
        if s.get("hr_at_fire") is not None: hrs.append(s["hr_at_fire"])
        pk = (summ.get("recoil") or {}).get("peak_r_mm")
        if pk is not None: peaks.append(pk)
        h = (summ.get("hold") or {}).get("hold_s")
        if h is not None: hold_s.append(h)

    def stats(vs, digits=2):
        if not vs:
            return "—"
        return (f"平均 {np.mean(vs):.{digits}f} · σ {np.std(vs):.{digits}f} · "
                f"最小 {np.min(vs):.{digits}f} · 最大 {np.max(vs):.{digits}f}")

    rows = [
        ("10a (1秒)",        stats(ten_a_s, 1),    "%"),
        ("10a-0.5 (0.5秒)",   stats(ten_a05_s, 1), "%"),
        ("S1 (1秒安定)",       stats(s1s, 2),       "mm"),
        ("S2 (0.5秒安定)",     stats(s2s, 2),       "mm"),
        ("銃の傾き (撃発時)",   stats(cants, 2),     "°"),
        ("静止時間 (直前)",     stats(hold_s, 2),    "秒"),
        ("反動の振幅",         stats(peaks, 1),     "mm"),
        ("心拍 (撃発時)",      stats(hrs, 0),       "bpm"),
    ]
    body = "".join(
        f"<tr><td>{k}</td><td>{v} {u}</td></tr>"
        for k, v, u in rows
    )
    return f"<table border='1' cellspacing='0' cellpadding='6'>{body}</table>"


def _build_pdf_html(session_meta: dict, shots: list[dict],
                    feedback_text: str = "") -> str:
    sid = session_meta.get("session_id", "—")
    pos = POSITION_NAMES_JP.get(session_meta.get("position"),
                                session_meta.get("position_name", "—"))
    dist = session_meta.get("distance", "—")
    n = len(shots)
    last_ts = shots[-1]["timer_ms"] if shots else None
    date_str = (datetime.datetime.fromtimestamp(last_ts / 1000)
                .strftime("%Y-%m-%d %H:%M")) if last_ts else "—"
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    shot_rows = "".join(_shot_table_row(i + 1, s) for i, s in enumerate(shots))

    fb_html = ""
    if feedback_text:
        fb_html = (
            "<h2>所見</h2>"
            f"<div style='background:#f5f7fa; padding:10px; border:1px solid #ddd;'>"
            f"{feedback_text.replace(chr(10), '<br>')}"
            f"</div>"
        )

    return f"""
<html>
<head>
<style>
  body {{ font-family: -apple-system, "Hiragino Kaku Gothic ProN", sans-serif;
          color: #222; font-size: 11pt; }}
  h1 {{ font-size: 18pt; margin: 0 0 4px; }}
  h2 {{ font-size: 13pt; color: #1a4a8a; margin: 18px 0 6px;
        border-bottom: 1px solid #aac; padding-bottom: 3px; }}
  .meta {{ color: #555; font-size: 10pt; margin-bottom: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 9pt; }}
  th, td {{ border: 1px solid #ccd; padding: 3px 6px; text-align: left; }}
  th {{ background: #eef; }}
  td.num {{ text-align: right; }}
</style>
</head>
<body>

<h1>Session #{sid}  レポート</h1>
<div class='meta'>
  日時: {date_str} ·  距離 {dist}m ·  姿勢 {pos} ·  shot 数 {n} ·
  作成日 {generated}
</div>

<h2>集計</h2>
{_session_summary_table(shots)}

<h2>Shot 一覧</h2>
<table>
<tr>
  <th>#</th><th>時刻</th><th>中心からの距離(mm)</th>
  <th>10a%</th><th>10a-0.5%</th><th>S1(mm)</th><th>S2(mm)</th><th>傾き(°)</th><th>flags</th>
</tr>
{shot_rows}
</table>

{fb_html}

<p style='margin-top:30px; font-size:8pt; color:#888;'>
SCATT Companion  ·  非公式の補助分析ツール  ·  Apache 2.0
</p>

</body>
</html>
"""


def export_session_pdf(path: str, session_meta: dict, shots: list[dict],
                       feedback_text: str = "") -> str:
    """セッション PDF を生成。`path` に出力、戻り値: 出力ファイル path。"""
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setResolution(150)
    try:
        writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    except Exception:
        pass
    doc = QTextDocument()
    doc.setHtml(_build_pdf_html(session_meta, shots, feedback_text))
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print(writer)
    return path

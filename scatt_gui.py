#!/opt/homebrew/bin/python3.10
"""SCATT Live Viewer (PyQt6 + pyqtgraph, ダーク + タブ構成)

伏射 (prone) に特化した補助ソフト。本家 SCATT の軌跡描画は補助として
タブの中に納め、メインは「本家にない指標」を一覧表示する。

タブ:
  Dashboard  - 直近 shot の KPI + 速度時系列 (発射 = 0 軸)
  Spectrum   - FFT スペクトル (振戦・呼吸)
  Shots      - セッション内 shot の KPI 一覧テーブル
  Drift      - shot 間ドリフト & Cant 相関散布図
  Target     - ターゲット + 軌跡 (確認用)

実行: /opt/homebrew/bin/python3.10 scatt_gui.py
"""

from __future__ import annotations

import argparse
import atexit
import os
import sqlite3
import struct
import subprocess
import sys
import time
import zlib

import numpy as np
import pyqtgraph as pg
import collections
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QRectF, QSettings, QByteArray
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
    QGraphicsPathItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QStatusBar, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextBrowser, QToolBar, QVBoxLayout, QGridLayout, QWidget,
)

# 自作分析モジュール
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scatt_analysis as A
import scatt_heart as H
import scatt_storage as ST
import scatt_feedback as FB
import scatt_export as EX


DEFAULT_DB = os.path.expanduser(
    "~/Library/Application Support/SCATT Electronics/Scatt Expert/storage.dat"
)
SUSPICIOUS_RADIUS_MM = 200.0  # 発射点がターゲット中心から N mm 以上 = 誤反応とみなす


# --- 設定 ---
class S:
    """QSettings ラッパ。型推論つき get/set、デフォルト値を一元管理。"""

    # default 値で型を決める
    DEFAULTS = {
        # window
        "window/geometry": None,           # QByteArray, restoreGeometry 用
        "window/splitter":  None,
        # behavior
        "behavior/live_on_startup": True,
        "behavior/polling_interval_s": 0.3,
        "behavior/always_on_top": False,
        "behavior/caffeinate": True,
        # thresholds
        "thresh/suspicious_radius_mm": 200.0,
        "thresh/hold_velocity_mm_s": 15.0,
        "thresh/r95_good_mm": 2.0,
        "thresh/r95_bad_mm": 5.0,
        "thresh/z_warn": 0.5,    # 「普段通り」判定を厳しく (0.5σ 以内のみ普通)
        "thresh/z_bad": 1.5,
        # layout
        "layout/dashboard_mode": "default",  # default | focused (main 2 graphs only)
        "layout/dashboard_graph_rows": 2,    # 1, 2, 3
        "layout/dashboard_graph_cols": 2,    # 1, 2, 3
        "layout/graph_default_1": "velocity",
        "layout/graph_default_2": "scatter",
        "layout/graph_default_3": "r95_history",
        "layout/graph_default_4": "r95_bars",
        "layout/graph_default_5": "cant_history",
        "layout/graph_default_6": "spectrum",
        "layout/graph_default_7": "trace_xy",
        "layout/graph_default_8": "timing_history",
        "layout/graph_default_9": "hold_history",
        "layout/show_shot_list": True,
        "layout/show_hero_cards": True,
        "layout/show_metrics_table": True,
        # tabs visibility
        "tabs/dashboard": True,
        "tabs/sessions": True,
        "tabs/spectrum": True,
        "tabs/shots": True,
        "tabs/recoil": True,
        "tabs/cant": True,
        "tabs/drift": True,
        "tabs/target": True,
        "tabs/help": True,
        # heart
        "heart/mode": "off",            # off | ble | mock
        "heart/device_address": "",     # 空 = 自動スキャン
        "heart/auto_start": False,
    }

    def __init__(self):
        self._q = QSettings("scatt-prone", "analyzer")

    def get(self, key: str):
        default = self.DEFAULTS.get(key)
        v = self._q.value(key, default)
        if v is None:
            return default
        # 型変換 (QSettings は文字列で保存される場合がある)
        if isinstance(default, bool):
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes")
            return bool(v)
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default
        return v

    def set(self, key: str, value):
        self._q.setValue(key, value)
        self._q.sync()

    def reset_window(self):
        self._q.remove("window/geometry")
        self._q.remove("window/splitter")
        self._q.sync()


SETTINGS = S()
XOR_KEY = bytes([
    0xe3, 0x00, 0xe9, 0x00, 0x34, 0x85, 0x1d, 0x04,
    0xf0, 0x95, 0xc0, 0x70, 0x0e, 0x1e, 0xb9, 0xf3,
])


# --- 色定義 (白背景・オフィススタイル) ---
class C:
    BG       = QColor(255, 255, 255)
    PANEL    = QColor(250, 250, 251)
    PANEL_LO = QColor(244, 244, 246)
    BORDER   = QColor(220, 220, 225)
    BORDER_STRONG = QColor(180, 180, 185)
    FG       = QColor(30, 30, 34)
    FG_MUTED = QColor(110, 110, 118)
    # アクセント色 (落ち着いた配色)
    ACCENT_G = QColor(40, 130, 70)     # 良好
    ACCENT_O = QColor(190, 110, 25)    # 警告
    ACCENT_R = QColor(180, 50, 50)     # 問題
    ACCENT_Y = QColor(170, 130, 0)     # 発射点
    ACCENT_B = QColor(50, 100, 175)    # 情報
    ACCENT_P = QColor(120, 80, 170)    # 補助

    # ターゲットは本物のターゲットらしい色 (白背景でも黒地は黒、白地は白)
    TARGET_WHITE = QColor(245, 245, 245)
    TARGET_BLACK = QColor(20, 20, 20)
    TARGET_LINE_LIGHT = QColor(120, 120, 125)
    TARGET_LINE_DARK  = QColor(220, 220, 220)


def hex_of(c: QColor) -> str:
    return f"rgb({c.red()},{c.green()},{c.blue()})"


pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', '#333')


# --- 復号 ---
def decode_trace(blob: bytes):
    if not blob or blob[0] != 0x01:
        raise ValueError("bad version byte")
    body = blob[1:]
    out = bytearray(len(body))
    prev = 0
    for i, c in enumerate(body):
        out[i] = prev ^ c ^ XOR_KEY[i % 16]
        prev = c
    raw = zlib.decompress(bytes(out[1:])[2:][4:])
    if raw[:4] != b"\x0a\x0b\x0c\x0d":
        raise ValueError("bad magic")
    n = struct.unpack(">H", raw[12:14])[0]
    return [
        struct.unpack(">fff", raw[15 + i * 12:15 + (i + 1) * 12]) for i in range(n)
    ]


def fetch_shots_for_trace(conn: sqlite3.Connection, trace_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT shot_id, trace_offset, phase, match_shot, deleted, favorite, missed "
        "FROM shots WHERE trace_id = ? AND deleted = 0 ORDER BY trace_offset",
        (trace_id,),
    ).fetchall()
    return [
        {"shot_id": r[0], "trace_offset": r[1], "phase": r[2],
         "match_shot": r[3], "deleted": r[4], "favorite": r[5], "missed": r[6]}
        for r in rows
    ]


def delete_shots(db_path: str, shot_ids: list[int]) -> dict:
    """対象 shot を物理削除し、その結果孤立した trace 行も削除する。

    返り値: {"shots": 削除 shot 数, "traces": [削除 trace_id, ...]}
    SCATT 起動中でも書き込めるよう busy_timeout を長めに取る。
    """
    if not shot_ids:
        return {"shots": 0, "traces": []}
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 5000;")
    cur = conn.cursor()
    # 対象 shot の trace_id を先に集める
    trace_ids: set[int] = set()
    for sid in shot_ids:
        row = cur.execute("SELECT trace_id FROM shots WHERE shot_id = ?", (sid,)).fetchone()
        if row:
            trace_ids.add(row[0])
    # shots を物理削除
    cur.executemany("DELETE FROM shots WHERE shot_id = ?", [(sid,) for sid in shot_ids])
    # 削除後に shot が残っていない trace は traces 行ごと削除
    deleted_traces: list[int] = []
    for tid in trace_ids:
        n_rem = cur.execute(
            "SELECT COUNT(*) FROM shots WHERE trace_id = ?", (tid,)
        ).fetchone()[0]
        if n_rem == 0:
            cur.execute("DELETE FROM traces WHERE trace_id = ?", (tid,))
            deleted_traces.append(tid)
    conn.commit()
    conn.close()
    return {"shots": len(shot_ids), "traces": deleted_traces}


POSITION_NAMES = {0: "prone", 1: "standing", 2: "kneeling", 3: "other"}


def fetch_session_meta(conn: sqlite3.Connection, session_id: int) -> dict:
    row = conn.execute(
        "SELECT distance, caliber, position, sample_rate, shot_count "
        "FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        return {}
    return {
        "session_id": session_id,
        "distance": row[0], "caliber": row[1],
        "position": row[2], "sample_rate": row[3],
        "shot_count": row[4],
        "position_name": POSITION_NAMES.get(row[2], f"pos{row[2]}"),
    }


def fetch_session_shots_by_filter(conn: sqlite3.Connection, scope: str,
                                  current_session_id: int) -> list[dict]:
    """scope:
      "session"  -> current_session のみ
      "position" -> current の position と同じ session 群を集約
      "all"      -> 全 shot
    """
    if scope == "session":
        return fetch_session_shots(conn, current_session_id)
    if scope == "position":
        meta = fetch_session_meta(conn, current_session_id)
        pos = meta.get("position")
        if pos is None:
            return fetch_session_shots(conn, current_session_id)
        sids = [r[0] for r in conn.execute(
            "SELECT session_id FROM sessions WHERE position = ?", (pos,)
        ).fetchall()]
    elif scope == "all":
        sids = [r[0] for r in conn.execute(
            "SELECT DISTINCT session_id FROM sessions"
        ).fetchall()]
    else:
        sids = [current_session_id]
    out: list[dict] = []
    for sid in sids:
        out.extend(fetch_session_shots(conn, sid))
    return out


def fetch_session_shots(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    """セッション内の全 shot をメタ情報込みで取得 (D, E タブ用)。"""
    rows = conn.execute(
        "SELECT sh.shot_id, sh.trace_id, sh.timer, sh.trace_offset, sh.phase, "
        "       sh.match_shot, sh.missed, sh.favorite, t.data, ss.sample_rate "
        "FROM shots sh "
        "JOIN traces t ON t.trace_id = sh.trace_id "
        "JOIN sessions ss ON ss.session_id = t.session_id "
        "WHERE t.session_id = ? AND sh.deleted = 0 "
        "ORDER BY sh.timer",
        (session_id,),
    ).fetchall()
    result = []
    for sid_id, tid, ts, tro, ph, ms, miss, fav, blob, sr in rows:
        try:
            samples = decode_trace(blob)
            fire = samples[tro] if 0 <= tro < len(samples) else None
            t_arr = A.to_trace_arrays(samples, sr, tro)
            summ = A.summarize(t_arr)
        except Exception:
            continue
        # 撃発タイミング速度
        timing_v = None
        if fire is not None and 0 < tro < len(samples):
            dx = samples[tro][0] - samples[tro - 1][0]
            dy = samples[tro][1] - samples[tro - 1][1]
            timing_v = (dx * dx + dy * dy) ** 0.5 * sr
        result.append({
            "shot_id": sid_id, "trace_id": tid, "timer_ms": ts,
            "trace_offset": tro, "phase": ph,
            "match_shot": ms, "missed": miss, "favorite": fav,
            "fire_x": fire[0] if fire else None,
            "fire_y": fire[1] if fire else None,
            "fire_cant": fire[2] if fire else None,
            "summary": summ,
            "sample_rate": sr,
            "timing_v": timing_v,
        })
    return result


# --- Poller ---
class PollerThread(QThread):
    new_trace = pyqtSignal(dict)
    active_session_changed = pyqtSignal(int)  # SCATT 側のセッションが変わった時

    def __init__(self, db_path: str, interval: float = 0.3):
        super().__init__()
        self.db_path = db_path
        self.interval = interval
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 1000;")
        last_id = conn.execute(
            "SELECT COALESCE(MAX(trace_id), 0) FROM traces"
        ).fetchone()[0]
        session_cache: dict = {}
        active_sid: int | None = None
        # 初期 active セッション(現状の最新 trace のセッション)
        try:
            row = conn.execute(
                "SELECT session_id FROM traces ORDER BY trace_id DESC LIMIT 1"
            ).fetchone()
            if row:
                active_sid = row[0]
                self.active_session_changed.emit(active_sid)
        except sqlite3.OperationalError:
            pass

        while self._running:
            # active session 検出(最新 trace の session_id を毎周確認)
            try:
                row = conn.execute(
                    "SELECT session_id FROM traces ORDER BY trace_id DESC LIMIT 1"
                ).fetchone()
                if row and row[0] != active_sid:
                    active_sid = row[0]
                    self.active_session_changed.emit(active_sid)
            except sqlite3.OperationalError:
                pass

            try:
                rows = conn.execute(
                    "SELECT trace_id, session_id, timer, timer_enter, data FROM traces "
                    "WHERE trace_id > ? ORDER BY trace_id ASC",
                    (last_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                time.sleep(self.interval)
                continue
            for tid, sid, ts, te, blob in rows:
                try:
                    samples = decode_trace(blob)
                except Exception:
                    last_id = tid
                    continue
                if sid not in session_cache:
                    s = conn.execute(
                        "SELECT distance, caliber, position, sample_rate FROM sessions "
                        "WHERE session_id = ?", (sid,),
                    ).fetchone()
                    session_cache[sid] = (
                        {"distance": s[0], "caliber": s[1], "position": s[2], "sample_rate": s[3]}
                        if s else {}
                    )
                shots = fetch_shots_for_trace(conn, tid)
                self.new_trace.emit({
                    "trace_id": tid, "session_id": sid,
                    "timer_ms": ts, "timer_enter_ms": te,
                    "samples": samples, "session": session_cache[sid],
                    "shots": shots,
                })
                last_id = tid
            time.sleep(self.interval)
        conn.close()


# ===========================================================================
# Tab 1: Dashboard
# ===========================================================================

def _metric_value(t: dict, key: str) -> float | None:
    """summary dict + 補助値 から指標値を取り出す。1 ヶ所で定義することで集計と整合させる。"""
    summ = t["summary"]
    if key == "timing_v":
        return t.get("timing_v")
    if key == "r95_05":
        return (summ.get("last_05s") or {}).get("r95")
    if key == "cant_at_fire_deg":
        return t.get("cant_at_fire_deg")
    if key == "cant_sd_deg":
        v = (summ.get("last_05s") or {}).get("cant_std_rad")
        return np.degrees(v) if v is not None else None
    if key == "hold_s":
        return (summ.get("hold") or {}).get("hold_s")
    if key == "aim_s":
        return summ.get("pre_duration_s")
    if key.startswith("r95_"):
        win_map = {"r95_1": 1.0, "r95_2": 2.0, "r95_3": 3.0}
        win = win_map.get(key)
        for s in (summ.get("stability") or []):
            if s.get("window_s") == win:
                return s.get("r95")
        return None
    if key == "tremor":
        return summ.get("tremor_power_pre")
    if key == "breath":
        return summ.get("breathing_power_pre")
    if key == "approach_mono":
        return (summ.get("approach") or {}).get("monotonic_fraction")
    if key == "approach_signs":
        return (summ.get("approach") or {}).get("sign_changes_per_s")
    if key == "hr_at_fire":
        return t.get("hr_at_fire")
    if key == "rmssd_30s":
        return t.get("rmssd_30s")
    # SCATT 互換: 10a / 10a-0.5 / 10b (inner10) / 9c
    if key == "ten_a_1s":
        return (summ.get("ten_a_1s") or {}).get("percent")
    if key == "ten_a_05s":
        return (summ.get("ten_a_05s") or {}).get("percent")
    if key == "ten_b_1s":
        return (summ.get("ten_b_1s") or {}).get("percent")
    if key == "ten_b_05s":
        return (summ.get("ten_b_05s") or {}).get("percent")
    if key == "nine_c_1s":
        return (summ.get("nine_c_1s") or {}).get("percent")
    if key == "nine_c_05s":
        return (summ.get("nine_c_05s") or {}).get("percent")
    # 反動詳細
    if key == "recoil_peak":
        return (summ.get("recoil") or {}).get("peak_r_mm")
    if key == "recoil_direction":
        return (summ.get("recoil") or {}).get("direction_deg")
    if key == "recoil_settle":
        return (summ.get("recoil") or {}).get("settle_time_s")
    if key == "recoil_post05_r95":
        return (summ.get("recoil") or {}).get("post_05_r95_mm")
    if key == "recoil_dir_std":
        return (summ.get("recoil") or {}).get("direction_std_deg")
    return None


# 指標定義: (key, ラベル, 単位, "low_good"|"high_good"|"abs_low_good"|"info", 表示桁)
METRICS = [
    # ----- SCATT 互換 (本家と同じ命名) -----
    ("ten_a_1s",         "10a (10-ring, 1s)",         "%",    "high_good",    1),
    ("ten_a_05s",        "10a-0.5 (10-ring, 0.5s)",   "%",    "high_good",    1),
    ("r95_1",            "S1 (1s stability)",         "mm",   "low_good",     2),
    ("r95_05",           "S2 (0.5s stability)",       "mm",   "low_good",     2),
    # ----- 補助指標 -----
    ("ten_b_1s",         "10b (inner-10, 1s)",        "%",    "high_good",    1),
    ("ten_b_05s",        "10b-0.5",                   "%",    "high_good",    1),
    ("nine_c_1s",        "9c (9-ring, 1s)",           "%",    "high_good",    1),
    ("r95_2",            "R95 last 2s",               "mm",   "low_good",     2),
    ("r95_3",            "R95 last 3s",               "mm",   "low_good",     2),
    ("timing_v",         "Trigger timing",            "mm/s", "low_good",     1),
    ("cant_at_fire_deg", "Cant (at fire)",            "°",    "info",         2),
    ("cant_sd_deg",      "Cant σ (last 0.5s)",        "°",    "low_good",     3),
    ("hold_s",           "Hold time (last)",          "s",    "high_good",    2),
    ("aim_s",            "Aim duration",              "s",    "info",         1),
    ("tremor",           "Tremor 8–12Hz",             "",     "low_good",     4),
    ("breath",           "Breath 0.15–0.5Hz",         "",     "low_good",     3),
    ("approach_mono",    "Approach monotonic",        "",     "high_good",    2),
    ("approach_signs",   "Approach oscill /s",        "",     "low_good",     1),
    ("hr_at_fire",       "HR at fire",                "bpm",  "low_good",     0),
    ("rmssd_30s",        "HRV (RMSSD 30s)",           "ms",   "high_good",    1),
    # ----- 反動受け -----
    ("recoil_peak",         "Recoil peak amplitude",     "mm",   "low_good",     1),
    ("recoil_settle",       "Recoil settle time (<5mm)", "s",    "low_good",     2),
    ("recoil_post05_r95",   "Follow-through R95 (0.5s)", "mm",   "low_good",     1),
    ("recoil_dir_std",      "Recoil direction σ",        "°",    "low_good",     0),
    ("recoil_direction",    "Recoil direction angle",    "°",    "info",         0),
]


def compute_session_stats(session_shots: list[dict]) -> dict[str, tuple[float, float]]:
    """session 内の全 shot から各指標の (μ, σ) を計算。"""
    bag: dict[str, list[float]] = {k: [] for (k, _, _, _, _) in METRICS}
    for s in session_shots:
        summ = s.get("summary") or {}
        if not summ:
            continue
        # 撃発タイミング (s に既に格納)
        t_obj = {
            "summary": summ,
            "timing_v": s.get("timing_v"),
            "cant_at_fire_deg": (
                np.degrees(s["fire_cant"]) if s.get("fire_cant") is not None else None
            ),
            "hr_at_fire": s.get("hr_at_fire"),
            "rmssd_30s": s.get("rmssd_30s"),
        }
        for key, _, _, _, _ in METRICS:
            v = _metric_value(t_obj, key)
            if v is not None and np.isfinite(v):
                bag[key].append(float(v))
    out: dict[str, tuple[float, float]] = {}
    for k, vals in bag.items():
        if len(vals) >= 2:
            out[k] = (float(np.mean(vals)), float(np.std(vals)))
    return out


def color_for_metric(v: float | None, direction: str,
                     stats: tuple[float, float] | None) -> QColor:
    """指標値 v を μ,σ と比較し、外れ具合に応じた色を返す。

    direction:
      low_good  : 小さいほど良い (R95 等)
      high_good : 大きいほど良い (Hold time 等)
      abs_low_good : 絶対値が小さいほど良い (cant)
      info      : 色付けなし
    """
    if v is None or stats is None:
        return C.FG
    mu, sigma = stats
    if sigma <= 0:
        return C.FG
    if direction == "info":
        return C.FG
    if direction == "abs_low_good":
        v = abs(v); mu = abs(mu)
    z = (v - mu) / sigma
    if direction == "high_good":
        z = -z  # 大きいほど良い → 反転して評価
    # z > 0 = 悪い、z < 0 = 良い
    z_warn = SETTINGS.get("thresh/z_warn")
    z_bad = SETTINGS.get("thresh/z_bad")
    if z >= z_bad:
        return C.ACCENT_R
    if z >= z_warn:
        return C.ACCENT_O
    if z <= -z_bad:
        return C.ACCENT_G
    if z <= -z_warn:
        return QColor(0, 110, 60)
    return C.FG


def _hero_card(title: str, unit: str) -> tuple[QWidget, QLabel, QLabel, QLabel]:
    """主役カード (大きな数字)。返り値: (widget, value_label, unit_label, sub_label)"""
    w = QWidget()
    w.setStyleSheet(
        f"QWidget {{ background-color: {hex_of(C.PANEL)};"
        f" border: 1px solid {hex_of(C.BORDER)}; border-radius: 3px; }}"
    )
    lay = QVBoxLayout(w)
    lay.setContentsMargins(16, 10, 16, 10)
    lay.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; border: none;"
    )
    title_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    val_row = QHBoxLayout()
    val_row.setSpacing(4)
    val_lbl = QLabel("—")
    val_lbl.setStyleSheet(
        f"color: {hex_of(C.FG)}; font-family: 'SF Mono', 'Menlo', monospace;"
        " font-size: 36px; font-weight: 400; border: none; background: transparent;"
    )
    unit_lbl = QLabel(unit)
    unit_lbl.setStyleSheet(
        f"color: {hex_of(C.FG_MUTED)}; font-size: 14px; border: none; background: transparent;"
    )
    unit_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom)
    val_row.addWidget(val_lbl, stretch=0, alignment=Qt.AlignmentFlag.AlignBottom)
    val_row.addWidget(unit_lbl, stretch=0, alignment=Qt.AlignmentFlag.AlignBottom)
    val_row.addStretch(1)
    sub_lbl = QLabel("")
    sub_lbl.setStyleSheet(
        f"color: {hex_of(C.FG_MUTED)}; font-size: 10px;"
        " font-family: 'SF Mono', 'Menlo', monospace;"
        " border: none; background: transparent;"
    )
    lay.addWidget(title_lbl)
    lay.addLayout(val_row)
    lay.addWidget(sub_lbl)
    return w, val_lbl, unit_lbl, sub_lbl


# ===========================================================================
# 選択可能なグラフ枠
# ===========================================================================

# グラフ種別の定義: key -> (label, render_function)
# render_function は (plot_widget, t_arr, samples, sample_rate, session_shots) を受ける
def _gr_velocity(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setLabel('left', 'velocity', units='mm/s')
    pw.setLabel('bottom', 't', units='s')
    pw.setTitle("Velocity vs time-from-fire")
    pw.addLine(x=0, pen=pg.mkPen(C.ACCENT_Y, width=1.5, style=Qt.PenStyle.DashLine))
    v = A.velocity(t_arr)
    if len(v) == 0:
        return
    t_axis = (np.arange(len(v)) + 0.5) / sr
    if t_arr.trace_offset is not None:
        t_axis -= t_arr.trace_offset / sr
    if t_arr.trace_offset is not None and 0 < t_arr.trace_offset < len(v):
        pw.plot(t_axis[:t_arr.trace_offset], v[:t_arr.trace_offset],
                pen=pg.mkPen(C.ACCENT_G, width=1.5))
        pw.plot(t_axis[t_arr.trace_offset:], v[t_arr.trace_offset:],
                pen=pg.mkPen(C.ACCENT_R, width=1.2))
    else:
        pw.plot(t_axis, v, pen=pg.mkPen(C.ACCENT_G, width=1.5))
    pw.addLine(y=15, pen=pg.mkPen(C.FG_MUTED, width=0.7, style=Qt.PenStyle.DotLine))


def _gr_r95_bars(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setLabel('left', 'R95', units='mm')
    pw.setLabel('bottom', '')
    pw.setTitle("Recent 5 shots R95 (last 0.5s)")
    pw.showGrid(x=False, y=True, alpha=0.15)
    if not sessshots:
        return
    recent = []
    for s in sessshots[-5:]:
        v_r = ((s.get("summary") or {}).get("last_05s") or {}).get("r95")
        if v_r is not None:
            recent.append(v_r)
    if not recent:
        return
    for i, val in enumerate(recent):
        is_current = (i == len(recent) - 1)
        col = C.ACCENT_B if is_current else QColor(190, 190, 195)
        bar = pg.BarGraphItem(
            x=[i], height=[val], width=0.7,
            brush=col, pen=pg.mkPen(C.BORDER_STRONG))
        pw.addItem(bar)
    pw.getAxis('bottom').setTicks([[(i, "now" if i == len(recent) - 1 else f"-{len(recent)-1-i}")
                                     for i in range(len(recent))]])


def _gr_shot_scatter(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("Shot impact scatter (mm)")
    pw.setLabel('left', 'Y', units='mm')
    pw.setLabel('bottom', 'X', units='mm')
    pw.setAspectLocked(True)
    pw.addLine(x=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
    pw.addLine(y=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
    if not sessshots:
        return
    valid = [s for s in sessshots if s.get("fire_x") is not None and s.get("fire_y") is not None]
    if not valid:
        return
    # SCATT 座標は y が下向き正 → pyqtgraph (y上向き) では反転
    xs = np.array([s["fire_x"] for s in valid])
    ys = -np.array([s["fire_y"] for s in valid])
    n = len(valid)
    for i, (xi, yi) in enumerate(zip(xs, ys)):
        f = i / max(1, n - 1)
        col = (int(60 + f * 180), int(100 - f * 80), int(180 - f * 130))
        is_current = (i == n - 1)
        pw.plot([xi], [yi], pen=None, symbol='o',
                symbolSize=10 if is_current else 7,
                symbolBrush=col,
                symbolPen=pg.mkPen(C.FG, width=0.8))
    cx, cy = float(np.mean(xs)), float(np.mean(ys))
    rs = np.hypot(xs - cx, ys - cy)
    r95 = float(np.percentile(rs, 95)) if len(rs) >= 2 else 0
    pw.plot([cx], [cy], pen=None, symbol='+', symbolSize=14,
            symbolPen=pg.mkPen(C.ACCENT_Y, width=2), symbolBrush=None)
    if r95 > 0:
        theta = np.linspace(0, 2 * np.pi, 64)
        pw.plot(cx + r95 * np.cos(theta), cy + r95 * np.sin(theta),
                pen=pg.mkPen(C.ACCENT_Y, width=1, style=Qt.PenStyle.DashLine))


def _gr_trace_xy(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("Current trace path (mm)")
    pw.setLabel('left', 'Y', units='mm')
    pw.setLabel('bottom', 'X', units='mm')
    pw.setAspectLocked(True)
    pw.addLine(x=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
    pw.addLine(y=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
    if not samples:
        return
    # y 反転 (SCATT y↓ → pyqtgraph y↑)
    xs = np.array([s[0] for s in samples])
    ys = -np.array([s[1] for s in samples])
    if t_arr.trace_offset is not None and 0 < t_arr.trace_offset < len(samples):
        pw.plot(xs[:t_arr.trace_offset + 1], ys[:t_arr.trace_offset + 1],
                pen=pg.mkPen(C.ACCENT_G, width=1.5))
        pw.plot(xs[t_arr.trace_offset:], ys[t_arr.trace_offset:],
                pen=pg.mkPen(C.ACCENT_R, width=1.0))
        pw.plot([xs[t_arr.trace_offset]], [ys[t_arr.trace_offset]],
                pen=None, symbol='+', symbolSize=14,
                symbolPen=pg.mkPen(C.ACCENT_Y, width=2), symbolBrush=None)
    else:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_G, width=1.5))


def _gr_cant_time(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("Cant over time (deg)")
    pw.setLabel('left', 'cant', units='°')
    pw.setLabel('bottom', 't', units='s')
    pw.addLine(x=0, pen=pg.mkPen(C.ACCENT_Y, width=1.5, style=Qt.PenStyle.DashLine))
    if not samples:
        return
    cants = np.array([np.degrees(s[2]) for s in samples])
    t_axis = np.arange(len(cants)) / sr
    if t_arr.trace_offset is not None:
        t_axis -= t_arr.trace_offset / sr
    pw.plot(t_axis, cants, pen=pg.mkPen(C.ACCENT_B, width=1.2))


def _gr_spectrum(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("FFT spectrum (pre-trigger)")
    pw.setLabel('left', 'magnitude')
    pw.setLabel('bottom', 'frequency', units='Hz')
    pw.setLogMode(False, True)
    pre = t_arr.pre()
    if pre.n < 16:
        return
    freq, mag_x = A.spectrum(pre.x - np.mean(pre.x), sr)
    _, mag_y = A.spectrum(pre.y - np.mean(pre.y), sr)
    mask = freq <= 30
    pw.plot(freq[mask], mag_x[mask], pen=pg.mkPen(C.ACCENT_B, width=1.5))
    pw.plot(freq[mask], mag_y[mask], pen=pg.mkPen(C.ACCENT_P if hasattr(C, 'ACCENT_P') else QColor(155,130,210), width=1.5))
    for lo, hi, brush in [(0.15, 0.5, (170, 130, 0, 30)), (8.0, 12.0, (180, 50, 50, 30))]:
        pw.addItem(pg.LinearRegionItem(values=(lo, hi), brush=pg.mkBrush(*brush),
                                       movable=False, pen=pg.mkPen(None)))


def _gr_r95_history(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("R95 (last 0.5 / 1 / 2 s) per shot")
    pw.setLabel('left', 'R95', units='mm')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    for win, col, name in [(0.5, C.ACCENT_R, "0.5s"), (1.0, C.ACCENT_O, "1s"), (2.0, C.ACCENT_B, "2s")]:
        xs, ys = [], []
        for i, s in enumerate(sessshots):
            stab = (s.get("summary") or {}).get("stability") or []
            for st in stab:
                if st.get("window_s") == win and st.get("r95") is not None:
                    xs.append(i); ys.append(st["r95"]); break
        if xs:
            pw.plot(xs, ys, pen=pg.mkPen(col, width=1.5), symbol='o', symbolSize=4,
                    symbolBrush=col, symbolPen=pg.mkPen(None), name=name)


def _gr_cant_history(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("Cant at fire per shot (deg)")
    pw.setLabel('left', 'cant', units='°')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for i, s in enumerate(sessshots):
        if s.get("fire_cant") is not None:
            xs.append(i); ys.append(np.degrees(s["fire_cant"]))
    if xs:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_B, width=1.5), symbol='o',
                symbolSize=5, symbolBrush=C.ACCENT_B, symbolPen=pg.mkPen(None))


def _gr_timing_history(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("Trigger timing velocity per shot (mm/s)")
    pw.setLabel('left', 'velocity', units='mm/s')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for i, s in enumerate(sessshots):
        if s.get("timing_v") is not None:
            xs.append(i); ys.append(s["timing_v"])
    if xs:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_O, width=1.5), symbol='o',
                symbolSize=5, symbolBrush=C.ACCENT_O, symbolPen=pg.mkPen(None))


def _gr_hold_history(pw, t_arr, samples, sr, sessshots):
    pw.clear()
    pw.setTitle("Hold time per shot (s)")
    pw.setLabel('left', 'hold time', units='s')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for i, s in enumerate(sessshots):
        h = ((s.get("summary") or {}).get("hold") or {}).get("hold_s")
        if h is not None:
            xs.append(i); ys.append(h)
    if xs:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_G, width=1.5), symbol='o',
                symbolSize=5, symbolBrush=C.ACCENT_G, symbolPen=pg.mkPen(None))


def _gr_hr_time(pw, t_arr, samples, sr, sessshots):
    """直近の心拍時系列。"""
    pw.clear()
    pw.setTitle("Heart rate over time (bpm)")
    pw.setLabel('left', 'bpm')
    pw.setLabel('bottom', 't', units='s')
    pw.showGrid(x=True, y=True, alpha=0.15)
    win = QApplication.activeWindow()
    if win is None or not hasattr(win, "hr_history") or not win.hr_history:
        return
    arr = list(win.hr_history)
    if not arr:
        return
    t0 = arr[0][0]
    ts = np.array([a[0] - t0 for a in arr])
    hrs = np.array([a[1] for a in arr])
    pw.plot(ts, hrs, pen=pg.mkPen(C.ACCENT_R, width=1.5))


def _gr_hr_vs_r95(pw, t_arr, samples, sr, sessshots):
    """shot ごとの HR vs R95 last 0.5s 散布図。心拍が高いと安定度が落ちる仮説の検証。"""
    pw.clear()
    pw.setTitle("HR vs R95 last 0.5s")
    pw.setLabel('left', 'R95 last 0.5s', units='mm')
    pw.setLabel('bottom', 'HR at fire', units='bpm')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for s in sessshots:
        hr = s.get("hr_at_fire")
        r95 = ((s.get("summary") or {}).get("last_05s") or {}).get("r95")
        if hr is not None and r95 is not None:
            xs.append(hr); ys.append(r95)
    if not xs:
        pw.setTitle("HR vs R95 last 0.5s  (心拍観測 shot がまだ無い)")
        return
    pw.plot(xs, ys, pen=None, symbol='o', symbolSize=7,
            symbolBrush=C.ACCENT_R, symbolPen=pg.mkPen(C.FG, width=0.5))
    # 回帰線
    if len(xs) >= 3:
        a, b = np.polyfit(xs, ys, 1)
        x_line = np.array([min(xs), max(xs)])
        pw.plot(x_line, a * x_line + b, pen=pg.mkPen(C.ACCENT_O, width=1.5,
                                                       style=Qt.PenStyle.DashLine))
        corr = float(np.corrcoef(xs, ys)[0, 1])
        pw.setTitle(f"HR vs R95 last 0.5s  (r = {corr:+.2f}, n={len(xs)})")


def _gr_rmssd_vs_r95(pw, t_arr, samples, sr, sessshots):
    """RMSSD vs R95。HRV が高い (リラックス) ほど安定するかの検証。"""
    pw.clear()
    pw.setTitle("RMSSD vs R95 last 0.5s")
    pw.setLabel('left', 'R95 last 0.5s', units='mm')
    pw.setLabel('bottom', 'RMSSD', units='ms')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for s in sessshots:
        rmssd = s.get("rmssd_30s")
        r95 = ((s.get("summary") or {}).get("last_05s") or {}).get("r95")
        if rmssd is not None and r95 is not None:
            xs.append(rmssd); ys.append(r95)
    if not xs:
        pw.setTitle("RMSSD vs R95  (RMSSD 観測 shot がまだ無い)")
        return
    pw.plot(xs, ys, pen=None, symbol='o', symbolSize=7,
            symbolBrush=C.ACCENT_P, symbolPen=pg.mkPen(C.FG, width=0.5))
    if len(xs) >= 3:
        a, b = np.polyfit(xs, ys, 1)
        x_line = np.array([min(xs), max(xs)])
        pw.plot(x_line, a * x_line + b, pen=pg.mkPen(C.ACCENT_O, width=1.5,
                                                       style=Qt.PenStyle.DashLine))
        corr = float(np.corrcoef(xs, ys)[0, 1])
        pw.setTitle(f"RMSSD vs R95  (r = {corr:+.2f}, n={len(xs)})")


def _gr_session_overview(pw, t_arr, samples, sr, sessshots):
    """セッション全体の俯瞰: shot 順 × (R95 last 0.5s, HR) を 2 軸で。

    本家 SCATT にない「練習の流れ」の可視化。
    """
    pw.clear()
    pw.setTitle("Session overview: R95 + HR over shots")
    pw.setLabel('left', 'R95 0.5s', units='mm')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs = list(range(len(sessshots)))
    r95s = []
    hrs = []
    for s in sessshots:
        r = ((s.get("summary") or {}).get("last_05s") or {}).get("r95")
        r95s.append(r if r is not None else float('nan'))
        h = s.get("hr_at_fire")
        hrs.append(h if h is not None else float('nan'))
    # R95 を主軸 (赤)
    pw.plot(xs, r95s, pen=pg.mkPen(C.ACCENT_R, width=1.5),
            symbol='o', symbolSize=5,
            symbolBrush=C.ACCENT_R, symbolPen=pg.mkPen(None))
    # HR を右軸 (青)
    vb2 = pg.ViewBox()
    pw.scene().addItem(vb2)
    pw.getAxis('right').linkToView(vb2)
    vb2.setXLink(pw.getViewBox())
    pw.showAxis('right')
    pw.getAxis('right').setLabel('HR', units='bpm', color=hex_of(C.ACCENT_B))
    if any(not np.isnan(h) for h in hrs):
        from pyqtgraph import PlotDataItem
        item = PlotDataItem(xs, hrs, pen=pg.mkPen(C.ACCENT_B, width=1.5),
                            symbol='s', symbolSize=5,
                            symbolBrush=C.ACCENT_B, symbolPen=pg.mkPen(None))
        vb2.addItem(item)
    def _update_view():
        vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
        vb2.linkedViewChanged(pw.getViewBox(), vb2.XAxis)
    pw.getViewBox().sigResized.connect(_update_view)
    _update_view()


def _gr_recoil_xy_overlay(pw, t_arr, samples, sr, sessshots):
    """セッション内全 shot の発射後 trace を、発射点を原点として重ね描き。"""
    pw.clear()
    pw.setTitle("Recoil trajectory overlay (post-shot, origin = fire point)")
    pw.setLabel('left', 'Y', units='mm')
    pw.setLabel('bottom', 'X', units='mm')
    pw.setAspectLocked(True)
    pw.showGrid(x=True, y=True, alpha=0.15)
    pw.addLine(x=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
    pw.addLine(y=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
    if not sessshots:
        return
    n = len(sessshots)
    # 各 shot の発射後 trace を読み込んで描画 (重い処理になるので最大 N 件に制限)
    LIMIT = 30
    target = sessshots[-LIMIT:]
    win = QApplication.activeWindow()
    db_path = getattr(win, "db_path", None) if win else None
    if not db_path:
        return
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        return
    for i, s in enumerate(target):
        try:
            row = conn.execute("SELECT data FROM traces WHERE trace_id = ?",
                               (s["trace_id"],)).fetchone()
            if not row:
                continue
            samp = decode_trace(row[0])
            tro = s["trace_offset"]
            if tro is None or tro >= len(samp):
                continue
            fx, fy = samp[tro][0], samp[tro][1]
            n_w = min(len(samp) - tro, int(0.8 * s.get("sample_rate", 120)))
            xs = [samp[tro + k][0] - fx for k in range(n_w)]
            # y 反転 (SCATT y↓ → pyqtgraph y↑)
            ys = [-(samp[tro + k][1] - fy) for k in range(n_w)]
            # 古い shot を淡く、新しい shot を濃く
            f = i / max(1, len(target) - 1)
            alpha = int(60 + f * 180)
            col = QColor(C.ACCENT_R.red(), C.ACCENT_R.green(), C.ACCENT_R.blue(), alpha)
            is_current = (i == len(target) - 1)
            pw.plot(xs, ys, pen=pg.mkPen(col, width=2 if is_current else 1))
        except Exception:
            continue
    conn.close()
    # 5mm 円 (settle threshold)
    theta = np.linspace(0, 2*np.pi, 64)
    pw.plot(5 * np.cos(theta), 5 * np.sin(theta),
            pen=pg.mkPen(C.FG_MUTED, width=0.8, style=Qt.PenStyle.DashLine))


def _gr_recoil_direction_hist(pw, t_arr, samples, sr, sessshots):
    """反動方向のヒストグラム (極座標風)。"""
    pw.clear()
    pw.setTitle("Recoil direction distribution (impulse 50ms angle)")
    pw.setLabel('left', 'count')
    pw.setLabel('bottom', 'direction', units='°')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    angles = []
    for s in sessshots:
        r = (s.get("summary") or {}).get("recoil") or {}
        if r.get("direction_deg") is not None and r.get("impulse_mm", 0) > 0.5:
            angles.append(r["direction_deg"])
    if not angles:
        return
    bins = np.linspace(-180, 180, 25)
    hist, edges = np.histogram(angles, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    bar = pg.BarGraphItem(x=centers, height=hist, width=14,
                          brush=C.ACCENT_R, pen=pg.mkPen(C.BORDER_STRONG))
    pw.addItem(bar)
    # 平均方向と σ をテキスト表示用に title に
    mean_x = float(np.mean(np.cos(np.radians(angles))))
    mean_y = float(np.mean(np.sin(np.radians(angles))))
    mean_dir = float(np.degrees(np.arctan2(mean_y, mean_x)))
    R = np.hypot(mean_x, mean_y)
    circ_std_deg = float(np.degrees(np.sqrt(-2 * np.log(max(R, 1e-6)))))
    pw.setTitle(f"Recoil direction  mean={mean_dir:+.0f}°  σ={circ_std_deg:.0f}°  n={len(angles)}")


def _gr_recoil_peak_history(pw, t_arr, samples, sr, sessshots):
    """shot 順での反動 peak amplitude の推移。低いほど良い。"""
    pw.clear()
    pw.setTitle("Recoil peak amplitude per shot (mm)")
    pw.setLabel('left', 'peak amplitude', units='mm')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for i, s in enumerate(sessshots):
        r = (s.get("summary") or {}).get("recoil") or {}
        pk = r.get("peak_r_mm")
        if pk is not None:
            xs.append(i); ys.append(pk)
    if xs:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_R, width=1.5),
                symbol='o', symbolSize=5,
                symbolBrush=C.ACCENT_R, symbolPen=pg.mkPen(None))


def _gr_recoil_speed_overlay(pw, t_arr, samples, sr, sessshots):
    """現在 trace の発射後速度時系列。"""
    pw.clear()
    pw.setTitle("Post-shot velocity (current trace)")
    pw.setLabel('left', 'velocity', units='mm/s')
    pw.setLabel('bottom', 't from fire', units='s')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if t_arr.trace_offset is None or t_arr.trace_offset >= t_arr.n - 2:
        return
    post = t_arr.post()
    v = A.velocity(post)
    if len(v) == 0:
        return
    t_axis = (np.arange(len(v)) + 0.5) / sr
    pw.plot(t_axis, v, pen=pg.mkPen(C.ACCENT_R, width=1.5))


def _gr_recoil_settle_history(pw, t_arr, samples, sr, sessshots):
    """shot 順での「反動戻り時間」推移。短いほど良い。"""
    pw.clear()
    pw.setTitle("Recoil settle time per shot (< 5mm)")
    pw.setLabel('left', 'settle time', units='s')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for i, s in enumerate(sessshots):
        st = (s.get("summary") or {}).get("recoil") or {}
        st_v = st.get("settle_time_s")
        if st_v is not None:
            xs.append(i); ys.append(st_v)
    if xs:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_R, width=1.5),
                symbol='o', symbolSize=5,
                symbolBrush=C.ACCENT_R, symbolPen=pg.mkPen(None))


def _gr_combined_timing_r95(pw, t_arr, samples, sr, sessshots):
    """撃発タイミングと R95 last 0.5s の散布図。「速いタイミングで撃つほど外す」傾向の検出。"""
    pw.clear()
    pw.setTitle("Trigger timing vs R95 last 0.5s")
    pw.setLabel('left', 'R95 last 0.5s', units='mm')
    pw.setLabel('bottom', 'trigger timing velocity', units='mm/s')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for s in sessshots:
        tv = s.get("timing_v")
        r95 = ((s.get("summary") or {}).get("last_05s") or {}).get("r95")
        if tv is not None and r95 is not None:
            xs.append(tv); ys.append(r95)
    if not xs:
        return
    pw.plot(xs, ys, pen=None, symbol='o', symbolSize=7,
            symbolBrush=C.ACCENT_G, symbolPen=pg.mkPen(C.FG, width=0.5))
    if len(xs) >= 3:
        a, b = np.polyfit(xs, ys, 1)
        x_line = np.array([min(xs), max(xs)])
        pw.plot(x_line, a * x_line + b, pen=pg.mkPen(C.ACCENT_O, width=1.5,
                                                       style=Qt.PenStyle.DashLine))
        corr = float(np.corrcoef(xs, ys)[0, 1])
        pw.setTitle(f"Trigger timing vs R95 0.5s  (r = {corr:+.2f}, n={len(xs)})")


GRAPH_KINDS = [
    ("velocity",       "Velocity (time-from-fire)",     _gr_velocity),
    ("r95_bars",       "Recent 5 shots R95 bars",       _gr_r95_bars),
    ("scatter",        "Shot impact scatter",           _gr_shot_scatter),
    ("trace_xy",       "Current trace X-Y path",        _gr_trace_xy),
    ("cant_time",      "Cant over time (current)",      _gr_cant_time),
    ("spectrum",       "FFT spectrum (pre-trigger)",    _gr_spectrum),
    ("r95_history",    "R95 history per shot",          _gr_r95_history),
    ("cant_history",   "Cant at fire per shot",         _gr_cant_history),
    ("timing_history", "Trigger timing per shot",       _gr_timing_history),
    ("hold_history",   "Hold time per shot",            _gr_hold_history),
    ("hr_time",        "Heart rate over time",          _gr_hr_time),
    ("hr_vs_r95",      "HR vs R95 (correlation)",       _gr_hr_vs_r95),
    ("rmssd_vs_r95",   "RMSSD vs R95 (HRV correlation)", _gr_rmssd_vs_r95),
    ("session_overview", "Session overview (R95 + HR)", _gr_session_overview),
    ("timing_vs_r95",  "Trigger timing vs R95",         _gr_combined_timing_r95),
    ("recoil_xy",         "Recoil trajectories overlay",   _gr_recoil_xy_overlay),
    ("recoil_dir_hist",   "Recoil direction histogram",    _gr_recoil_direction_hist),
    ("recoil_settle",     "Recoil settle time per shot",   _gr_recoil_settle_history),
    ("recoil_peak_hist",  "Recoil peak amplitude per shot", _gr_recoil_peak_history),
    ("recoil_speed",      "Post-shot velocity (current)",  _gr_recoil_speed_overlay),
]


# ===========================================================================
# Heart Rate Qt ブリッジ
# ===========================================================================

class HeartRateBridge(QObject):
    """別スレッドからの心拍コールバックを Qt signal に変換。"""

    data_received = pyqtSignal(dict)
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.client: H.HeartRateClient | None = None

    def start(self, mode: str, device_address: str = ""):
        if self.client is not None:
            return
        self.client = H.HeartRateClient(mock=(mode == "mock"))
        self.client.on_data = lambda d: self.data_received.emit(d)
        self.client.on_status = lambda s: self.status_changed.emit(s)
        self.client.start(device_address or None)

    def stop(self):
        if self.client is None:
            return
        self.client.stop()
        self.client = None


class GraphPanel(QWidget):
    """ComboBox で表示するグラフを切替可能な PlotWidget ホルダ。"""

    def __init__(self, default_kind: str = "velocity"):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.combo = QComboBox()
        for k, label, _ in GRAPH_KINDS:
            self.combo.addItem(label, k)
        idx = next((i for i, (k, _, _) in enumerate(GRAPH_KINDS) if k == default_kind), 0)
        self.combo.setCurrentIndex(idx)
        self.combo.setStyleSheet(
            f"QComboBox {{ background-color: {hex_of(C.PANEL)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; padding: 2px 8px; }}"
            f"QComboBox QAbstractItemView {{ background-color: {hex_of(C.BG)}; }}"
        )
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        lay.addWidget(self.combo)
        lay.addWidget(self.plot, stretch=1)
        self.combo.currentIndexChanged.connect(self._redraw)
        self._last_args = None

    def update_data(self, t_arr, samples, sample_rate, session_shots):
        self._last_args = (t_arr, samples, sample_rate, session_shots)
        self._redraw()

    def _redraw(self):
        if self._last_args is None:
            return
        kind = self.combo.currentData()
        for k, _, fn in GRAPH_KINDS:
            if k == kind:
                fn(self.plot, *self._last_args)
                return


class DashboardTab(QWidget):
    """主役 2 枚 + 全指標表 + グラフ × 4 (各枠は ComboBox で種別選択可)"""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # ----- 上段: 主役 4 枚 (本家 SCATT 互換: 10a / 10a-0.5 / S1 / S2) -----
        hero_row = QHBoxLayout()
        hero_row.setSpacing(8)
        self.hero_10a = _hero_card("10a   10-ring time (last 1s)", "%")
        self.hero_10a5 = _hero_card("10a-0.5   10-ring time (last 0.5s)", "%")
        self.hero_s1 = _hero_card("S1   stability (last 1s)", "mm")
        self.hero_s2 = _hero_card("S2   stability (last 0.5s)", "mm")
        for hero in [self.hero_10a, self.hero_10a5, self.hero_s1, self.hero_s2]:
            hero_row.addWidget(hero[0], stretch=1)
        outer.addLayout(hero_row)

        # ----- 中段: 全指標表 (label, value, μ, σ, z) -----
        n_metrics = len(METRICS)
        ncols = 5  # label / value / μ / σ / hint
        tbl = QTableWidget(n_metrics, ncols)
        tbl.setShowGrid(False)
        tbl.setHorizontalHeaderLabels(["指標", "今回", "過去 μ", "過去 σ", "判定"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl.setStyleSheet(
            f"QTableWidget {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; gridline-color: transparent;"
            "   font-family: 'SF Mono', Menlo, monospace; font-size: 12px; }"
            f"QTableWidget::item {{ padding: 5px 10px; }}"
            f"QHeaderView::section {{ background-color: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG_MUTED)};"
            f"  padding: 4px 8px; border: none; border-bottom: 1px solid {hex_of(C.BORDER)};"
            "   font-size: 11px; }"
        )
        tbl.setColumnWidth(0, 200)
        tbl.setColumnWidth(1, 110)
        tbl.setColumnWidth(2, 110)
        tbl.setColumnWidth(3, 90)
        for r in range(n_metrics):
            tbl.setRowHeight(r, 26)
        self.metrics_table = tbl
        # 行作成
        for row, (key, label, unit, _, _) in enumerate(METRICS):
            lbl_item = QTableWidgetItem(label)
            lbl_item.setForeground(QBrush(C.FG_MUTED))
            tbl.setItem(row, 0, lbl_item)
            for c in range(1, ncols):
                tbl.setItem(row, c, QTableWidgetItem("—"))
            tbl.item(row, 4).setForeground(QBrush(C.FG_MUTED))
        outer.addWidget(tbl, stretch=1)

        # ----- フィードバックパネル (ローカル NLG) -----
        self.feedback_label = QLabel("")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet(
            f"QLabel {{ background-color: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; padding: 8px 12px;"
            "   font-size: 12px; line-height: 1.5; }"
        )
        self.feedback_label.setMinimumHeight(70)
        self.feedback_label.setMaximumHeight(140)
        outer.addWidget(self.feedback_label)

        # ----- 下段: 選択可能グラフ枠 (rows × cols は設定で可変) -----
        self._graphs_widget = QWidget()
        self.graphs: list[GraphPanel] = []
        outer.addWidget(self._graphs_widget, stretch=3)
        rows = SETTINGS.get("layout/dashboard_graph_rows")
        cols = SETTINGS.get("layout/dashboard_graph_cols")
        self.rebuild_graphs(rows, cols)
        # hero_cards / metrics_table 可視性
        if not SETTINGS.get("layout/show_hero_cards"):
            for hero in [self.hero_10a, self.hero_10a5, self.hero_s1, self.hero_s2]:
                hero[0].hide()
        if not SETTINGS.get("layout/show_metrics_table"):
            self.metrics_table.hide()

    def _set_hero(self, hero, value_text: str, sub_text: str, color: QColor):
        hero[1].setText(value_text)
        hero[1].setStyleSheet(
            f"color: {hex_of(color)}; font-family: 'SF Mono', 'Menlo', monospace;"
            " font-size: 32px; border: none; background: transparent;"
        )
        hero[3].setText(sub_text)

    def _set_hero_by_key(self, hero, cur, stats, key: str, digits: int):
        """指標を主役カードに表示。z-score に応じた色付け。"""
        v = _metric_value(cur, key)
        stat = stats.get(key)
        if v is None:
            self._set_hero(hero, "—", "(履歴なし)", C.FG_MUTED)
            return
        # direction を METRICS から探す
        direction = next((m[3] for m in METRICS if m[0] == key), "info")
        col = color_for_metric(v, direction, stat)
        sub = ""
        if stat is not None:
            mu, sigma = stat
            sub = f"過去平均: {mu:.{digits}f} ± {sigma:.{digits}f}"
        self._set_hero(hero, f"{v:.{digits}f}", sub, col)

    def rebuild_graphs(self, rows: int, cols: int):
        """グラフ枠数を変更して再構築。"""
        # 既存ウィジェット削除
        for g in self.graphs:
            g.setParent(None)
            g.deleteLater()
        self.graphs = []
        # 新しいレイアウト
        n = rows * cols
        defaults = [SETTINGS.get(f"layout/graph_default_{i+1}") for i in range(n)]
        # graphs_box は最初に作った QGridLayout 内部、再取得
        gw = self._graphs_widget
        # 古いレイアウトを破棄して新規作成
        old_lay = gw.layout()
        if old_lay is not None:
            QWidget().setLayout(old_lay)
        gg = QGridLayout(gw)
        gg.setContentsMargins(0, 0, 0, 0)
        gg.setHorizontalSpacing(8)
        gg.setVerticalSpacing(8)
        for i in range(n):
            gp = GraphPanel(defaults[i] or "velocity")
            r = i // cols
            c = i % cols
            gg.addWidget(gp, r, c)
            self.graphs.append(gp)

    def update_trace(self, samples, shots, sample_rate,
                     session_shots: list[dict] | None = None):
        """session_shots を渡せば μ,σ 比較で色付け。"""
        t_arr = A.to_trace_arrays(samples, sample_rate,
                                  shots[0]["trace_offset"] if shots else None)
        summ = A.summarize(t_arr)
        # 撃発タイミング (発射前後 1 サンプル の速度)
        timing_v = None
        if t_arr.trace_offset is not None and 0 < t_arr.trace_offset < t_arr.n:
            dx = samples[t_arr.trace_offset][0] - samples[t_arr.trace_offset - 1][0]
            dy = samples[t_arr.trace_offset][1] - samples[t_arr.trace_offset - 1][1]
            timing_v = (dx * dx + dy * dy) ** 0.5 * sample_rate
        cant_at_fire_deg = None
        if t_arr.trace_offset is not None and t_arr.trace_offset < t_arr.n:
            cant_at_fire_deg = float(np.degrees(t_arr.samples[t_arr.trace_offset, 2]))

        # 現在 shot を「shot 集計と同じ構造」にまとめる
        # MainWindow が事前に samples / shots / sample_rate に加えて
        # session_shots と共に hr_at_fire / rmssd_30s を引数経由で渡す方法も検討したが、
        # ここでは shots[0] に埋め込んでもらう前提とする (なければ None)
        cur_shot = shots[0] if shots else {}
        cur = {
            "summary": summ,
            "timing_v": timing_v,
            "cant_at_fire_deg": cant_at_fire_deg,
            "hr_at_fire": cur_shot.get("hr_at_fire"),
            "rmssd_30s": cur_shot.get("rmssd_30s"),
        }

        # session 平均 μ, σ を計算 (現在 shot 自身を除外したいので、引数の session_shots
        # 側で除いて渡すか、ここで shot_id 一致のものを外す。簡略のため引数前提)
        stats = compute_session_stats(session_shots or [])

        # --- 主役 4 枚 (本家 SCATT 互換) ---
        self._set_hero_by_key(self.hero_10a,  cur, stats, "ten_a_1s",  1)
        self._set_hero_by_key(self.hero_10a5, cur, stats, "ten_a_05s", 1)
        self._set_hero_by_key(self.hero_s1,   cur, stats, "r95_1",     2)
        self._set_hero_by_key(self.hero_s2,   cur, stats, "r95_05",    2)

        # --- 中段 指標表 ---
        # 「全部赤」を避けるため、まず全指標の z-score を一括計算し、
        # 悪い側 z 上位 2 だけ赤、次 2 を橙、最良 1 を緑、その他は黒にする。
        # info / 計算不可は除外。
        z_warn = SETTINGS.get("thresh/z_warn")
        z_bad = SETTINGS.get("thresh/z_bad")
        z_scores: dict[str, float] = {}
        for key, _, _, direction, _ in METRICS:
            if direction == "info":
                continue
            v = _metric_value(cur, key)
            stat = stats.get(key)
            if v is None or stat is None:
                continue
            mu, sigma = stat
            if sigma <= 0:
                continue
            if direction == "abs_low_good":
                z = (abs(v) - abs(mu)) / sigma
            else:
                z = (v - mu) / sigma
            if direction == "high_good":
                z = -z
            z_scores[key] = z

        # ランキング (z 大 = 悪い、z 小 = 良い)
        sorted_by_bad = sorted(z_scores.items(), key=lambda x: -x[1])
        red_keys = {k for k, z in sorted_by_bad[:2] if z >= z_warn}
        orange_keys = {k for k, z in sorted_by_bad[2:4]
                       if z >= z_warn and k not in red_keys}
        sorted_by_good = sorted(z_scores.items(), key=lambda x: x[1])
        green_keys = {k for k, z in sorted_by_good[:1] if z <= -z_warn}

        # 指標表は z-score の絶対値で並べ替え (悪い順 → 普段通り → 良い順)
        # z 値の大きい順 (= 悪いほど上)
        def sort_key(m):
            k = m[0]
            if k not in z_scores:
                return 999.0   # 計算不可は最後尾
            return -z_scores[k]
        sorted_metrics = sorted(METRICS, key=sort_key)

        for row, (key, label, unit, direction, digits) in enumerate(sorted_metrics):
            # ラベル列を更新(ソートされたので)
            lbl_item = self.metrics_table.item(row, 0)
            lbl_item.setText(label)
            lbl_item.setForeground(QBrush(C.FG_MUTED))

            v = _metric_value(cur, key)
            stat = stats.get(key)
            if v is None:
                self.metrics_table.item(row, 1).setText("—")
                self.metrics_table.item(row, 1).setForeground(QBrush(C.FG_MUTED))
                hint = ""
                color = C.FG_MUTED
            else:
                txt = f"{v:.{digits}f}"
                if unit:
                    txt += f" {unit}"
                self.metrics_table.item(row, 1).setText(txt)
                if key in red_keys:
                    color = C.ACCENT_R
                elif key in orange_keys:
                    color = C.ACCENT_O
                elif key in green_keys:
                    color = C.ACCENT_G
                else:
                    color = C.FG
                self.metrics_table.item(row, 1).setForeground(QBrush(color))
                # 判定列 (z 0.5σ 以内のみ「普段通り」、それ以外は 数値表示)
                z = z_scores.get(key)
                if direction == "info":
                    hint = ""
                elif stat is None:
                    hint = "(履歴なし)"
                elif z is None:
                    hint = ""
                elif key in red_keys:
                    hint = f"悪 ↑↑  z={z:+.1f}σ"
                elif key in orange_keys:
                    hint = f"やや悪  z={z:+.1f}σ"
                elif key in green_keys:
                    hint = f"良 ↓  z={z:+.1f}σ"
                elif abs(z) < 0.5:
                    hint = f"普段通り  z={z:+.1f}σ"
                elif z > 0:
                    hint = f"わずかに悪  z={z:+.1f}σ"
                else:
                    hint = f"わずかに良  z={z:+.1f}σ"
            self.metrics_table.item(row, 4).setText(hint)
            self.metrics_table.item(row, 4).setForeground(QBrush(color))
            if stat is not None:
                mu, sigma = stat
                self.metrics_table.item(row, 2).setText(f"{mu:.{digits}f}")
                self.metrics_table.item(row, 3).setText(f"±{sigma:.{digits}f}")
                self.metrics_table.item(row, 2).setForeground(QBrush(C.FG_MUTED))
                self.metrics_table.item(row, 3).setForeground(QBrush(C.FG_MUTED))
            else:
                self.metrics_table.item(row, 2).setText("—")
                self.metrics_table.item(row, 3).setText("—")

        # --- ローカル NLG フィードバック ---
        try:
            cur_for_fb = dict(cur)
            # cur (現在 shot) の metric を平坦化 (_metric_value 互換構造のまま)
            cur_metrics = {}
            for key in (
                "timing_v", "r95_05", "r95_1", "r95_2", "r95_3",
                "cant_at_fire_deg", "cant_sd_deg", "hold_s", "aim_s",
                "tremor", "breath", "approach_mono", "approach_signs",
                "hr_at_fire", "rmssd_30s",
                "ten_a_1s", "ten_a_05s", "ten_b_1s", "ten_b_05s", "nine_c_1s",
                "recoil_peak", "recoil_settle", "recoil_post05_r95",
                "recoil_dir_std",
            ):
                cur_metrics[key] = _metric_value(cur, key)
            fb_text = FB.shot_feedback(cur_metrics, stats)
            self.feedback_label.setText(fb_text)
        except Exception as e:
            self.feedback_label.setText(f"(feedback unavailable: {e})")

        # --- 4 枠グラフを更新 ---
        for g in self.graphs:
            g.update_data(t_arr, samples, sample_rate, session_shots or [])


# ===========================================================================
# Tab 2: Spectrum (FFT)
# ===========================================================================

class SpectrumTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        info = QLabel(
            "Pre-trigger spectrum (X / Y). Yellow band = breath (0.15–0.5Hz), "
            "Red band = physiological tremor (8–12Hz)."
        )
        info.setStyleSheet(f"color: {hex_of(C.FG_MUTED)}; font-size: 11px;")
        lay.addWidget(info)
        self.plot = pg.PlotWidget(title="FFT spectrum (pre-trigger)")
        self.plot.setLabel('left', 'magnitude')
        self.plot.setLabel('bottom', 'frequency', units='Hz')
        self.plot.setLogMode(False, True)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        lay.addWidget(self.plot, stretch=1)
        self.summary = QLabel("—")
        self.summary.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', Menlo, monospace; font-size: 12px;"
        )
        lay.addWidget(self.summary)

    def update_trace(self, samples, shots, sample_rate):
        t = A.to_trace_arrays(samples, sample_rate,
                              shots[0]["trace_offset"] if shots else None)
        pre = t.pre()
        if pre.n < 16:
            self.plot.clear()
            self.summary.setText("(not enough pre-trigger samples)")
            return
        x = pre.x - np.mean(pre.x)
        y = pre.y - np.mean(pre.y)
        freq, mag_x = A.spectrum(x, sample_rate)
        _, mag_y = A.spectrum(y, sample_rate)
        mask = freq <= 30.0
        freq = freq[mask]; mag_x = mag_x[mask]; mag_y = mag_y[mask]
        self.plot.clear()
        self.plot.plot(freq, mag_x, pen=pg.mkPen(C.ACCENT_B, width=1.5))
        self.plot.plot(freq, mag_y, pen=pg.mkPen(C.ACCENT_P, width=1.5))
        for lo, hi, col in [(0.15, 0.5, C.ACCENT_Y), (8.0, 12.0, C.ACCENT_R)]:
            self.plot.addItem(pg.LinearRegionItem(
                values=(lo, hi),
                brush=pg.mkBrush(col.red(), col.green(), col.blue(), 50),
                movable=False, pen=pg.mkPen(None),
            ))
        tremor = A.tremor_band(freq, mag_x)
        breath = A.breathing_band(freq, mag_x)
        peak_idx = int(np.argmax(mag_x))
        self.summary.setText(
            f"tremor 8–12Hz: {tremor:.4f}    "
            f"breath 0.15–0.5Hz: {breath:.4f}    "
            f"peak: {freq[peak_idx]:.2f}Hz @ {mag_x[peak_idx]:.3f}    "
            f"(blue = X axis,  purple = Y axis)"
        )


# ===========================================================================
# Tab 3: Shots KPI list
# ===========================================================================

class SeriesTargetView(QGraphicsView):
    """Series の弾着を表示する簡略 ISSF 50m ライフルターゲット。

    各 shot の発射点を番号付きでプロット、古→新で色変化、重心 + R95 円。
    """

    OUTER_DIAM_MM = 154.4
    RING_STEP_MM = 16.0
    BLACK_DIAM_MM = 112.4
    INNER_TEN_DIAM_MM = 5.0

    def __init__(self):
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene = QGraphicsScene()
        self.setScene(self._scene)
        self.setBackgroundBrush(QBrush(C.BG))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setFixedSize(220, 220)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._draw_target()
        self._dyn = []

    def _draw_target(self):
        # 簡略版: 黒地のみ、リング線、Inner 10
        r_out = self.OUTER_DIAM_MM / 2.0
        self._scene.addEllipse(
            -r_out, -r_out, self.OUTER_DIAM_MM, self.OUTER_DIAM_MM,
            QPen(QColor(80, 80, 80)),
            QBrush(C.TARGET_WHITE),
        )
        r_black = self.BLACK_DIAM_MM / 2.0
        self._scene.addEllipse(
            -r_black, -r_black, self.BLACK_DIAM_MM, self.BLACK_DIAM_MM,
            QPen(QColor(30, 30, 30)),
            QBrush(C.TARGET_BLACK),
        )
        pen_w = QPen(C.TARGET_LINE_LIGHT); pen_w.setWidthF(0.25)
        pen_b = QPen(C.TARGET_LINE_DARK);  pen_b.setWidthF(0.25)
        for ring in range(1, 11):
            d = self.OUTER_DIAM_MM - (ring - 1) * self.RING_STEP_MM
            r = d / 2.0
            pen = pen_w if d > self.BLACK_DIAM_MM else pen_b
            self._scene.addEllipse(-r, -r, d, d, pen, QBrush(Qt.BrushStyle.NoBrush))
        r_inner = self.INNER_TEN_DIAM_MM / 2.0
        pen_x = QPen(QColor(255, 255, 255)); pen_x.setWidthF(0.25)
        pen_x.setStyle(Qt.PenStyle.DashLine)
        self._scene.addEllipse(
            -r_inner, -r_inner, self.INNER_TEN_DIAM_MM, self.INNER_TEN_DIAM_MM,
            pen_x, QBrush(Qt.BrushStyle.NoBrush),
        )

    def _clear_dyn(self):
        for it in self._dyn:
            self._scene.removeItem(it)
        self._dyn = []

    def show_shots(self, shots: list[dict]):
        """shots: [{"fire_x": .., "fire_y": .., ...}]、Series 内 1〜10。"""
        self._clear_dyn()
        valid = [(i + 1, s) for i, s in enumerate(shots)
                 if s.get("fire_x") is not None and s.get("fire_y") is not None]
        if not valid:
            return
        n = len(valid)
        xs = np.array([s["fire_x"] for _, s in valid])
        ys = np.array([s["fire_y"] for _, s in valid])
        # 着弾点と番号
        font = QFont(); font.setPointSizeF(4.0); font.setBold(True)
        for pos, (idx, s) in enumerate(valid):
            x = s["fire_x"]
            y = s["fire_y"]  # SCATT y↓ = QGraphicsView y↓ なのでそのまま
            # 色: 古→新 を青→赤
            f = pos / max(1, n - 1)
            col = QColor(int(60 + f * 180), int(100 - f * 80), int(220 - f * 180))
            # 点
            dot = self._scene.addEllipse(
                x - 2, y - 2, 4, 4,
                QPen(C.FG, 0.4),
                QBrush(col),
            )
            self._dyn.append(dot)
            # 番号
            t = self._scene.addText(str(idx), font)
            t.setDefaultTextColor(C.FG)
            t.setPos(x + 2.5, y - 3.0)
            self._dyn.append(t)
        # 重心 + R95
        if n >= 2:
            cx, cy = float(np.mean(xs)), float(np.mean(ys))
            rs = np.hypot(xs - cx, ys - cy)
            r95 = float(np.percentile(rs, 95))
            # 重心 (黄十字)
            cross_pen = QPen(C.ACCENT_Y); cross_pen.setWidthF(0.5)
            self._dyn.append(self._scene.addLine(cx - 3, cy, cx + 3, cy, cross_pen))
            self._dyn.append(self._scene.addLine(cx, cy - 3, cx, cy + 3, cross_pen))
            # R95 円
            if r95 > 0:
                ring_pen = QPen(C.ACCENT_Y); ring_pen.setWidthF(0.3)
                ring_pen.setStyle(Qt.PenStyle.DashLine)
                self._dyn.append(self._scene.addEllipse(
                    cx - r95, cy - r95, 2 * r95, 2 * r95,
                    ring_pen, QBrush(Qt.BrushStyle.NoBrush),
                ))

    def resizeEvent(self, e):
        self.fitInView(QRectF(-95, -95, 190, 190), Qt.AspectRatioMode.KeepAspectRatio)
        super().resizeEvent(e)


class SeriesPanel(QWidget):
    """1 Series のブロック: 左にターゲット、右に shot テーブル + 集計。"""

    COLUMNS = [
        ("#",        30),
        ("time",     75),
        ("dist mm",  62),
        ("10a %",    55),
        ("10a-0.5",  60),
        ("10b %",    55),
        ("9c %",     50),
        ("S1 mm",    55),
        ("S2 mm",    55),
        ("cant°",    55),
        ("flags",    50),
    ]

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)
        # ヘッダラベル
        self.header = QLabel("Series —")
        self.header.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-size: 12px; font-weight: 600;"
            f" padding: 2px 4px; background-color: {hex_of(C.PANEL_LO)};"
            f" border-bottom: 1px solid {hex_of(C.BORDER)};"
        )
        outer.addWidget(self.header)
        body = QHBoxLayout()
        body.setSpacing(8)
        outer.addLayout(body)
        # 左: ターゲット
        self.target = SeriesTargetView()
        body.addWidget(self.target)
        # 右: テーブル
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; gridline-color: transparent;"
            "   font-family: 'SF Mono', Menlo, monospace; font-size: 11px; }"
            f"QTableWidget::item {{ padding: 2px 6px; }}"
            f"QHeaderView::section {{ background-color: {hex_of(C.PANEL_LO)};"
            f"  color: {hex_of(C.FG_MUTED)}; padding: 2px 4px; border: none;"
            f"  border-bottom: 1px solid {hex_of(C.BORDER)}; font-size: 10px; }}"
        )
        from PyQt6.QtWidgets import QAbstractItemView
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for i, (_, w) in enumerate(self.COLUMNS):
            self.table.setColumnWidth(i, w)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        body.addWidget(self.table, stretch=1)
        self.shot_ids_by_row: dict[int, int] = {}  # row → shot_id
        self.on_select = None
        self.table.itemSelectionChanged.connect(self._on_select)

    def _on_select(self):
        row = self.table.currentRow()
        if row in self.shot_ids_by_row and self.on_select:
            self.on_select(self.shot_ids_by_row[row], row)

    def update_series(self, series_no: int, series_shots: list[dict],
                      threshold_mm: float = 200.0):
        import datetime
        self.header.setText(
            f"Series {series_no}   ({len(series_shots)} shots)"
        )
        # ターゲット
        self.target.show_shots(series_shots)
        # テーブル: 10 shots + μ 行
        self.shot_ids_by_row.clear()
        nrows = len(series_shots) + 1  # +1 for μ row
        self.table.setRowCount(nrows)
        # 行高を固定
        for r in range(nrows):
            self.table.setRowHeight(r, 18)
        # 各 shot 行
        for pos, s in enumerate(series_shots):
            summ = s.get("summary") or {}
            stab = {st["window_s"]: st for st in (summ.get("stability") or [])}
            def get_r95(w): return stab.get(w, {}).get("r95")
            def pct(k): return (summ.get(k) or {}).get("percent")
            t_str = datetime.datetime.fromtimestamp(s["timer_ms"] / 1000).strftime("%H:%M:%S")
            flags = []
            if s.get("match_shot"): flags.append("M")
            if s.get("favorite"): flags.append("★")
            if s.get("missed"): flags.append("X")
            cant_deg = np.degrees(s["fire_cant"]) if s.get("fire_cant") is not None else None
            fx, fy = s.get("fire_x"), s.get("fire_y")
            dist = (fx * fx + fy * fy) ** 0.5 if (fx is not None and fy is not None) else None
            cells = [
                f"{pos + 1}",
                t_str,
                f"{dist:.0f}" if dist is not None else "—",
                f"{pct('ten_a_1s'):.1f}" if pct('ten_a_1s') is not None else "—",
                f"{pct('ten_a_05s'):.1f}" if pct('ten_a_05s') is not None else "—",
                f"{pct('ten_b_1s'):.1f}" if pct('ten_b_1s') is not None else "—",
                f"{pct('nine_c_1s'):.1f}" if pct('nine_c_1s') is not None else "—",
                f"{get_r95(1.0):.2f}" if get_r95(1.0) else "—",
                f"{get_r95(0.5):.2f}" if get_r95(0.5) else "—",
                f"{cant_deg:+.2f}" if cant_deg is not None else "—",
                " ".join(flags),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, s["trace_id"])
                # 色
                if c in (3, 4, 5, 6):
                    try:
                        v = float(text)
                        if v >= 80: item.setForeground(QBrush(C.ACCENT_G))
                        elif v < 30: item.setForeground(QBrush(C.ACCENT_R))
                    except ValueError:
                        pass
                if c in (7, 8):
                    try:
                        v = float(text)
                        if v < 2: item.setForeground(QBrush(C.ACCENT_G))
                        elif v >= 5: item.setForeground(QBrush(C.ACCENT_R))
                    except ValueError:
                        pass
                if c == 2 and dist is not None and dist >= threshold_mm:
                    item.setBackground(QBrush(QColor(255, 230, 230)))
                self.table.setItem(pos, c, item)
            self.shot_ids_by_row[pos] = s["shot_id"]

        # μ 集計行
        def avg(key_path):
            vs = []
            for s in series_shots:
                cur = s.get("summary") or {}
                for k in key_path:
                    cur = (cur or {}).get(k) if isinstance(cur, dict) else None
                    if cur is None: break
                if cur is not None:
                    vs.append(cur)
            return float(np.mean(vs)) if vs else None
        def avg_r95(win):
            vs = []
            for s in series_shots:
                for st in (s.get("summary") or {}).get("stability") or []:
                    if st.get("window_s") == win:
                        vs.append(st["r95"]); break
            return float(np.mean(vs)) if vs else None
        cants = [np.degrees(s["fire_cant"]) for s in series_shots
                 if s.get("fire_cant") is not None]
        avg_cant = float(np.mean(cants)) if cants else None
        summary_cells = [
            "μ", "", "",
            f"{avg(['ten_a_1s', 'percent']):.1f}" if avg(['ten_a_1s', 'percent']) is not None else "—",
            f"{avg(['ten_a_05s', 'percent']):.1f}" if avg(['ten_a_05s', 'percent']) is not None else "—",
            f"{avg(['ten_b_1s', 'percent']):.1f}" if avg(['ten_b_1s', 'percent']) is not None else "—",
            f"{avg(['nine_c_1s', 'percent']):.1f}" if avg(['nine_c_1s', 'percent']) is not None else "—",
            f"{avg_r95(1.0):.2f}" if avg_r95(1.0) is not None else "—",
            f"{avg_r95(0.5):.2f}" if avg_r95(0.5) is not None else "—",
            f"{avg_cant:+.2f}" if avg_cant is not None else "—",
            "",
        ]
        for c, text in enumerate(summary_cells):
            item = QTableWidgetItem(text)
            item.setBackground(QBrush(C.PANEL))
            item.setForeground(QBrush(C.ACCENT_B))
            f = item.font(); f.setItalic(True); item.setFont(f)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(len(series_shots), c, item)
        # 高さを行数に合わせる
        h = 20 + (nrows + 1) * 19
        self.setMinimumHeight(max(h, 240))


class ShotsTab(QWidget):
    """セッション内 shot を **10 発ごとの Series** で表示。本家 SCATT 互換。

    各 Series: 左にターゲット (着弾点 + 重心 + R95)、右に shot テーブル + μ 行。
    複数 Series を縦にスクロール。
    """

    # 旧構成 (1 つの大テーブル) の互換用カラム (削除機能で使用)
    COLUMNS = [
        ("#",        40),
        ("time",     90),
        ("dist mm",  70),
        ("10a %",    60),
        ("10a-0.5",  60),
        ("10b %",    60),
        ("9c %",     60),
        ("S1 mm",    60),
        ("S2 mm",    60),
        ("cant°",    60),
        ("flags",    60),
    ]

    def __init__(self):
        super().__init__()
        self.on_shot_selected = None
        self.on_delete_committed = None
        self.db_path = None
        self._row_to_shot_id: dict[int, int] = {}
        self._suspicious_shot_ids: set[int] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ツールバー
        tb = QHBoxLayout()
        tb.setSpacing(8)
        info = QLabel("session を Series 10 発ずつ表示。右クリック等の機能は今後実装予定。")
        info.setStyleSheet(f"color: {hex_of(C.FG_MUTED)}; font-size: 11px;")
        tb.addWidget(info, stretch=1)

        tb.addWidget(QLabel("異常閾値 (mm):"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(50.0, 1000.0)
        self.threshold_spin.setSingleStep(10.0)
        self.threshold_spin.setValue(SUSPICIOUS_RADIUS_MM)
        self.threshold_spin.setStyleSheet(
            f"background-color: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG)};"
            f" border: 1px solid {hex_of(C.BORDER)}; padding: 2px 4px;"
        )
        self.threshold_spin.valueChanged.connect(self._reload_panels)
        tb.addWidget(self.threshold_spin)

        self.del_suspicious_btn = QPushButton("異常 shot を一括削除")
        self.del_suspicious_btn.clicked.connect(self._delete_suspicious)
        tb.addWidget(self.del_suspicious_btn)

        outer.addLayout(tb)

        # Series パネルを縦並びにする QScrollArea
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._series_container = QWidget()
        self._series_layout = QVBoxLayout(self._series_container)
        self._series_layout.setContentsMargins(0, 0, 0, 0)
        self._series_layout.setSpacing(10)
        self.scroll.setWidget(self._series_container)
        outer.addWidget(self.scroll, stretch=1)

        # サマリ
        self.summary = QLabel("")
        self.summary.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-family: 'SF Mono', monospace; font-size: 11px;"
        )
        outer.addWidget(self.summary)

        # SeriesPanel リスト + キャッシュした session_shots
        self.series_panels: list[SeriesPanel] = []
        self._session_shots_cache: list[dict] = []
        # 旧 table は使わない (削除機能用に dummy)
        from PyQt6.QtWidgets import QAbstractItemView
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.hide()

    def _on_clicked(self, item):
        row = item.row()
        tid_item = self.table.item(row, 0)
        if tid_item and self.on_shot_selected:
            trace_id = tid_item.data(Qt.ItemDataRole.UserRole)
            if trace_id is not None:
                self.on_shot_selected(trace_id)

    def update_session(self, session_shots: list[dict], db_path: str | None = None):
        """session 内 shot を 10 発ずつ Series ブロックで表示。

        各 Series: SeriesPanel (ターゲット + テーブル + μ 行)。
        """
        if db_path:
            self.db_path = db_path
        self._session_shots_cache = list(session_shots)
        self._row_to_shot_id.clear()
        # 既存 SeriesPanel を削除
        for p in self.series_panels:
            p.setParent(None)
            p.deleteLater()
        self.series_panels = []

        n = len(session_shots)
        if n == 0:
            self.summary.setText("(no shots in this session)")
            self._suspicious_shot_ids.clear()
            return

        threshold = self.threshold_spin.value()
        n_series = (n + 9) // 10
        self._suspicious_shot_ids.clear()
        for series_no in range(1, n_series + 1):
            start = (series_no - 1) * 10
            end = min(start + 10, n)
            series_shots = session_shots[start:end]
            panel = SeriesPanel()
            panel.on_select = self._on_series_shot_clicked
            panel.update_series(series_no, series_shots, threshold_mm=threshold)
            self._series_layout.addWidget(panel)
            self.series_panels.append(panel)
            # 異常 shot を集計
            for s in series_shots:
                fx, fy = s.get("fire_x"), s.get("fire_y")
                if fx is None or fy is None:
                    continue
                if (fx * fx + fy * fy) ** 0.5 >= threshold:
                    self._suspicious_shot_ids.add(s["shot_id"])
                # _row_to_shot_id は削除機能用に維持 (Series 跨ぎで)
                self._row_to_shot_id[s["shot_id"]] = s["shot_id"]
        # スペーサ
        self._series_layout.addStretch(1)
        # サマリ
        self.summary.setText(
            f"session: {n} shots  /  {n_series} series  /  suspicious "
            f"(≥{threshold:.0f}mm): {len(self._suspicious_shot_ids)}"
        )

    def _on_series_shot_clicked(self, shot_id: int, row: int):
        """SeriesPanel 内クリック時。trace_id を解決して on_shot_selected を呼ぶ。"""
        if self.on_shot_selected is None:
            return
        for s in self._session_shots_cache:
            if s["shot_id"] == shot_id:
                self.on_shot_selected(s["trace_id"])
                return

    def _reload_panels(self):
        """閾値変更時に再描画。"""
        if self._session_shots_cache:
            self.update_session(self._session_shots_cache, db_path=self.db_path)

    # ↓ 旧 1 テーブル方式のコードは Series ブロック化により削除済み
    def _DELETED_LEGACY(self):
        """旧コードはこの行から関数末尾までブロック化(到達不能)。"""
        return
        # 以下は完全に到達不能 (return の後)
        n_series = (n + 9) // 10
        total_rows = n + 2 * n_series
        self.table.setRowCount(total_rows)
        ncols = self.table.columnCount()

        row_i = 0
        for series_no in range(1, n_series + 1):
            start = (series_no - 1) * 10
            end = min(start + 10, n)
            series_shots = session_shots[start:end]
            # --- Series ヘッダ行 ---
            self.table.setRowHeight(row_i, 22)
            self.table.setSpan(row_i, 0, 1, ncols)
            hdr = QTableWidgetItem(f"  Series {series_no}   ({end - start} shots)")
            f = hdr.font(); f.setBold(True); hdr.setFont(f)
            hdr.setForeground(QBrush(C.FG))
            hdr.setBackground(QBrush(C.PANEL_LO))
            hdr.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row_i, 0, hdr)
            row_i += 1

            # --- 各 shot 行 ---
            for pos, s in enumerate(series_shots, start=1):
                summ = s.get("summary", {}) or {}
                stab = {st["window_s"]: st for st in (summ.get("stability") or [])}

                def get_r95(w): return stab.get(w, {}).get("r95")
                def pct(k):
                    return (summ.get(k) or {}).get("percent")

                t_str = datetime.datetime.fromtimestamp(
                    s["timer_ms"] / 1000
                ).strftime("%H:%M:%S")
                flags = []
                if s.get("match_shot"): flags.append("M")
                if s.get("favorite"): flags.append("★")
                if s.get("missed"): flags.append("X")
                cant_deg = np.degrees(s["fire_cant"]) if s.get("fire_cant") is not None else None
                fx, fy = s.get("fire_x"), s.get("fire_y")
                dist = (fx * fx + fy * fy) ** 0.5 if (fx is not None and fy is not None) else None

                ten_a    = pct("ten_a_1s")
                ten_a05  = pct("ten_a_05s")
                ten_b    = pct("ten_b_1s")
                nine_c   = pct("nine_c_1s")

                cells_text = [
                    f"{pos}",
                    t_str,
                    f"{dist:.0f}" if dist is not None else "—",
                    f"{ten_a:.1f}" if ten_a is not None else "—",
                    f"{ten_a05:.1f}" if ten_a05 is not None else "—",
                    f"{ten_b:.1f}" if ten_b is not None else "—",
                    f"{nine_c:.1f}" if nine_c is not None else "—",
                    f"{get_r95(1.0):.2f}" if get_r95(1.0) else "—",
                    f"{get_r95(0.5):.2f}" if get_r95(0.5) else "—",
                    f"{cant_deg:+.2f}" if cant_deg is not None else "—",
                    " ".join(flags),
                ]
                self.table.setRowHeight(row_i, 20)
                for c, text in enumerate(cells_text):
                    item = QTableWidgetItem(text)
                    if c == 0:
                        # trace_id を UserRole に
                        item.setData(Qt.ItemDataRole.UserRole, s["trace_id"])
                    # 色付け
                    if c in (3, 4, 5, 6):  # 10a 系 (高いほど良い)
                        try:
                            v = float(text)
                            if v >= 80: item.setForeground(QBrush(C.ACCENT_G))
                            elif v < 30: item.setForeground(QBrush(C.ACCENT_R))
                        except ValueError:
                            pass
                    if c in (7, 8):  # S1, S2 (低いほど良い)
                        try:
                            v = float(text)
                            if v < 2: item.setForeground(QBrush(C.ACCENT_G))
                            elif v >= 5: item.setForeground(QBrush(C.ACCENT_R))
                        except ValueError:
                            pass
                    if c == 2 and dist is not None and dist >= self.threshold_spin.value():
                        item.setForeground(QBrush(C.ACCENT_R))
                    self.table.setItem(row_i, c, item)
                self._row_to_shot_id[row_i] = s["shot_id"]
                row_i += 1

            # --- Series 集計行 ---
            def series_avg(key_path):
                vs = []
                for s in series_shots:
                    cur = s.get("summary") or {}
                    for k in key_path:
                        cur = (cur or {}).get(k) if isinstance(cur, dict) else None
                        if cur is None: break
                    if cur is not None:
                        vs.append(cur)
                return float(np.mean(vs)) if vs else None

            def series_avg_r95(win):
                vs = []
                for s in series_shots:
                    for st in (s.get("summary") or {}).get("stability") or []:
                        if st.get("window_s") == win:
                            vs.append(st["r95"]); break
                return float(np.mean(vs)) if vs else None

            avg_ten_a = series_avg(["ten_a_1s", "percent"])
            avg_ten_a05 = series_avg(["ten_a_05s", "percent"])
            avg_ten_b = series_avg(["ten_b_1s", "percent"])
            avg_nine_c = series_avg(["nine_c_1s", "percent"])
            avg_s1 = series_avg_r95(1.0)
            avg_s2 = series_avg_r95(0.5)
            avg_cants = [np.degrees(s["fire_cant"]) for s in series_shots
                         if s.get("fire_cant") is not None]
            avg_cant = float(np.mean(avg_cants)) if avg_cants else None

            summary_cells = [
                "μ", "", "",
                f"{avg_ten_a:.1f}" if avg_ten_a is not None else "—",
                f"{avg_ten_a05:.1f}" if avg_ten_a05 is not None else "—",
                f"{avg_ten_b:.1f}" if avg_ten_b is not None else "—",
                f"{avg_nine_c:.1f}" if avg_nine_c is not None else "—",
                f"{avg_s1:.2f}" if avg_s1 is not None else "—",
                f"{avg_s2:.2f}" if avg_s2 is not None else "—",
                f"{avg_cant:+.2f}" if avg_cant is not None else "—",
                "",
            ]
            self.table.setRowHeight(row_i, 22)
            for c, text in enumerate(summary_cells):
                item = QTableWidgetItem(text)
                item.setBackground(QBrush(C.PANEL))
                f = item.font(); f.setItalic(True); item.setFont(f)
                item.setForeground(QBrush(C.ACCENT_B))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(row_i, c, item)
            row_i += 1

        self._refresh_marks()

    def _refresh_marks(self):
        """閾値変更時に異常 shot をマーク。dist 列は新スキーマで index 2。"""
        threshold = self.threshold_spin.value()
        self._suspicious_shot_ids.clear()
        suspicious_count = 0
        for row in range(self.table.rowCount()):
            # _row_to_shot_id に登録されているのが個別 shot 行 (Series header / summary は対象外)
            if row not in self._row_to_shot_id:
                continue
            dist_item = self.table.item(row, 2)
            if dist_item is None:
                continue
            try:
                dist = float(dist_item.text())
            except ValueError:
                continue
            is_suspicious = dist >= threshold
            if is_suspicious:
                suspicious_count += 1
                shot_id = self._row_to_shot_id.get(row)
                if shot_id is not None:
                    self._suspicious_shot_ids.add(shot_id)
            for col in range(self.table.columnCount()):
                it = self.table.item(row, col)
                if it is None:
                    continue
                if is_suspicious:
                    it.setBackground(QBrush(QColor(255, 230, 230)))
                else:
                    it.setBackground(QBrush(C.BG))
        n_shots = len(self._row_to_shot_id)
        self.summary.setText(
            f"shots: {n_shots}   suspicious (≥{threshold:.0f}mm): {suspicious_count}"
        )

    def _delete_suspicious(self):
        ids = sorted(self._suspicious_shot_ids)
        if not ids:
            QMessageBox.information(self, "削除なし", "閾値を超える shot がありません。")
            return
        self._confirm_and_delete(ids, f"異常 shot {len(ids)} 件")

    def _delete_selected(self):
        # 新 ShotsTab では選択削除は提供しない (Series 内クリックは Dashboard 移動)
        QMessageBox.information(
            self, "未対応",
            "選択削除は新 UI で未対応。閾値以上の異常 shot は『異常 shot を一括削除』をお使いください。"
        )

    def _confirm_and_delete(self, shot_ids: list[int], label: str):
        if self.db_path is None:
            QMessageBox.warning(self, "エラー", "DB パスが未設定です。")
            return
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("削除確認")
        msg.setText(f"{label} を物理削除します。")
        msg.setInformativeText(
            "対応する trace に他 shot が無ければ trace 行も削除されます。\n"
            "この操作は SCATT Expert の表示にも反映されます (取り消し不可)。\n\n"
            f"shot_id: {shot_ids}"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Ok:
            return
        try:
            result = delete_shots(self.db_path, shot_ids)
        except Exception as e:
            QMessageBox.critical(self, "削除失敗", str(e))
            return
        QMessageBox.information(
            self, "削除完了",
            f"shots: {result['shots']} 件削除\ntraces: {len(result['traces'])} 件削除\n"
            f"trace_ids: {result['traces']}"
        )
        if self.on_delete_committed:
            self.on_delete_committed()


# ===========================================================================
# Tab 4: Drift (shot 間ドリフト + Cant 相関)
# ===========================================================================

class DriftTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel("セッション内 shot の発射点散布図と Cant 推移。色は shot 順 (古→新)。")
        info.setStyleSheet(f"color: {hex_of(C.FG_MUTED)}; font-size: 11px;")
        lay.addWidget(info)
        # 上: 発射点散布図 (ターゲット座標)
        self.scatter_plot = pg.PlotWidget(title="Shot impact scatter (mm)")
        self.scatter_plot.setLabel('left', 'Y', units='mm')
        self.scatter_plot.setLabel('bottom', 'X', units='mm')
        self.scatter_plot.setAspectLocked(True)
        self.scatter_plot.showGrid(x=True, y=True, alpha=0.2)
        # 中心十字
        self.scatter_plot.addLine(x=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
        self.scatter_plot.addLine(y=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
        lay.addWidget(self.scatter_plot, stretch=2)
        # 下: Cant 推移
        self.cant_plot = pg.PlotWidget(title="Cant at fire (deg) over shot order")
        self.cant_plot.setLabel('left', 'cant', units='°')
        self.cant_plot.setLabel('bottom', 'shot index')
        self.cant_plot.showGrid(x=True, y=True, alpha=0.2)
        lay.addWidget(self.cant_plot, stretch=1)
        # サマリ
        self.summary = QLabel("—")
        self.summary.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace; font-size: 12px;"
        )
        lay.addWidget(self.summary)

    def update_session(self, session_shots: list[dict]):
        valid = [s for s in session_shots
                 if s.get("fire_x") is not None and s.get("fire_y") is not None]
        if not valid:
            self.scatter_plot.clear()
            self.cant_plot.clear()
            self.summary.setText("(shot がない or 復号失敗)")
            return
        xs = np.array([s["fire_x"] for s in valid])
        # y 反転 (SCATT y↓ → pyqtgraph y↑)
        ys = -np.array([s["fire_y"] for s in valid])
        cants_deg = np.array([np.degrees(s["fire_cant"]) for s in valid if s.get("fire_cant") is not None])

        self.scatter_plot.clear()
        self.scatter_plot.addLine(x=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
        self.scatter_plot.addLine(y=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
        n = len(valid)
        # 色: 古→新 を 青→緑→黄→赤 で遷移
        colors = []
        for i in range(n):
            f = i / max(1, n - 1)
            r = int(50 + f * 200)
            g = int(200 - abs(f - 0.5) * 200)
            b = int(255 - f * 200)
            colors.append((r, g, b))
        for (xi, yi, col) in zip(xs, ys, colors):
            self.scatter_plot.plot(
                [xi], [yi],
                pen=None, symbol='o', symbolSize=8,
                symbolBrush=col, symbolPen=pg.mkPen(C.FG, width=0.5),
            )
        # 重心
        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        self.scatter_plot.plot([cx], [cy], pen=None, symbol='+', symbolSize=14,
                                symbolPen=pg.mkPen(C.ACCENT_Y, width=2),
                                symbolBrush=None)
        # 順番に線で連結 (ドリフト可視化)
        self.scatter_plot.plot(xs, ys, pen=pg.mkPen(C.FG_MUTED, width=0.5, style=Qt.PenStyle.DotLine))

        # Cant 推移
        self.cant_plot.clear()
        if len(cants_deg) > 0:
            self.cant_plot.plot(np.arange(len(cants_deg)), cants_deg,
                                pen=pg.mkPen(C.ACCENT_B, width=1.5),
                                symbol='o', symbolSize=6,
                                symbolBrush=C.ACCENT_B,
                                symbolPen=pg.mkPen(None))

        # サマリ計算
        rs = np.hypot(xs - cx, ys - cy)
        drift = float(np.sum(np.hypot(np.diff(xs), np.diff(ys))) / max(1, n - 1))
        corr_text = ""
        if len(cants_deg) >= 3 and len(cants_deg) == n:
            cx_corr = float(np.corrcoef(cants_deg, xs)[0, 1])
            cy_corr = float(np.corrcoef(cants_deg, ys)[0, 1])
            corr_text = f"  corr(cant,x)={cx_corr:+.2f}  corr(cant,y)={cy_corr:+.2f}"
        self.summary.setText(
            f"n={n}  R95={np.percentile(rs, 95):.1f}mm  "
            f"mean drift/shot={drift:.1f}mm  "
            f"cant μ={np.mean(cants_deg):+.2f}° σ={np.std(cants_deg):.2f}°"
            + corr_text
        )


# ===========================================================================
# Tab 5: Target (legacy)
# ===========================================================================

def _gr_cant_histogram(pw, t_arr, samples, sr, sessshots):
    """session 内 shot 発射時 Cant のヒストグラム。"""
    pw.clear()
    pw.setTitle("Cant at fire — distribution (°)")
    pw.setLabel('left', 'count')
    pw.setLabel('bottom', 'cant', units='°')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    vals = [np.degrees(s["fire_cant"]) for s in sessshots
            if s.get("fire_cant") is not None]
    if not vals:
        return
    bins = np.linspace(min(vals) - 0.5, max(vals) + 0.5, 25)
    hist, edges = np.histogram(vals, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    width = (edges[1] - edges[0]) * 0.85
    bar = pg.BarGraphItem(x=centers, height=hist, width=width,
                          brush=C.ACCENT_B, pen=pg.mkPen(C.BORDER_STRONG))
    pw.addItem(bar)
    mu = float(np.mean(vals))
    sd = float(np.std(vals))
    pw.setTitle(f"Cant at fire dist  μ={mu:+.2f}°  σ={sd:.2f}°  n={len(vals)}")


def _gr_cant_sd_history(pw, t_arr, samples, sr, sessshots):
    """shot 順での「発射前 0.5 秒 Cant σ」推移。低いほど cant が固定できている。"""
    pw.clear()
    pw.setTitle("Pre-trigger Cant σ per shot (last 0.5s)")
    pw.setLabel('left', 'cant σ', units='°')
    pw.setLabel('bottom', 'shot order')
    pw.showGrid(x=True, y=True, alpha=0.15)
    if not sessshots:
        return
    xs, ys = [], []
    for i, s in enumerate(sessshots):
        v = ((s.get("summary") or {}).get("last_05s") or {}).get("cant_std_rad")
        if v is not None:
            xs.append(i)
            ys.append(np.degrees(v))
    if xs:
        pw.plot(xs, ys, pen=pg.mkPen(C.ACCENT_O, width=1.5),
                symbol='o', symbolSize=5, symbolBrush=C.ACCENT_O,
                symbolPen=pg.mkPen(None))


# Cant 関連グラフを GRAPH_KINDS にも登録
GRAPH_KINDS.append(("cant_hist",       "Cant distribution (session)",   _gr_cant_histogram))
GRAPH_KINDS.append(("cant_sd_history", "Pre-trigger Cant σ per shot",   _gr_cant_sd_history))


class CantTab(QWidget):
    """Cant (銃身ロール) のセッション単位レビュー専用タブ。

    指標:
      - Cant μ (session 内発射時の平均、°)
      - Cant σ (session 内発射時のばらつき、°)
      - Cant σ pre-0.5s μ (発射前 0.5 秒の σ の session 平均、低いほど狙い中固定)
      - Cant drift (前半 vs 後半の平均差)
    """

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        self.header = QLabel("Session: —")
        self.header.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; padding: 0 2px;"
        )
        outer.addWidget(self.header)

        # KPI 4 枚 (compact)
        hero_row = QHBoxLayout()
        hero_row.setSpacing(6)
        self.hero_cant_mu  = RecoilTab._compact_card.__func__(self, "Cant μ (発射時 平均)", "°") \
            if False else self._compact_card("Cant μ (発射時 平均)", "°")
        self.hero_cant_sd  = self._compact_card("Cant σ session (ばらつき)", "°")
        self.hero_presd_mu = self._compact_card("Pre-0.5s σ μ (狙い中 cant 変動)", "°")
        self.hero_drift    = self._compact_card("Drift 前半→後半 (平均差)", "°")
        for h in [self.hero_cant_mu, self.hero_cant_sd, self.hero_presd_mu, self.hero_drift]:
            hero_row.addWidget(h[0], stretch=1)
        outer.addLayout(hero_row)

        # 詳細表 + トレンド
        mid_row = QHBoxLayout()
        mid_row.setSpacing(6)
        tbl = QTableWidget(4, 6)
        tbl.setHorizontalHeaderLabels(["指標", "μ", "σ", "min", "max", "n"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl.setStyleSheet(
            f"QTableWidget {{ background-color: {hex_of(C.PANEL)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; gridline-color: transparent;"
            "   font-family: 'SF Mono', Menlo, monospace; font-size: 11px; }"
            f"QTableWidget::item {{ padding: 2px 8px; }}"
            f"QHeaderView::section {{ background-color: {hex_of(C.PANEL_LO)};"
            f"  color: {hex_of(C.FG_MUTED)}; padding: 2px 6px; border: none;"
            f"  border-bottom: 1px solid {hex_of(C.BORDER)}; font-size: 10px; }}"
        )
        tbl.setColumnWidth(0, 220)
        for c in range(1, 5):
            tbl.setColumnWidth(c, 65)
        for r in range(4):
            tbl.setRowHeight(r, 20)
            for c in range(6):
                tbl.setItem(r, c, QTableWidgetItem("—"))
            tbl.item(r, 0).setForeground(QBrush(C.FG_MUTED))
        tbl.setFixedHeight(108)
        self.detail_table = tbl
        mid_row.addWidget(tbl, stretch=3)

        self.trend_label = QLabel("")
        self.trend_label.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace; font-size: 10px;"
            f" background-color: {hex_of(C.PANEL)}; border: 1px solid {hex_of(C.BORDER)};"
            " padding: 4px 8px;"
        )
        self.trend_label.setWordWrap(True)
        mid_row.addWidget(self.trend_label, stretch=2)
        outer.addLayout(mid_row)

        # グラフ 2×2: 発射時 cant 推移 / 分布 / pre-0.5s σ 推移 / 現在 trace の cant 時系列
        gw = QWidget()
        gg = QGridLayout(gw)
        gg.setContentsMargins(0, 4, 0, 0)
        gg.setHorizontalSpacing(6)
        gg.setVerticalSpacing(6)
        self.graphs = [
            GraphPanel("cant_history"),     # shot 順 cant
            GraphPanel("cant_hist"),        # ヒストグラム (新規)
            GraphPanel("cant_sd_history"),  # pre-0.5s σ 推移 (新規)
            GraphPanel("cant_time"),        # 現在 trace の cant 時系列
        ]
        gg.addWidget(self.graphs[0], 0, 0)
        gg.addWidget(self.graphs[1], 0, 1)
        gg.addWidget(self.graphs[2], 1, 0)
        gg.addWidget(self.graphs[3], 1, 1)
        outer.addWidget(gw, stretch=10)

    def _compact_card(self, title: str, unit: str):
        """RecoilTab._compact_card と同じ実装。"""
        w = QWidget()
        w.setStyleSheet(
            f"QWidget {{ background-color: {hex_of(C.PANEL)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; border-radius: 2px; }}"
        )
        w.setFixedHeight(64)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 10px; border: none;"
            " background: transparent;"
        )
        val_row = QHBoxLayout(); val_row.setSpacing(4)
        val_lbl = QLabel("—")
        val_lbl.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace;"
            " font-size: 22px; border: none; background: transparent;"
        )
        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; border: none;"
            " background: transparent;"
        )
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom)
        val_row.addWidget(val_lbl, alignment=Qt.AlignmentFlag.AlignBottom)
        val_row.addWidget(unit_lbl, alignment=Qt.AlignmentFlag.AlignBottom)
        val_row.addStretch(1)
        sub_lbl = QLabel("")
        sub_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 9px;"
            " font-family: 'SF Mono', monospace; border: none; background: transparent;"
        )
        lay.addWidget(title_lbl)
        lay.addLayout(val_row)
        lay.addWidget(sub_lbl)
        return w, val_lbl, unit_lbl, sub_lbl

    def update_session(self, sid, meta, session_shots,
                       current_samples=None, current_shots=None, sample_rate=120):
        import datetime
        if sid is None or not session_shots:
            self.header.setText("Session: (no data)")
        else:
            ts = session_shots[-1].get("timer_ms")
            date_str = datetime.datetime.fromtimestamp(ts/1000).strftime("%Y-%m-%d %H:%M") if ts else ""
            self.header.setText(
                f"Session #{sid}  {date_str}  "
                f"{meta.get('distance','—')}m {meta.get('position_name','—')}  "
                f"{len(session_shots)} shots"
            )

        # 発射時 cant (deg) と pre-0.5s σ (deg) を集める
        cant_vals = [np.degrees(s["fire_cant"]) for s in session_shots
                     if s.get("fire_cant") is not None]
        pre_sd_vals = []
        for s in session_shots:
            v = ((s.get("summary") or {}).get("last_05s") or {}).get("cant_std_rad")
            if v is not None:
                pre_sd_vals.append(np.degrees(v))

        def _set(hero, val_text, sub_text):
            hero[1].setText(val_text)
            hero[3].setText(sub_text)

        # KPI 4 枚
        if cant_vals:
            mu = float(np.mean(cant_vals)); sd = float(np.std(cant_vals))
            _set(self.hero_cant_mu, f"{mu:+.2f}", f"n={len(cant_vals)}")
            _set(self.hero_cant_sd, f"{sd:.2f}", f"min={min(cant_vals):+.2f} max={max(cant_vals):+.2f}")
        else:
            _set(self.hero_cant_mu, "—", "(no data)")
            _set(self.hero_cant_sd, "—", "(no data)")
        if pre_sd_vals:
            mu_psd = float(np.mean(pre_sd_vals))
            _set(self.hero_presd_mu, f"{mu_psd:.2f}", f"σ={np.std(pre_sd_vals):.2f}  n={len(pre_sd_vals)}")
        else:
            _set(self.hero_presd_mu, "—", "(no data)")
        # Drift = 前半 vs 後半平均差
        if len(cant_vals) >= 6:
            h = len(cant_vals) // 2
            d = float(np.mean(cant_vals[h:]) - np.mean(cant_vals[:h]))
            label = "悪化" if abs(d) > 1.0 else "安定"
            _set(self.hero_drift, f"{d:+.2f}", label)
        else:
            _set(self.hero_drift, "—", "(< 6 shots)")

        # 詳細表 (μ, σ, min, max, n)
        def stats_row(vals):
            if not vals:
                return ("—",) * 5
            return (
                f"{np.mean(vals):+.2f}", f"{np.std(vals):.2f}",
                f"{np.min(vals):+.2f}", f"{np.max(vals):+.2f}",
                str(len(vals)),
            )
        rows = [
            ("Cant at fire (°)",       stats_row(cant_vals)),
            ("Pre-0.5s Cant σ (°)",    stats_row(pre_sd_vals)),
        ]
        # 行 3, 4 は将来用、空表示
        rows.append(("(reserved)", ("—",) * 5))
        rows.append(("(reserved)", ("—",) * 5))
        for r_i, (label, st) in enumerate(rows):
            self.detail_table.item(r_i, 0).setText(label)
            for c_i, v in enumerate(st, start=1):
                self.detail_table.item(r_i, c_i).setText(v)

        # トレンド (前半 vs 後半)
        trend_text = []
        for name, vals in [("Cant", cant_vals), ("Pre σ", pre_sd_vals)]:
            if len(vals) >= 6:
                h = len(vals) // 2
                first = float(np.mean(vals[:h])); second = float(np.mean(vals[h:]))
                d = second - first
                sign = "+" if d >= 0 else ""
                trend_text.append(f"{name}: {first:+.2f}→{second:+.2f} ({sign}{d:.2f})")
        self.trend_label.setText("前半→後半:  " + "    ".join(trend_text) if trend_text else "")

        # グラフ更新
        if current_samples is not None and current_shots is not None:
            t_arr = A.to_trace_arrays(
                current_samples, sample_rate,
                current_shots[0]["trace_offset"] if current_shots else None,
            )
        else:
            t_arr = A.to_trace_arrays([], sample_rate, None)
        for g in self.graphs:
            g.update_data(t_arr, current_samples or [], sample_rate, session_shots)


class RecoilTab(QWidget):
    """反動受け 専用タブ — セッション全体を通した反動傾向のレビュー。"""

    # 反動詳細表に出す指標 (key, ラベル, 単位, 方向, 桁)
    RECOIL_METRICS = [
        ("recoil_peak",       "Peak amplitude",        "mm", "low_good",  2),
        ("recoil_settle",     "Settle time (<5mm)",    "s",  "low_good",  2),
        ("recoil_post05_r95", "Follow-through R95",    "mm", "low_good",  2),
        ("recoil_direction",  "Direction angle",       "°",  "info",      0),
    ]

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # ヘッダ (1 行、薄め)
        self.header = QLabel("Session: —")
        self.header.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; padding: 0 2px;"
        )
        outer.addWidget(self.header)

        # 主要 KPI 4 枚 (横並び、コンパクト、各 70px 高さ)
        hero_row = QHBoxLayout()
        hero_row.setSpacing(6)
        self.hero_peak    = self._compact_card("Peak μ (反動振幅)", "mm")
        self.hero_settle  = self._compact_card("Settle μ (5mm 復元)", "s")
        self.hero_follow  = self._compact_card("Follow R95 μ (0.5s)", "mm")
        self.hero_dir_std = self._compact_card("Dir σ (方向ばらつき)", "°")
        for h in [self.hero_peak, self.hero_settle, self.hero_follow, self.hero_dir_std]:
            hero_row.addWidget(h[0], stretch=1)
        outer.addLayout(hero_row)

        # 詳細表 + トレンドを横並び (1 行 1 指標、コンパクト)
        mid_row = QHBoxLayout()
        mid_row.setSpacing(6)
        n = len(self.RECOIL_METRICS)
        tbl = QTableWidget(n, 6)
        tbl.setHorizontalHeaderLabels(["指標", "μ", "σ", "min", "max", "n"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl.setStyleSheet(
            f"QTableWidget {{ background-color: {hex_of(C.PANEL)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; gridline-color: transparent;"
            "   font-family: 'SF Mono', Menlo, monospace; font-size: 11px; }"
            f"QTableWidget::item {{ padding: 2px 8px; }}"
            f"QHeaderView::section {{ background-color: {hex_of(C.PANEL_LO)};"
            f"  color: {hex_of(C.FG_MUTED)}; padding: 2px 6px; border: none;"
            f"  border-bottom: 1px solid {hex_of(C.BORDER)}; font-size: 10px; }}"
        )
        tbl.setColumnWidth(0, 180)
        for c in range(1, 5):
            tbl.setColumnWidth(c, 65)
        for r in range(n):
            tbl.setRowHeight(r, 20)
            for c in range(6):
                tbl.setItem(r, c, QTableWidgetItem("—"))
            tbl.item(r, 0).setForeground(QBrush(C.FG_MUTED))
        # ヘッダ込みの高さ: header (~22) + 4 行 × 20 + border
        tbl.setFixedHeight(108)
        self.detail_table = tbl
        mid_row.addWidget(tbl, stretch=3)

        # 右側にトレンド + 説明 (縦並び)
        side = QVBoxLayout()
        side.setSpacing(2)
        self.trend_label = QLabel("")
        self.trend_label.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace; font-size: 10px;"
            f" background-color: {hex_of(C.PANEL)}; border: 1px solid {hex_of(C.BORDER)};"
            " padding: 4px 8px;"
        )
        self.trend_label.setWordWrap(True)
        side.addWidget(self.trend_label, stretch=1)
        mid_row.addLayout(side, stretch=2)
        outer.addLayout(mid_row)

        # グラフ 2×2 (画面大半)
        gw = QWidget()
        gg = QGridLayout(gw)
        gg.setContentsMargins(0, 4, 0, 0)
        gg.setHorizontalSpacing(6)
        gg.setVerticalSpacing(6)
        self.graphs = [
            GraphPanel("recoil_xy"),
            GraphPanel("recoil_dir_hist"),
            GraphPanel("recoil_peak_hist"),
            GraphPanel("recoil_settle"),
        ]
        gg.addWidget(self.graphs[0], 0, 0)
        gg.addWidget(self.graphs[1], 0, 1)
        gg.addWidget(self.graphs[2], 1, 0)
        gg.addWidget(self.graphs[3], 1, 1)
        outer.addWidget(gw, stretch=10)

    def _compact_card(self, title: str, unit: str):
        """KPI カードのコンパクト版。固定高さ 64px、横並びに最適化。"""
        w = QWidget()
        w.setStyleSheet(
            f"QWidget {{ background-color: {hex_of(C.PANEL)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; border-radius: 2px; }}"
        )
        w.setFixedHeight(64)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 10px; border: none;"
            " background: transparent;"
        )
        val_row = QHBoxLayout(); val_row.setSpacing(4)
        val_lbl = QLabel("—")
        val_lbl.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace;"
            " font-size: 22px; border: none; background: transparent;"
        )
        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; border: none;"
            " background: transparent;"
        )
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom)
        val_row.addWidget(val_lbl, alignment=Qt.AlignmentFlag.AlignBottom)
        val_row.addWidget(unit_lbl, alignment=Qt.AlignmentFlag.AlignBottom)
        val_row.addStretch(1)
        sub_lbl = QLabel("")
        sub_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 9px;"
            " font-family: 'SF Mono', monospace; border: none; background: transparent;"
        )
        lay.addWidget(title_lbl)
        lay.addLayout(val_row)
        lay.addWidget(sub_lbl)
        # 既存の _hero_card 互換 (widget, val_lbl, unit_lbl, sub_lbl)
        return w, val_lbl, unit_lbl, sub_lbl

    def update_session(self, sid: int | None, meta: dict, session_shots: list[dict],
                       current_samples=None, current_shots=None, sample_rate: int = 120):
        """セッション全体の反動傾向を表示。current_* は (グラフ用に) 現在 shot を渡せる。"""
        import datetime
        # ヘッダ
        if sid is None or not session_shots:
            self.header.setText("Session: (no data)")
        else:
            ts = session_shots[-1].get("timer_ms")
            date_str = datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else ""
            self.header.setText(
                f"Session #{sid}  {date_str}  "
                f"{meta.get('distance','—')}m {meta.get('position_name','—')}  "
                f"{len(session_shots)} shots"
            )

        # 各指標の値を集める
        peak_vals = []
        settle_vals = []
        follow_vals = []
        dir_vals_rad = []
        for s in session_shots:
            r = (s.get("summary") or {}).get("recoil") or {}
            if r.get("peak_r_mm") is not None: peak_vals.append(r["peak_r_mm"])
            if r.get("settle_time_s") is not None: settle_vals.append(r["settle_time_s"])
            if r.get("post_05_r95_mm") is not None: follow_vals.append(r["post_05_r95_mm"])
            if r.get("direction_deg") is not None and r.get("impulse_mm", 0) > 0.5:
                dir_vals_rad.append(np.radians(r["direction_deg"]))

        # session 内 方向 σ (円形統計)
        if len(dir_vals_rad) >= 2:
            mx = float(np.mean(np.cos(dir_vals_rad)))
            my = float(np.mean(np.sin(dir_vals_rad)))
            R = np.hypot(mx, my)
            sess_dir_std = float(np.degrees(np.sqrt(-2 * np.log(max(R, 1e-6)))))
            sess_dir_mean = float(np.degrees(np.arctan2(my, mx)))
        else:
            sess_dir_std = None
            sess_dir_mean = None

        # --- KPI 4 枚 (compact_card 互換: [widget, val, unit, sub]) ---
        def _set_compact(hero, val_text, sub_text):
            hero[1].setText(val_text)
            hero[3].setText(sub_text)

        for hero, vals, digits in [
            (self.hero_peak,   peak_vals,   1),
            (self.hero_settle, settle_vals, 2),
            (self.hero_follow, follow_vals, 1),
        ]:
            if vals:
                mu = float(np.mean(vals))
                sd = float(np.std(vals))
                _set_compact(hero, f"{mu:.{digits}f}", f"σ={sd:.{digits}f}  n={len(vals)}")
            else:
                _set_compact(hero, "—", "(no data)")
        # 方向 σ KPI
        if sess_dir_std is not None:
            _set_compact(
                self.hero_dir_std, f"{sess_dir_std:.0f}",
                f"mean={sess_dir_mean:+.0f}°  n={len(dir_vals_rad)}",
            )
        else:
            _set_compact(self.hero_dir_std, "—", "(no data)")

        # --- 詳細表 ---
        def stats_row(vals):
            if not vals:
                return ("—",) * 5
            return (
                f"{np.mean(vals):.2f}",
                f"{np.std(vals):.2f}",
                f"{np.min(vals):.2f}",
                f"{np.max(vals):.2f}",
                str(len(vals)),
            )

        rows = [
            ("Peak amplitude",       stats_row(peak_vals)),
            ("Settle time (<5mm)",   stats_row(settle_vals)),
            ("Follow-through R95",   stats_row(follow_vals)),
            ("Direction angle",      stats_row([np.degrees(a) for a in dir_vals_rad])),
        ]
        for r_i, (label, stats) in enumerate(rows):
            self.detail_table.item(r_i, 0).setText(label)
            for c_i, v in enumerate(stats, start=1):
                self.detail_table.item(r_i, c_i).setText(v)

        # --- トレンド (前半 vs 後半) ---
        trend_text = []
        for name, vals, low_better in [
            ("Peak",        peak_vals,   True),
            ("Settle",      settle_vals, True),
            ("Follow R95",  follow_vals, True),
        ]:
            if len(vals) >= 6:
                half = len(vals) // 2
                first = float(np.mean(vals[:half]))
                second = float(np.mean(vals[half:]))
                diff = second - first
                direction = "改善" if (diff < 0) == low_better else "悪化"
                sign = "+" if diff >= 0 else ""
                trend_text.append(f"{name}: {first:.2f}→{second:.2f} ({sign}{diff:.2f}, {direction})")
        if trend_text:
            self.trend_label.setText("前半→後半:  " + "    ".join(trend_text))
        else:
            self.trend_label.setText("")

        # --- グラフ 4 枚 ---
        # 現在 shot の trace を渡せばグラフがリッチに、なくても session_shots ベースで動く
        if current_samples is not None and current_shots is not None:
            t_arr = A.to_trace_arrays(
                current_samples, sample_rate,
                current_shots[0]["trace_offset"] if current_shots else None,
            )
        else:
            t_arr = A.to_trace_arrays([], sample_rate, None)
        for g in self.graphs:
            g.update_data(t_arr, current_samples or [], sample_rate, session_shots)


class SessionDetailPanel(QWidget):
    """Sessions タブ下段: 選択中セッションの集計 + トレンドグラフ。"""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(6)

        # ヘッダ
        self.header = QLabel("Session: (select a row above)")
        self.header.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-size: 13px; font-weight: 600; padding: 2px 4px;"
        )
        outer.addWidget(self.header)

        # KPI 6 枚 (10a μ, 10a-0.5 μ, S1 μ, S2 μ, Peak μ, HR μ)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(6)
        self.kpi_10a   = _hero_card("10a μ (10-ring 1s)",   "%")
        self.kpi_10a5  = _hero_card("10a-0.5 μ",             "%")
        self.kpi_s1    = _hero_card("S1 μ (1s stability)",   "mm")
        self.kpi_s2    = _hero_card("S2 μ (0.5s stability)", "mm")
        self.kpi_peak  = _hero_card("Recoil peak μ",         "mm")
        self.kpi_hr    = _hero_card("HR μ",                  "bpm")
        for k in [self.kpi_10a, self.kpi_10a5, self.kpi_s1, self.kpi_s2,
                  self.kpi_peak, self.kpi_hr]:
            kpi_row.addWidget(k[0], stretch=1)
        outer.addLayout(kpi_row)

        # トレンドグラフ 2×2
        gw = QWidget()
        gg = QGridLayout(gw)
        gg.setContentsMargins(0, 0, 0, 0)
        gg.setHorizontalSpacing(8)
        gg.setVerticalSpacing(8)

        self.plot_scatter = pg.PlotWidget(title="Shot impact scatter")
        self.plot_scatter.setLabel('left', 'Y', units='mm')
        self.plot_scatter.setLabel('bottom', 'X', units='mm')
        self.plot_scatter.setAspectLocked(True)
        self.plot_scatter.showGrid(x=True, y=True, alpha=0.15)
        gg.addWidget(self.plot_scatter, 0, 0)

        self.plot_r95 = pg.PlotWidget(title="S1 / S2 per shot")
        self.plot_r95.setLabel('left', 'mm')
        self.plot_r95.setLabel('bottom', 'shot order')
        self.plot_r95.showGrid(x=True, y=True, alpha=0.15)
        gg.addWidget(self.plot_r95, 0, 1)

        self.plot_10a = pg.PlotWidget(title="10a / 10a-0.5 per shot")
        self.plot_10a.setLabel('left', '%')
        self.plot_10a.setLabel('bottom', 'shot order')
        self.plot_10a.showGrid(x=True, y=True, alpha=0.15)
        gg.addWidget(self.plot_10a, 1, 0)

        self.plot_recoil = pg.PlotWidget(title="Recoil peak amplitude per shot")
        self.plot_recoil.setLabel('left', 'mm')
        self.plot_recoil.setLabel('bottom', 'shot order')
        self.plot_recoil.showGrid(x=True, y=True, alpha=0.15)
        gg.addWidget(self.plot_recoil, 1, 1)

        outer.addWidget(gw, stretch=1)

        # サマリ文
        self.trend_label = QLabel("")
        self.trend_label.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace; font-size: 11px;"
        )
        outer.addWidget(self.trend_label)

        # ローカル NLG セッション所見
        self.session_feedback_label = QLabel("")
        self.session_feedback_label.setWordWrap(True)
        self.session_feedback_label.setStyleSheet(
            f"QLabel {{ background-color: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; padding: 8px 12px;"
            "   font-size: 12px; line-height: 1.5; }"
        )
        outer.addWidget(self.session_feedback_label)

    def clear(self):
        for p in [self.plot_scatter, self.plot_r95, self.plot_10a, self.plot_recoil]:
            p.clear()
        self.header.setText("Session: (select a row above)")
        for k in [self.kpi_10a, self.kpi_10a5, self.kpi_s1, self.kpi_s2,
                  self.kpi_peak, self.kpi_hr]:
            k[1].setText("—")
            k[3].setText("")
        self.trend_label.setText("")

    def update_session(self, sid: int, meta: dict, session_shots: list[dict]):
        import datetime
        date_str = ""
        if session_shots:
            ts = session_shots[-1].get("timer_ms")
            if ts:
                date_str = datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
        pos_name = meta.get("position_name", "—")
        dist = meta.get("distance", "—")
        n = len(session_shots)
        self.header.setText(
            f"Session #{sid}  {date_str}  {dist}m {pos_name}  {n} shots"
        )

        # 各指標の値を集める
        ten_a_vals, ten_a5_vals, s1_vals, s2_vals = [], [], [], []
        peak_vals, hr_vals = [], []
        xs, ys = [], []
        cants = []
        for s in session_shots:
            summ = s.get("summary") or {}
            v = (summ.get("ten_a_1s") or {}).get("percent")
            if v is not None: ten_a_vals.append(v)
            v = (summ.get("ten_a_05s") or {}).get("percent")
            if v is not None: ten_a5_vals.append(v)
            for st in (summ.get("stability") or []):
                if st.get("window_s") == 1.0:
                    s1_vals.append(st["r95"])
                if st.get("window_s") == 0.5:
                    s2_vals.append(st["r95"])
            pk = (summ.get("recoil") or {}).get("peak_r_mm")
            if pk is not None: peak_vals.append(pk)
            if s.get("hr_at_fire") is not None: hr_vals.append(s["hr_at_fire"])
            if s.get("fire_x") is not None and s.get("fire_y") is not None:
                # y 反転 (SCATT y↓ → pyqtgraph y↑)
                xs.append(s["fire_x"]); ys.append(-s["fire_y"])
            if s.get("fire_cant") is not None:
                cants.append(np.degrees(s["fire_cant"]))

        # KPI 更新
        def fmt(vals, digits, suffix=""):
            if not vals:
                return "—", ""
            mu = np.mean(vals)
            sd = np.std(vals)
            return f"{mu:.{digits}f}", f"σ={sd:.{digits}f}  n={len(vals)}{suffix}"

        for kpi, vals, digits in [
            (self.kpi_10a,  ten_a_vals,  1),
            (self.kpi_10a5, ten_a5_vals, 1),
            (self.kpi_s1,   s1_vals,     2),
            (self.kpi_s2,   s2_vals,     2),
            (self.kpi_peak, peak_vals,   1),
            (self.kpi_hr,   hr_vals,     0),
        ]:
            val_text, sub_text = fmt(vals, digits)
            kpi[1].setText(val_text)
            kpi[1].setStyleSheet(
                f"color: {hex_of(C.FG)}; font-family: 'SF Mono', monospace;"
                " font-size: 26px; border: none; background: transparent;"
            )
            kpi[3].setText(sub_text)

        # 着弾点散布図
        self.plot_scatter.clear()
        self.plot_scatter.addLine(x=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
        self.plot_scatter.addLine(y=0, pen=pg.mkPen(C.FG_MUTED, width=0.5))
        if xs:
            n_pts = len(xs)
            for i, (xi, yi) in enumerate(zip(xs, ys)):
                f = i / max(1, n_pts - 1)
                col = (int(60 + f * 180), int(150 - f * 100), int(220 - f * 180))
                self.plot_scatter.plot([xi], [yi], pen=None, symbol='o', symbolSize=7,
                                       symbolBrush=col, symbolPen=pg.mkPen(C.FG, width=0.5))
            cx, cy = float(np.mean(xs)), float(np.mean(ys))
            rs = np.hypot(np.array(xs) - cx, np.array(ys) - cy)
            r95 = float(np.percentile(rs, 95)) if len(rs) >= 2 else 0
            self.plot_scatter.plot([cx], [cy], pen=None, symbol='+', symbolSize=14,
                                   symbolPen=pg.mkPen(C.ACCENT_Y, width=2), symbolBrush=None)
            if r95 > 0:
                theta = np.linspace(0, 2*np.pi, 64)
                self.plot_scatter.plot(cx + r95 * np.cos(theta), cy + r95 * np.sin(theta),
                                       pen=pg.mkPen(C.ACCENT_Y, width=1,
                                                    style=Qt.PenStyle.DashLine))

        # S1 / S2 推移
        self.plot_r95.clear()
        if s1_vals:
            self.plot_r95.plot(range(len(s1_vals)), s1_vals,
                               pen=pg.mkPen(C.ACCENT_O, width=1.5),
                               symbol='o', symbolSize=5, symbolBrush=C.ACCENT_O,
                               symbolPen=pg.mkPen(None), name='S1')
        if s2_vals:
            self.plot_r95.plot(range(len(s2_vals)), s2_vals,
                               pen=pg.mkPen(C.ACCENT_R, width=1.5),
                               symbol='s', symbolSize=5, symbolBrush=C.ACCENT_R,
                               symbolPen=pg.mkPen(None), name='S2')

        # 10a / 10a-0.5 推移
        self.plot_10a.clear()
        if ten_a_vals:
            self.plot_10a.plot(range(len(ten_a_vals)), ten_a_vals,
                                pen=pg.mkPen(C.ACCENT_G, width=1.5),
                                symbol='o', symbolSize=5, symbolBrush=C.ACCENT_G,
                                symbolPen=pg.mkPen(None))
        if ten_a5_vals:
            self.plot_10a.plot(range(len(ten_a5_vals)), ten_a5_vals,
                                pen=pg.mkPen(C.ACCENT_B, width=1.5),
                                symbol='s', symbolSize=5, symbolBrush=C.ACCENT_B,
                                symbolPen=pg.mkPen(None))

        # Recoil peak 推移
        self.plot_recoil.clear()
        if peak_vals:
            self.plot_recoil.plot(range(len(peak_vals)), peak_vals,
                                  pen=pg.mkPen(C.ACCENT_R, width=1.5),
                                  symbol='o', symbolSize=5, symbolBrush=C.ACCENT_R,
                                  symbolPen=pg.mkPen(None))

        # トレンド (前半 vs 後半 比較 = 疲労 or 改善検出)
        trend_text = []
        for name, vals, low_better in [
            ("10a",  ten_a_vals,  False),
            ("S1",   s1_vals,     True),
            ("S2",   s2_vals,     True),
            ("Peak", peak_vals,   True),
        ]:
            if len(vals) >= 6:
                half = len(vals) // 2
                first = float(np.mean(vals[:half]))
                second = float(np.mean(vals[half:]))
                diff = second - first
                # 改善 / 悪化判定
                if low_better:
                    direction = "改善" if diff < 0 else "悪化"
                else:
                    direction = "改善" if diff > 0 else "悪化"
                sign = "+" if diff >= 0 else ""
                trend_text.append(f"{name}: {first:.2f}→{second:.2f} ({sign}{diff:.2f}, {direction})")
        if trend_text:
            self.trend_label.setText("前半→後半:  " + "    ".join(trend_text))
        else:
            self.trend_label.setText("")

        # セッション NLG 所見
        try:
            self.session_feedback_label.setText(FB.session_feedback(session_shots))
        except Exception as e:
            self.session_feedback_label.setText(f"(feedback unavailable: {e})")


class SessionsTab(QWidget):
    """セッション一覧 (上段) + 選択 session の詳細レビュー (下段)。"""

    COLUMNS = [
        ("session", 70),
        ("date",    110),
        ("pos",     70),
        ("dist",    60),
        ("shots",   50),
        ("10a μ",   60),
        ("10a-0.5 μ", 70),
        ("S1 μ",    60),
        ("S2 μ",    60),
        ("Cant μ",  60),
        ("HR μ",    60),
        ("best 10a", 70),
        ("worst 10a", 70),
    ]

    def __init__(self):
        super().__init__()
        self.on_session_selected = None
        self.db_path = None
        self._all_shots: dict[int, list[dict]] = {}
        self._meta: dict[int, dict] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        info = QLabel("セッション横断レビュー。行を選ぶと下段サブタブに詳細表示(↑↓ で切替可)。ダブルクリックで Dashboard へジャンプ。")
        info.setStyleSheet(f"color: {hex_of(C.FG_MUTED)}; font-size: 11px;")
        outer.addWidget(info)

        split = QSplitter(Qt.Orientation.Vertical)
        outer.addWidget(split, stretch=1)

        # 上段: テーブル
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)};"
            "   font-family: 'SF Mono', Menlo, monospace; font-size: 11px; }"
            f"QHeaderView::section {{ background-color: {hex_of(C.PANEL_LO)};"
            f"  color: {hex_of(C.FG_MUTED)}; padding: 4px; border: none; font-size: 10px; }}"
        )
        from PyQt6.QtWidgets import QAbstractItemView
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for i, (_, w) in enumerate(self.COLUMNS):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        split.addWidget(self.table)

        # 下段: サブタブ (Overview / Recoil / Cant / Drift / Spectrum)
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)
        self.sub_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {hex_of(C.BORDER)};"
            f"  background-color: {hex_of(C.BG)}; top: -1px; }}"
            f"QTabBar::tab {{ background: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG_MUTED)};"
            f"  padding: 5px 12px; border: 1px solid {hex_of(C.BORDER)};"
            "  border-bottom: none; font-size: 11px; min-width: 60px; }"
            f"QTabBar::tab:selected {{ background: {hex_of(C.BG)}; color: {hex_of(C.FG)}; }}"
        )
        self.detail = SessionDetailPanel()
        self.sub_recoil = RecoilTab()
        self.sub_cant = CantTab()
        self.sub_drift = DriftTab()
        self.sub_spectrum = SpectrumTab()
        self.sub_tabs.addTab(self.detail, "Overview")
        self.sub_tabs.addTab(self.sub_recoil, "Recoil")
        self.sub_tabs.addTab(self.sub_cant, "Cant")
        self.sub_tabs.addTab(self.sub_drift, "Drift")
        self.sub_tabs.addTab(self.sub_spectrum, "Spectrum")
        split.addWidget(self.sub_tabs)
        split.setSizes([180, 600])

    def _current_sid(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection_changed(self):
        sid = self._current_sid()
        if sid is None:
            return
        meta = self._meta.get(sid, {})
        shots = self._all_shots.get(sid, [])
        sr = meta.get("sample_rate", 120) or 120
        # 全サブタブを更新 (session 単位)
        self.detail.update_session(sid, meta, shots)
        # サブタブはセッション最新 shot trace をベースに描画 (代表値として)
        latest_samples = None
        latest_shots = None
        if shots:
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
                last_tid = shots[-1]["trace_id"]
                row = conn.execute(
                    "SELECT data FROM traces WHERE trace_id = ?", (last_tid,)
                ).fetchone()
                conn.close()
                if row:
                    latest_samples = decode_trace(row[0])
                    latest_shots = [{
                        "shot_id": shots[-1]["shot_id"],
                        "trace_offset": shots[-1]["trace_offset"],
                    }]
            except Exception:
                pass
        self.sub_recoil.update_session(sid, meta, shots,
                                       current_samples=latest_samples,
                                       current_shots=latest_shots, sample_rate=sr)
        self.sub_cant.update_session(sid, meta, shots,
                                     current_samples=latest_samples,
                                     current_shots=latest_shots, sample_rate=sr)
        self.sub_drift.update_session(shots)
        if latest_samples is not None and latest_shots is not None:
            self.sub_spectrum.update_trace(latest_samples, latest_shots, sr)

    def _on_double_clicked(self, _item):
        sid = self._current_sid()
        if sid is not None and self.on_session_selected:
            self.on_session_selected(sid)

    def reload(self, db_path: str, hr_at_shot: dict | None = None):
        self.db_path = db_path
        hr_at_shot = hr_at_shot or {}
        self._all_shots.clear()
        self._meta.clear()
        import datetime
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        except Exception:
            return
        rows = conn.execute("""
            SELECT s.session_id, s.distance, s.caliber, s.position, s.sample_rate,
                   (SELECT MAX(timer) FROM traces WHERE session_id = s.session_id) AS last_t
            FROM sessions s ORDER BY last_t DESC NULLS LAST
        """).fetchall()
        self.table.setRowCount(len(rows))
        for r_i, (sid, dist, cal, pos, sr, last_t) in enumerate(rows):
            pos_name = POSITION_NAMES.get(pos, f"pos{pos}")
            date_str = ""
            if last_t:
                date_str = datetime.datetime.fromtimestamp(last_t / 1000).strftime("%m-%d %H:%M")
            # session の shot を取得して集計
            session_shots = fetch_session_shots(conn, sid)
            # HR を埋め込み(in-memory)
            for s in session_shots:
                hr_info = hr_at_shot.get(s["shot_id"]) or {}
                s["hr_at_fire"] = hr_info.get("hr")
                s["rmssd_30s"] = hr_info.get("rmssd")
            # キャッシュ
            self._all_shots[sid] = session_shots
            self._meta[sid] = {
                "session_id": sid, "distance": dist, "caliber": cal,
                "position": pos, "sample_rate": sr,
                "position_name": POSITION_NAMES.get(pos, f"pos{pos}"),
            }
            n_shots = len(session_shots)
            def avg(key_path):
                vals = []
                for s in session_shots:
                    summ = s.get("summary") or {}
                    cur = summ
                    for k in key_path:
                        if isinstance(cur, dict):
                            cur = cur.get(k)
                        else:
                            cur = None; break
                    if cur is not None:
                        vals.append(cur)
                return float(np.mean(vals)) if vals else None
            avg_10a = avg(["ten_a_1s", "percent"])
            avg_10a5 = avg(["ten_a_05s", "percent"])
            # stability はリストなので個別処理
            s1_vals, s2_vals = [], []
            for s in session_shots:
                stab = (s.get("summary") or {}).get("stability") or []
                for st in stab:
                    if st.get("window_s") == 1.0:
                        s1_vals.append(st["r95"])
                    if st.get("window_s") == 0.5:
                        s2_vals.append(st["r95"])
            avg_s1 = float(np.mean(s1_vals)) if s1_vals else None
            avg_s2 = float(np.mean(s2_vals)) if s2_vals else None
            cant_vals = [s["fire_cant"] for s in session_shots
                         if s.get("fire_cant") is not None]
            avg_cant_deg = float(np.degrees(np.mean(cant_vals))) if cant_vals else None
            hr_vals = [s["hr_at_fire"] for s in session_shots
                       if s.get("hr_at_fire") is not None]
            avg_hr = float(np.mean(hr_vals)) if hr_vals else None
            # ベスト/ワースト 10a
            ten_a_list = [
                ((s.get("summary") or {}).get("ten_a_1s") or {}).get("percent")
                for s in session_shots
            ]
            ten_a_list = [v for v in ten_a_list if v is not None]
            best_10a = max(ten_a_list) if ten_a_list else None
            worst_10a = min(ten_a_list) if ten_a_list else None

            cells = [
                f"#{sid}", date_str, pos_name, f"{dist}m", str(n_shots),
                f"{avg_10a:.1f}%" if avg_10a is not None else "—",
                f"{avg_10a5:.1f}%" if avg_10a5 is not None else "—",
                f"{avg_s1:.2f}" if avg_s1 is not None else "—",
                f"{avg_s2:.2f}" if avg_s2 is not None else "—",
                f"{avg_cant_deg:+.2f}" if avg_cant_deg is not None else "—",
                f"{avg_hr:.0f}" if avg_hr is not None else "—",
                f"{best_10a:.1f}%" if best_10a is not None else "—",
                f"{worst_10a:.1f}%" if worst_10a is not None else "—",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, sid)
                self.table.setItem(r_i, c, item)
        conn.close()
        # 起動時は先頭行を選択して詳細表示
        if self.table.rowCount() > 0:
            self.table.selectRow(0)


HELP_HTML = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #222; line-height: 1.6; }
  h2 { color: #1a4a8a; border-bottom: 1px solid #ccd; padding-bottom: 4px; margin-top: 24px; }
  h3 { color: #333; margin-top: 14px; }
  .key { font-family: 'SF Mono', monospace; background: #f3f3f6; padding: 1px 4px; border-radius: 3px; }
  .good { color: #287d2c; font-weight: 600; }
  .bad  { color: #b22222; font-weight: 600; }
  .muted { color: #707075; font-size: 90%; }
  table { border-collapse: collapse; margin: 8px 0; }
  th, td { border: 1px solid #d0d0d5; padding: 4px 10px; font-size: 13px; }
  th { background: #f3f3f6; }
</style>

<h2>このソフトについて</h2>
<p>SCATT Expert の補助ツール。本家 SCATT が既に表示している指標(10点/10.5点圏内の安定性、平均標準点の安定性、1秒/250ms の照準起動速さ等)とは
重複させず、<b>本家にない or 見えにくい補助指標を多面的に出す</b>のが目的。</p>
<p>伏射 (prone) に特化した数字を中心に据えているが、他姿勢でも有効。</p>

<h2>色の意味 (Dashboard)</h2>
<p>各指標は <b>セッション内の過去 shot の μ ± σ と比較</b>して色付けされる:</p>
<table>
  <tr><th>色</th><th>意味</th></tr>
  <tr><td><span class="good">緑(濃)</span></td><td>普段より <b>2σ 以上 良い</b> 方向</td></tr>
  <tr><td><span style="color:#006e3c">緑(淡)</span></td><td>普段より 1σ 良い</td></tr>
  <tr><td>黒</td><td>普段通り (μ±σ 以内)</td></tr>
  <tr><td><span style="color:#be6e19">橙</span></td><td>普段より 1σ 悪い</td></tr>
  <tr><td><span class="bad">赤</span></td><td>普段より <b>2σ 以上 悪い</b> = 外した原因の可能性</td></tr>
</table>

<h2>主役 (Hero) 指標 — 本家 SCATT 互換</h2>
<h3 class="key">10a   10-ring time (last 1s)</h3>
<p>発射直前 1 秒のうち照準が <b>10-ring (R≤5.2mm)</b> 内にあった時間の割合 (%)。高いほど良い。本家 SCATT の "10a" と同義。</p>
<h3 class="key">10a-0.5   10-ring time (last 0.5s)</h3>
<p>同じく 10-ring 内時間 %、ただし発射前 <b>0.5 秒</b>の窓。高いほど良い。本家の "10a-0.5"(or "10a5")相当。</p>
<h3 class="key">S1   stability (last 1s)</h3>
<p>発射前 1 秒のホールド円半径(R95: 95% を含む円)。<b>mm 単位、低いほど安定</b>。本家 "S1"。</p>
<h3 class="key">S2   stability (last 0.5s)</h3>
<p>同じく <b>0.5 秒</b>。伏射の最重要指標。本家 "S2"。</p>
<p class="muted">本家には他に <b>10b</b>(inner-10、R≤2.5mm)、<b>9c</b>(9-ring、R≤13.2mm) 等もあり、本ソフトでは中段指標表に並ぶ。</p>

<h2>中段指標</h2>
<table>
  <tr><th>指標</th><th>意味</th><th>方向</th></tr>
  <tr><td class="key">10b / 10b-0.5</td><td>Inner-10 (R≤2.5mm) 内時間 %、1s / 0.5s</td><td>高いほど良い</td></tr>
  <tr><td class="key">9c</td><td>9-ring (R≤13.2mm) 内時間 %、1s</td><td>高いほど良い</td></tr>
  <tr><td class="key">R95 last 2/3s</td><td>発射前 2/3 秒のホールド円</td><td>低いほど良い (S1/S2 の長窓版)</td></tr>
  <tr><td class="key">Trigger timing</td><td>発射の瞬間のサイト移動速度 (mm/s)</td><td>低いほど良い(止めて撃てた)</td></tr>
  <tr><td class="key">Cant (at fire)</td><td>発射の瞬間の銃身ロール角(度)</td><td>個人毎の自然な角度から外れていなければOK</td></tr>
  <tr><td class="key">Cant σ (last 0.5s)</td><td>発射直前 0.5 秒の cant の標準偏差</td><td>低いほど良い (cant がブレていない)</td></tr>
  <tr><td class="key">Hold time</td><td>発射直前に速度 15mm/s 未満が連続した秒数</td><td>高いほど良い (止めていた時間)</td></tr>
  <tr><td class="key">Aim duration</td><td>構え始め〜発射までの時間</td><td>個人による(2〜10秒典型)</td></tr>
  <tr><td class="key">Tremor 8–12Hz</td><td>生理振戦帯域の FFT パワー(X 座標)</td><td>低いほど良い</td></tr>
  <tr><td class="key">Breath 0.15–0.5Hz</td><td>呼吸帯域の FFT パワー(X 座標)</td><td>低いほど良い(息止め成功)</td></tr>
  <tr><td class="key">Approach monotonic</td><td>発射前 2 秒の中心への単調収束率</td><td>高いほど良い (狙い直しが少ない)</td></tr>
  <tr><td class="key">Approach oscill /s</td><td>同 1 秒あたりの振動回数</td><td>低いほど良い</td></tr>
  <tr><td class="key">HR at fire</td><td>発射時の心拍数 (bpm)。BLE 心拍受信時のみ</td><td>低いほど落ち着き</td></tr>
  <tr><td class="key">HRV (RMSSD 30s)</td><td>直近 30 秒の心拍変動 (ms)</td><td>高いほど自律神経バランス◯</td></tr>
  <tr><td class="key">Recoil peak amplitude</td><td>発射後の最大変位 (mm)</td><td>低いほど良い</td></tr>
  <tr><td class="key">Recoil settle time</td><td>発射後 5mm 以内に戻る時間 (秒)</td><td>低いほど良い (素早く戻る)</td></tr>
  <tr><td class="key">Follow-through R95</td><td>発射後 0.5 秒の R95 (mm)</td><td>低いほど良い (フォロースルー安定)</td></tr>
  <tr><td class="key">Recoil direction σ</td><td>反動方向のばらつき (度)</td><td>低いほど良い (毎回同方向に反動)</td></tr>
</table>

<h2>グラフ</h2>
<p>Dashboard の下段 4 枠は ComboBox でグラフ種別を選択できる。</p>
<table>
  <tr><th>種別</th><th>意味</th></tr>
  <tr><td>Velocity (time-from-fire)</td><td>速度時系列。x=0 が発射の瞬間。緑=狙い、赤=反動。点線 15mm/s = hold 閾値</td></tr>
  <tr><td>Recent 5 shots R95 bars</td><td>直近 5 発の R95 last 0.5s を棒グラフで比較</td></tr>
  <tr><td>Shot impact scatter</td><td>session 内の発射点散布図。古→新で色変化、中心 = +、95% 円</td></tr>
  <tr><td>Current trace X-Y path</td><td>現在 trace の軌跡。緑=狙い、赤=反動、黄=発射点</td></tr>
  <tr><td>Cant over time (current)</td><td>現在 trace の cant 時系列(度)</td></tr>
  <tr><td>FFT spectrum (pre-trigger)</td><td>発射前期間の周波数スペクトル。橙帯=呼吸、赤帯=振戦</td></tr>
  <tr><td>R95 history per shot</td><td>shot 順での R95 0.5/1/2s 推移</td></tr>
  <tr><td>Cant at fire per shot</td><td>shot 順での発射時 cant 推移(姿勢崩れ検出)</td></tr>
  <tr><td>Trigger timing per shot</td><td>shot 順での撃発タイミング速度(タイミング癖)</td></tr>
  <tr><td>Hold time per shot</td><td>shot 順での hold time 推移</td></tr>
</table>

<h2>その他のタブ</h2>
<table>
  <tr><th>Tab</th><th>内容</th></tr>
  <tr><td>Sessions</td><td>全 session を横断レビュー(集計指標、ベスト/ワースト)。行クリックで該当 session に切替</td></tr>
  <tr><td>Spectrum</td><td>pre-trigger 全期間の FFT スペクトル(X / Y 両軸、振戦・呼吸帯ハイライト)</td></tr>
  <tr><td>Shots</td><td>session 内全 shot を表形式で横断比較。発射点距離 200mm 以上の異常 shot を赤背景で表示、ボタンで一括物理削除可</td></tr>
  <tr><td><b>Recoil</b></td><td><b>反動受け 専用タブ</b>。Peak / Settle time / Follow-through / Direction σ の 4 KPI + 詳細表 + 反動軌跡オーバーレイ / 方向ヒストグラム / 戻り時間推移 / Peak 振幅推移 のグラフ 4 枚</td></tr>
  <tr><td>Drift</td><td>shot 発射点散布図(古→新)+ Cant 推移 + 相関値</td></tr>
  <tr><td>Target</td><td>ISSF 50m ライフルターゲット + 軌跡(本家 SCATT 同等のサブ表示)</td></tr>
</table>

<h2>Recoil タブの読み方</h2>
<table>
  <tr><th>指標</th><th>意味</th><th>狙うべき値</th></tr>
  <tr><td class="key">Peak amplitude</td><td>発射後の最大変位 (mm)</td><td>低いほど抑え込めている</td></tr>
  <tr><td class="key">Settle time</td><td>反動後、発射点から 5mm 以内に戻るまでの時間 (秒)。戻らなければ "—"</td><td>0.3〜0.6 秒程度が典型、低いほど復元が早い</td></tr>
  <tr><td class="key">Follow-through R95</td><td>発射後 0.5 秒のホールド円 (mm)。フォロースルー中の安定度</td><td>低いほどフォロースルーが綺麗</td></tr>
  <tr><td class="key">Direction σ</td><td>発射 50ms 後の動きベクトル方向の標準偏差 (度、円形統計)</td><td>低いほど毎回同方向に反動 = 銃の保持が一貫</td></tr>
  <tr><td class="key">Direction angle</td><td>反動初期の方向 (0°=右、90°=上)</td><td>個人/銃で固有、急変したら持ち方異常</td></tr>
</table>

<h3>4 つのグラフ</h3>
<ul>
  <li><b>Recoil trajectories overlay</b>: 直近 30 shot の発射後軌跡を発射点を原点として重ねる。古→新で色濃く、現在 shot 太線。5mm の "settle 円" 点線つき。<br>
    → <b>銃の保持と反動方向の一貫性が一目で分かる</b></li>
  <li><b>Direction histogram</b>: 反動方向 (50ms 動きベクトル) の度数分布。平均方向と円形 σ も表示</li>
  <li><b>Settle time per shot</b>: shot 順に戻り時間がどう推移するか</li>
  <li><b>Peak amplitude per shot</b>: 反動振幅の推移。疲労や持ち方崩れで増えていないか</li>
</ul>

<h2>誤反応 shot の自動検出と削除</h2>
<p>Shots タブで <b>発射点距離 (= 中心からの mm) </b> が閾値 (デフォルト 200mm) 以上の shot を赤背景表示。
<span class="key">異常 shot を一括削除</span> ボタンで <b>shots 行を物理削除</b>(SCATT 側からも消える)し、孤立した traces 行も削除する。
取り消し不可なので確認ダイアログあり。</p>

<h2>Live モード</h2>
<p>起動時から自動で polling 開始(<span class="key">--no-live</span> で停止可)。
新規 trace に shot が紐付いていれば自動で Dashboard を更新、shot がない (銃口が target を横切っただけ等) trace は無視して<b>前の表示を保持</b>する。</p>

<h2>SCATT 本家との関係</h2>
<p>SCATT Expert が既に提供している以下の指標は本ソフトでは敢えて重複させていない:</p>
<ul>
  <li>10点/10.5点圏内の安定性</li>
  <li>平均標準点の安定性</li>
  <li>1秒/250ms 単位の照準起動速さ</li>
  <li>軌跡の時間グラデーション描画(本家の方が美しい)</li>
  <li>スコア計算 (decimal scoring 等)</li>
</ul>
<p>本ソフトはあくまで補助。SCATT の右隣に並べて使うことを想定している。</p>
"""


class SettingsTab(QWidget):
    """設定タブ。値を SETTINGS に保存、変更通知 signal を発行。"""

    layout_changed = pyqtSignal()
    behavior_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        v = QVBoxLayout(inner)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(18)

        # ========== General ==========
        v.addWidget(self._header("General  動作"))
        form_g = QFormLayout()
        form_g.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.cb_live = QCheckBox()
        self.cb_live.setChecked(SETTINGS.get("behavior/live_on_startup"))
        form_g.addRow("起動時に Live polling を開始", self.cb_live)
        self.sp_polling = QDoubleSpinBox()
        self.sp_polling.setRange(0.05, 5.0)
        self.sp_polling.setSingleStep(0.05)
        self.sp_polling.setDecimals(2)
        self.sp_polling.setValue(SETTINGS.get("behavior/polling_interval_s"))
        self.sp_polling.setSuffix(" s")
        form_g.addRow("Polling 間隔", self.sp_polling)
        self.cb_top = QCheckBox()
        self.cb_top.setChecked(SETTINGS.get("behavior/always_on_top"))
        form_g.addRow("常に最前面 (always on top)", self.cb_top)
        self.cb_caffeine = QCheckBox()
        self.cb_caffeine.setChecked(SETTINGS.get("behavior/caffeinate"))
        form_g.addRow("画面スリープ抑制 (caffeinate)", self.cb_caffeine)
        gw = QWidget(); gw.setLayout(form_g); v.addWidget(gw)

        # ========== Thresholds ==========
        v.addWidget(self._header("Thresholds  閾値"))
        form_t = QFormLayout()
        form_t.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.sp_suspicious = QDoubleSpinBox()
        self.sp_suspicious.setRange(50.0, 1000.0); self.sp_suspicious.setSingleStep(10.0)
        self.sp_suspicious.setValue(SETTINGS.get("thresh/suspicious_radius_mm"))
        self.sp_suspicious.setSuffix(" mm")
        form_t.addRow("誤反応 shot 判定距離", self.sp_suspicious)
        self.sp_hold_v = QDoubleSpinBox()
        self.sp_hold_v.setRange(1.0, 100.0); self.sp_hold_v.setSingleStep(1.0)
        self.sp_hold_v.setValue(SETTINGS.get("thresh/hold_velocity_mm_s"))
        self.sp_hold_v.setSuffix(" mm/s")
        form_t.addRow("Hold time 速度閾値", self.sp_hold_v)
        self.sp_r95_good = QDoubleSpinBox()
        self.sp_r95_good.setRange(0.1, 20.0); self.sp_r95_good.setSingleStep(0.1)
        self.sp_r95_good.setValue(SETTINGS.get("thresh/r95_good_mm"))
        self.sp_r95_good.setSuffix(" mm")
        form_t.addRow("R95 良判定 (≤)", self.sp_r95_good)
        self.sp_r95_bad = QDoubleSpinBox()
        self.sp_r95_bad.setRange(0.1, 30.0); self.sp_r95_bad.setSingleStep(0.1)
        self.sp_r95_bad.setValue(SETTINGS.get("thresh/r95_bad_mm"))
        self.sp_r95_bad.setSuffix(" mm")
        form_t.addRow("R95 要改善判定 (≥)", self.sp_r95_bad)
        self.sp_z_warn = QDoubleSpinBox()
        self.sp_z_warn.setRange(0.5, 5.0); self.sp_z_warn.setSingleStep(0.1)
        self.sp_z_warn.setValue(SETTINGS.get("thresh/z_warn"))
        self.sp_z_warn.setSuffix(" σ")
        form_t.addRow("Z-score 警告閾値 (橙)", self.sp_z_warn)
        self.sp_z_bad = QDoubleSpinBox()
        self.sp_z_bad.setRange(0.5, 5.0); self.sp_z_bad.setSingleStep(0.1)
        self.sp_z_bad.setValue(SETTINGS.get("thresh/z_bad"))
        self.sp_z_bad.setSuffix(" σ")
        form_t.addRow("Z-score 異常閾値 (赤)", self.sp_z_bad)
        tw = QWidget(); tw.setLayout(form_t); v.addWidget(tw)

        # ========== Layout ==========
        v.addWidget(self._header("Layout  ダッシュボード"))
        form_l = QFormLayout()
        form_l.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.sp_rows = QSpinBox(); self.sp_rows.setRange(1, 3)
        self.sp_rows.setValue(SETTINGS.get("layout/dashboard_graph_rows"))
        form_l.addRow("グラフ枠 行数", self.sp_rows)
        self.sp_cols = QSpinBox(); self.sp_cols.setRange(1, 3)
        self.sp_cols.setValue(SETTINGS.get("layout/dashboard_graph_cols"))
        form_l.addRow("グラフ枠 列数", self.sp_cols)
        self.cb_graphs: list[QComboBox] = []
        for i in range(9):
            cb = QComboBox()
            for k, label, _ in GRAPH_KINDS:
                cb.addItem(label, k)
            cur = SETTINGS.get(f"layout/graph_default_{i+1}")
            for j in range(cb.count()):
                if cb.itemData(j) == cur:
                    cb.setCurrentIndex(j); break
            self.cb_graphs.append(cb)
            form_l.addRow(f"枠 #{i+1} 初期グラフ", cb)
        self.cb_show_shotlist = QCheckBox()
        self.cb_show_shotlist.setChecked(SETTINGS.get("layout/show_shot_list"))
        form_l.addRow("左 shot 一覧を表示", self.cb_show_shotlist)
        self.cb_show_hero = QCheckBox()
        self.cb_show_hero.setChecked(SETTINGS.get("layout/show_hero_cards"))
        form_l.addRow("主役カード 2 枚を表示", self.cb_show_hero)
        self.cb_show_metrics = QCheckBox()
        self.cb_show_metrics.setChecked(SETTINGS.get("layout/show_metrics_table"))
        form_l.addRow("指標表を表示", self.cb_show_metrics)
        lw = QWidget(); lw.setLayout(form_l); v.addWidget(lw)

        # ========== Heart Rate ==========
        v.addWidget(self._header("Heart Rate  心拍 (BLE)"))
        form_h = QFormLayout()
        form_h.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.cb_hr_mode = QComboBox()
        self.cb_hr_mode.addItem("Off", "off")
        self.cb_hr_mode.addItem("BLE (Heart Rate Profile)", "ble")
        self.cb_hr_mode.addItem("Mock (擬似データ)", "mock")
        cur_mode = SETTINGS.get("heart/mode")
        for j in range(self.cb_hr_mode.count()):
            if self.cb_hr_mode.itemData(j) == cur_mode:
                self.cb_hr_mode.setCurrentIndex(j); break
        form_h.addRow("ソース", self.cb_hr_mode)
        from PyQt6.QtWidgets import QLineEdit
        self.le_hr_addr = QLineEdit()
        self.le_hr_addr.setPlaceholderText("空欄で自動スキャン")
        self.le_hr_addr.setText(SETTINGS.get("heart/device_address") or "")
        form_h.addRow("BLE デバイス address", self.le_hr_addr)
        self.cb_hr_auto = QCheckBox()
        self.cb_hr_auto.setChecked(SETTINGS.get("heart/auto_start"))
        form_h.addRow("起動時に自動接続", self.cb_hr_auto)
        note = QLabel(
            "<small style='color:#666'>Apple Watch から心拍を Mac に送るには、Watch 側に "
            "<b>HeartCast</b> / <b>BlueHeart</b> 等の BLE Heart Rate Profile "
            "ブロードキャストアプリが必要。胸ベルト (Polar H10 等) は同じインターフェースで動く。</small>"
        )
        note.setWordWrap(True)
        form_h.addRow("", note)
        hw = QWidget(); hw.setLayout(form_h); v.addWidget(hw)

        # ========== Tabs visibility ==========
        v.addWidget(self._header("Tabs  表示するタブ (再起動で反映)"))
        form_tabs = QFormLayout()
        form_tabs.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.cb_tabs: dict[str, QCheckBox] = {}
        for key, label in [("dashboard", "Dashboard"), ("sessions", "Sessions"),
                           ("shots", "Shots"), ("target", "Target"),
                           ("help", "Help")]:
            cb = QCheckBox(); cb.setChecked(SETTINGS.get(f"tabs/{key}"))
            self.cb_tabs[key] = cb
            form_tabs.addRow(label, cb)
        tabw = QWidget(); tabw.setLayout(form_tabs); v.addWidget(tabw)

        # ========== Export ==========
        v.addWidget(self._header("Export  データ出力"))
        export_row = QHBoxLayout()
        self.btn_export_shots_csv = QPushButton("現セッション shots を CSV")
        self.btn_export_shots_csv.clicked.connect(self._on_export_shots_csv)
        export_row.addWidget(self.btn_export_shots_csv)
        self.btn_export_shots_json = QPushButton("現セッション shots を JSON")
        self.btn_export_shots_json.clicked.connect(self._on_export_shots_json)
        export_row.addWidget(self.btn_export_shots_json)
        self.btn_export_all_summary = QPushButton("全 session 集計 CSV")
        self.btn_export_all_summary.clicked.connect(self._on_export_all_summary)
        export_row.addWidget(self.btn_export_all_summary)
        export_row.addStretch()
        v.addLayout(export_row)
        export_note = QLabel(
            "<small style='color:#666'>shots を pandas/Excel/R で解析する用。"
            "JSON 形式は samples (生 trace) を含めずメタ + 集計のみ。</small>"
        )
        export_note.setWordWrap(True)
        v.addWidget(export_note)

        # ========== ボタン ==========
        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("変更を適用")
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_apply)
        self.btn_reset_window = QPushButton("ウィンドウサイズをリセット")
        self.btn_reset_window.clicked.connect(self._on_reset_window)
        btn_row.addWidget(self.btn_reset_window)
        btn_row.addStretch()
        v.addLayout(btn_row)
        v.addStretch()

    def _on_export_shots_csv(self):
        # MainWindow 側でハンドリング
        self.layout_changed.emit  # noqa (signal は別途用意)
        win = self.parent()
        while win is not None and not isinstance(win, QMainWindow):
            win = win.parent()
        if win and hasattr(win, "_export_shots_csv"):
            win._export_shots_csv()

    def _on_export_shots_json(self):
        win = self.parent()
        while win is not None and not isinstance(win, QMainWindow):
            win = win.parent()
        if win and hasattr(win, "_export_shots_json"):
            win._export_shots_json()

    def _on_export_all_summary(self):
        win = self.parent()
        while win is not None and not isinstance(win, QMainWindow):
            win = win.parent()
        if win and hasattr(win, "_export_all_summary"):
            win._export_all_summary()

    def _header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {hex_of(C.FG)}; font-size: 14px; font-weight: 600;"
            f" border-bottom: 1px solid {hex_of(C.BORDER)}; padding: 4px 0; margin-top: 6px;"
        )
        return lbl

    def _on_apply(self):
        # 動作
        SETTINGS.set("behavior/live_on_startup", self.cb_live.isChecked())
        SETTINGS.set("behavior/polling_interval_s", self.sp_polling.value())
        SETTINGS.set("behavior/always_on_top", self.cb_top.isChecked())
        SETTINGS.set("behavior/caffeinate", self.cb_caffeine.isChecked())
        # 閾値
        SETTINGS.set("thresh/suspicious_radius_mm", self.sp_suspicious.value())
        SETTINGS.set("thresh/hold_velocity_mm_s", self.sp_hold_v.value())
        SETTINGS.set("thresh/r95_good_mm", self.sp_r95_good.value())
        SETTINGS.set("thresh/r95_bad_mm", self.sp_r95_bad.value())
        SETTINGS.set("thresh/z_warn", self.sp_z_warn.value())
        SETTINGS.set("thresh/z_bad", self.sp_z_bad.value())
        # レイアウト
        SETTINGS.set("layout/dashboard_graph_rows", self.sp_rows.value())
        SETTINGS.set("layout/dashboard_graph_cols", self.sp_cols.value())
        for i, cb in enumerate(self.cb_graphs):
            SETTINGS.set(f"layout/graph_default_{i+1}", cb.currentData())
        SETTINGS.set("layout/show_shot_list", self.cb_show_shotlist.isChecked())
        SETTINGS.set("layout/show_hero_cards", self.cb_show_hero.isChecked())
        SETTINGS.set("layout/show_metrics_table", self.cb_show_metrics.isChecked())
        for key, cb in self.cb_tabs.items():
            SETTINGS.set(f"tabs/{key}", cb.isChecked())
        # 心拍
        SETTINGS.set("heart/mode", self.cb_hr_mode.currentData())
        SETTINGS.set("heart/device_address", self.le_hr_addr.text().strip())
        SETTINGS.set("heart/auto_start", self.cb_hr_auto.isChecked())
        self.layout_changed.emit()
        self.behavior_changed.emit()
        QMessageBox.information(
            self, "適用しました",
            "設定を保存しました。\nタブの表示/非表示は次回起動時に反映されます。"
        )

    def _on_reset_window(self):
        SETTINGS.reset_window()
        QMessageBox.information(
            self, "リセット予約",
            "次回起動時にウィンドウサイズがデフォルト (1400×900) に戻ります。"
        )


class HelpTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            f"QTextBrowser {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: none; padding: 14px 20px; }}"
        )
        browser.setHtml(HELP_HTML)
        lay.addWidget(browser)


class TargetTab(QGraphicsView):
    """ISSF 50m ライフルターゲット + 軌跡 (発射前/後 色分け) + 発射点マーカー。"""

    OUTER_DIAM_MM = 154.4
    RING_STEP_MM = 16.0
    BLACK_DIAM_MM = 112.4
    INNER_TEN_DIAM_MM = 5.0

    def __init__(self):
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene = QGraphicsScene()
        self.setScene(self._scene)
        self.setBackgroundBrush(QBrush(C.BG))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._draw_target()
        self._dyn = []

    def _draw_target(self):
        r_out = self.OUTER_DIAM_MM / 2.0
        self._scene.addEllipse(-r_out, -r_out, self.OUTER_DIAM_MM, self.OUTER_DIAM_MM,
                               QPen(QColor(80, 80, 80)), QBrush(C.TARGET_WHITE))
        r_black = self.BLACK_DIAM_MM / 2.0
        self._scene.addEllipse(-r_black, -r_black, self.BLACK_DIAM_MM, self.BLACK_DIAM_MM,
                               QPen(QColor(30, 30, 30)), QBrush(C.TARGET_BLACK))
        pen_w = QPen(C.TARGET_LINE_LIGHT); pen_w.setWidthF(0.25)
        pen_b = QPen(C.TARGET_LINE_DARK);  pen_b.setWidthF(0.25)
        for ring in range(1, 11):
            d = self.OUTER_DIAM_MM - (ring - 1) * self.RING_STEP_MM
            r = d / 2.0
            pen = pen_w if d > self.BLACK_DIAM_MM else pen_b
            self._scene.addEllipse(-r, -r, d, d, pen, QBrush(Qt.BrushStyle.NoBrush))
        r_inner = self.INNER_TEN_DIAM_MM / 2.0
        pen_x = QPen(QColor(255, 255, 255)); pen_x.setWidthF(0.25); pen_x.setStyle(Qt.PenStyle.DashLine)
        self._scene.addEllipse(-r_inner, -r_inner, self.INNER_TEN_DIAM_MM, self.INNER_TEN_DIAM_MM,
                               pen_x, QBrush(Qt.BrushStyle.NoBrush))
        font = QFont(); font.setPointSizeF(3.5)
        for ring in range(1, 10):
            d = self.OUTER_DIAM_MM - (ring - 1) * self.RING_STEP_MM
            r = d / 2.0
            tx = self._scene.addText(str(ring), font)
            tx.setDefaultTextColor(QColor(200, 200, 200) if d < self.BLACK_DIAM_MM else QColor(40, 40, 40))
            tx.setPos(-2.0, -r - 4.5)
        cross_pen = QPen(QColor(220, 220, 220)); cross_pen.setWidthF(0.15)
        self._scene.addLine(-2, 0, 2, 0, cross_pen)
        self._scene.addLine(0, -2, 0, 2, cross_pen)

    def _clear_dyn(self):
        for it in self._dyn:
            self._scene.removeItem(it)
        self._dyn = []

    def show_trace(self, samples, shots):
        self._clear_dyn()
        if not samples:
            return
        fire_idx = None
        if shots:
            fire_idx = shots[0]["trace_offset"]
            if not (0 <= fire_idx < len(samples)):
                fire_idx = None
        def mk(seg):
            p = QPainterPath()
            if seg:
                p.moveTo(seg[0][0], seg[0][1])
                for x, y, _ in seg[1:]:
                    p.lineTo(x, y)
            return p
        if fire_idx is None:
            pre, post = list(samples), []
        else:
            pre = list(samples[:fire_idx + 1])
            post = list(samples[fire_idx:])
        if pre:
            pen = QPen(C.ACCENT_G); pen.setWidthF(0.5); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            it = QGraphicsPathItem(mk(pre)); it.setPen(pen)
            self._scene.addItem(it); self._dyn.append(it)
        if post:
            pen = QPen(QColor(C.ACCENT_R.red(), C.ACCENT_R.green(), C.ACCENT_R.blue(), 180))
            pen.setWidthF(0.4); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            it = QGraphicsPathItem(mk(post)); it.setPen(pen)
            self._scene.addItem(it); self._dyn.append(it)
        x_end, y_end, _ = samples[-1]
        self._dyn.append(self._scene.addEllipse(x_end - 0.9, y_end - 0.9, 1.8, 1.8,
                                                QPen(Qt.PenStyle.NoPen), QBrush(C.ACCENT_O)))
        if fire_idx is not None:
            fx, fy, _ = samples[fire_idx]
            yp = QPen(C.ACCENT_Y); yp.setWidthF(0.4)
            self._dyn.append(self._scene.addEllipse(fx - 3, fy - 3, 6, 6, yp, QBrush(Qt.BrushStyle.NoBrush)))
            self._dyn.append(self._scene.addLine(fx - 4.5, fy, fx + 4.5, fy, yp))
            self._dyn.append(self._scene.addLine(fx, fy - 4.5, fx, fy + 4.5, yp))
            self._dyn.append(self._scene.addEllipse(fx - 0.6, fy - 0.6, 1.2, 1.2,
                                                    QPen(Qt.PenStyle.NoPen), QBrush(C.ACCENT_Y)))

    def update_trace(self, samples, shots, sample_rate):
        self.show_trace(samples, shots)

    def resizeEvent(self, e):
        self.fitInView(QRectF(-95, -95, 190, 190), Qt.AspectRatioMode.KeepAspectRatio)
        super().resizeEvent(e)


# ===========================================================================
# Shot List (左ペイン) — shot 単位の一覧、クリックで該当 trace を表示
# ===========================================================================

class ShotListPanel(QListWidget):
    """左ペイン: 過去 shot を新しい順に並べる。
    マウスクリック / 矢印キー (↑↓) 両方で on_select(trace_id) が呼ばれる。
    """

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.on_select = None
        self._suppress = False  # reload 中のシグナル抑制
        self.setStyleSheet(
            f"QListWidget {{ background-color: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER)}; "
            "  font-family: 'SF Mono', Menlo, monospace; font-size: 11px; }"
            "QListWidget::item { padding: 5px 10px; "
            f"  border-bottom: 1px solid {hex_of(C.BORDER)}; }}"
            f"QListWidget::item:selected {{ background-color: {hex_of(C.ACCENT_B)};"
            f"  color: white; }}"
        )
        # currentItemChanged: 矢印キーやマウス選択の両方で発火
        self.currentItemChanged.connect(self._on_current_changed)

    def _on_current_changed(self, current, _previous):
        if self._suppress or current is None or self.on_select is None:
            return
        tid = current.data(Qt.ItemDataRole.UserRole)
        if tid is not None:
            self.on_select(tid)

    def reload(self):
        import datetime
        self._suppress = True
        self.clear()
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            rows = conn.execute(
                "SELECT shot_id, trace_id, timer, match_shot, missed, favorite "
                "FROM shots WHERE deleted = 0 ORDER BY timer DESC LIMIT 300"
            ).fetchall()
            conn.close()
        except Exception as e:
            self.addItem(f"<error: {e}>")
            self._suppress = False
            return
        for sid, tid, ts, match, missed, fav in rows:
            t_str = datetime.datetime.fromtimestamp(ts / 1000).strftime("%m-%d %H:%M")
            tags = []
            if match: tags.append("M")
            if fav: tags.append("★")
            if missed: tags.append("X")
            tag = " ".join(tags) if tags else ""
            label = f"#{sid:>3}  {t_str}  {tag}"
            item = QTableWidgetItem(label) if False else None
            # QListWidget 用に普通の addItem を使う
            self.addItem(label)
            self.item(self.count() - 1).setData(Qt.ItemDataRole.UserRole, tid)
        self._suppress = False

    def prepend_shot(self, shot_id: int, trace_id: int, timer_ms: int,
                     match: bool, missed: bool, favorite: bool):
        import datetime
        t_str = datetime.datetime.fromtimestamp(timer_ms / 1000).strftime("%m-%d %H:%M")
        tags = []
        if match: tags.append("M")
        if favorite: tags.append("★")
        if missed: tags.append("X")
        tag = " ".join(tags) if tags else ""
        self._suppress = True
        self.insertItem(0, f"#{shot_id:>3}  {t_str}  {tag}  *new*")
        self.item(0).setData(Qt.ItemDataRole.UserRole, trace_id)
        self._suppress = False

    def select_trace_id(self, trace_id: int):
        """外部から trace_id 指定で選択状態を移動 (signal は抑制)。"""
        self._suppress = True
        for i in range(self.count()):
            if self.item(i).data(Qt.ItemDataRole.UserRole) == trace_id:
                self.setCurrentRow(i)
                break
        self._suppress = False


# ===========================================================================
# Main Window
# ===========================================================================

class MainWindow(QMainWindow):
    def __init__(self, db_path: str, auto_live: bool = True, initial_trace: int | None = None):
        super().__init__()
        self.db_path = db_path
        self.setWindowTitle(f"SCATT prone analyzer — {os.path.basename(db_path)}")
        # ウィンドウサイズを SETTINGS から復元
        geom = SETTINGS.get("window/geometry")
        if isinstance(geom, QByteArray) and not geom.isEmpty():
            self.restoreGeometry(geom)
        else:
            self.resize(1400, 900)
        self.setStyleSheet(
            f"QMainWindow, QWidget {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)}; }}"
            f"QToolBar {{ background-color: {hex_of(C.PANEL)}; border: none;"
            f"  border-bottom: 1px solid {hex_of(C.BORDER)}; padding: 4px 8px; spacing: 6px; }}"
            f"QPushButton {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER_STRONG)}; padding: 4px 12px;"
            "  border-radius: 3px; }"
            f"QPushButton:hover {{ background-color: {hex_of(C.PANEL_LO)}; }}"
            f"QPushButton:pressed {{ background-color: {hex_of(C.PANEL)}; }}"
            f"QTabWidget::pane {{ border: 1px solid {hex_of(C.BORDER)}; background-color: {hex_of(C.BG)};"
            "  top: -1px; }"
            f"QTabBar::tab {{ background: {hex_of(C.PANEL_LO)}; color: {hex_of(C.FG_MUTED)};"
            f"  padding: 7px 14px; border: 1px solid {hex_of(C.BORDER)}; "
            "  border-bottom: none; font-size: 12px; min-width: 70px; }"
            f"QTabBar::tab:selected {{ background: {hex_of(C.BG)}; color: {hex_of(C.FG)}; }}"
            f"QSplitter::handle {{ background-color: {hex_of(C.BORDER)}; }}"
            f"QStatusBar {{ color: {hex_of(C.FG_MUTED)}; "
            f"  border-top: 1px solid {hex_of(C.BORDER)}; }}"
            f"QLabel {{ color: {hex_of(C.FG)}; }}"
        )

        # トップタブを 6 個に絞る (Spectrum/Recoil/Cant/Drift は Sessions のサブタブへ移行)
        self.dashboard = DashboardTab()
        self.sessions_tab = SessionsTab()
        self.sessions_tab.on_session_selected = self._on_sessions_tab_select
        self.shots_tab = ShotsTab()
        self.shots_tab.on_shot_selected = self._on_shot_selected
        self.shots_tab.on_delete_committed = self._on_delete_committed
        self.target = TargetTab()
        self.help_tab = HelpTab()
        self.settings_tab = SettingsTab()
        self.settings_tab.layout_changed.connect(self._on_layout_changed)
        self.settings_tab.behavior_changed.connect(self._on_behavior_changed)

        # Sessions サブタブのインスタンスを Dashboard 連動用にも参照
        # (Dashboard 表示中の active session も自動で Sessions サブタブを更新したいため)
        self.spectrum = self.sessions_tab.sub_spectrum
        self.recoil_tab = self.sessions_tab.sub_recoil
        self.cant_tab = self.sessions_tab.sub_cant
        self.drift = self.sessions_tab.sub_drift

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setDocumentMode(True)
        # 表示する tab を SETTINGS から (トップタブは 6 個)
        tab_defs = [
            ("dashboard", self.dashboard, "Dashboard"),
            ("sessions", self.sessions_tab, "Sessions"),
            ("shots", self.shots_tab, "Shots"),
            ("target", self.target, "Target"),
            ("help", self.help_tab, "Help"),
        ]
        for key, w, label in tab_defs:
            if SETTINGS.get(f"tabs/{key}"):
                self.tabs.addTab(w, label)
        # Settings タブは常時表示
        self.tabs.addTab(self.settings_tab, "Settings")

        # 左ペイン: shot 一覧 (設定で非表示も可)
        self.shot_list = ShotListPanel(db_path)
        self.shot_list.on_select = self._on_shot_selected

        self.main_splitter = QSplitter()
        if SETTINGS.get("layout/show_shot_list"):
            self.main_splitter.addWidget(self.shot_list)
        self.main_splitter.addWidget(self.tabs)
        # スプリッタ状態の復元 (なければデフォルト)
        splitter_state = SETTINGS.get("window/splitter")
        if isinstance(splitter_state, QByteArray) and not splitter_state.isEmpty():
            self.main_splitter.restoreState(splitter_state)
        else:
            if SETTINGS.get("layout/show_shot_list"):
                self.main_splitter.setSizes([220, 1180])
        self.setCentralWidget(self.main_splitter)

        tb = QToolBar("toolbar")
        self.addToolBar(tb)
        self.start_btn = QPushButton("Live Start")
        self.start_btn.clicked.connect(self._toggle_live)
        tb.addWidget(self.start_btn)
        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self.shot_list.reload)
        tb.addWidget(reload_btn)
        # セッション切替 + Active 表示
        tb.addSeparator()
        sess_lbl = QLabel("Session")
        sess_lbl.setStyleSheet(
            f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; padding: 0 4px;"
        )
        tb.addWidget(sess_lbl)
        self.session_selector = QComboBox()
        self.session_selector.setMinimumWidth(280)
        self.session_selector.setStyleSheet(
            f"QComboBox {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER_STRONG)}; padding: 3px 8px;"
            "   font-family: 'SF Mono', Menlo, monospace; font-size: 11px; }"
            f"QComboBox QAbstractItemView {{ background-color: {hex_of(C.BG)};"
            f"  selection-background-color: {hex_of(C.ACCENT_B)}; }}"
        )
        self.session_selector.currentIndexChanged.connect(self._on_session_selected)
        tb.addWidget(self.session_selector)
        # SCATT が現在 active なセッションを示すドット
        self.active_indicator = QLabel("●")
        self.active_indicator.setToolTip("SCATT が active なセッションを表示中")
        self.active_indicator.setStyleSheet(
            f"color: {hex_of(C.ACCENT_G)}; font-size: 16px; padding: 0 6px;"
        )
        self.active_indicator.setVisible(False)
        tb.addWidget(self.active_indicator)
        # 比較範囲ドロップダウン
        cmp_lbl = QLabel("compare:")
        cmp_lbl.setStyleSheet(f"color: {hex_of(C.FG_MUTED)}; font-size: 11px; padding: 0 4px;")
        tb.addWidget(cmp_lbl)
        self.compare_scope = QComboBox()
        self.compare_scope.addItem("current session", "session")
        self.compare_scope.addItem("same position", "position")
        self.compare_scope.addItem("all shots", "all")
        self.compare_scope.setCurrentIndex(0)
        self.compare_scope.currentIndexChanged.connect(self._on_compare_scope_changed)
        self.compare_scope.setStyleSheet(
            f"QComboBox {{ background-color: {hex_of(C.BG)}; color: {hex_of(C.FG)};"
            f"  border: 1px solid {hex_of(C.BORDER_STRONG)}; padding: 2px 8px; }}"
        )
        tb.addWidget(self.compare_scope)
        # 心拍 ToolBar
        tb.addSeparator()
        self.hr_label = QLabel("HR: —    RMSSD: —")
        self.hr_label.setStyleSheet(
            f"color: {hex_of(C.ACCENT_R)}; font-family: 'SF Mono', monospace;"
            "  font-size: 12px; padding: 0 8px;"
        )
        tb.addWidget(self.hr_label)
        self.hr_btn = QPushButton("HR Start")
        self.hr_btn.clicked.connect(self._toggle_hr)
        tb.addWidget(self.hr_btn)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(f"db: {db_path}")

        self.poller: PollerThread | None = None
        self._session_cache: dict = {}  # (sid, scope) -> list[shot]
        self._current_session_id: int | None = None
        self._scatt_active_session_id: int | None = None
        # 心拍データ保持
        self.hr_history: collections.deque = collections.deque(maxlen=1800)  # 30 分 (1Hz)
        self.rr_history: collections.deque = collections.deque(maxlen=600)
        self._hr_current: int | None = None
        self._rmssd_current: float | None = None
        # 補助 DB (心拍・IMU など) の永続化を初期化 + 既存データ復元
        try:
            ST.ensure_db()
            extras = ST.load_all_extras()
        except Exception as e:
            extras = {}
            print(f"[warn] extra DB load failed: {e}", file=sys.stderr)
        # extras 構造: {shot_id: {"hr": int, "rmssd": float, ...}}
        self._hr_at_shot: dict[int, dict] = dict(extras)
        # 起動時に観測した数を status に表示
        if extras:
            print(f"[info] loaded {len(extras)} shot extras from {ST.DEFAULT_EXTRA_DB}",
                  file=sys.stderr)
        # 心拍ブリッジ
        self.hr_bridge = HeartRateBridge()
        self.hr_bridge.data_received.connect(self._on_hr_data)
        self.hr_bridge.status_changed.connect(self._on_hr_status)
        self.shot_list.reload()
        self.sessions_tab.reload(self.db_path, self._hr_at_shot)

        # 起動順序: 先に最新 shot 付き trace を取得して current_session_id を確定 → そのあと selector を埋める
        # こうしないと最初の表示が active session と一致しないことがある (Reload 必要バグ)
        target_tid = initial_trace
        if target_tid is None:
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
                row = conn.execute(
                    "SELECT trace_id FROM shots WHERE deleted=0 "
                    "ORDER BY timer DESC LIMIT 1"
                ).fetchone()
                conn.close()
                if row:
                    target_tid = row[0]
            except Exception:
                pass
        if target_tid is not None:
            self._replay_trace_id(target_tid)
        # current_session_id 確定後にセッションリストを埋める
        self._reload_session_list()
        if auto_live:
            self._toggle_live()
        # 心拍自動接続
        if SETTINGS.get("heart/auto_start") and SETTINGS.get("heart/mode") != "off":
            self._toggle_hr()

    def _toggle_live(self):
        if self.poller is None:
            interval = SETTINGS.get("behavior/polling_interval_s")
            self.poller = PollerThread(self.db_path, interval=interval)
            self.poller.new_trace.connect(self._on_new_trace)
            self.poller.active_session_changed.connect(self._on_active_session_changed)
            self.poller.start()
            self.start_btn.setText("Live Stop")
            self.status.showMessage("Live polling started")
        else:
            self.poller.stop()
            self.poller.wait(2000)
            self.poller = None
            self.start_btn.setText("Live Start")
            self.status.showMessage("Live polling stopped")

    def _reload_session_list(self):
        """sessions テーブルから全セッションを読み込んで session_selector に反映。"""
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            rows = conn.execute("""
                SELECT s.session_id, s.distance, s.caliber, s.position, s.sample_rate,
                       (SELECT COUNT(*) FROM shots sh
                        JOIN traces t ON t.trace_id = sh.trace_id
                        WHERE t.session_id = s.session_id AND sh.deleted = 0) AS n_shots,
                       (SELECT MAX(timer) FROM traces WHERE session_id = s.session_id) AS last_t
                FROM sessions s
                ORDER BY last_t DESC NULLS LAST
            """).fetchall()
            conn.close()
        except Exception:
            return
        # signal を一時停止
        self.session_selector.blockSignals(True)
        self.session_selector.clear()
        import datetime
        for sid, dist, cal, pos, sr, n_shots, last_t in rows:
            pos_name = POSITION_NAMES.get(pos, f"pos{pos}")
            date_str = ""
            if last_t:
                date_str = datetime.datetime.fromtimestamp(last_t / 1000).strftime("%m-%d")
            label = f"#{sid:>3}  {date_str}  {dist}m {pos_name}  {n_shots} shots"
            self.session_selector.addItem(label, sid)
        # 現在 session を選択
        if self._current_session_id is not None:
            for i in range(self.session_selector.count()):
                if self.session_selector.itemData(i) == self._current_session_id:
                    self.session_selector.setCurrentIndex(i)
                    break
        self.session_selector.blockSignals(False)

    def _on_session_selected(self, _idx: int):
        sid = self.session_selector.currentData()
        if sid is None or sid == self._current_session_id:
            return
        # 該当 session の最新 shot 付き trace、なければ最新 trace を表示
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            row = conn.execute(
                "SELECT trace_id FROM shots WHERE deleted=0 AND trace_id IN "
                "(SELECT trace_id FROM traces WHERE session_id = ?) "
                "ORDER BY timer DESC LIMIT 1", (sid,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT trace_id FROM traces WHERE session_id=? "
                    "ORDER BY trace_id DESC LIMIT 1", (sid,)
                ).fetchone()
            conn.close()
        except Exception:
            row = None
        self._update_session_views(sid)
        if row:
            self._replay_trace_id(row[0])
        # active かどうかインジケータ更新
        self.active_indicator.setVisible(sid == self._scatt_active_session_id)
        self.status.showMessage(f"session: #{sid}")

    def _on_active_session_changed(self, sid: int):
        """SCATT 側の最新 trace が別 session になった(SCATT 内で session 切替検出)"""
        self._scatt_active_session_id = sid
        # session_selector に該当 sid が無ければ reload (新規セッション検出時)
        found = False
        for i in range(self.session_selector.count()):
            if self.session_selector.itemData(i) == sid:
                found = True
                break
        if not found:
            self._reload_session_list()
        # session_selector が古ければ更新
        cur_idx = self.session_selector.currentIndex()
        cur_sid = self.session_selector.itemData(cur_idx) if cur_idx >= 0 else None
        if cur_sid != sid:
            # selector に sid がなければ reload
            found = False
            for i in range(self.session_selector.count()):
                if self.session_selector.itemData(i) == sid:
                    self.session_selector.setCurrentIndex(i)  # → _on_session_selected が動く
                    found = True
                    break
            if not found:
                self._reload_session_list()
                for i in range(self.session_selector.count()):
                    if self.session_selector.itemData(i) == sid:
                        self.session_selector.setCurrentIndex(i)
                        break
        # 既に同じ session を見ているなら、active 表示だけ更新
        self.active_indicator.setVisible(sid == self._current_session_id)

    def _on_compare_scope_changed(self, _idx: int):
        """比較範囲 (current session / same position / all) 変更時、表示を再計算。"""
        sid = self._current_session_id
        if sid is None:
            return
        # cache_key は (sid, scope) tuple なので該当 sid の全エントリを消す
        for k in [k for k in self._session_cache if isinstance(k, tuple) and k[0] == sid]:
            del self._session_cache[k]
        self._update_session_views(sid)
        # 現在表示中の trace を再描画
        # (Dashboard などに新しい比較セットを反映するため)
        if hasattr(self, "_current_trace_dict"):
            self._apply_trace(self._current_trace_dict)

    def _on_layout_changed(self):
        """Settings タブから layout 変更が来たとき"""
        # ダッシュボードのグラフ枠を再構築
        rows = SETTINGS.get("layout/dashboard_graph_rows")
        cols = SETTINGS.get("layout/dashboard_graph_cols")
        self.dashboard.rebuild_graphs(rows, cols)
        # 表示要素の可視性
        self.dashboard.hero_timing[0].setVisible(SETTINGS.get("layout/show_hero_cards"))
        self.dashboard.hero_r95[0].setVisible(SETTINGS.get("layout/show_hero_cards"))
        self.dashboard.metrics_table.setVisible(SETTINGS.get("layout/show_metrics_table"))
        # shot list 表示切替
        show_list = SETTINGS.get("layout/show_shot_list")
        if show_list and self.shot_list.parent() is None:
            self.main_splitter.insertWidget(0, self.shot_list)
        elif not show_list and self.shot_list.parent() is not None:
            self.shot_list.setParent(None)
        # 現在 trace を再描画
        if hasattr(self, "_current_trace_dict"):
            self._apply_trace(self._current_trace_dict)

    def _on_behavior_changed(self):
        """polling interval / always on top / caffeinate の即時反映"""
        if self.poller is not None:
            self.poller.interval = SETTINGS.get("behavior/polling_interval_s")
        on_top = SETTINGS.get("behavior/always_on_top")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        self.show()

    # ----- 心拍 -----

    def _toggle_hr(self):
        if self.hr_bridge.client is None:
            mode = SETTINGS.get("heart/mode")
            if mode == "off":
                mode = "ble"
            addr = SETTINGS.get("heart/device_address") or ""
            self.hr_bridge.start(mode, addr)
            self.hr_btn.setText("HR Stop")
            self.status.showMessage(f"heart rate source: {mode}")
        else:
            self.hr_bridge.stop()
            self.hr_btn.setText("HR Start")
            self._hr_current = None
            self._rmssd_current = None
            self.hr_label.setText("HR: —    RMSSD: —")
            self.status.showMessage("heart rate stopped")

    def _on_hr_data(self, d: dict):
        ts = d.get("timestamp", time.time())
        hr = d.get("hr")
        if hr is not None:
            self._hr_current = hr
            self.hr_history.append((ts, hr))
        for rr in (d.get("rr_intervals_s") or []):
            self.rr_history.append((ts, rr))
        # 直近 30 秒の RR から RMSSD
        cutoff = ts - 30.0
        recent_rr = [r for (t, r) in self.rr_history if t >= cutoff]
        rmssd_val = H.rmssd(recent_rr) if len(recent_rr) >= 2 else None
        self._rmssd_current = rmssd_val
        # ToolBar 更新
        rm_text = f"{rmssd_val:.0f}ms" if rmssd_val is not None else "—"
        self.hr_label.setText(f"HR: {hr if hr is not None else '—'}    RMSSD: {rm_text}")

    def _on_hr_status(self, s: str):
        self.status.showMessage(f"[HR] {s}")

    def _on_new_trace(self, t: dict):
        """新規 trace を受信。

        shot 付き trace のみ表示更新 + shot 一覧に追加。
        shot なし trace (銃口が target を横切っただけ等) は無視し、前の表示を保持。
        """
        shots = t.get("shots") or []
        if not shots:
            self.status.showMessage(
                f"trace #{t['trace_id']} (no shot — keeping previous display)"
            )
            return
        # 心拍の現在値を shot に紐付け + 永続化
        for s in shots:
            if self._hr_current is not None:
                self._hr_at_shot[s["shot_id"]] = {
                    "hr": self._hr_current,
                    "rmssd": self._rmssd_current,
                }
                # 別 DB に永続化 (SCATT 側 DB は触らない)
                try:
                    ST.save_shot_extras(
                        s["shot_id"],
                        hr_at_fire=self._hr_current,
                        rmssd_30s=self._rmssd_current,
                    )
                except Exception as e:
                    print(f"[warn] extra save failed: {e}", file=sys.stderr)
        self._apply_trace(t)
        # shot 一覧の先頭に新しい shot を挿入
        for s in shots:
            self.shot_list.prepend_shot(
                shot_id=s["shot_id"], trace_id=t["trace_id"],
                timer_ms=t["timer_ms"],
                match=bool(s.get("match_shot")),
                missed=bool(s.get("missed")),
                favorite=bool(s.get("favorite")),
            )
        # session shots cache を invalidate して D/E タブを更新
        sid = t["session_id"]
        for k in [k for k in self._session_cache if isinstance(k, tuple) and k[0] == sid]:
            del self._session_cache[k]
        self._update_session_views(sid)
        self.status.showMessage(f"new shot #{shots[0]['shot_id']} (trace #{t['trace_id']})")

    def _on_shot_selected(self, trace_id: int):
        self._replay_trace_id(trace_id)
        self.tabs.setCurrentWidget(self.dashboard)

    def _on_sessions_tab_select(self, sid: int):
        """Sessions タブの行クリック → session_selector を変更 + Dashboard へ。"""
        for i in range(self.session_selector.count()):
            if self.session_selector.itemData(i) == sid:
                self.session_selector.setCurrentIndex(i)
                break
        self.tabs.setCurrentWidget(self.dashboard)

    def _on_delete_committed(self):
        """ShotsTab で削除が確定したあとの後処理: cache クリア + 全タブ更新。

        SCATT 側で消した shot に対応する extra DB の行も削除する。
        """
        sid = self._current_session_id
        self._session_cache.clear()
        # 残存する shot_id 一覧を取得して extra DB の orphan を掃除
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            valid_ids = [r[0] for r in conn.execute(
                "SELECT shot_id FROM shots WHERE deleted = 0"
            ).fetchall()]
            conn.close()
            removed = ST.cleanup_orphans(valid_ids)
            if removed:
                print(f"[info] removed {removed} orphan extras", file=sys.stderr)
                # in-memory cache からも orphan を削除
                for sid_o in list(self._hr_at_shot.keys()):
                    if sid_o not in valid_ids:
                        self._hr_at_shot.pop(sid_o, None)
        except Exception as e:
            print(f"[warn] orphan cleanup failed: {e}", file=sys.stderr)
        self.shot_list.reload()
        self._reload_session_list()
        self.sessions_tab.reload(self.db_path, self._hr_at_shot)
        if sid is not None:
            self._update_session_views(sid)
        self.status.showMessage("shots/traces deleted, session reloaded")

    def _replay_trace_id(self, tid: int):
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            row = conn.execute(
                "SELECT trace_id, session_id, timer, timer_enter, data FROM traces "
                "WHERE trace_id = ?", (tid,),
            ).fetchone()
            if not row:
                conn.close()
                self.status.showMessage(f"trace #{tid} not found")
                return
            tid, sid, ts, te, blob = row
            samples = decode_trace(blob)
            s = conn.execute(
                "SELECT distance, caliber, position, sample_rate FROM sessions "
                "WHERE session_id = ?", (sid,),
            ).fetchone()
            shots = fetch_shots_for_trace(conn, tid)
            conn.close()
        except Exception as e:
            self.status.showMessage(f"replay fail: {e}")
            return
        sess = {"distance": s[0], "caliber": s[1], "position": s[2], "sample_rate": s[3]} if s else {}
        t = {
            "trace_id": tid, "session_id": sid, "timer_ms": ts, "timer_enter_ms": te,
            "samples": samples, "session": sess, "shots": shots,
        }
        self._apply_trace(t)
        self._update_session_views(sid)
        self.status.showMessage(f"trace #{tid}" + (f"  shot #{shots[0]['shot_id']}" if shots else ""))

    def _apply_trace(self, t: dict):
        sr = (t.get("session") or {}).get("sample_rate", 120) or 120
        samples = t["samples"]
        shots = list(t.get("shots") or [])
        sid = t["session_id"]
        self._current_trace_dict = t
        # 現在 shot に観測済み HR/RMSSD を埋め込む
        for s in shots:
            hr_info = self._hr_at_shot.get(s["shot_id"]) or {}
            s["hr_at_fire"] = hr_info.get("hr")
            s["rmssd_30s"] = hr_info.get("rmssd")
        # 比較範囲(設定)を取得
        scope = self.compare_scope.currentData() if hasattr(self, "compare_scope") else "session"
        cache_key = (sid, scope)
        if cache_key not in self._session_cache:
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
                self._session_cache[cache_key] = fetch_session_shots_by_filter(
                    conn, scope, sid
                )
                conn.close()
            except Exception:
                self._session_cache[cache_key] = []
        # 比較対象 shot にも HR を補完(extra DB から復元済み + 起動後追記分)
        for s in self._session_cache[cache_key]:
            hr_info = self._hr_at_shot.get(s["shot_id"]) or {}
            s["hr_at_fire"] = hr_info.get("hr")
            s["rmssd_30s"] = hr_info.get("rmssd")
        cur_shot_id = shots[0]["shot_id"] if shots else None
        compare_set = [s for s in self._session_cache[cache_key]
                       if s["shot_id"] != cur_shot_id]
        self.dashboard.update_trace(samples, shots, sr, session_shots=compare_set)
        self.spectrum.update_trace(samples, shots, sr)
        # Recoil タブはセッション単位 (現セッションの全 shot で集計、現在 shot は graph 用に渡す)
        sess_shots_for_recoil = self._session_cache.get((sid, "session"), [])
        meta = {
            "distance": (t.get("session") or {}).get("distance", "—"),
            "position_name": POSITION_NAMES.get(
                (t.get("session") or {}).get("position"), "—"
            ),
        }
        self.recoil_tab.update_session(
            sid, meta, sess_shots_for_recoil,
            current_samples=samples, current_shots=shots, sample_rate=sr,
        )
        self.cant_tab.update_session(
            sid, meta, sess_shots_for_recoil,
            current_samples=samples, current_shots=shots, sample_rate=sr,
        )
        self.target.update_trace(samples, shots, sr)

    def _update_session_views(self, sid: int):
        if sid is None:
            return
        # 現セッションの shot 一覧は常に "session" スコープで取得 (Shots/Drift タブはこれを使う)
        key = (sid, "session")
        if key not in self._session_cache:
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
                self._session_cache[key] = fetch_session_shots(conn, sid)
                conn.close()
            except Exception as e:
                self.status.showMessage(f"session shots load fail: {e}")
                return
        self._current_session_id = sid
        self.shots_tab.update_session(self._session_cache[key], db_path=self.db_path)
        self.drift.update_session(self._session_cache[key])

    # ----- Export ハンドラ -----

    def _export_shots_csv(self):
        from PyQt6.QtWidgets import QFileDialog
        sid = self._current_session_id
        if sid is None:
            QMessageBox.information(self, "エラー", "セッションが選択されていません。")
            return
        cache_key = (sid, "session")
        shots = self._session_cache.get(cache_key) or []
        if not shots:
            QMessageBox.information(self, "エラー", "現セッションに shot がありません。")
            return
        # HR 補完
        for s in shots:
            hr = self._hr_at_shot.get(s["shot_id"]) or {}
            s.setdefault("hr_at_fire", hr.get("hr"))
            s.setdefault("rmssd_30s", hr.get("rmssd"))
            s.setdefault("session_id", sid)
        path, _ = QFileDialog.getSaveFileName(
            self, "shots CSV を保存", f"scatt_shots_session_{sid}.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            n = EX.export_shots_csv(shots, path)
            self.status.showMessage(f"CSV exported: {n} shots → {path}")
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))

    def _export_shots_json(self):
        from PyQt6.QtWidgets import QFileDialog
        sid = self._current_session_id
        if sid is None:
            return
        cache_key = (sid, "session")
        shots = self._session_cache.get(cache_key) or []
        for s in shots:
            hr = self._hr_at_shot.get(s["shot_id"]) or {}
            s.setdefault("hr_at_fire", hr.get("hr"))
            s.setdefault("rmssd_30s", hr.get("rmssd"))
            s.setdefault("session_id", sid)
        path, _ = QFileDialog.getSaveFileName(
            self, "shots JSON を保存", f"scatt_shots_session_{sid}.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            n = EX.export_shots_json(shots, path)
            self.status.showMessage(f"JSON exported: {n} shots → {path}")
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))

    def _export_all_summary(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "全 session 集計 CSV", "scatt_sessions_summary.csv", "CSV (*.csv)"
        )
        if not path:
            return
        # 全 session の shot を取得
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            sids = [r[0] for r in conn.execute("SELECT session_id FROM sessions").fetchall()]
            sessions_data = []
            for sid in sids:
                meta = fetch_session_meta(conn, sid)
                shots = fetch_session_shots(conn, sid)
                for s in shots:
                    hr = self._hr_at_shot.get(s["shot_id"]) or {}
                    s["hr_at_fire"] = hr.get("hr")
                    s["rmssd_30s"] = hr.get("rmssd")
                sessions_data.append({
                    "session_id": sid, "meta": meta, "shots": shots,
                })
            conn.close()
            n = EX.export_session_summary_csv(sessions_data, path)
            self.status.showMessage(f"session summary exported: {n} sessions → {path}")
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))

    def closeEvent(self, e):
        try:
            SETTINGS.set("window/geometry", self.saveGeometry())
            SETTINGS.set("window/splitter", self.main_splitter.saveState())
        except Exception:
            pass
        if self.poller is not None:
            self.poller.stop()
            self.poller.wait(2000)
        try:
            self.hr_bridge.stop()
        except Exception:
            pass
        super().closeEvent(e)


def _start_caffeinate():
    try:
        p = subprocess.Popen(["/usr/bin/caffeinate", "-d", "-i", "-w", str(os.getpid())])
        atexit.register(lambda: p.terminate())
        return p
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="SCATT prone analyzer (PyQt6)")
    ap.add_argument("--db", default=os.environ.get("SCATT_DB", DEFAULT_DB))
    ap.add_argument("--no-live", action="store_true", help="今回のみ Live を OFF")
    ap.add_argument("--live", action="store_true", help="今回のみ Live を ON")
    ap.add_argument("--trace", type=int, default=None)
    ap.add_argument("--top", action="store_true", help="今回のみ最前面")
    ap.add_argument("--no-top", action="store_true", help="今回のみ最前面 OFF")
    ap.add_argument("--no-caffeinate", action="store_true",
                    help="今回のみスリープ抑制を OFF")
    args = ap.parse_args()
    if not os.path.exists(args.db):
        print(f"error: db not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    # 引数優先 → 未指定なら SETTINGS から
    auto_live = SETTINGS.get("behavior/live_on_startup")
    if args.live: auto_live = True
    if args.no_live: auto_live = False
    on_top = SETTINGS.get("behavior/always_on_top")
    if args.top: on_top = True
    if args.no_top: on_top = False
    caffeinate = SETTINGS.get("behavior/caffeinate") and not args.no_caffeinate

    if caffeinate:
        _start_caffeinate()

    app = QApplication(sys.argv)
    # 白背景に合わせたパレット
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, C.BG)
    pal.setColor(QPalette.ColorRole.Base, C.BG)
    pal.setColor(QPalette.ColorRole.WindowText, C.FG)
    pal.setColor(QPalette.ColorRole.Text, C.FG)
    pal.setColor(QPalette.ColorRole.Button, C.PANEL)
    pal.setColor(QPalette.ColorRole.ButtonText, C.FG)
    app.setPalette(pal)

    w = MainWindow(args.db, auto_live=auto_live, initial_trace=args.trace)
    if on_top:
        w.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

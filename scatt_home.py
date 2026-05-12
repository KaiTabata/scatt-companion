"""起動時ホーム画面 (Welcome ダイアログ)。

射手 (Profile) と 射撃種目 (Discipline) を最初に確定し、
最近のセッション + 週/月ダイジェストを見せて本画面へ。

表示条件 (`home/show_on_startup` = "auto" の場合):
  - 初回起動 (home/seen が False)
  - profile が 2 つ以上
  - "always" の場合は常に表示
  - "never" の場合は出さない

scatt_gui.main() から show_if_needed() を呼ぶ。
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

POSITION_NAMES = {0: "prone", 1: "standing", 2: "kneeling", 3: "other"}


def _ms_to_dt(ms: Optional[int]) -> Optional[datetime.datetime]:
    if not ms:
        return None
    try:
        return datetime.datetime.fromtimestamp(ms / 1000)
    except (OSError, ValueError, TypeError):
        return None


def fetch_recent_sessions(db_path: str, limit: int = 5) -> list[dict]:
    """SCATT storage.dat から最近のセッションを集計。

    各行: {sid, dt, position, n_shots, ten_a_mean (or None), r95_mean}
    """
    out: list[dict] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return out
    try:
        rows = conn.execute("""
            SELECT s.session_id, s.position,
                   (SELECT MAX(timer) FROM traces WHERE session_id = s.session_id) AS last_t,
                   (SELECT COUNT(*) FROM shots WHERE session_id = s.session_id) AS n_shots
            FROM sessions s ORDER BY last_t DESC NULLS LAST LIMIT ?
        """, (limit,)).fetchall()
    except sqlite3.Error:
        conn.close()
        return out
    for sid, pos, last_t, n in rows:
        out.append({
            "sid": sid,
            "dt": _ms_to_dt(last_t),
            "position": POSITION_NAMES.get(pos, f"pos{pos}"),
            "n_shots": n or 0,
        })
    conn.close()
    return out


def fetch_digest(db_path: str) -> dict:
    """今週・今月の集計を返す。

    返り値: {"week": {sessions, shots}, "month": {sessions, shots}}
    SCATT 側に 10a/R95 は集計値として保存されていないので、本数のみ。
    """
    now = datetime.datetime.now()
    week_start = (now - datetime.timedelta(days=7)).timestamp() * 1000
    month_start = (now - datetime.timedelta(days=30)).timestamp() * 1000
    result = {"week": {"sessions": 0, "shots": 0},
              "month": {"sessions": 0, "shots": 0}}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return result
    try:
        rows = conn.execute("""
            SELECT s.session_id,
                   (SELECT MAX(timer) FROM traces WHERE session_id = s.session_id) AS last_t,
                   (SELECT COUNT(*) FROM shots WHERE session_id = s.session_id) AS n
            FROM sessions s
        """).fetchall()
    except sqlite3.Error:
        conn.close()
        return result
    conn.close()
    for sid, last_t, n in rows:
        if last_t is None:
            continue
        if last_t >= week_start:
            result["week"]["sessions"] += 1
            result["week"]["shots"] += n or 0
        if last_t >= month_start:
            result["month"]["sessions"] += 1
            result["month"]["shots"] += n or 0
    return result


def should_show(settings, profiles_mgr) -> bool:
    """auto モードの判定。"""
    mode = settings.get("home/show_on_startup") or "auto"
    if mode == "always":
        return True
    if mode == "never":
        return False
    # auto モード
    if not settings.get("home/seen"):
        return True
    if len(profiles_mgr.list_profiles()) >= 2:
        return True
    return False


class HomeScreen(QDialog):
    """射手・種目を選び、最近のセッション + ダイジェストを見せる。

    accept() 後に self.selected_profile_id / self.selected_discipline_key が決まる。
    self.dont_show_again が True なら呼び出し側で home/show_on_startup="never" に。
    """

    def __init__(self, parent, profiles_mgr, discipline_mod, settings, db_path: str):
        super().__init__(parent)
        self.profiles_mgr = profiles_mgr
        self.T = discipline_mod
        self.settings = settings
        self.db_path = db_path
        self.selected_profile_id = profiles_mgr.current_id()
        self.selected_discipline_key = discipline_mod.current_key()
        self.selected_session_id: Optional[int] = None
        self.dont_show_again = False
        self._recent_rows: list[dict] = []
        self._build()

    # ---- UI ----

    def _build(self):
        self.setWindowTitle("SCATT Prone Analyzer")
        self.setMinimumWidth(640)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)

        # タイトル
        title = QLabel("SCATT Prone Analyzer")
        f = QFont(); f.setPointSize(20); f.setBold(True)
        title.setFont(f)
        v.addWidget(title)
        sub = QLabel("今日の準備 — 射手と種目を選んで始めましょう")
        sub.setStyleSheet("color: #666; font-size: 13px;")
        v.addWidget(sub)
        v.addSpacing(6)

        # 射手 + 種目
        row = QHBoxLayout()
        # 射手
        profile_col = QVBoxLayout()
        plbl = QLabel("射手")
        plbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        profile_col.addWidget(plbl)
        pbox = QHBoxLayout()
        self.profile_combo = QComboBox()
        for p in self.profiles_mgr.list_profiles():
            self.profile_combo.addItem(p.name, p.id)
        idx = self.profile_combo.findData(self.selected_profile_id)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        pbox.addWidget(self.profile_combo, 1)
        new_btn = QPushButton("+ 新規")
        new_btn.clicked.connect(self._on_new_profile)
        pbox.addWidget(new_btn)
        profile_col.addLayout(pbox)
        row.addLayout(profile_col, 1)
        row.addSpacing(20)
        # 種目
        disc_col = QVBoxLayout()
        dlbl = QLabel("射撃種目")
        dlbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        disc_col.addWidget(dlbl)
        self.disc_combo = QComboBox()
        for k, d in self.T.DISCIPLINES.items():
            self.disc_combo.addItem(d.label, k)
        idx = self.disc_combo.findData(self.selected_discipline_key)
        if idx >= 0:
            self.disc_combo.setCurrentIndex(idx)
        disc_col.addWidget(self.disc_combo)
        row.addLayout(disc_col, 1)
        v.addLayout(row)

        # 区切り
        v.addWidget(self._hline())

        # 最近のセッション
        rec_lbl = QLabel("最近のセッション  (ダブルクリックでそのセッションへ)")
        rec_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        v.addWidget(rec_lbl)
        self.recent_table = QTableWidget()
        self.recent_table.doubleClicked.connect(self._on_recent_double_clicked)
        self.recent_table.setColumnCount(3)
        self.recent_table.setHorizontalHeaderLabels(["日時", "姿勢", "shots"])
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.recent_table.setShowGrid(False)
        self.recent_table.setMaximumHeight(150)
        hh = self.recent_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.recent_table)
        self._fill_recent()

        # ダイジェスト
        v.addWidget(self._hline())
        dig_lbl = QLabel("ダイジェスト")
        dig_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        v.addWidget(dig_lbl)
        self.digest_label = QLabel("…")
        self.digest_label.setStyleSheet("color: #444; font-size: 13px;")
        v.addWidget(self.digest_label)
        self._fill_digest()

        v.addSpacing(8)

        # フッタ
        self.cb_dont_show = QCheckBox("次回からこの画面を表示しない")
        v.addWidget(self.cb_dont_show)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        skip_btn = QPushButton("スキップ")
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)
        start_btn = QPushButton("始める")
        f2 = QFont(); f2.setBold(True)
        start_btn.setFont(f2)
        start_btn.setDefault(True)
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(start_btn)
        v.addLayout(btn_row)

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #ddd;")
        return line

    def _fill_recent(self):
        rows = fetch_recent_sessions(self.db_path, limit=5)
        self._recent_rows = rows
        self.recent_table.setRowCount(len(rows) or 1)
        if not rows:
            it = QTableWidgetItem("(セッション履歴なし)")
            it.setForeground(Qt.GlobalColor.gray)
            self.recent_table.setItem(0, 0, it)
            self.recent_table.setSpan(0, 0, 1, 3)
            return
        for r_i, r in enumerate(rows):
            dt_str = r["dt"].strftime("%Y-%m-%d %H:%M") if r["dt"] else "—"
            self.recent_table.setItem(r_i, 0, QTableWidgetItem(dt_str))
            self.recent_table.setItem(r_i, 1, QTableWidgetItem(r["position"]))
            self.recent_table.setItem(r_i, 2, QTableWidgetItem(str(r["n_shots"])))

    def _on_recent_double_clicked(self, index):
        r = index.row()
        if 0 <= r < len(self._recent_rows):
            self.selected_session_id = self._recent_rows[r]["sid"]
            self.selected_profile_id = self.profile_combo.currentData()
            self.selected_discipline_key = self.disc_combo.currentData()
            self.dont_show_again = self.cb_dont_show.isChecked()
            self.accept()

    def _fill_digest(self):
        d = fetch_digest(self.db_path)
        w = d["week"]; m = d["month"]
        self.digest_label.setText(
            f"今週 (過去 7 日): <b>{w['sessions']}</b> セッション, "
            f"<b>{w['shots']}</b> shots &nbsp; / &nbsp; "
            f"今月 (過去 30 日): <b>{m['sessions']}</b> セッション, "
            f"<b>{m['shots']}</b> shots"
        )

    # ---- アクション ----

    def _on_new_profile(self):
        name, ok = QInputDialog.getText(self, "新しい射手", "射手名:")
        if not ok or not name.strip():
            return
        new_p = self.profiles_mgr.add(name.strip())
        self.profile_combo.addItem(new_p.name, new_p.id)
        idx = self.profile_combo.findData(new_p.id)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

    def _on_start(self):
        self.selected_profile_id = self.profile_combo.currentData()
        self.selected_discipline_key = self.disc_combo.currentData()
        self.dont_show_again = self.cb_dont_show.isChecked()
        self.accept()


def show_if_needed(parent, profiles_mgr, discipline_mod, settings, db_path: str) -> Optional[int]:
    """条件を満たすときだけ表示。

    返り値:
      None  → 表示しなかった / スキップされた
      int   → ユーザが選んだ session_id (ジャンプ先)
      0     → 「始める」されたが特定 session の選択なし

    accept された場合は profile・discipline を実際に切替、Settings に反映する。
    """
    if not should_show(settings, profiles_mgr):
        return None
    dlg = HomeScreen(parent, profiles_mgr, discipline_mod, settings, db_path)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    profiles_mgr.set_current(dlg.selected_profile_id)
    if dlg.selected_discipline_key != discipline_mod.current_key():
        settings.set("discipline", dlg.selected_discipline_key)
        discipline_mod.set_current(dlg.selected_discipline_key)
    settings.set("home/seen", True)
    if dlg.dont_show_again:
        settings.set("home/show_on_startup", "never")
    return dlg.selected_session_id if dlg.selected_session_id is not None else 0

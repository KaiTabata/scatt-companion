"""ホーム画面 (Welcome タブ)。

射手 (Profile) と 射撃種目 (Discipline) を確認・切替、
最近のセッション + 週/月ダイジェストを表示する MainWindow 内のタブ。

シグナル:
  start_clicked(profile_id: str, discipline_key: str)
    「始める」ボタンが押されたとき
  session_jump(sid: int)
    「最近のセッション」行をダブルクリックされたとき
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

POSITION_NAMES = {0: "伏射", 1: "立射", 2: "膝射", 3: "他"}


def _ms_to_dt(ms: Optional[int]) -> Optional[datetime.datetime]:
    if not ms:
        return None
    try:
        return datetime.datetime.fromtimestamp(ms / 1000)
    except (OSError, ValueError, TypeError):
        return None


def detect_discipline_label(dist: float | None, cal: float | None,
                              pos: int | None) -> str:
    """SCATT の sessions row から「種目 + 姿勢」ラベルを生成。

    SCATT は position を 0 のままにすることが多い (= 不正確) ので、
    distance と caliber から discipline を推定する。
      - dist ≤ 10.5 & cal ≤ 5.0 → 10m AR
      - dist ≤ 10.5 & cal > 5.0 → 10m AP
      - dist ≥ 25 → 50m/25m など, position 名を併記
    """
    if dist is None:
        return "?"
    if dist <= 10.5 and cal is not None:
        if cal <= 5.0:
            return "10m AR (立射)"
        return "10m AP"
    pos_name = POSITION_NAMES.get(pos, "?")
    return f"{int(dist)}m {pos_name}"


def fetch_recent_sessions(db_path: str, limit: int = 10) -> list[dict]:
    """SCATT storage.dat から最近のセッションを集計。

    persons テーブル JOIN で射手名、distance/caliber から discipline を推定。
    """
    out: list[dict] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return out
    try:
        rows = conn.execute("""
            SELECT s.session_id, s.position, s.distance, s.caliber,
                   p.name,
                   (SELECT MAX(timer) FROM traces WHERE session_id = s.session_id) AS last_t,
                   (SELECT COUNT(*) FROM shots WHERE session_id = s.session_id) AS n_shots
            FROM sessions s
            LEFT JOIN persons p ON p.person_id = s.person_id
            ORDER BY last_t DESC NULLS LAST LIMIT ?
        """, (limit,)).fetchall()
    except sqlite3.Error:
        conn.close()
        return out
    for sid, pos, dist, cal, name, last_t, n in rows:
        out.append({
            "sid": sid,
            "dt": _ms_to_dt(last_t),
            "position": detect_discipline_label(dist, cal, pos),
            "shooter": name or "—",
            "n_shots": n or 0,
        })
    conn.close()
    return out


def fetch_digest(db_path: str) -> dict:
    """今週・今月の集計を返す。"""
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


def should_auto_focus(settings, profiles_mgr) -> bool:
    """起動時にホームタブをフォーカスするかの判定 (auto モード)。"""
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


class HomeTab(QWidget):
    """ホーム画面 (タブとして MainWindow に埋め込み)。

    Dialog ではなく通常のタブ。MainWindow が tabs.addTab(HomeTab(...), "ホーム")
    する。「始める」で start_clicked、行ダブルクリックで session_jump。
    """

    start_clicked = pyqtSignal(str, str, str)  # (profile_id, discipline_key, mode_key)
    session_jump = pyqtSignal(int)
    mode_changed = pyqtSignal(str)  # mode_key

    def __init__(self, profiles_mgr, discipline_mod, settings, db_path: str,
                 modes_mod=None, parent=None):
        super().__init__(parent)
        self.profiles_mgr = profiles_mgr
        self.T = discipline_mod
        self.M = modes_mod  # scatt_modes (省略可: 未提供なら mode UI を出さない)
        self.settings = settings
        self.db_path = db_path
        self._recent_rows: list[dict] = []
        self._build()

    # ---- UI ----

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 32, 40, 28)
        outer.setSpacing(16)

        # タイトル
        title = QLabel("SCATT Companion")
        f = QFont(); f.setPointSize(22); f.setBold(True)
        title.setFont(f)
        outer.addWidget(title)
        sub = QLabel("今日の準備 — 射手と種目を選んで始めましょう")
        sub.setStyleSheet("color: #666; font-size: 13px;")
        outer.addWidget(sub)
        outer.addSpacing(8)

        # 射手 + 種目 + モード を 3 列で並べる
        row = QHBoxLayout()
        row.setSpacing(24)
        # 射手
        profile_col = QVBoxLayout()
        plbl = QLabel("射手")
        plbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        profile_col.addWidget(plbl)
        pbox = QHBoxLayout()
        self.profile_combo = QComboBox()
        self._fill_profile_combo()
        pbox.addWidget(self.profile_combo, 1)
        new_btn = QPushButton("+ 新規")
        new_btn.clicked.connect(self._on_new_profile)
        pbox.addWidget(new_btn)
        profile_col.addLayout(pbox)
        row.addLayout(profile_col, 1)
        # 射撃種目
        disc_col = QVBoxLayout()
        dlbl = QLabel("射撃種目")
        dlbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        disc_col.addWidget(dlbl)
        self.disc_combo = QComboBox()
        for k, d in self.T.DISCIPLINES.items():
            self.disc_combo.addItem(d.label, k)
        idx = self.disc_combo.findData(self.T.current_key())
        if idx >= 0:
            self.disc_combo.setCurrentIndex(idx)
        disc_col.addWidget(self.disc_combo)
        row.addLayout(disc_col, 1)
        # モード
        if self.M is not None:
            mode_col = QVBoxLayout()
            mlbl = QLabel("モード")
            mlbl.setStyleSheet("font-weight: bold; font-size: 12px;")
            mode_col.addWidget(mlbl)
            self.mode_combo = QComboBox()
            for k, m in self.M.MODES.items():
                self.mode_combo.addItem(m.label, k)
            cur_mode = self.settings.get("mode") or "prone"
            idx = self.mode_combo.findData(cur_mode)
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            mode_col.addWidget(self.mode_combo)
            self.mode_desc = QLabel("")
            self.mode_desc.setStyleSheet("color: #777; font-size: 11px;")
            self.mode_desc.setWordWrap(True)
            mode_col.addWidget(self.mode_desc)
            row.addLayout(mode_col, 1)
            self._update_mode_desc()
        else:
            self.mode_combo = None
            self.mode_desc = None
        outer.addLayout(row)

        outer.addWidget(self._hline())

        # 最近のセッション
        rec_lbl = QLabel("最近のセッション  (ダブルクリックでそのセッションへ)")
        rec_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        outer.addWidget(rec_lbl)
        self.recent_table = QTableWidget()
        self.recent_table.doubleClicked.connect(self._on_recent_double_clicked)
        self.recent_table.setColumnCount(4)
        self.recent_table.setHorizontalHeaderLabels(["日時", "射手", "種目/姿勢", "shots"])
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.recent_table.setShowGrid(False)
        hh = self.recent_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self.recent_table, stretch=1)
        self._fill_recent()

        outer.addWidget(self._hline())

        # ダイジェスト
        dig_lbl = QLabel("ダイジェスト")
        dig_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        outer.addWidget(dig_lbl)
        self.digest_label = QLabel("…")
        self.digest_label.setStyleSheet("color: #444; font-size: 14px; padding: 4px 0;")
        self.digest_label.setWordWrap(True)
        outer.addWidget(self.digest_label)
        self._fill_digest()

        outer.addSpacing(12)

        # フッタ
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("更新")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        start_btn = QPushButton("始める →")
        f2 = QFont(); f2.setBold(True); f2.setPointSize(14)
        start_btn.setFont(f2)
        start_btn.setMinimumHeight(40)
        start_btn.setMinimumWidth(160)
        start_btn.setDefault(True)
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(start_btn)
        outer.addLayout(btn_row)

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #ddd;")
        return line

    def _fill_profile_combo(self):
        cur_id = self.profiles_mgr.current_id()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in self.profiles_mgr.list_profiles():
            self.profile_combo.addItem(p.name, p.id)
        idx = self.profile_combo.findData(cur_id)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)

    def _fill_recent(self):
        rows = fetch_recent_sessions(self.db_path, limit=10)
        self._recent_rows = rows
        self.recent_table.setRowCount(len(rows) or 1)
        if not rows:
            it = QTableWidgetItem("(セッション履歴なし)")
            it.setForeground(Qt.GlobalColor.gray)
            self.recent_table.setItem(0, 0, it)
            self.recent_table.setSpan(0, 0, 1, 4)
            return
        for r_i, r in enumerate(rows):
            dt_str = r["dt"].strftime("%Y-%m-%d %H:%M") if r["dt"] else "—"
            self.recent_table.setItem(r_i, 0, QTableWidgetItem(dt_str))
            self.recent_table.setItem(r_i, 1, QTableWidgetItem(r.get("shooter", "—")))
            self.recent_table.setItem(r_i, 2, QTableWidgetItem(r["position"]))
            self.recent_table.setItem(r_i, 3, QTableWidgetItem(str(r["n_shots"])))

    def _fill_digest(self):
        d = fetch_digest(self.db_path)
        w = d["week"]; m = d["month"]
        self.digest_label.setText(
            f"今週 (過去 7 日): <b>{w['sessions']}</b> セッション, "
            f"<b>{w['shots']}</b> shots &nbsp; / &nbsp; "
            f"今月 (過去 30 日): <b>{m['sessions']}</b> セッション, "
            f"<b>{m['shots']}</b> shots"
        )

    # ---- 公開 API ----

    def refresh(self):
        """外部から呼ばれて UI を再描画 (profile 追加後等)。"""
        self._fill_profile_combo()
        self._fill_recent()
        self._fill_digest()

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

    def _on_recent_double_clicked(self, index):
        r = index.row()
        if 0 <= r < len(self._recent_rows):
            sid = self._recent_rows[r]["sid"]
            self._apply_selection()
            self.session_jump.emit(sid)

    def _on_start(self):
        self._apply_selection()
        prof_id = self.profile_combo.currentData() or self.profiles_mgr.current_id()
        disc_key = self.disc_combo.currentData() or self.T.current_key()
        mode_key = (self.mode_combo.currentData() if self.mode_combo
                    else (self.settings.get("mode") or "prone"))
        self.start_clicked.emit(prof_id, disc_key, mode_key)

    def _on_mode_changed(self, _idx):
        if self.M is None or self.mode_combo is None:
            return
        new_mode = self.mode_combo.currentData()
        if not new_mode:
            return
        # モード切替: 推奨 discipline も自動で追従
        m = self.M.MODES.get(new_mode)
        if m:
            i = self.disc_combo.findData(m.suggested_discipline)
            if i >= 0:
                self.disc_combo.setCurrentIndex(i)
        self._update_mode_desc()
        self.mode_changed.emit(new_mode)

    def _update_mode_desc(self):
        if self.M is None or self.mode_combo is None or self.mode_desc is None:
            return
        key = self.mode_combo.currentData()
        m = self.M.MODES.get(key)
        if m:
            self.mode_desc.setText(m.description)

    def _apply_selection(self):
        """profile / discipline / mode の選択を実反映。"""
        pid = self.profile_combo.currentData()
        if pid and pid != self.profiles_mgr.current_id():
            self.profiles_mgr.set_current(pid)
        dk = self.disc_combo.currentData()
        if dk and dk != self.T.current_key():
            self.settings.set("discipline", dk)
            self.T.set_current(dk)
        if self.M is not None and self.mode_combo is not None:
            mk = self.mode_combo.currentData()
            if mk and mk != (self.settings.get("mode") or "prone"):
                # mode 切替: settings に layout プリセットを書き込み
                self.M.apply_to_settings(mk, self.settings)
        self.settings.set("home/seen", True)

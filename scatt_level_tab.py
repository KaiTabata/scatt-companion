"""水準器 (Level) タブ — カント角を計器的に可視化。

人工水平 (attitude indicator) 風: 円形の枠の中で「水平線」が傾く。
数字は下に小さく。トレンドグラフ・統計・直近 shot は控えめに残す。
横方向のリサイズに耐える (画面 1/4 幅でも崩れない)。

公開 API:
  update_trace(samples, shots, sample_rate, session_label=None)
    poller の new_trace を受けるたびに呼ぶ
  set_current_shot(cant_deg, shot_label)
    直近 shot の発射時カント (degrees) と表示ラベルをセット
"""

from __future__ import annotations

import math
import time
from collections import deque

import numpy as np
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)
import pyqtgraph as pg


# ---- 色 (scatt_gui.C と整合) ----
_GREEN  = QColor(40, 130, 70)
_YELLOW = QColor(190, 145, 25)
_RED    = QColor(180, 50, 50)
_GRAY   = QColor(110, 110, 118)
_BG     = QColor(255, 255, 255)
_PANEL  = QColor(250, 250, 251)
_BORDER = QColor(180, 180, 185)
_FG     = QColor(30, 30, 34)


def _classify(abs_deg: float, green_thr: float, yellow_thr: float) -> QColor:
    if abs_deg <= green_thr:
        return _GREEN
    if abs_deg <= yellow_thr:
        return _YELLOW
    return _RED


def _has_cant_data(samples) -> bool:
    """samples の cant (z) が記録されているか。旧 SCATT 形式は全 0。"""
    if not samples:
        return False
    n = min(len(samples), 64)
    return any(abs(samples[i][2]) > 1e-9 for i in range(n))


# ===========================================================================
# 人工水平 (Attitude Indicator) - カスタム QWidget
# ===========================================================================

class AttitudeIndicator(QWidget):
    """人工水平風カント表示。

    円形の枠内で「水平線」が cant 角に応じて傾く。中央には固定マーカー。
    閾値色で水平線を着色。横幅・高さに応じてサイズが自動追従。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value: float | None = None
        self._green = 1.0
        self._yellow = 3.0
        self.setMinimumHeight(60)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_value(self, deg: float | None):
        self._value = deg
        self.update()

    def set_thresholds(self, green: float, yellow: float):
        self._green = green
        self._yellow = yellow
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()
        # 中心と半径 (枠は正方形)
        cx = w / 2.0
        cy = h / 2.0
        r = min(w, h) / 2.0 - 6
        if r <= 8:
            p.end()
            return

        # クリップ円(内側に水平線・地面を収める)
        p.save()
        path_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        clip_path = pg.QtGui.QPainterPath()
        clip_path.addEllipse(path_rect)
        p.setClipPath(clip_path)

        # 水平線の傾き — cant 角だけ計器を逆方向に回す
        value = self._value if (self._value is not None and math.isfinite(self._value)) else 0.0
        p.translate(cx, cy)
        p.rotate(-value)  # 正のカント = 計器面では右下がり (機体は右に傾く)

        # 空・地 (淡色の背景)
        sky_rect = QRectF(-r * 1.5, -r * 1.5, r * 3, r * 1.5)
        ground_rect = QRectF(-r * 1.5, 0, r * 3, r * 1.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(232, 240, 248)))  # ごく薄い空
        p.drawRect(sky_rect)
        p.setBrush(QBrush(QColor(238, 230, 220)))  # ごく薄い大地
        p.drawRect(ground_rect)

        # 水平線 (閾値色)
        line_color = _classify(abs(value), self._green, self._yellow)
        pen = QPen(line_color, 2.2)
        p.setPen(pen)
        p.drawLine(QPointF(-r, 0), QPointF(r, 0))

        # 補助目盛り (-10, -5, +5, +10 度方向の短い線)
        p.setPen(QPen(_GRAY, 1))
        for dy_frac in (-0.5, -0.25, 0.25, 0.5):
            y = r * dy_frac
            length = r * (0.25 if abs(dy_frac) == 0.5 else 0.15)
            p.drawLine(QPointF(-length, y), QPointF(length, y))

        p.restore()

        # 外円 (ベゼル)
        p.setPen(QPen(_BORDER, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(path_rect)

        # 中央固定マーカー (機体マーク風: 短い水平線 + 中央ドット)
        p.setPen(QPen(_FG, 2.0))
        marker_w = r * 0.35
        p.drawLine(QPointF(cx - marker_w, cy), QPointF(cx - r * 0.08, cy))
        p.drawLine(QPointF(cx + r * 0.08, cy), QPointF(cx + marker_w, cy))
        p.setBrush(QBrush(_FG))
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

        # ベゼル外側に閾値マーク (12 時を 0° として、±yellow を黄ティック)
        p.setPen(QPen(_YELLOW.darker(120), 2))
        for sign in (-1, 1):
            ang = math.radians(90 - sign * self._yellow)  # 12 時 = 90°
            x1 = cx + (r + 1) * math.cos(ang)
            y1 = cy - (r + 1) * math.sin(ang)
            x2 = cx + (r + 5) * math.cos(ang)
            y2 = cy - (r + 5) * math.sin(ang)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        # 0° (上) のマーク
        p.setPen(QPen(_FG, 1.2))
        p.drawLine(QPointF(cx, cy - r - 1), QPointF(cx, cy - r - 6))

        p.end()


# ===========================================================================
# Level タブ本体
# ===========================================================================

class LevelTab(QWidget):
    """水準器タブ。

    settings から閾値・トレンド秒数を取得。SETTINGS 互換 (get/set) のオブジェクトを
    コンストラクタで受け取る。
    """

    # 接続が「停止中」と判定する無更新秒数
    _STOPPED_AFTER_S = 3.0

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        # ring buffer: (monotonic_time_s, cant_deg)
        self._buf: deque[tuple[float, float]] = deque()
        self._last_update_t: float | None = None
        # shot 統計: degrees の list (現セッション内 shot 発射カント)
        self._shot_cants: list[float] = []
        self._current_session_id: int | None = None
        self._current_shot_label: str = "—"
        self._current_shot_cant: float | None = None
        self._has_data = False  # 現 trace に cant 記録あり

        self._build()
        self._reload_settings()
        self._apply_responsive_layout()

        # 接続状態と表示の定期更新 (250ms)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(250)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    # ---- UI ----

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(10)

        # ヘッダ: 接続インジケータ + セッションラベル
        head = QHBoxLayout()
        head.setSpacing(6)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #aaa; font-size: 14px;")
        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        self.status_label.setMinimumWidth(0)
        head.addWidget(self.status_dot)
        head.addWidget(self.status_label)
        head.addStretch()
        self.session_label = QLabel("")
        self.session_label.setStyleSheet("color: #777; font-size: 12px;")
        self.session_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # 横幅に応じて省略表示するため raw 文字列を保持
        self._session_text_raw = ""
        head.addWidget(self.session_label, stretch=1)
        outer.addLayout(head)

        # 人工水平 (Attitude Indicator) — メインビジュアル
        self.bar = AttitudeIndicator()
        outer.addWidget(self.bar, stretch=4)

        # 数字 (控えめサイズ、計器の下にキャプション的に)
        self.big_label = QLabel("—")
        self._big_font = QFont()
        self._big_font.setFamilies(["SF Pro Display", "Helvetica Neue", "Arial"])
        self._big_font.setPointSize(18)
        self.big_label.setFont(self._big_font)
        self.big_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.big_label.setStyleSheet("color: #888;")
        self.big_label.setMinimumWidth(40)
        outer.addWidget(self.big_label)

        # 直近 shot
        self.shot_label = QLabel("直近 shot: —")
        f2 = QFont(); f2.setPointSize(13)
        self.shot_label.setFont(f2)
        self.shot_label.setStyleSheet("color: #555; padding: 6px 0;")
        self.shot_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.shot_label.setWordWrap(True)
        self.shot_label.setMinimumWidth(60)
        outer.addWidget(self.shot_label)

        # トレンドグラフ
        self.trend = pg.PlotWidget()
        self.trend.setBackground('w')
        self.trend.showGrid(x=False, y=True, alpha=0.2)
        self.trend.setLabel('left', "カント", units="°")
        self.trend.setLabel('bottom', "経過 (秒前)")
        self.trend.getAxis('bottom').setTextPen(pg.mkPen('#444'))
        self.trend.getAxis('left').setTextPen(pg.mkPen('#444'))
        self.trend.setMouseEnabled(x=False, y=False)
        self.trend.hideButtons()
        self.trend.setMinimumHeight(50)
        self.trend.setMinimumWidth(50)
        self._trend_curve = self.trend.plot([], [], pen=pg.mkPen('#3870b8', width=2))
        # 0 ライン + 閾値ライン
        self._trend_zero = self.trend.addLine(y=0, pen=pg.mkPen('#999', width=0.8, style=Qt.PenStyle.DashLine))
        self._trend_green_lo = self.trend.addLine(y=0, pen=pg.mkPen(_GREEN, width=0.6, style=Qt.PenStyle.DotLine))
        self._trend_green_hi = self.trend.addLine(y=0, pen=pg.mkPen(_GREEN, width=0.6, style=Qt.PenStyle.DotLine))
        self._trend_yellow_lo = self.trend.addLine(y=0, pen=pg.mkPen(_YELLOW, width=0.6, style=Qt.PenStyle.DotLine))
        self._trend_yellow_hi = self.trend.addLine(y=0, pen=pg.mkPen(_YELLOW, width=0.6, style=Qt.PenStyle.DotLine))
        outer.addWidget(self.trend, stretch=3)

        # 統計
        self.stats_label = QLabel("ライブ SD: —   |   shot 平均: —")
        self.stats_label.setStyleSheet("color: #444; font-size: 13px; padding-top: 4px;")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.stats_label.setWordWrap(True)
        self.stats_label.setMinimumWidth(60)
        outer.addWidget(self.stats_label)

    # ---- settings 連動 ----

    def _reload_settings(self):
        """閾値・トレンド秒数を settings から取り直し、UI に反映。"""
        self._green_thr = float(self._settings.get("level/threshold_green") or 1.0)
        self._yellow_thr = float(self._settings.get("level/threshold_yellow") or 3.0)
        self._window_s = float(self._settings.get("level/trend_seconds") or 30.0)
        self.bar.set_thresholds(self._green_thr, self._yellow_thr)
        self._trend_green_lo.setValue(-self._green_thr)
        self._trend_green_hi.setValue(self._green_thr)
        self._trend_yellow_lo.setValue(-self._yellow_thr)
        self._trend_yellow_hi.setValue(self._yellow_thr)
        self.trend.setXRange(-self._window_s, 0, padding=0.02)
        self._refresh_display()

    def settings_changed(self):
        """外部 (Settings タブ Apply) から呼ぶフック。"""
        self._reload_settings()

    # ---- 公開 API ----

    def update_trace(self, samples, shots, sample_rate, session_label=None,
                     session_id=None):
        """新規 trace 受信時に呼ぶ。

        - 最新サンプルの z を「ライブカント」として更新
        - 全 z サンプルをトレンドバッファに追加 (サンプル数で時刻を内挿)
        - shot が含まれていれば最新 shot のカントを更新 + shot 統計に追加
        """
        if not samples:
            return
        # session 切替で shot 統計をリセット
        if session_id is not None and session_id != self._current_session_id:
            self._current_session_id = session_id
            self._shot_cants = []
            if session_label is None:
                session_label = f"session #{session_id}"

        if session_label is not None:
            self._session_text_raw = session_label
            self._refresh_session_label()

        self._has_data = _has_cant_data(samples)
        if not self._has_data:
            # cant 記録なし trace は表示更新しない (旧形式 / カント未取得機種)
            self._last_update_t = time.monotonic()
            return

        # トレンドバッファに追加。trace は連続サンプル列なので、末尾サンプル時刻を now、
        # それ以前を (N - i) / sr 秒前として配置する。
        now = time.monotonic()
        sr = float(sample_rate) if sample_rate else 120.0
        n = len(samples)
        # 重い処理を避けるため stride
        stride = max(1, n // 240)  # 1 trace 最大 240 点
        for i in range(0, n, stride):
            t = now - (n - 1 - i) / sr
            cant_deg = math.degrees(samples[i][2])
            self._buf.append((t, cant_deg))

        # 古いサンプルを破棄
        cutoff = now - max(self._window_s, 60.0)
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()

        self._last_update_t = now

        # shot が含まれていれば直近 shot のカントを更新
        if shots:
            for sh in shots:
                tro = sh.get("trace_offset")
                if tro is not None and 0 <= tro < n:
                    cant_deg = math.degrees(samples[tro][2])
                    self._shot_cants.append(cant_deg)
                    self._current_shot_cant = cant_deg
                    sid = sh.get("shot_id")
                    self._current_shot_label = f"shot #{sid}" if sid else "shot"

        self._refresh_display()

    def set_current_shot(self, cant_deg: float | None, shot_label: str):
        """shot 選択 UI からの呼び出し用 (Dashboard の shot 切替に追従)。"""
        if cant_deg is not None and math.isfinite(cant_deg):
            self._current_shot_cant = cant_deg
            self._current_shot_label = shot_label
            self._refresh_display()

    # ---- 内部 ----

    # ---- リサイズ対応 ----

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        """幅・高さに応じて要素サイズ・可視性を調整。

        計器 (AttitudeIndicator) を主役に、数字・他要素は控えめ。
        画面 1/4 幅でも崩れない設計。
        """
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        # 数字フォント: 幅で軽くスケール (14〜26pt 程度に抑える)
        pt = 14 if w < 200 else (16 if w < 320 else (18 if w < 480 else 22))
        if self._big_font.pointSize() != pt:
            self._big_font.setPointSize(pt)
            self.big_label.setFont(self._big_font)

        # トレンドグラフ: 高さが狭い時は隠す
        self.trend.setVisible(h >= 320)

        # 統計: 横幅で 1 行/2 行を切替
        prev_inline = getattr(self, "_stats_inline", True)
        self._stats_inline = (w >= 420)
        if prev_inline != self._stats_inline:
            self._refresh_stats_label()

        # ヘッダ session ラベルの省略を更新
        self._refresh_session_label()

    def _tick(self):
        """接続インジケータの更新 + 旧サンプル破棄 (ライブ表示が止まっても進む)。"""
        now = time.monotonic()
        # 旧サンプル破棄
        cutoff = now - max(self._window_s, 60.0)
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()

        if self._last_update_t is None:
            self.status_dot.setStyleSheet("color: #aaa; font-size: 14px;")
            self.status_label.setText("待機中 (Live 開始してください)")
        else:
            since = now - self._last_update_t
            if since < self._STOPPED_AFTER_S:
                self.status_dot.setStyleSheet(
                    f"color: {_GREEN.name()}; font-size: 14px;"
                )
                self.status_label.setText("Live")
            else:
                self.status_dot.setStyleSheet(
                    f"color: {_YELLOW.name()}; font-size: 14px;"
                )
                self.status_label.setText(f"停止中 ({int(since)} 秒前)")
        # トレンド曲線とライブ統計を再描画 (時間軸が進むため)
        self._refresh_trend_curve()
        self._refresh_stats_label()

    def _refresh_display(self):
        """巨大数字 + バー + shot ラベルを更新 (trace 受信時に呼ぶ)。"""
        if not self._has_data:
            self.big_label.setText("(カント記録なし)")
            self.big_label.setStyleSheet("color: #aaa;")
            self.bar.set_value(None)
        elif self._buf:
            last_deg = self._buf[-1][1]
            color = _classify(abs(last_deg), self._green_thr, self._yellow_thr)
            self.big_label.setText(f"{last_deg:+.2f}°")
            self.big_label.setStyleSheet(f"color: {color.name()};")
            self.bar.set_value(last_deg)
        else:
            self.big_label.setText("—")
            self.big_label.setStyleSheet("color: #aaa;")
            self.bar.set_value(None)

        if self._current_shot_cant is None:
            self.shot_label.setText("直近 shot: —")
        else:
            color = _classify(
                abs(self._current_shot_cant), self._green_thr, self._yellow_thr
            )
            self.shot_label.setText(
                f"<span style='color:{_GRAY.name()}'>直近 shot:</span> "
                f"<span style='color:{color.name()}; font-weight:600'>"
                f"{self._current_shot_cant:+.2f}°</span> "
                f"<span style='color:{_GRAY.name()}; font-size:11px'>"
                f"({self._current_shot_label})</span>"
            )
            self.shot_label.setTextFormat(Qt.TextFormat.RichText)

        self._refresh_trend_curve()
        self._refresh_stats_label()

    def _refresh_trend_curve(self):
        if not self._buf:
            self._trend_curve.setData([], [])
            return
        now = time.monotonic()
        # window 内のみ抽出
        xs = []
        ys = []
        for t, v in self._buf:
            dt = t - now  # 負値 (秒前)
            if dt < -self._window_s:
                continue
            xs.append(dt)
            ys.append(v)
        self._trend_curve.setData(xs, ys)

    def _refresh_session_label(self):
        """セッションラベルを利用可能幅で elide (省略)。"""
        text = self._session_text_raw or ""
        w = max(40, self.session_label.width())
        fm = QFontMetrics(self.session_label.font())
        self.session_label.setText(fm.elidedText(text, Qt.TextElideMode.ElideMiddle, w))
        self.session_label.setToolTip(text if text else "")

    def _refresh_stats_label(self):
        # ライブ SD: window 内
        live_sd_str = "—"
        if len(self._buf) >= 8:
            arr = np.array([v for _, v in self._buf])
            live_sd_str = f"{arr.std():.2f}°"
        # shot 平均 ± SD
        shot_str = "—"
        if self._shot_cants:
            arr = np.array(self._shot_cants)
            if len(arr) == 1:
                shot_str = f"{arr.mean():+.2f}° (1 shot)"
            else:
                shot_str = f"{arr.mean():+.2f}° ±{arr.std():.2f}° ({len(arr)} shots)"
        # 狭ければ 2 行、広ければ 1 行
        sep = " &nbsp;|&nbsp; " if getattr(self, "_stats_inline", True) else "<br>"
        self.stats_label.setText(
            f"ライブ SD: <b>{live_sd_str}</b>"
            f"{sep}"
            f"shot 平均: <b>{shot_str}</b>"
        )
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)

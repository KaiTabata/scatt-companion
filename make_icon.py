#!/opt/homebrew/bin/python3.10
"""SCATT Companion のアプリアイコンを生成する。

ISSF 50m ライフルターゲットをモチーフに、中央に弾着グループを配置。
PyQt6 の QPainter で 1024×1024 PNG を描画 → macOS の sips/iconutil で
icon.iconset → icon.icns まで自動生成。

使い方:
  /opt/homebrew/bin/python3.10 make_icon.py
  → assets/icon.png, assets/icon.icns が生成される

setup_app.py が assets/icon.icns を参照する。
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PyQt6.QtWidgets import QApplication

OUT_DIR = Path(__file__).parent / "assets"
OUT_PNG = OUT_DIR / "icon.png"
OUT_ICNS = OUT_DIR / "icon.icns"


def draw_icon(size: int = 1024) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    cx = cy = size / 2

    # ----- 背景: macOS rounded square、淡いグラデ -----
    bg_grad = QLinearGradient(0, 0, 0, size)
    bg_grad.setColorAt(0.0, QColor(245, 247, 250))
    bg_grad.setColorAt(1.0, QColor(220, 225, 232))
    p.setBrush(QBrush(bg_grad))
    p.setPen(Qt.PenStyle.NoPen)
    r_round = size * 0.18  # macOS Big Sur アイコン半径
    p.drawRoundedRect(QRectF(0, 0, size, size), r_round, r_round)

    # 微かな影
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 18), max(1, int(size * 0.004))))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), r_round, r_round)

    # ----- ターゲット (ISSF 50m ライフル風、簡略 5 リング) -----
    outer_r = size * 0.40  # 外輪 (1 ring)
    # 白地リング (外)
    p.setBrush(QBrush(QColor(248, 248, 248)))
    p.setPen(QPen(QColor(150, 150, 150), size * 0.003))
    p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
    # 黒色 aiming mark
    black_r = outer_r * (112.4 / 154.4)
    p.setBrush(QBrush(QColor(20, 22, 26)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, cy), black_r, black_r)
    # 黒地内に白いリング線 (5,6,7,8,9,10)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(230, 230, 230), size * 0.002))
    ring_step = (outer_r - outer_r * 0.027) / 9  # 1リング→10リング の半径
    for ring in range(5, 11):
        r = outer_r - (ring - 1) * ring_step
        p.drawEllipse(QPointF(cx, cy), r, r)
    # 白地に薄リング線 (1,2,3,4)
    p.setPen(QPen(QColor(60, 60, 60), size * 0.002))
    for ring in range(1, 5):
        r = outer_r - (ring - 1) * ring_step
        p.drawEllipse(QPointF(cx, cy), r, r)
    # Inner 10 (X)
    inner_r = outer_r * (5.0 / 154.4)
    pen_x = QPen(QColor(255, 255, 255, 200), size * 0.002)
    pen_x.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen_x)
    p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

    # ----- 弾着グループ (3 発、緑→黄→赤の時系列色) + R95 円 -----
    impacts = [
        # (dx_frac, dy_frac, color)
        (-0.02, -0.015, QColor(95, 200, 130)),   # 緑 (古いショット)
        (0.015, -0.005, QColor(245, 200, 60)),   # 黄
        (0.005, 0.025, QColor(230, 80, 70)),     # 赤 (最新ショット)
    ]
    dot_r = size * 0.018
    for dx, dy, color in impacts:
        x = cx + dx * size
        y = cy + dy * size
        # 外側に半透明グロウ
        p.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(x, y), dot_r * 1.8, dot_r * 1.8)
        # 本体
        p.setBrush(QBrush(color))
        p.setPen(QPen(QColor(255, 255, 255), size * 0.0015))
        p.drawEllipse(QPointF(x, y), dot_r, dot_r)

    # 重心 + R95 円
    avg_x = cx + sum(d[0] for d in impacts) / len(impacts) * size
    avg_y = cy + sum(d[1] for d in impacts) / len(impacts) * size
    r95 = max(
        math.hypot(cx + d[0] * size - avg_x, cy + d[1] * size - avg_y)
        for d in impacts
    )
    # R95 円 (黄破線)
    ring_pen = QPen(QColor(245, 200, 60), size * 0.003)
    ring_pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(ring_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(avg_x, avg_y), r95 * 1.4, r95 * 1.4)

    # ----- アクセント: 右上に小さい "A" (Analyzer) マーク -----
    # ※ プレースホルダ感を出さないため省略可。今は入れない。

    p.end()
    return img


def png_to_icns(png_path: Path, icns_path: Path):
    """macOS の sips + iconutil で多解像度 PNG → .icns。"""
    iconset_dir = png_path.parent / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)
    # 必要な解像度
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for px, name in sizes:
        target = iconset_dir / name
        subprocess.run(
            ["sips", "-z", str(px), str(px), str(png_path), "--out", str(target)],
            check=True, capture_output=True,
        )
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=True,
    )
    print(f"  ✓ {icns_path}")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    print("rendering icon...")
    img = draw_icon(1024)
    img.save(str(OUT_PNG), "PNG")
    print(f"  ✓ {OUT_PNG}")
    if sys.platform == "darwin":
        png_to_icns(OUT_PNG, OUT_ICNS)
    else:
        print("  (macOS 以外なので .icns 変換はスキップ)")


if __name__ == "__main__":
    main()

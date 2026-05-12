"""アプリ全体のログ + uncaught exception ハンドラ。

ログ出力先: ~/Library/Logs/scatt-analyzer/app.log
標準エラーにも同時出力。

例外発生時:
  - logging.error() でスタックトレース記録
  - GUI が動いていれば QMessageBox で内容表示 (Detailed に full traceback)
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

LOG_DIR = Path.home() / "Library/Logs/scatt-analyzer"
LOG_FILE = LOG_DIR / "app.log"

_logger: Optional[logging.Logger] = None


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """logging 初期化。複数回呼んでも安全。"""
    global _logger
    if _logger is not None:
        return _logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = []
    try:
        fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt))
        handlers.append(fh)
    except Exception as e:
        print(f"[warn] log file open failed: {e}", file=sys.stderr)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter(fmt))
    handlers.append(sh)
    logging.basicConfig(level=level, handlers=handlers, force=True)
    _logger = logging.getLogger("scatt")
    _logger.info("=" * 60)
    _logger.info("scatt-analyzer 起動")
    return _logger


def install_exception_handler():
    """uncaught exception を logging + ダイアログで通知する hook を設置。"""
    def handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.error("uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        # GUI ダイアログを試みる(失敗してもログには記録済み)
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                return
            full_tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("予期しないエラー")
            msg.setText(f"{exc_type.__name__}: {exc_value}")
            msg.setInformativeText(
                f"このエラーは無視して使い続けることもできますが、"
                f"再現するようなら GitHub Issues か開発者に連絡してください。\n\n"
                f"ログ: {LOG_FILE}"
            )
            msg.setDetailedText(full_tb)
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
        except Exception:
            pass

    sys.excepthook = handler


def warn(msg: str):
    logging.warning(msg)


def info(msg: str):
    logging.info(msg)


def error(msg: str, exc_info=True):
    logging.error(msg, exc_info=exc_info)

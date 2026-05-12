"""OS 別パスの一元管理 (macOS / Windows / Linux)。

外部依存 (appdirs 等) は使わず、`platform.system()` で分岐するだけの軽量実装。

ディレクトリ:
  app_support     アプリの永続データ (extra.db、profiles/)
  logs            ログ
  scatt_storage   SCATT Expert 本体の storage.dat (read 専用)
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

_OS = platform.system()  # "Darwin" | "Windows" | "Linux"


def is_macos() -> bool:
    return _OS == "Darwin"


def is_windows() -> bool:
    return _OS == "Windows"


def app_support_dir() -> Path:
    """本アプリの永続データ置き場 (extra.db / profiles/ など)。"""
    if is_macos():
        return Path.home() / "Library/Application Support/scatt-prone-analyzer"
    if is_windows():
        # %APPDATA% = C:\Users\<user>\AppData\Roaming
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "scatt-prone-analyzer"
    # Linux / その他 — XDG_DATA_HOME に倣う
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "scatt-prone-analyzer"


def logs_dir() -> Path:
    if is_macos():
        return Path.home() / "Library/Logs/scatt-analyzer"
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
        return Path(base) / "scatt-analyzer/logs"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / "scatt-analyzer/logs"


def settings_files_for_backup() -> list[Path]:
    """QSettings の保存先候補 (バックアップ対象)。OS で形式が違う。"""
    if is_macos():
        return [
            Path.home() / "Library/Preferences/com.scatt-prone.analyzer.plist",
            Path.home() / "Library/Preferences/com.scatt-prone.analyzer.SCATT-Prone-Analyzer.plist",
        ]
    if is_windows():
        # Windows では QSettings はレジストリ (HKCU\Software\scatt-prone\analyzer) に書く
        # ので物理ファイルではバックアップできない。空リストを返す
        return []
    return [
        # Linux: QSettings は ~/.config/scatt-prone/analyzer.conf
        Path.home() / ".config/scatt-prone/analyzer.conf",
    ]


def default_scatt_storage_path() -> str:
    """SCATT Expert 本体の storage.dat デフォルト位置 (read 専用)。

    Windows の SCATT インストール先は公式情報が薄いので推定。実装時に検証要。
    """
    if is_macos():
        return os.path.expanduser(
            "~/Library/Application Support/SCATT Electronics/Scatt Expert/storage.dat"
        )
    if is_windows():
        # SCATT Expert (Windows) の保存先候補
        # 1) %APPDATA%\SCATT Electronics\Scatt Expert\storage.dat (Roaming)
        # 2) %LOCALAPPDATA%\SCATT Electronics\Scatt Expert\storage.dat
        # 環境依存のため、最も可能性が高い Roaming を返す
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return str(Path(base) / "SCATT Electronics/Scatt Expert/storage.dat")
    # Linux: SCATT Expert は Linux 版未提供 (Wine 経由のみ) なので無効デフォルト
    return ""


# ----- 後方互換: 直接 import 用 -----

APP_SUPPORT_DIR = str(app_support_dir())
LOGS_DIR = str(logs_dir())
DEFAULT_EXTRA_DB = str(app_support_dir() / "extra.db")
PROFILES_DIR = str(app_support_dir() / "profiles")
DEFAULT_SCATT_STORAGE = default_scatt_storage_path()

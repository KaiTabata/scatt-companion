"""scatt_paths: OS 別パス分岐の sanity チェック。"""

import os
from unittest.mock import patch

import scatt_paths as P


def test_current_os_returns_dirs():
    """現在 OS で各ディレクトリが Path として返る。"""
    assert P.app_support_dir().name == "scatt-companion"
    assert "scatt-analyzer" in str(P.logs_dir())


def test_macos_paths():
    with patch.object(P, "_OS", "Darwin"):
        assert P.is_macos() is True
        assert P.is_windows() is False
        s = str(P.app_support_dir())
        assert "Library/Application Support" in s
        assert s.endswith("scatt-companion")
        l = str(P.logs_dir())
        assert "Library/Logs" in l


def test_windows_paths(monkeypatch):
    monkeypatch.setattr(P, "_OS", "Windows")
    monkeypatch.setenv("APPDATA", "C:\\Users\\Alice\\AppData\\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Alice\\AppData\\Local")
    assert P.is_windows() is True
    assert P.is_macos() is False
    s = str(P.app_support_dir())
    assert "AppData" in s and "scatt-companion" in s
    scatt = P.default_scatt_storage_path()
    assert "SCATT Electronics" in scatt
    assert "Scatt Expert" in scatt
    assert "storage.dat" in scatt


def test_windows_appdata_fallback(monkeypatch):
    """APPDATA 環境変数がない Windows でもフォールバックする。"""
    monkeypatch.setattr(P, "_OS", "Windows")
    monkeypatch.delenv("APPDATA", raising=False)
    s = str(P.app_support_dir())
    assert "scatt-companion" in s


def test_linux_paths(monkeypatch):
    monkeypatch.setattr(P, "_OS", "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert P.is_macos() is False
    assert P.is_windows() is False
    s = str(P.app_support_dir())
    assert ".local/share/scatt-companion" in s


def test_settings_files_for_backup_macos(monkeypatch):
    monkeypatch.setattr(P, "_OS", "Darwin")
    files = P.settings_files_for_backup()
    assert len(files) >= 1
    assert all("Library/Preferences" in str(f) for f in files)


def test_settings_files_for_backup_windows(monkeypatch):
    """Windows は QSettings がレジストリ → ファイル無し。"""
    monkeypatch.setattr(P, "_OS", "Windows")
    assert P.settings_files_for_backup() == []

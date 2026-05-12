"""scatt_backup: zip 書き出し → manifest 読み込みのラウンドトリップ。"""

import os
import tempfile
import zipfile
from pathlib import Path

import scatt_backup as BK


def test_backup_creates_zip(tmp_path, monkeypatch):
    """ダミー extra.db を用意 → zip 化 → 読み戻し。"""
    fake_extra = tmp_path / "extra.db"
    fake_extra.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    monkeypatch.setattr(BK, "EXTRA_DB", fake_extra)
    # plist は無いので None で OK
    monkeypatch.setattr(BK, "SETTINGS_PLIST_CANDIDATES", [tmp_path / "no.plist"])

    out = tmp_path / "out.zip"
    mf = BK.backup_archive(str(out), version="test-1.0")
    assert out.exists()
    assert mf["scatt_analyzer_version"] == "test-1.0"
    assert any(f["name"] == "extra.db" for f in mf["files"])

    inspected = BK.inspect_archive(str(out))
    assert "scatt-backup/manifest.json" in inspected["zip_entries"]
    assert "scatt-backup/extra.db" in inspected["zip_entries"]
    assert inspected["scatt_analyzer_version"] == "test-1.0"


def test_restore_writes_extra_db(tmp_path, monkeypatch):
    """zip から extra.db を復元できる。"""
    original = tmp_path / "extra.db"
    original.write_bytes(b"original-content")
    monkeypatch.setattr(BK, "EXTRA_DB", original)
    monkeypatch.setattr(BK, "SETTINGS_PLIST_CANDIDATES", [tmp_path / "x.plist"])

    out = tmp_path / "out.zip"
    BK.backup_archive(str(out), version="x")
    # 別の内容に上書きしてから復元
    original.write_bytes(b"corrupted")
    result = BK.restore_archive(str(out))
    assert result["extra_db"] is True
    assert original.read_bytes() == b"original-content"
    assert result["errors"] == []

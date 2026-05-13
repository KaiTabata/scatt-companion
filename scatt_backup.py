"""補助データのバックアップとインポート。

backup_archive(path):
  - extra.db (~/Library/Application Support/scatt-companion/extra.db)
  - QSettings の plist (~/Library/Preferences/com.scatt-companion.app.plist)
  を 1 つの zip にまとめる

restore_archive(path):
  - zip を展開して上書き

zip 構造:
  scatt-backup/
    manifest.json    バージョン情報、作成日時、ホスト
    extra.db
    settings.plist
"""

from __future__ import annotations

import datetime
import json
import os
import platform
import zipfile
from pathlib import Path

import scatt_paths

EXTRA_DB = Path(scatt_paths.DEFAULT_EXTRA_DB)
SETTINGS_PLIST_CANDIDATES = scatt_paths.settings_files_for_backup()


def _find_settings_plist() -> Path | None:
    for p in SETTINGS_PLIST_CANDIDATES:
        if p.exists():
            return p
    return None


def backup_archive(out_path: str, version: str = "unknown") -> dict:
    """補助データを zip にまとめる。返り値: 含まれたファイル情報。"""
    out_path_p = Path(out_path)
    out_path_p.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "scatt_analyzer_version": version,
        "created_at": datetime.datetime.now().isoformat(),
        "host": platform.node(),
        "platform": platform.platform(),
        "files": [],
    }
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if EXTRA_DB.exists():
            zf.write(EXTRA_DB, arcname="scatt-backup/extra.db")
            manifest["files"].append({"name": "extra.db", "size": EXTRA_DB.stat().st_size})
        plist = _find_settings_plist()
        if plist is not None:
            zf.write(plist, arcname="scatt-backup/settings.plist")
            manifest["files"].append({"name": "settings.plist", "size": plist.stat().st_size})
        # manifest を最後に
        zf.writestr("scatt-backup/manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def inspect_archive(in_path: str) -> dict:
    """zip 内の manifest を読んで内容を確認。"""
    with zipfile.ZipFile(in_path, "r") as zf:
        names = zf.namelist()
        try:
            with zf.open("scatt-backup/manifest.json") as f:
                manifest = json.load(f)
        except KeyError:
            manifest = {"files": [], "scatt_analyzer_version": "?", "created_at": "?"}
        manifest["zip_entries"] = names
    return manifest


def restore_archive(in_path: str, overwrite: bool = True) -> dict:
    """zip から復元。返り値: 復元した内容。"""
    result = {"extra_db": False, "settings_plist": False, "errors": []}
    with zipfile.ZipFile(in_path, "r") as zf:
        names = zf.namelist()
        # extra.db
        if "scatt-backup/extra.db" in names:
            try:
                EXTRA_DB.parent.mkdir(parents=True, exist_ok=True)
                if EXTRA_DB.exists() and not overwrite:
                    result["errors"].append("extra.db existed (not overwritten)")
                else:
                    with zf.open("scatt-backup/extra.db") as src, open(EXTRA_DB, "wb") as dst:
                        dst.write(src.read())
                    result["extra_db"] = True
            except Exception as e:
                result["errors"].append(f"extra.db restore failed: {e}")
        # settings.plist
        if "scatt-backup/settings.plist" in names:
            try:
                target = SETTINGS_PLIST_CANDIDATES[0]
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open("scatt-backup/settings.plist") as src, open(target, "wb") as dst:
                    dst.write(src.read())
                result["settings_plist"] = True
            except Exception as e:
                result["errors"].append(f"settings.plist restore failed: {e}")
    return result

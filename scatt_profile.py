"""射手 (Profile) 管理。

複数射手対応のため、心拍/HRV/除外フラグ等の補助 DB を射手別に持つ。

データ構造:
  profiles[i] = {"id": "<slug>", "name": "表示名", "db": "<file path>"}

DB ファイル配置:
  ~/Library/Application Support/scatt-prone-analyzer/profiles/<id>/extra.db

互換性:
  既存ユーザの単一 extra.db (DEFAULT_EXTRA_DB) は "default" profile として
  そのまま継続利用。プロファイル追加で新規 DB を別パスに作る。

QSettings での保存形式:
  - "profiles/list"     : JSON 文字列 [{id, name, db}, ...]
  - "profiles/current"  : 現在 profile の id
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import scatt_storage as ST

PROFILES_DIR = os.path.expanduser(
    "~/Library/Application Support/scatt-prone-analyzer/profiles"
)


@dataclass
class Profile:
    id: str
    name: str
    db: str

    def to_dict(self) -> dict:
        return asdict(self)


def _slugify(name: str) -> str:
    """ファイルパスに使える slug を生成。日本語名でも安全。"""
    # 英数字とハイフン/アンダースコアのみ残す
    s = unicodedata.normalize("NFKD", name)
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-")
    return s.lower() or "profile"


def _ensure_unique_id(base: str, existing: list[str]) -> str:
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


class ProfileManager:
    """QSettings をストアとして使う profile manager。

    GUI 側からは get_profiles / current / set_current / add / rename / delete を呼ぶ。
    """

    def __init__(self, settings):
        """settings: scatt_gui.S インスタンス相当 (get/set)。"""
        self._s = settings
        self._migrate_if_empty()

    # ---- 内部 ----

    def _migrate_if_empty(self):
        """初回起動時: 既存 DEFAULT_EXTRA_DB を default profile として登録。"""
        if self._raw_list():
            return
        default_p = Profile(id="default", name="既定", db=ST.DEFAULT_EXTRA_DB)
        self._save_list([default_p])
        self._s.set("profiles/current", "default")

    def _raw_list(self) -> list[dict]:
        raw = self._s.get("profiles/list") or ""
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except (json.JSONDecodeError, TypeError):
            return []
        return []

    def _save_list(self, profiles: list[Profile]):
        self._s.set("profiles/list", json.dumps([p.to_dict() for p in profiles],
                                                 ensure_ascii=False))

    # ---- 公開 ----

    def list_profiles(self) -> list[Profile]:
        return [Profile(**d) for d in self._raw_list()]

    def current_id(self) -> str:
        return self._s.get("profiles/current") or "default"

    def current(self) -> Profile:
        cid = self.current_id()
        for p in self.list_profiles():
            if p.id == cid:
                return p
        # フォールバック (壊れた設定)
        fallback = Profile(id="default", name="既定", db=ST.DEFAULT_EXTRA_DB)
        self._save_list([fallback])
        self._s.set("profiles/current", "default")
        return fallback

    def set_current(self, profile_id: str) -> bool:
        """profile を切替。返り値: 成功なら True。"""
        for p in self.list_profiles():
            if p.id == profile_id:
                self._s.set("profiles/current", profile_id)
                ST.set_active_path(p.db)
                ST.ensure_db()
                return True
        return False

    def add(self, name: str) -> Profile:
        """新規 profile を作成し DB ファイルも初期化。"""
        existing = self.list_profiles()
        ids = [p.id for p in existing]
        slug = _ensure_unique_id(_slugify(name), ids)
        db_path = os.path.join(PROFILES_DIR, slug, "extra.db")
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        new_p = Profile(id=slug, name=name.strip() or slug, db=db_path)
        self._save_list(existing + [new_p])
        # DB スキーマを作っておく
        ST.ensure_db(db_path)
        return new_p

    def rename(self, profile_id: str, new_name: str) -> bool:
        profiles = self.list_profiles()
        for p in profiles:
            if p.id == profile_id:
                p.name = new_name.strip() or p.id
                self._save_list(profiles)
                return True
        return False

    def delete(self, profile_id: str, *, remove_db_file: bool = False) -> bool:
        """profile を一覧から削除。default は削除不可。

        remove_db_file=True なら DB ファイルも削除。
        """
        if profile_id == "default":
            return False
        profiles = self.list_profiles()
        new_list = [p for p in profiles if p.id != profile_id]
        if len(new_list) == len(profiles):
            return False  # 見つからなかった
        target = next((p for p in profiles if p.id == profile_id), None)
        self._save_list(new_list)
        if self.current_id() == profile_id:
            self.set_current("default")
        if remove_db_file and target:
            try:
                if os.path.exists(target.db):
                    os.remove(target.db)
            except OSError:
                pass
        return True

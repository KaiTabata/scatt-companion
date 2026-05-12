"""scatt_profile: 複数射手の管理 (追加 / 改名 / 削除 / 切替)。"""

import scatt_profile as PR
import scatt_storage as ST


class FakeSettings:
    """QSettings 代替: dict ベースの軽量実装。"""
    def __init__(self):
        self._d = {}

    def get(self, key):
        return self._d.get(key)

    def set(self, key, value):
        self._d[key] = value


def test_default_profile_auto_created(tmp_path, monkeypatch):
    """初回 init で default profile が登録される。"""
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    profs = pm.list_profiles()
    assert len(profs) == 1
    assert profs[0].id == "default"
    assert pm.current().id == "default"


def test_add_profile_creates_db_file(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    new_p = pm.add("Alice")
    assert new_p.name == "Alice"
    assert new_p.id == "alice"
    # DB ファイルが作られ、スキーマが存在する
    import os, sqlite3
    assert os.path.exists(new_p.db)
    conn = sqlite3.connect(new_p.db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(shot_extras)")]
    conn.close()
    assert "shot_id" in cols
    assert "hidden" in cols


def test_duplicate_name_gets_unique_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    p1 = pm.add("Bob")
    p2 = pm.add("Bob")
    assert p1.id != p2.id
    assert p2.id == "bob-2"


def test_set_current_switches_active_db(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    new_p = pm.add("Carol")
    assert pm.set_current(new_p.id) is True
    assert ST.active_path() == new_p.db
    # 元に戻す
    ST.set_active_path(ST.DEFAULT_EXTRA_DB)


def test_delete_profile_removes_from_list(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    new_p = pm.add("Dave")
    assert pm.delete(new_p.id) is True
    assert all(p.id != new_p.id for p in pm.list_profiles())


def test_cannot_delete_default(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    assert pm.delete("default") is False
    assert any(p.id == "default" for p in pm.list_profiles())


def test_rename(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    new_p = pm.add("Eve")
    assert pm.rename(new_p.id, "Eve-Renamed") is True
    refreshed = next(p for p in pm.list_profiles() if p.id == new_p.id)
    assert refreshed.name == "Eve-Renamed"


def test_japanese_name_slugify(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    pm = PR.ProfileManager(s)
    # 日本語名でも何らかの slug ができる (パス可能)
    p = pm.add("田畑")
    assert p.id  # 空でない
    assert p.name == "田畑"

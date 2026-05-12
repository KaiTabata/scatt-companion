"""scatt_home: ホーム画面の表示判定とデータ取得 (DB なしケース)。"""

import datetime
import sqlite3
import tempfile

import pytest

import scatt_home as HOME
import scatt_profile as PR


class FakeSettings:
    def __init__(self):
        self._d = {}

    def get(self, key):
        return self._d.get(key)

    def set(self, key, value):
        self._d[key] = value


def _seeded_profile_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(PR, "PROFILES_DIR", str(tmp_path / "profiles"))
    s = FakeSettings()
    return s, PR.ProfileManager(s)


def test_should_show_first_launch(tmp_path, monkeypatch):
    """home/seen=False なら auto モードで表示する。"""
    s, pm = _seeded_profile_manager(tmp_path, monkeypatch)
    s.set("home/show_on_startup", "auto")
    assert HOME.should_show(s, pm) is True


def test_should_show_seen_single_profile(tmp_path, monkeypatch):
    """home/seen=True かつ profile が 1 つ → 表示しない。"""
    s, pm = _seeded_profile_manager(tmp_path, monkeypatch)
    s.set("home/show_on_startup", "auto")
    s.set("home/seen", True)
    assert HOME.should_show(s, pm) is False


def test_should_show_multiple_profiles(tmp_path, monkeypatch):
    """profile が 2 つ以上なら auto モードでも表示する。"""
    s, pm = _seeded_profile_manager(tmp_path, monkeypatch)
    s.set("home/show_on_startup", "auto")
    s.set("home/seen", True)
    pm.add("Alice")
    assert HOME.should_show(s, pm) is True


def test_mode_always(tmp_path, monkeypatch):
    s, pm = _seeded_profile_manager(tmp_path, monkeypatch)
    s.set("home/show_on_startup", "always")
    s.set("home/seen", True)
    assert HOME.should_show(s, pm) is True


def test_mode_never(tmp_path, monkeypatch):
    s, pm = _seeded_profile_manager(tmp_path, monkeypatch)
    s.set("home/show_on_startup", "never")
    s.set("home/seen", False)
    pm.add("Alice")
    pm.add("Bob")
    # never は何があっても表示しない
    assert HOME.should_show(s, pm) is False


def test_fetch_recent_no_db(tmp_path):
    """存在しない DB → 空リスト (例外を投げない)。"""
    bogus = str(tmp_path / "nope.db")
    rows = HOME.fetch_recent_sessions(bogus, limit=5)
    assert rows == []


def test_fetch_digest_no_db(tmp_path):
    """存在しない DB → ゼロ集計。"""
    bogus = str(tmp_path / "nope.db")
    d = HOME.fetch_digest(bogus)
    assert d == {"week": {"sessions": 0, "shots": 0},
                 "month": {"sessions": 0, "shots": 0}}


def test_fetch_recent_with_synthetic_db(tmp_path):
    """合成 SCATT 形式 DB から最近セッションを取り出せる。"""
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE sessions (
            session_id INTEGER PRIMARY KEY, position INTEGER, distance INTEGER,
            caliber INTEGER, sample_rate INTEGER
        );
        CREATE TABLE traces (session_id INTEGER, timer INTEGER);
        CREATE TABLE shots (session_id INTEGER);
    """)
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    conn.execute("INSERT INTO sessions VALUES (1, 0, 50, 22, 120)")
    conn.execute("INSERT INTO traces VALUES (1, ?)", (now_ms,))
    conn.executemany("INSERT INTO shots VALUES (?)", [(1,)] * 10)
    conn.commit()
    conn.close()
    rows = HOME.fetch_recent_sessions(str(db), limit=5)
    assert len(rows) == 1
    assert rows[0]["sid"] == 1
    assert rows[0]["n_shots"] == 10
    assert rows[0]["position"] == "prone"

"""SCATT 外部データ(心拍 / HRV / IMU 等)の永続化。

SCATT 本体の storage.dat には記録されないデータを、shot_id をキーとした
別 SQLite ファイルに保存する。SCATT 側の shot が削除されても孤立しないように
削除フローと同期する。

DB 場所: ~/Library/Application Support/scatt-prone-analyzer/extra.db

スキーマ:
  shot_extras(
    shot_id  PRIMARY KEY,    -- SCATT 側 shots.shot_id と 1:1
    hr_at_fire  INTEGER,     -- 発射時の HR (bpm)
    rmssd_30s   REAL,        -- 直近 30秒の HRV (ms)
    imu_yaw     REAL,        -- 銃身 yaw 角 (degrees、IMU 連携時)
    imu_pitch   REAL,        -- 銃身 pitch 角 (degrees)
    imu_roll    REAL,        -- 銃身 roll 角 (degrees、SCATT cant とは別)
    note        TEXT,        -- 任意のメモ
    created_at  INTEGER,     -- ms unix epoch
    updated_at  INTEGER
  )

将来のセンサ追加もカラム追加だけで対応できる構造。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

import scatt_paths

DEFAULT_EXTRA_DB = scatt_paths.DEFAULT_EXTRA_DB

# Profile (複数射手) 対応のため active path を切替可能に。
# scatt_profile.set_current() がここを書き換える。
_ACTIVE_EXTRA_DB = DEFAULT_EXTRA_DB


def set_active_path(path: str) -> None:
    """以降の load_all_extras 等のデフォルト path を切替。

    profile 切替で呼ばれる。明示的に path 引数を渡したコールは影響を受けない。
    """
    global _ACTIVE_EXTRA_DB
    _ACTIVE_EXTRA_DB = path


def active_path() -> str:
    return _ACTIVE_EXTRA_DB


def _resolve(path: Optional[str]) -> str:
    return path if path is not None else _ACTIVE_EXTRA_DB


def ensure_db(path: Optional[str] = None) -> str:
    path = _resolve(path)
    """DB ファイルとテーブルを作成 (なければ)。返り値: 実 path。

    既存 DB に新規カラム (hidden) があれば ALTER TABLE で追加する。
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shot_extras (
                shot_id     INTEGER PRIMARY KEY,
                hr_at_fire  INTEGER,
                rmssd_30s   REAL,
                imu_yaw     REAL,
                imu_pitch   REAL,
                imu_roll    REAL,
                note        TEXT,
                hidden      INTEGER DEFAULT 0,
                created_at  INTEGER DEFAULT (CAST(strftime('%s', 'now') AS INTEGER) * 1000),
                updated_at  INTEGER DEFAULT (CAST(strftime('%s', 'now') AS INTEGER) * 1000)
            )
        """)
        # 既存テーブルに hidden 列が無い場合の migration
        cols = [r[1] for r in conn.execute("PRAGMA table_info(shot_extras)").fetchall()]
        if "hidden" not in cols:
            conn.execute("ALTER TABLE shot_extras ADD COLUMN hidden INTEGER DEFAULT 0")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_extras_updated "
            "ON shot_extras(updated_at)"
        )
        conn.commit()
    finally:
        conn.close()
    return path


def set_shot_hidden(shot_id: int, hidden: bool, path: Optional[str] = None):
    """shot を集計から除外 (hidden=1) / 復帰 (hidden=0)。"""
    path = _resolve(path)
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute(
            """
            INSERT INTO shot_extras (shot_id, hidden)
            VALUES (?, ?)
            ON CONFLICT(shot_id) DO UPDATE SET
              hidden = excluded.hidden,
              updated_at = CAST(strftime('%s','now') AS INTEGER) * 1000
            """,
            (shot_id, 1 if hidden else 0),
        )
        conn.commit()
    finally:
        conn.close()


def save_shot_extras(
    shot_id: int,
    *,
    hr_at_fire: Optional[int] = None,
    rmssd_30s: Optional[float] = None,
    imu_yaw: Optional[float] = None,
    imu_pitch: Optional[float] = None,
    imu_roll: Optional[float] = None,
    note: Optional[str] = None,
    path: Optional[str] = None,
):
    """shot_id に対する補助データを upsert。

    None の引数は既存値を上書きしない(COALESCE)。
    """
    path = _resolve(path)
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute(
            """
            INSERT INTO shot_extras
              (shot_id, hr_at_fire, rmssd_30s, imu_yaw, imu_pitch, imu_roll, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shot_id) DO UPDATE SET
              hr_at_fire = COALESCE(excluded.hr_at_fire, shot_extras.hr_at_fire),
              rmssd_30s  = COALESCE(excluded.rmssd_30s,  shot_extras.rmssd_30s),
              imu_yaw    = COALESCE(excluded.imu_yaw,    shot_extras.imu_yaw),
              imu_pitch  = COALESCE(excluded.imu_pitch,  shot_extras.imu_pitch),
              imu_roll   = COALESCE(excluded.imu_roll,   shot_extras.imu_roll),
              note       = COALESCE(excluded.note,       shot_extras.note),
              updated_at = CAST(strftime('%s','now') AS INTEGER) * 1000
            """,
            (shot_id, hr_at_fire, rmssd_30s, imu_yaw, imu_pitch, imu_roll, note),
        )
        conn.commit()
    finally:
        conn.close()


def load_all_extras(path: Optional[str] = None) -> dict[int, dict]:
    path = _resolve(path)
    """全 shot_extras を {shot_id: {...}} で返す。DB 未作成なら空 dict。"""
    if not os.path.exists(path):
        return {}
    # 念のため migration 確認
    try:
        ensure_db(path)
    except Exception:
        pass
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    try:
        out: dict[int, dict] = {}
        for row in conn.execute(
            "SELECT shot_id, hr_at_fire, rmssd_30s, imu_yaw, imu_pitch, imu_roll, note, hidden "
            "FROM shot_extras"
        ):
            sid = row[0]
            out[sid] = {
                "hr": row[1],
                "rmssd": row[2],
                "imu_yaw": row[3],
                "imu_pitch": row[4],
                "imu_roll": row[5],
                "note": row[6],
                "hidden": bool(row[7]) if row[7] is not None else False,
            }
        return out
    finally:
        conn.close()


def delete_shot_extras(shot_ids: list[int], path: Optional[str] = None) -> int:
    path = _resolve(path)
    """SCATT 側で shot 削除した時に呼ぶ。返り値: 削除した行数。"""
    if not shot_ids or not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        cur = conn.cursor()
        cur.executemany(
            "DELETE FROM shot_extras WHERE shot_id = ?",
            [(sid,) for sid in shot_ids],
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def cleanup_orphans(valid_shot_ids: list[int], path: Optional[str] = None) -> int:
    path = _resolve(path)
    """SCATT 側に存在しなくなった shot_id の extras を一括削除。"""
    if not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        existing = set()
        for (sid,) in conn.execute("SELECT shot_id FROM shot_extras"):
            existing.add(sid)
        orphans = existing - set(valid_shot_ids)
        if not orphans:
            return 0
        conn.executemany(
            "DELETE FROM shot_extras WHERE shot_id = ?",
            [(sid,) for sid in orphans],
        )
        conn.commit()
        return len(orphans)
    finally:
        conn.close()


def export_to_jsonl(path: Optional[str] = None) -> list[dict]:
    path = _resolve(path)
    """全 shot_extras を [{shot_id, hr_at_fire, ...}, ...] のリストで返す
    (バックアップ / 解析用)。
    """
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    cols = ("shot_id", "hr_at_fire", "rmssd_30s", "imu_yaw", "imu_pitch",
            "imu_roll", "note", "created_at", "updated_at")
    try:
        return [
            dict(zip(cols, row))
            for row in conn.execute(
                "SELECT " + ", ".join(cols) + " FROM shot_extras "
                "ORDER BY shot_id"
            )
        ]
    finally:
        conn.close()

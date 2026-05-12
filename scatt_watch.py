#!/usr/bin/env python3
"""SCATT Expert storage.dat の新規 trace をリアルタイム監視し、復号して JSONL で stdout に出力する。

使い方:
  python3 scatt_watch.py                     # 起動時点以降の新規分のみ
  python3 scatt_watch.py --from 0            # 全件
  python3 scatt_watch.py --from 900          # trace_id > 900 から
  python3 scatt_watch.py --interval 0.5      # ポーリング間隔(秒)
  python3 scatt_watch.py --db /path/to/storage.dat
"""

import argparse
import json
import os
import sqlite3
import struct
import sys
import time
import zlib

DEFAULT_DB = os.path.expanduser(
    "~/Library/Application Support/SCATT Electronics/Scatt Expert/storage.dat"
)

XOR_KEY = bytes([
    0xe3, 0x00, 0xe9, 0x00, 0x34, 0x85, 0x1d, 0x04,
    0xf0, 0x95, 0xc0, 0x70, 0x0e, 0x1e, 0xb9, 0xf3,
])


def decode_trace(blob: bytes):
    """trace.data BLOB を復号して [(x, y, z), ...] のサンプル配列を返す。"""
    if not blob or blob[0] != 0x01:
        raise ValueError(f"unexpected version byte: {blob[:1].hex() if blob else 'empty'}")
    body = blob[1:]
    out = bytearray(len(body))
    prev = 0
    for i, c in enumerate(body):
        out[i] = prev ^ c ^ XOR_KEY[i % 16]
        prev = c
    # 1B drop -> 2B checksum drop -> qCompress (4B BE length) + zlib
    raw = zlib.decompress(bytes(out[1:])[2:][4:])
    # ヘッダ: 4B magic 0a0b0c0d, 4B 10000010, 4B 00000002, 2B uint16 count BE, 1B flag
    if raw[:4] != b"\x0a\x0b\x0c\x0d":
        raise ValueError(f"bad QDataStream magic: {raw[:4].hex()}")
    n = struct.unpack(">H", raw[12:14])[0]
    body_bytes = raw[15:]
    if len(body_bytes) != 12 * n:
        raise ValueError(f"sample length mismatch n={n} body={len(body_bytes)}")
    samples = []
    for i in range(n):
        x, y, z = struct.unpack(">fff", body_bytes[i * 12:(i + 1) * 12])
        samples.append((x, y, z))
    return samples


def open_db_ro(path: str) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.execute("PRAGMA busy_timeout = 1000;")
    return conn


def fetch_session_info(conn: sqlite3.Connection, session_id: int):
    row = conn.execute(
        "SELECT person_id, distance, caliber, position, sample_rate, shot_count FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "person_id": row[0],
        "distance": row[1],
        "caliber": row[2],
        "position": row[3],
        "sample_rate": row[4],
        "shot_count": row[5],
    }


def fetch_new_traces(conn: sqlite3.Connection, last_id: int):
    return conn.execute(
        "SELECT trace_id, session_id, timer, timer_enter, data FROM traces "
        "WHERE trace_id > ? ORDER BY trace_id ASC",
        (last_id,),
    ).fetchall()


def emit(record: dict):
    json.dump(record, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB, help=f"storage.dat path (default: {DEFAULT_DB})")
    ap.add_argument("--from", dest="from_id", type=int, default=None,
                    help="開始 trace_id (この値より大きいものを出力)。未指定なら起動時点の MAX")
    ap.add_argument("--interval", type=float, default=0.3, help="polling 間隔秒 (default 0.3)")
    ap.add_argument("--include-samples", action="store_true", default=True,
                    help="サンプル配列を含める (デフォルト on)")
    ap.add_argument("--no-samples", dest="include_samples", action="store_false",
                    help="サンプルを省略しメタ情報のみ")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"error: db not found: {args.db}", file=sys.stderr)
        sys.exit(1)
    # 旧 GUI 用の依存メモ: scatt_gui.py は pyqtgraph も使用するので
    # `pip3 install --user pyqtgraph` が必要。scatt_watch.py は標準ライブラリのみ。

    conn = open_db_ro(args.db)
    session_cache: dict = {}

    if args.from_id is None:
        last_id = conn.execute("SELECT COALESCE(MAX(trace_id), 0) FROM traces").fetchone()[0]
        print(f"# watching from trace_id > {last_id} (current max)", file=sys.stderr)
    else:
        last_id = args.from_id
        print(f"# watching from trace_id > {last_id} (--from)", file=sys.stderr)

    while True:
        try:
            rows = fetch_new_traces(conn, last_id)
        except sqlite3.OperationalError as e:
            print(f"# db busy: {e}", file=sys.stderr)
            time.sleep(args.interval)
            try:
                conn.close()
            except Exception:
                pass
            conn = open_db_ro(args.db)
            continue

        for trace_id, session_id, timer, timer_enter, data in rows:
            try:
                samples = decode_trace(data) if args.include_samples else None
            except Exception as e:
                print(f"# decode failed trace_id={trace_id}: {e}", file=sys.stderr)
                last_id = trace_id
                continue

            if session_id not in session_cache:
                session_cache[session_id] = fetch_session_info(conn, session_id)
            sess = session_cache[session_id]

            record = {
                "trace_id": trace_id,
                "session_id": session_id,
                "timer_ms": timer,
                "timer_enter_ms": timer_enter,
                "n_samples": len(samples) if samples is not None else None,
                "session": sess,
            }
            if samples is not None:
                record["samples"] = samples
            emit(record)
            last_id = trace_id

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

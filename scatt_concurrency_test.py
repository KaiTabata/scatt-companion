#!/usr/bin/env python3
"""SCATT Expert 起動中の storage.dat 並行読み出し検証。

目的:
  SCATT Expert が書き込みしている最中に scatt_watch.py / scatt_gui.py が
  問題なく読めるか、SQLITE_BUSY や読み取り欠損が発生しないかを計測する。

使い方:
  1. SCATT Expert を起動 → 射撃シミュレーションまたは記録モードに入る
  2. このスクリプトを実行(別ターミナル)
       /opt/homebrew/bin/python3.10 scatt_concurrency_test.py
  3. SCATT 側で射撃 / trace 生成 / セッション操作を行う
  4. 指定時間(デフォルト 60 秒)経過 or Ctrl-C で集計表示

オプション:
  --duration N    計測時間(秒)、default 60
  --interval S    polling 間隔(秒)、default 0.1 (= 10Hz)
  --busy-ms N     PRAGMA busy_timeout (ms)、default 1000
  --db PATH       storage.dat path
"""

import argparse
import os
import sqlite3
import sys
import time

DEFAULT_DB = os.path.expanduser(
    "~/Library/Application Support/SCATT Electronics/Scatt Expert/storage.dat"
)


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(len(s) * p)))
    return s[k]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--duration", type=float, default=60.0, help="計測時間(秒)")
    ap.add_argument("--interval", type=float, default=0.1, help="polling 間隔(秒)")
    ap.add_argument("--busy-ms", type=int, default=1000, help="PRAGMA busy_timeout (ms)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"error: db not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    try:
        conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.OperationalError as e:
        print(f"open failed: {e}", file=sys.stderr)
        sys.exit(1)
    conn.execute(f"PRAGMA busy_timeout = {args.busy_ms};")

    initial = conn.execute("SELECT COALESCE(MAX(trace_id), 0) FROM traces").fetchone()[0]
    print(f"db        : {args.db}")
    print(f"initial   : max trace_id = {initial}")
    print(f"duration  : {args.duration}s, interval = {args.interval}s")
    print(f"busy_to   : {args.busy_ms}ms")
    print("-" * 60)
    print("SCATT 側で射撃などをして、新規 trace を発生させてください。")
    print("(Ctrl-C で途中終了)")
    print()

    t_start = time.monotonic()
    polls = 0
    busy_count = 0
    other_errors = 0
    blob_decode_fail = 0
    latencies_ms: list[float] = []
    seen_tids: set[int] = set()
    last_id = initial

    try:
        while time.monotonic() - t_start < args.duration:
            t0 = time.monotonic()
            polls += 1
            try:
                rows = conn.execute(
                    "SELECT trace_id, session_id, length(data) FROM traces "
                    "WHERE trace_id > ? ORDER BY trace_id",
                    (last_id,),
                ).fetchall()
                latencies_ms.append((time.monotonic() - t0) * 1000.0)
                for tid, sid, sz in rows:
                    if tid not in seen_tids:
                        seen_tids.add(tid)
                        elapsed = time.monotonic() - t_start
                        print(f"  +{elapsed:>5.1f}s  new trace #{tid:<5}  "
                              f"session={sid}  data={sz}B")
                        last_id = max(last_id, tid)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "lock" in msg or "busy" in msg:
                    busy_count += 1
                    elapsed = time.monotonic() - t_start
                    print(f"  +{elapsed:>5.1f}s  BUSY: {e}")
                else:
                    other_errors += 1
                    print(f"  +{time.monotonic()-t_start:>5.1f}s  ERROR: {e}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n(interrupted)")

    elapsed = time.monotonic() - t_start
    print()
    print("=" * 60)
    print(f"elapsed         : {elapsed:.1f} s")
    print(f"polls           : {polls}")
    print(f"new traces seen : {len(seen_tids)}")
    print(f"busy errors     : {busy_count}  ({100*busy_count/polls if polls else 0:.2f}%)")
    print(f"other errors    : {other_errors}")
    if latencies_ms:
        print(f"query latency   : "
              f"p50={percentile(latencies_ms, 0.50):.2f}ms  "
              f"p95={percentile(latencies_ms, 0.95):.2f}ms  "
              f"p99={percentile(latencies_ms, 0.99):.2f}ms  "
              f"max={max(latencies_ms):.2f}ms")
    if seen_tids:
        tids = sorted(seen_tids)
        gaps = [tids[i + 1] - tids[i] for i in range(len(tids) - 1)]
        if gaps and max(gaps) > 1:
            print(f"WARN: trace_id に隙間あり (max gap={max(gaps)}): "
                  "並行読み中に取りこぼし or 内部削除の可能性")
    print()
    if busy_count == 0 and other_errors == 0:
        print("結論: 並行読み出し OK ✓ (busy/error なし)")
    elif busy_count > 0:
        print(f"結論: busy が {busy_count} 件発生。"
              f"--busy-ms を大きく (例: 5000) or --interval を長く(0.3〜0.5)推奨")
    if seen_tids:
        print(f"検出された新規 trace_id: {sorted(seen_tids)}")


if __name__ == "__main__":
    main()

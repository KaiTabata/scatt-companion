#!/bin/bash
# Finder からダブルクリックで起動できる SCATT 監視ランチャ (JSONL を Terminal に流す)
set -e
cd "$(dirname "$0")"

# 標準ライブラリのみで動くので system Python でも OK
PY=/opt/homebrew/bin/python3.10
[ -x "$PY" ] || PY=/usr/bin/python3

echo "[scatt-watch] Ctrl-C で終了"
echo "----------------------------------------"
exec "$PY" scatt_watch.py --no-samples "$@"

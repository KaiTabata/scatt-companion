#!/bin/bash
# Finder からダブルクリックで起動できる SCATT GUI ランチャ
# デフォルトで Live モード ON + 最前面 + 画面スリープ抑制
set -e
cd "$(dirname "$0")"

PY=/opt/homebrew/bin/python3.10
if [ ! -x "$PY" ]; then
    echo "[error] Python 3.10 が見つかりません: $PY"
    echo "        brew install python@3.10 を実行してください。"
    echo ""
    read -n 1 -s -r -p "Enter で終了..."
    exit 1
fi

# 依存チェック (なければインストール)
if ! "$PY" -c "import PyQt6, numpy, pyqtgraph" >/dev/null 2>&1; then
    echo "[info] 依存パッケージ (PyQt6, numpy, pyqtgraph) をインストールします..."
    "$PY" -m pip install --user PyQt6 numpy pyqtgraph || {
        echo "[error] インストールに失敗しました。"
        read -n 1 -s -r -p "Enter で終了..."
        exit 1
    }
fi

# 触らずに使える前提: Live モード ON、最前面、スリープ抑制
exec "$PY" scatt_gui.py --top "$@"

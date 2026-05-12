# SCATT データ解析ツール群
# 使い方: make help

PYTHON ?= /opt/homebrew/bin/python3.10
DB     ?= $(HOME)/Library/Application Support/SCATT Electronics/Scatt Expert/storage.dat

.PHONY: help gui watch watch-full check install clean concurrency-test ble-scan app app-clean app-sign

help:
	@echo "SCATT データ解析ツール"
	@echo ""
	@echo "  make gui                GUI ビューアを起動"
	@echo "  make watch              新規 trace をメタ情報のみ JSONL で表示"
	@echo "  make watch-full         新規 trace を samples 含めて JSONL で表示"
	@echo "  make concurrency-test   SCATT 起動中の並行読み出しを 60 秒間計測"
	@echo "  make ble-scan           周囲の BLE 心拍デバイスを 10 秒スキャン"
	@echo ""
	@echo "  make app                .app バンドルをビルド (dist/SCATT Prone Analyzer.app)"
	@echo "  make app-sign           ビルド後の .app に ad-hoc 署名"
	@echo "  make app-clean          build/ dist/ を削除"
	@echo "  make check              環境チェック (Python・依存・DB の存在)"
	@echo "  make install            依存パッケージ (PyQt6, numpy) をインストール"
	@echo "  make clean              __pycache__ を削除"
	@echo ""
	@echo "PYTHON=... DB=... で上書き可"

gui:
	@$(PYTHON) scatt_gui.py

watch:
	@$(PYTHON) scatt_watch.py --no-samples

watch-full:
	@$(PYTHON) scatt_watch.py

check:
	@echo "--- python ---"
	@$(PYTHON) --version
	@echo "--- 依存 ---"
	@$(PYTHON) -c "import PyQt6.QtCore as c; print('  PyQt6', c.PYQT_VERSION_STR)" 2>/dev/null || echo "  PyQt6: not installed"
	@$(PYTHON) -c "import numpy as n; print('  numpy', n.__version__)" 2>/dev/null || echo "  numpy: not installed"
	@echo "--- db ---"
	@if [ -e "$(DB)" ]; then \
	    SZ=$$(stat -f%z "$(DB)"); \
	    echo "  found: $(DB) ($$SZ bytes)"; \
	else \
	    echo "  NOT FOUND: $(DB)"; \
	fi

install:
	$(PYTHON) -m pip install --user PyQt6 numpy pyqtgraph

concurrency-test:
	@$(PYTHON) scatt_concurrency_test.py

ble-scan:
	@$(PYTHON) scatt_ble_scan.py

# ----- 配布 (.app) -----
app: app-clean
	$(PYTHON) -m pip install --user py2app
	$(PYTHON) setup_app.py py2app
	@echo ""
	@echo "Build complete: dist/SCATT Prone Analyzer.app"
	@echo "ad-hoc 署名する場合: make app-sign"
	@echo "DMG にする場合: hdiutil create -volname 'SCATT Prone Analyzer' \\"
	@echo "  -srcfolder 'dist/SCATT Prone Analyzer.app' -ov -format UDZO dist/scatt-prone-analyzer.dmg"

app-sign:
	@codesign --force --deep --sign - "dist/SCATT Prone Analyzer.app"
	@echo "ad-hoc signed."

app-clean:
	rm -rf build dist
	rm -f *.egg-info

clean:
	rm -rf __pycache__

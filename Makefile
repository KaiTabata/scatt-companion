# SCATT データ解析ツール群
# 使い方: make help

PYTHON ?= /opt/homebrew/bin/python3.10
DB     ?= $(HOME)/Library/Application Support/SCATT Electronics/Scatt Expert/storage.dat

.PHONY: help gui watch watch-full check install clean concurrency-test ble-scan app app-clean app-sign icon dmg test

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
	@echo "  make dmg                .app を DMG にまとめる (dist/scatt-prone-analyzer-VER.dmg)"
	@echo "  make app-clean          build/ dist/ を削除"
	@echo "  make check              環境チェック (Python・依存・DB の存在)"
	@echo "  make install            依存パッケージ (PyQt6, numpy) をインストール"
	@echo "  make test               pytest で単体テスト実行 (tests/)"
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
app: app-clean icon
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

icon:
	$(PYTHON) make_icon.py

# .app から DMG を生成 (ad-hoc 署名前提)
VERSION := $(shell $(PYTHON) -c "import re; v=re.search(r'version *= *\"([^\"]+)\"', open('pyproject.toml').read()); print(v.group(1) if v else 'dev')")
dmg:
	@test -d "dist/SCATT Prone Analyzer.app" || (echo "先に make app を実行してください"; exit 1)
	rm -f dist/scatt-prone-analyzer-*.dmg
	hdiutil create -volname "SCATT Prone Analyzer" \
		-srcfolder "dist/SCATT Prone Analyzer.app" \
		-ov -format UDZO \
		"dist/scatt-prone-analyzer-$(VERSION).dmg"
	@echo ""
	@echo "DMG 完成: dist/scatt-prone-analyzer-$(VERSION).dmg"
	@ls -la "dist/scatt-prone-analyzer-$(VERSION).dmg"

test:
	@$(PYTHON) -m pip install --user --quiet pytest
	@$(PYTHON) -m pytest tests/ -v

clean:
	rm -rf __pycache__ tests/__pycache__ .pytest_cache

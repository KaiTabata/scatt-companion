"""py2app セットアップ: macOS .app バンドルを生成する。

ビルド方法:
  /opt/homebrew/bin/python3.10 -m pip install --user py2app
  /opt/homebrew/bin/python3.10 setup_app.py py2app

または:
  make app

生成物: dist/SCATT Companion.app
未署名なので初回起動時に macOS Gatekeeper の警告が出る:
  右クリック → 開く → 警告ダイアログで「開く」

ad-hoc 署名済みにするなら、ビルド後:
  codesign --force --deep --sign - "dist/SCATT Companion.app"
"""

from setuptools import setup

APP = ["scatt_gui.py"]
APP_NAME = "SCATT Companion"
DATA_FILES = [
    "README.html",
    "LICENSE",
]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/icon.icns",
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.scatt-companion.app",
        "CFBundleVersion": "0.4.0",
        "CFBundleShortVersionString": "0.4.0",
        "NSHumanReadableCopyright": "Apache License 2.0",
        # macOS 権限の説明
        "NSBluetoothAlwaysUsageDescription":
            "心拍計 (Apple Watch / 胸ベルト) を BLE で受信して shot ごとの心拍データを記録します。",
        "NSBluetoothPeripheralUsageDescription":
            "心拍計の BLE 通信に使用します。",
        # 最低 macOS バージョン
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        # ファイル拡張子の関連付けは不要 (SCATT 側 storage.dat を直接読みに行く)
    },
    "packages": ["PyQt6", "numpy", "pyqtgraph"],
    "includes": [
        "scatt_analysis",
        "scatt_heart",
        "scatt_storage",
        "scatt_feedback",
        "scatt_watch",
        "bleak",
        "collections",
        "sqlite3",
    ],
    "excludes": [
        "matplotlib", "scipy", "PyQt5", "PySide2", "PySide6",
        "test", "tests", "pytest",
        # WebEngine は 200MB 級で重く、本アプリでは不要
        "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngine", "PyQt6.QtWebChannel",
        # 他にも使わない Qt モジュール
        "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
        "PyQt6.Qt3DCore", "PyQt6.Qt3DRender",
    ],
    # bleak が ObjC 系を使うので site-packages を取り込む
    "site_packages": True,
}

setup(
    app=APP,
    name=APP_NAME,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

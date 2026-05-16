# PyInstaller spec — SCATT Companion (Windows / Linux ビルド用)
#
# Windows ビルド:
#   pyinstaller scatt_companion.spec --clean
#
# 生成物: dist/SCATT Companion/  (windowed app + 依存 dll/dylib)
# Windows では NSIS で installer 化 (build_windows.nsi)

import sys
from pathlib import Path

block_cipher = None

# プロジェクトルート (spec があるディレクトリ)
ROOT = Path(SPECPATH)

# ライセンス・README 同梱
datas = [
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "README.html"), "."),
]

# 隠し依存 (PyInstaller が自動検出しにくいもの)
hiddenimports = [
    "pyqtgraph",
    "numpy",
    "scatt_analysis",
    "scatt_heart",
    "scatt_storage",
    "scatt_feedback",
    "scatt_export",
    "scatt_pdf",
    "scatt_logging",
    "scatt_backup",
    "scatt_target",
    "scatt_update",
    "scatt_auto_update",
    "scatt_profile",
    "scatt_home",
    "scatt_paths",
    "scatt_metric_docs",
    "scatt_modes",
    "scatt_level_tab",
    "scatt_i18n",
]

# Windows のみ bleak (BLE 心拍) のバックエンドを明示
if sys.platform.startswith("win"):
    hiddenimports += [
        "bleak.backends.winrt",
        "bleak.backends.winrt.client",
        "bleak.backends.winrt.scanner",
    ]

a = Analysis(
    [str(ROOT / "scatt_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 不要な大物を除外
        "tkinter",
        "matplotlib",
        "scipy",
        "PIL",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows: アイコンを使う ( assets/icon.ico を CI で生成する想定 )
icon_path = ROOT / "assets" / "icon.ico"
icon_arg = str(icon_path) if icon_path.exists() else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SCATT Companion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # GUI app: コンソールウィンドウ非表示
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SCATT Companion",
)

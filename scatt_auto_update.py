"""自動アップデート機構 (macOS .app バンドル / Windows NSIS インストーラ)。

起動時に公開 manifest.json を fetch し、新版があればダイアログで通知。
ユーザーが「今すぐ更新」を選ぶと OS 対応のインストーラをテンポラリにダウンロードし、
自己更新スクリプト (Mac: bash / Win: BAT) を spawn してアプリを終了する。
スクリプトは親プロセスの終了を待ってから:
- Mac: DMG をマウントして /Applications/ の旧 .app を新版に置き換え、新版を起動
- Win: NSIS インストーラ .exe を非サイレント起動 (Finish で自動起動)

依存:
- PyQt6 (QThread, pyqtSignal)
- Mac: hdiutil / xattr / open (ad-hoc 署名 + quarantine 強制解除)
- Win: cmd.exe / tasklist

manifest.json 形式 (docs/manifest.json):
  {
    "latest_version": "0.4.12",
    "url":     "https://.../scatt-companion-0.4.12.dmg",   # Mac 旧クライアント互換
    "mac_url": "https://.../scatt-companion-0.4.12.dmg",   # v0.4.12+ Mac 用
    "win_url": "https://.../SCATT-Companion-Setup-0.4.12.exe",  # v0.4.12+ Win 用
    "notes": "..."
  }
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


DEFAULT_MANIFEST_URL = "https://kaitabata.github.io/scatt-analyzer/manifest.json"


def parse_version(v: str) -> tuple:
    """'v0.4.9' / '0.4.9' → (0, 4, 9). 数値化できない要素は 0 として扱う。"""
    parts: list[int] = []
    for p in v.strip().lstrip("v").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def current_platform() -> str:
    """実行プラットフォームを返す。

    "mac" — macOS の py2app バンドル (.app)
    "win" — Windows の PyInstaller bundled exe
    "dev" — 上記以外 (生 Python 実行、Linux 等)
    """
    try:
        if sys.platform == "darwin":
            exe = os.path.realpath(sys.executable or "")
            argv0 = os.path.realpath(sys.argv[0] if sys.argv else "")
            if "SCATT Companion.app" in exe or "SCATT Companion.app" in argv0:
                return "mac"
            return "dev"
        if sys.platform.startswith("win"):
            # PyInstaller bundled は frozen=True かつ _MEIPASS 属性を持つ
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                return "win"
            return "dev"
    except Exception:
        pass
    return "dev"


def is_bundle_app() -> bool:
    """bundled (Mac .app / Win PyInstaller) なら True、生 Python 実行なら False。"""
    return current_platform() in {"mac", "win"}


def select_url_for_platform(data: dict, platform: str) -> str:
    """manifest 辞書から現プラットフォーム用の URL を選ぶ。

    - Win: win_url のみ (旧 `url` は Mac DMG なので fallback 不可)
    - Mac/dev: mac_url → 旧 `url` の順で fallback
    """
    mac_url = str(data.get("mac_url", "")).strip()
    win_url = str(data.get("win_url", "")).strip()
    legacy_url = str(data.get("url", "")).strip()
    if platform == "win":
        return win_url
    return mac_url or legacy_url


class UpdateChecker(QThread):
    """manifest を fetch して新版有無を通知する QThread。"""

    update_available = pyqtSignal(str, str, str)  # latest_version, installer_url, notes
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, current_version: str, manifest_url: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.manifest_url = manifest_url

    def run(self):
        try:
            req = urllib.request.Request(
                self.manifest_url,
                headers={"User-Agent": f"scatt-companion/{self.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            latest = str(data.get("latest_version", "")).strip()
            notes = str(data.get("notes", "")).strip()
            url = select_url_for_platform(data, current_platform())
            if not latest:
                self.error.emit("manifest が不正です (latest_version が無い)")
                return
            if not url:
                self.error.emit("manifest にこの OS 向けのインストーラ URL がありません")
                return
            if parse_version(latest) > parse_version(self.current_version):
                self.update_available.emit(latest, url, notes)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


def _local_filename_for_url(url: str, pid: int) -> str:
    """URL 拡張子からテンポラリのファイル名を決める (.exe / .dmg)。"""
    ext = ".exe" if url.lower().split("?")[0].endswith(".exe") else ".dmg"
    return f"scatt-companion-update-{pid}{ext}"


class Downloader(QThread):
    """インストーラ (DMG / EXE) をテンポラリディレクトリにダウンロードする QThread。

    progress(received, total) を逐次発火、完了時 done(local_path) を 1 回発火。
    cancel() でループを抜けて部分ファイルを削除する。
    """

    progress = pyqtSignal(int, int)  # received_bytes, total_bytes
    done = pyqtSignal(str)           # local file path
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        local: Path | None = None
        try:
            tmpdir = Path(tempfile.gettempdir())
            local = tmpdir / _local_filename_for_url(self.url, os.getpid())
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "scatt-companion-updater"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                total = int(r.headers.get("Content-Length", "0") or 0)
                received = 0
                with open(local, "wb") as f:
                    while True:
                        if self._cancel:
                            f.close()
                            try:
                                local.unlink()
                            except Exception:
                                pass
                            return
                        chunk = r.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        self.progress.emit(received, total)
            self.done.emit(str(local))
        except Exception as e:
            if local is not None:
                try:
                    local.unlink()
                except Exception:
                    pass
            self.error.emit(f"{type(e).__name__}: {e}")


def install_and_relaunch(installer_path: str) -> None:
    """インストーラを spawn して新版に入れ替え、新版を起動する。

    OS によって処理は別物だが、共通点は「親プロセス (= 現アプリ) の終了を待って
    から動くスクリプトを spawn する」こと。これにより呼び出し側 (scatt_gui) は
    `install_and_relaunch()` の直後に QApplication.quit() してよい。
    """
    plat = current_platform()
    if plat == "win":
        _install_and_relaunch_win(installer_path)
    else:
        _install_and_relaunch_mac(installer_path)


def _install_and_relaunch_mac(dmg_path: str) -> None:
    pid = os.getpid()
    tmpdir = Path(tempfile.gettempdir())
    log_path = tmpdir / f"scatt_update_{pid}.log"
    script_path = tmpdir / f"scatt_update_{pid}.sh"

    dmg_q = shlex.quote(dmg_path)
    log_q = shlex.quote(str(log_path))

    script = f"""#!/bin/bash
exec > {log_q} 2>&1
set -x

# 親プロセス (現アプリ) の終了を待つ (最大 20 秒)
for i in $(seq 1 200); do
    if ! kill -0 {pid} 2>/dev/null; then
        break
    fi
    sleep 0.1
done
sleep 0.5

# DMG をマウント (ブラウザ表示・確認スキップ)
MOUNT_OUT=$(hdiutil attach -nobrowse -noverify -noautoopen {dmg_q})
echo "$MOUNT_OUT"
MOUNT=$(echo "$MOUNT_OUT" | grep '/Volumes/' | tail -1 | sed 's|.*/Volumes/|/Volumes/|' | sed 's|[[:space:]]*$||')

if [ -z "$MOUNT" ] || [ ! -d "$MOUNT/SCATT Companion.app" ]; then
    osascript -e 'display dialog "更新の DMG をマウントできませんでした。手動で DMG を開いてインストールしてください。" buttons {{"OK"}} default button "OK" with icon caution'
    exit 1
fi

# 既存版を削除して新版をコピー
rm -rf "/Applications/SCATT Companion.app"
cp -R "$MOUNT/SCATT Companion.app" "/Applications/SCATT Companion.app"
xattr -dr com.apple.quarantine "/Applications/SCATT Companion.app" 2>/dev/null || true

# アンマウント (失敗しても続行)
hdiutil detach "$MOUNT" >/dev/null 2>&1 || true

# DMG とインストーラ自身を削除
rm -f {dmg_q}

# 新版を起動
open "/Applications/SCATT Companion.app"
"""

    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o755)

    # nohup 相当: start_new_session で親と切り離す
    subprocess.Popen(
        ["/bin/bash", str(script_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _install_and_relaunch_win(exe_path: str) -> None:
    """Windows: 親プロセス終了を待って NSIS インストーラを非サイレント起動する BAT を spawn。

    NSIS インストーラの MUI_FINISHPAGE_RUN により Finish ボタンで新版が自動起動する。
    インストーラ自身と BAT は完了後に自己削除する。
    """
    pid = os.getpid()
    tmpdir = Path(tempfile.gettempdir())
    log_path = tmpdir / f"scatt_update_{pid}.log"
    bat_path = tmpdir / f"scatt_update_{pid}.bat"

    # BAT 内で参照するパスは " " で囲んで空白対応。^ などのエスケープは BAT 文法に従う。
    bat = (
        "@echo off\r\n"
        f'set "LOG={log_path}"\r\n'
        f'set "EXE={exe_path}"\r\n'
        f'set "PARENT_PID={pid}"\r\n'
        '> "%LOG%" 2>&1 (\r\n'
        '  echo waiting for parent %PARENT_PID%\r\n'
        '  set /a tries=0\r\n'
        '  :waitloop\r\n'
        '  tasklist /FI "PID eq %PARENT_PID%" 2>nul | find "%PARENT_PID%" >nul\r\n'
        '  if errorlevel 1 goto run\r\n'
        '  set /a tries+=1\r\n'
        '  if %tries% GEQ 200 goto run\r\n'
        '  timeout /t 1 /nobreak >nul\r\n'
        '  goto waitloop\r\n'
        '  :run\r\n'
        '  echo launching installer\r\n'
        '  "%EXE%"\r\n'
        '  echo installer exited %errorlevel%\r\n'
        '  del "%EXE%"\r\n'
        ')\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )

    # Windows コンソール BAT は CP932 (Shift-JIS) で書き出すのが無難。
    # 内容は ASCII のみなので utf-8 でも動くが、安全策として cp932 で。
    bat_path.write_text(bat, encoding="cp932", errors="replace")

    # Windows: DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP で親と切り離す
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )

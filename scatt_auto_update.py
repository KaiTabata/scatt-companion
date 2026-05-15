"""自動アップデート機構 (macOS / .app バンドル限定)。

起動時に公開 manifest.json を fetch し、新版があればダイアログで通知。
ユーザーが「今すぐ更新」を選ぶと DMG をテンポラリにダウンロードし、
自己更新インストーラ (sh スクリプト) を spawn してアプリを終了。
インストーラが /Applications/ の旧 .app を新版に置き換え、新版を起動する。

依存:
- PyQt6 (QThread, pyqtSignal)
- macOS hdiutil / xattr / open
- Apple Developer Program 未加入のため ad-hoc 署名 + quarantine 強制解除

manifest.json 形式 (docs/manifest.json):
  {
    "latest_version": "0.4.9",
    "url": "https://.../scatt-companion-0.4.9.dmg",
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


def is_bundle_app() -> bool:
    """py2app バンドルから起動されているかを判定。

    開発実行 (`python scatt_gui.py`) では自動更新が無意味なので False を返す。
    """
    try:
        exe = os.path.realpath(sys.executable or "")
        argv0 = os.path.realpath(sys.argv[0] if sys.argv else "")
        marker = "SCATT Companion.app"
        return marker in exe or marker in argv0
    except Exception:
        return False


class UpdateChecker(QThread):
    """manifest を fetch して新版有無を通知する QThread。"""

    update_available = pyqtSignal(str, str, str)  # latest_version, dmg_url, notes
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
            url = str(data.get("url", "")).strip()
            notes = str(data.get("notes", "")).strip()
            if not latest or not url:
                self.error.emit("manifest が不正です (latest_version / url が無い)")
                return
            if parse_version(latest) > parse_version(self.current_version):
                self.update_available.emit(latest, url, notes)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class Downloader(QThread):
    """DMG をテンポラリディレクトリにダウンロードする QThread。

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
            local = tmpdir / f"scatt-companion-update-{os.getpid()}.dmg"
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


def install_and_relaunch(dmg_path: str) -> None:
    """DMG をマウントして /Applications/ に入れ替え、新版を起動する。

    インストール処理はサブプロセスのシェルスクリプトに委ねる。スクリプトは
    親プロセス (= 現アプリ) の終了を待ってから動き出すので、本関数を呼んだら
    すぐに QApplication.quit() してよい。
    """
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

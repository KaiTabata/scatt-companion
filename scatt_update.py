"""アップデート通知。

GitHub Releases API は private repo 非対応のため、
公開予定の manifest URL (JSON) を取りに行く構成とする。

期待される JSON 形式:
  {
    "latest_version": "0.3.0",
    "url":  "https://github.com/.../releases/download/v0.3.0/scatt-prone-analyzer-0.3.0.dmg",
    "notes": "新機能 ..."
  }

manifest URL は Settings から指定可。空 ("") = チェック無効。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Optional


def _parse_version(v: str) -> tuple[int, int, int]:
    """'0.2.0' → (0, 2, 0)。失敗時 (0, 0, 0)。pre-release は無視。"""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(v).strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def check_for_update(current_version: str,
                     manifest_url: str,
                     timeout_s: float = 5.0) -> Optional[dict]:
    """manifest をフェッチして更新有無を返す。

    返り値:
      None                                  チェック不能 (URL 未設定 / ネット不通)
      {"available": False, "latest": ...}   最新
      {"available": True, "latest": ..., "url": ..., "notes": ...}  更新あり
    """
    if not manifest_url or not manifest_url.startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(
            manifest_url,
            headers={"User-Agent": f"scatt-prone-analyzer/{current_version}"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError):
        return None
    latest = str(data.get("latest_version", "")).strip()
    if not latest:
        return None
    cur_t = _parse_version(current_version)
    latest_t = _parse_version(latest)
    available = latest_t > cur_t
    result = {
        "available": available,
        "latest": latest,
        "current": current_version,
    }
    if available:
        result["url"] = data.get("url", "")
        result["notes"] = data.get("notes", "")
    return result

"""scatt_auto_update: バージョン解析と OS 別 URL 選択ロジック。

実 manifest 取得や Qt 周りには触れない (純粋ロジックのみ)。
"""

import scatt_auto_update as AU


def test_parse_version_basic():
    assert AU.parse_version("0.4.11") == (0, 4, 11)
    assert AU.parse_version("v0.4.11") == (0, 4, 11)
    assert AU.parse_version("0.4.11-beta") == (0, 4, 0)  # beta → 0
    assert AU.parse_version("") == (0,)


def test_parse_version_ordering():
    # 文字列比較なら 0.4.11 < 0.4.2 になるが、tuple なら逆転しない
    assert AU.parse_version("0.4.11") > AU.parse_version("0.4.2")
    assert AU.parse_version("0.5.0") > AU.parse_version("0.4.99")


def test_select_url_for_platform_new_manifest():
    """新フォーマット (mac_url / win_url) を各 OS 向けに正しく選ぶ。"""
    data = {
        "latest_version": "0.4.12",
        "url": "https://x/mac-legacy.dmg",
        "mac_url": "https://x/mac-new.dmg",
        "win_url": "https://x/win.exe",
    }
    assert AU.select_url_for_platform(data, "mac") == "https://x/mac-new.dmg"
    assert AU.select_url_for_platform(data, "win") == "https://x/win.exe"
    # dev は Mac 扱い
    assert AU.select_url_for_platform(data, "dev") == "https://x/mac-new.dmg"


def test_select_url_for_platform_legacy_manifest():
    """旧フォーマット (url のみ) は Mac として fallback、Win は空。"""
    data = {
        "latest_version": "0.4.11",
        "url": "https://x/mac.dmg",
    }
    assert AU.select_url_for_platform(data, "mac") == "https://x/mac.dmg"
    assert AU.select_url_for_platform(data, "win") == ""  # Win は legacy にフォールバックしない
    assert AU.select_url_for_platform(data, "dev") == "https://x/mac.dmg"


def test_select_url_for_platform_mac_prefers_new_over_legacy():
    """mac_url と url が両方ある場合は mac_url を優先する。"""
    data = {
        "mac_url": "https://x/new.dmg",
        "url": "https://x/old.dmg",
    }
    assert AU.select_url_for_platform(data, "mac") == "https://x/new.dmg"


def test_select_url_for_platform_empty():
    assert AU.select_url_for_platform({}, "mac") == ""
    assert AU.select_url_for_platform({}, "win") == ""


def test_local_filename_for_url_extension():
    """URL 拡張子から保存ファイル名の拡張子を決める。"""
    assert AU._local_filename_for_url("https://x/foo.dmg", 123).endswith(".dmg")
    assert AU._local_filename_for_url("https://x/foo.exe", 123).endswith(".exe")
    assert AU._local_filename_for_url("https://x/foo.EXE", 123).endswith(".exe")
    # クエリ付き URL
    assert AU._local_filename_for_url("https://x/foo.exe?token=abc", 123).endswith(".exe")
    # 未知拡張子は .dmg にフォールバック (Mac 想定の歴史的経緯)
    assert AU._local_filename_for_url("https://x/foo", 123).endswith(".dmg")


def test_current_platform_returns_known_value():
    """戻り値は "mac" / "win" / "dev" のいずれか。"""
    assert AU.current_platform() in {"mac", "win", "dev"}


def test_is_bundle_app_consistent_with_current_platform():
    assert AU.is_bundle_app() == (AU.current_platform() in {"mac", "win"})

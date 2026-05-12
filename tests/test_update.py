"""scatt_update: バージョン比較ロジック + URL 未設定時の挙動。"""

import scatt_update as UPD


def test_parse_version():
    assert UPD._parse_version("0.2.0") == (0, 2, 0)
    assert UPD._parse_version("v1.2.3") == (1, 2, 3)
    assert UPD._parse_version("1.0") == (0, 0, 0)
    assert UPD._parse_version("") == (0, 0, 0)
    assert UPD._parse_version("invalid") == (0, 0, 0)


def test_version_ordering():
    """0.2.10 > 0.2.9 (文字列比較ではバグる範囲)。"""
    assert UPD._parse_version("0.2.10") > UPD._parse_version("0.2.9")
    assert UPD._parse_version("1.0.0") > UPD._parse_version("0.99.99")


def test_check_for_update_empty_url():
    """URL 空ならネット叩かずに None。"""
    assert UPD.check_for_update("0.2.0", "") is None
    assert UPD.check_for_update("0.2.0", None) is None


def test_check_for_update_invalid_url():
    """ファイルスキームや空白文字列は弾く。"""
    assert UPD.check_for_update("0.2.0", "file:///etc/passwd") is None
    assert UPD.check_for_update("0.2.0", "not-a-url") is None

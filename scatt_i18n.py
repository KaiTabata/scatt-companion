"""簡易 i18n: SETTINGS['ui/language'] (ja|en) を見て翻訳キーを引く。

使い方::

    from scatt_i18n import t, set_language
    set_language("en")
    t("tab.home")  # -> "Home"

新規キー追加時は ja / en の両方に必ず登録する。
未登録キーはキー文字列をそのまま返す (デバッグしやすいよう)。
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_LANG = "ja"
SUPPORTED = ("ja", "en")

_current_lang: str = DEFAULT_LANG


TRANSLATIONS: dict[str, dict[str, str]] = {
    # ===== タブ ラベル =====
    "tab.home":       {"ja": "ホーム",     "en": "Home"},
    "tab.dashboard":  {"ja": "Dashboard",  "en": "Dashboard"},
    "tab.sessions":   {"ja": "Sessions",   "en": "Sessions"},
    "tab.shots":      {"ja": "Shots",      "en": "Shots"},
    "tab.help":       {"ja": "Help",       "en": "Help"},
    "tab.graphs":     {"ja": "グラフ",     "en": "Graphs"},
    "tab.settings":   {"ja": "Settings",   "en": "Settings"},
    # サブタブ
    "subtab.overview": {"ja": "Overview", "en": "Overview"},
    "subtab.recoil":   {"ja": "Recoil",   "en": "Recoil"},
    "subtab.cant":     {"ja": "Cant",     "en": "Cant"},
    "subtab.drift":    {"ja": "Drift",    "en": "Drift"},
    "subtab.spectrum": {"ja": "Spectrum", "en": "Spectrum"},

    # ===== About =====
    "about.title":   {"ja": "About — SCATT Companion",
                      "en": "About — SCATT Companion"},
    "about.tagline": {"ja": "射撃トレーニングを「数字」で読み解く",
                      "en": "Read shooting training in numbers"},
    "about.developer": {"ja": "開発: Kai Tabata + Claude Opus 4.7",
                        "en": "Developed by Kai Tabata + Claude Opus 4.7"},
    "about.license": {"ja": "ライセンス: Apache 2.0",
                      "en": "License: Apache 2.0"},
    "about.subtitle": {
        "ja": "伏射 / 立射対応の SCATT Expert 補助分析ツール",
        "en": "Unofficial SCATT Expert analysis tool (Prone / AR support)",
    },
    "about.disclaimer": {
        "ja": "SCATT Electronics の <b>公式ソフトではありません</b>。"
              "SCATT が保存した自身の射撃データをローカルで読み取って解析する非公式ツールです。",
        "en": "This is <b>not</b> an official SCATT Electronics product. "
              "It is an unofficial tool that reads your locally-stored SCATT data.",
    },
    "about.repository": {"ja": "Repository", "en": "Repository"},
    "about.license_label": {"ja": "License", "en": "License"},
    "about.log_label":     {"ja": "ログ", "en": "Log"},
    "about.data_label":    {"ja": "データ", "en": "Data"},
    "about.trademark": {
        "ja": "SCATT, SCATT Expert は SCATT Electronics の商標です。"
              "本ソフトは公式ではない補助ツールであり、SCATT Electronics と関係ありません。",
        "en": "SCATT and SCATT Expert are trademarks of SCATT Electronics. "
              "This software is an unofficial helper tool and is not affiliated with SCATT Electronics.",
    },
    # 閉じるボタン
    "common.close": {"ja": "閉じる", "en": "Close"},

    # ===== Settings 主要セクション =====
    "settings.general":  {"ja": "全般",     "en": "General"},
    "settings.language": {"ja": "表示言語", "en": "Language"},
    "settings.language.ja": {"ja": "日本語", "en": "Japanese"},
    "settings.language.en": {"ja": "English", "en": "English"},
    "settings.discipline": {"ja": "種目",   "en": "Discipline"},
    "settings.mode":     {"ja": "モード",   "en": "Mode"},
    "settings.layout":   {"ja": "レイアウト", "en": "Layout"},
    "settings.thresholds": {"ja": "しきい値", "en": "Thresholds"},
    "settings.behavior": {"ja": "動作",      "en": "Behavior"},
    "settings.tabs":     {"ja": "タブの表示", "en": "Tabs visibility"},

    # ===== 種目 =====
    "discipline.rifle_50m": {"ja": "50m ライフル", "en": "50m Rifle"},
    "discipline.rifle_10m": {"ja": "10m エアライフル", "en": "10m Air Rifle"},
    "discipline.pistol_10m": {"ja": "10m エアピストル", "en": "10m Air Pistol"},

    # ===== モード =====
    "mode.prone": {"ja": "伏射", "en": "Prone"},
    "mode.ar":    {"ja": "AR (10m エアライフル)", "en": "AR (10m Air Rifle)"},
    "mode.hold_practice": {"ja": "ホールド練習", "en": "Hold Practice"},

    # ===== 言語切替の再起動メッセージ =====
    "lang.restart_required.title": {
        "ja": "再起動が必要です",
        "en": "Restart required",
    },
    "lang.restart_required.body": {
        "ja": "言語の変更は次回起動時に反映されます。",
        "en": "Language change will take effect after restart.",
    },
}


def set_language(lang: Optional[str]) -> None:
    """カレント言語を切替える (ja/en 以外は ja にフォールバック)。"""
    global _current_lang
    if lang in SUPPORTED:
        _current_lang = lang
    else:
        _current_lang = DEFAULT_LANG
        if lang:
            log.warning("unsupported language %r, falling back to %s", lang, DEFAULT_LANG)


def current_language() -> str:
    return _current_lang


def t(key: str) -> str:
    """key を現在の言語で翻訳。未登録ならキー文字列をそのまま返す。"""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(_current_lang) or entry.get(DEFAULT_LANG) or key

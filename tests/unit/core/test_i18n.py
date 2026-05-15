"""Unit tests for src/i18n.py"""

import pytest
import importlib

import src.i18n as i18n_mod
from src.i18n import tr, set_language, get_language, get_available_languages


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_language():
    """Always restore English after each test so tests don't bleed state."""
    yield
    set_language("en")


# ──────────────────────────────────────────────────────────────────────────────
# set_language / get_language
# ──────────────────────────────────────────────────────────────────────────────

class TestSetGetLanguage:
    def test_default_is_english(self):
        assert get_language() == "en"

    def test_switch_to_zhtw(self):
        set_language("zh_TW")
        assert get_language() == "zh_TW"

    def test_switch_back_to_en(self):
        set_language("zh_TW")
        set_language("en")
        assert get_language() == "en"

    def test_unsupported_code_is_ignored(self):
        set_language("fr")
        assert get_language() == "en"

    def test_empty_string_is_ignored(self):
        set_language("")
        assert get_language() == "en"


# ──────────────────────────────────────────────────────────────────────────────
# get_available_languages
# ──────────────────────────────────────────────────────────────────────────────

class TestAvailableLanguages:
    def test_returns_list_of_tuples(self):
        langs = get_available_languages()
        assert isinstance(langs, list)
        assert len(langs) >= 2

    def test_contains_english_and_zhtw(self):
        codes = [code for code, _ in get_available_languages()]
        assert "en" in codes
        assert "zh_TW" in codes

    def test_all_entries_are_two_tuples(self):
        for entry in get_available_languages():
            assert len(entry) == 2


# ──────────────────────────────────────────────────────────────────────────────
# tr() – translation look-up
# ──────────────────────────────────────────────────────────────────────────────

class TestTr:
    def test_en_returns_key_unchanged(self):
        set_language("en")
        assert tr("Load Image") == "Load Image"
        assert tr("Unknown Key XYZ") == "Unknown Key XYZ"

    def test_zhtw_translates_known_key(self):
        set_language("zh_TW")
        result = tr("Load Image")
        assert result == "載入圖片"

    def test_zhtw_falls_back_to_key_for_missing(self):
        set_language("zh_TW")
        key = "This key definitely does not exist 12345"
        assert tr(key) == key

    def test_menu_items_translate_correctly(self):
        set_language("zh_TW")
        assert tr("Edit") == "編輯"
        assert tr("File") == "檔案"
        assert tr("Settings") == "設定"
        assert tr("Help") == "說明"

    def test_tab_names_translate(self):
        set_language("zh_TW")
        assert "合成器" in tr("🎬 Composer")
        assert "批次處理" in tr("⚡ Batch Processor")

    def test_all_zh_tw_values_are_non_empty(self):
        """Sanity-check: every translated value should be a non-empty string."""
        translations = i18n_mod._TRANSLATIONS.get("zh_TW", {})
        for key, value in translations.items():
            assert isinstance(value, str) and len(value) > 0, (
                f"Empty translation for key: {key!r}"
            )

    def test_tr_is_idempotent_in_en(self):
        """Calling tr() multiple times with English must always return the key."""
        set_language("en")
        key = "Export GIF"
        assert tr(key) == tr(key) == key

    def test_language_switch_affects_tr_immediately(self):
        set_language("en")
        en_result = tr("Load Image")
        set_language("zh_TW")
        zh_result = tr("Load Image")
        assert en_result != zh_result
        assert zh_result == "載入圖片"

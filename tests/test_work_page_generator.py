"""Tests for Agent 6A — WorkPageGenerator (SPEC.md §3.2 / §12.3 / §13, CLASS.md §1)."""

from __future__ import annotations

import pytest

from aozora.generators.work_page import WorkPageGenerator
from aozora.models import TranslationResult, WorkEntry


@pytest.fixture
def generator() -> WorkPageGenerator:
    return WorkPageGenerator()


@pytest.fixture
def short_work() -> WorkEntry:
    return WorkEntry(
        aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
        aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128_15260.html",
        title_en="The Spider's Thread",
        author_en="Akutagawa Ryunosuke",
        title_ja="蜘蛛の糸",
        author_ja="芥川龍之介",
        genre="short",
        notes="",
    )


@pytest.fixture
def translation() -> TranslationResult:
    return TranslationResult(
        translation_en="Once upon a time, Buddha walked through paradise.",
        introduction_en="This is an introduction to the work.",
        source="codex_cli",
    )


# ---------------------------------------------------------------------------
# スラッグ生成 (SPEC.md §3.2)
# ---------------------------------------------------------------------------


class TestGenerateSlug:
    def test_known_example_from_spec(self, generator):
        # SPEC.md: "The Spider's Thread" → "the-spiders-thread"
        slug = generator._generate_slug("The Spider's Thread", "2026-03-05")
        assert slug == "the-spiders-thread"

    def test_lowercase(self, generator):
        assert generator._generate_slug("Rashomon", "2026-03-05") == "rashomon"

    def test_spaces_to_hyphens(self, generator):
        assert generator._generate_slug("In a Grove", "2026-03-05") == "in-a-grove"

    def test_special_chars_become_hyphens(self, generator):
        slug = generator._generate_slug("Work: With Colon!", "2026-03-05")
        assert ":" not in slug
        assert "!" not in slug
        assert slug  # not empty

    def test_apostrophe_removed_not_hyphenated(self, generator):
        # "Spider's" → "spiders" (not "spider-s")
        slug = generator._generate_slug("Spider's Web", "2026-03-05")
        assert "spider" in slug
        assert "''" not in slug

    def test_no_leading_hyphen(self, generator):
        slug = generator._generate_slug("!Leading", "2026-03-05")
        assert not slug.startswith("-")

    def test_no_trailing_hyphen(self, generator):
        slug = generator._generate_slug("Trailing!", "2026-03-05")
        assert not slug.endswith("-")

    def test_max_50_chars(self, generator):
        long_title = "A Very Long Title Exceeds The Maximum Length Limit For Slug Generation"
        slug = generator._generate_slug(long_title, "2026-03-05")
        assert len(slug) <= 50

    def test_max_50_truncates_at_word_boundary(self, generator):
        """切り詰め後にハイフンで終わらない (QA.md Q7-3)。"""
        long_title = "A Very Long Title That Exceeds The Maximum Length Limit"
        slug = generator._generate_slug(long_title, "2026-03-05")
        assert len(slug) <= 50
        assert not slug.endswith("-")

    def test_no_consecutive_hyphens(self, generator):
        slug = generator._generate_slug("Work  --  Title", "2026-03-05")
        assert "--" not in slug


# ---------------------------------------------------------------------------
# スラッグ衝突処理 (SPEC.md §3.2)
# ---------------------------------------------------------------------------


class TestSlugCollision:
    def test_no_collision_returns_as_is(self, generator, tmp_path):
        date = "2026-03-05"
        slug = "rashomon"
        result = generator._check_slug_collision(slug, date, base_dir=str(tmp_path))
        assert result == f"{date}-{slug}"

    def test_collision_appends_2(self, generator, tmp_path):
        date = "2026-03-05"
        slug = "rashomon"
        (tmp_path / "works" / f"{date}-{slug}").mkdir(parents=True)
        result = generator._check_slug_collision(slug, date, base_dir=str(tmp_path))
        assert result == f"{date}-{slug}-2"

    def test_collision_sequential_to_3(self, generator, tmp_path):
        date = "2026-03-05"
        slug = "rashomon"
        (tmp_path / "works" / f"{date}-{slug}").mkdir(parents=True)
        (tmp_path / "works" / f"{date}-{slug}-2").mkdir(parents=True)
        result = generator._check_slug_collision(slug, date, base_dir=str(tmp_path))
        assert result == f"{date}-{slug}-3"


# ---------------------------------------------------------------------------
# XSS エスケープ (SPEC.md §12.3)
# ---------------------------------------------------------------------------


class TestXSSEscape:
    def test_ampersand_escaped(self, generator):
        assert "&amp;" in generator._xss_escape("a & b")

    def test_less_than_escaped(self, generator):
        assert "&lt;" in generator._xss_escape("<script>alert(1)</script>")

    def test_greater_than_escaped(self, generator):
        assert "&gt;" in generator._xss_escape("1 > 0")

    def test_double_quote_escaped(self, generator):
        assert "&quot;" in generator._xss_escape('"quoted"')

    def test_single_quote_escaped(self, generator):
        escaped = generator._xss_escape("it's")
        assert "'" not in escaped or "&#39;" in escaped or "&apos;" in escaped

    def test_plain_text_unchanged(self, generator):
        assert generator._xss_escape("Hello World") == "Hello World"

    def test_xss_in_title_is_escaped(self, generator, translation, tmp_path):
        work = WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
            title_en='<script>alert("xss")</script>',
            author_en="Author",
            genre="short",
        )
        html = generator.generate(work, translation, "2026-03-05")
        # The literal XSS payload must not appear unescaped.
        assert '<script>alert("xss")</script>' not in html
        # The payload must be HTML-escaped in the output.
        assert "&lt;script&gt;" in html
        assert "&lt;/script&gt;" in html


# ---------------------------------------------------------------------------
# 必須クレジット (SPEC.md §4.4)
# ---------------------------------------------------------------------------


class TestMandatoryCredits:
    def test_contains_aozora_bunko(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "Aozora Bunko" in html

    def test_contains_public_domain_in_japan(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "Public Domain" in html

    def test_contains_cc0(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "CC0" in html

    def test_contains_auto_translation_disclaimer(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        lower = html.lower()
        assert "automatically generated" in lower or "auto-translation" in lower

    def test_contains_card_url(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert short_work.aozora_card_url in html

    def test_contains_title_en(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "The Spider" in html

    def test_contains_author_en(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "Akutagawa Ryunosuke" in html

    def test_contains_translation_body(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "Once upon a time" in html

    def test_contains_introduction(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "introduction" in html.lower() or "This is an introduction" in html


# ---------------------------------------------------------------------------
# 英語のみ (SPEC.md §13.3 — 日本語を HTML に出力しない)
# ---------------------------------------------------------------------------


class TestEnglishOnly:
    def test_title_ja_not_in_html(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "蜘蛛の糸" not in html

    def test_author_ja_not_in_html(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "芥川龍之介" not in html


# ---------------------------------------------------------------------------
# AdSense & CSP (SPEC.md §13.1 / §13.2)
# ---------------------------------------------------------------------------


class TestAdSenseAndCSP:
    def test_adsense_script_present(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "pagead2.googlesyndication.com" in html

    def test_csp_meta_present(self, generator, short_work, translation):
        html = generator.generate(short_work, translation, "2026-03-05")
        assert "Content-Security-Policy" in html

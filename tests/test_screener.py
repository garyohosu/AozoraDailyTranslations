"""Tests for Agent 1 — Screener (SPEC.md §4, CLASS.md §1)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from aozora.agents.screener import Screener
from aozora.models import WorkEntry


@pytest.fixture
def screener() -> Screener:
    return Screener()


@pytest.fixture
def short_work() -> WorkEntry:
    return WorkEntry(
        aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
        aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128_15260.html",
        title_en="Rashomon",
        author_en="Akutagawa Ryunosuke",
        genre="short",
    )


# ---------------------------------------------------------------------------
# パブリックドメインチェック
# ---------------------------------------------------------------------------

PUBLIC_DOMAIN_HTML = """
<html><body>
<div class="bibliographic_information">
<p>著作権保護期間満了</p>
<p>底本：　「羅生門・鼻」岩波文庫</p>
</div>
</body></html>
"""

PROTECTED_HTML = """
<html><body>
<div>この作品は著作権で保護されています</div>
</body></html>
"""

TRANSLATION_HTML = """
<html><body>
<div class="bibliographic_information">
<p>著作権保護期間満了</p>
<p>翻訳者：田中太郎</p>
<p>原作：ギ・ド・モーパッサン</p>
</div>
</body></html>
"""

ANNOTATION_HEAVY_HTML = "<html><body>" + "［＃注釈内容ここに］" * 60 + "</body></html>"


class TestPublicDomainCheck:
    def test_expired_copyright_is_public_domain(self, screener):
        assert screener._check_public_domain(PUBLIC_DOMAIN_HTML) is True

    def test_protected_work_is_not_public_domain(self, screener):
        assert screener._check_public_domain(PROTECTED_HTML) is False

    def test_unknown_status_defaults_false(self, screener):
        """判断できない場合はスキップ (SPEC.md §4.2 — Safety bias)。"""
        html = "<html><body><p>内容不明</p></body></html>"
        assert screener._check_public_domain(html) is False


# ---------------------------------------------------------------------------
# 翻訳作品検出 (SPEC.md §4.2 — 外国語翻訳はスキップ)
# ---------------------------------------------------------------------------


class TestTranslationWorkDetection:
    def test_original_japanese_work_not_detected(self, screener):
        assert screener._detect_translation_work(PUBLIC_DOMAIN_HTML) is False

    def test_foreign_translation_detected(self, screener):
        assert screener._detect_translation_work(TRANSLATION_HTML) is True

    def test_no_translation_indicator_returns_false(self, screener):
        html = "<html><body><p>芥川龍之介の作品</p></body></html>"
        assert screener._detect_translation_work(html) is False


# ---------------------------------------------------------------------------
# 注釈過多チェック (SPEC.md §4.2)
# ---------------------------------------------------------------------------


class TestAnnotationHeavyCheck:
    def test_normal_work_not_annotation_heavy(self, screener):
        assert screener._check_annotation_heavy(PUBLIC_DOMAIN_HTML) is False

    def test_many_annotations_is_heavy(self, screener):
        assert screener._check_annotation_heavy(ANNOTATION_HEAVY_HTML) is True

    def test_few_annotations_not_heavy(self, screener):
        html = "<html><body><p>本文。</p>［＃注釈1つ］</body></html>"
        assert screener._check_annotation_heavy(html) is False


# ---------------------------------------------------------------------------
# screen() 統合テスト (ScreenResult を返す)
# ---------------------------------------------------------------------------


class TestScreenMethod:
    def test_eligible_public_domain_original(self, screener, short_work):
        with patch.object(screener, "_fetch_card_html", return_value=PUBLIC_DOMAIN_HTML):
            result = screener.screen(short_work)
        assert result.status == "ELIGIBLE"
        assert result.reason == "" or result.reason is not None  # reason フィールドが存在する

    def test_ineligible_when_translation_work(self, screener, short_work):
        with patch.object(screener, "_fetch_card_html", return_value=TRANSLATION_HTML):
            result = screener.screen(short_work)
        assert result.status == "INELIGIBLE"
        assert result.reason  # reason は空でない

    def test_ineligible_when_protected(self, screener, short_work):
        with patch.object(screener, "_fetch_card_html", return_value=PROTECTED_HTML):
            result = screener.screen(short_work)
        assert result.status == "INELIGIBLE"

    def test_ineligible_when_annotation_heavy(self, screener, short_work):
        with patch.object(screener, "_fetch_card_html", return_value=ANNOTATION_HEAVY_HTML):
            result = screener.screen(short_work)
        assert result.status == "INELIGIBLE"

    def test_ineligible_when_us_distribution_risk(self, screener, short_work):
        with patch.object(
            screener, "_fetch_card_html", return_value=PUBLIC_DOMAIN_HTML
        ), patch.object(screener, "_check_public_domain", return_value=True), patch.object(
            screener, "_detect_translation_work", return_value=False
        ), patch.object(screener, "_check_annotation_heavy", return_value=False), patch.object(
            screener, "_check_us_distribution_risk", return_value=True
        ):
            result = screener.screen(short_work)
        assert result.status == "INELIGIBLE"
        assert result.reason

    def test_eligible_when_us_distribution_risk_false(self, screener, short_work):
        with patch.object(
            screener, "_fetch_card_html", return_value=PUBLIC_DOMAIN_HTML
        ), patch.object(screener, "_check_public_domain", return_value=True), patch.object(
            screener, "_detect_translation_work", return_value=False
        ), patch.object(screener, "_check_annotation_heavy", return_value=False), patch.object(
            screener, "_check_us_distribution_risk", return_value=False
        ):
            result = screener.screen(short_work)
        assert result.status == "ELIGIBLE"

    def test_ineligible_on_fetch_failure(self, screener, short_work):
        """ネットワークエラー時は安全側に倒して INELIGIBLE (SPEC.md §4.2 — safety bias)。"""
        with patch.object(screener, "_fetch_card_html", side_effect=Exception("Network error")):
            result = screener.screen(short_work)
        assert result.status == "INELIGIBLE"
        assert "error" in result.reason.lower() or result.reason

    def test_screen_result_has_status_and_reason(self, screener, short_work):
        with patch.object(screener, "_fetch_card_html", return_value=PUBLIC_DOMAIN_HTML):
            result = screener.screen(short_work)
        assert hasattr(result, "status")
        assert hasattr(result, "reason")

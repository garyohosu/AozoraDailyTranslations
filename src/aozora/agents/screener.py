"""Agent 1 — Screener: eligibility checks for Aozora Bunko works."""

from __future__ import annotations

import re

import requests

from aozora.models import ScreenResult, WorkEntry

# 著作権保護期間満了を示す青空文庫のキーワード
_PUBLIC_DOMAIN_KEYWORDS = [
    "著作権保護期間満了",
    "パブリックドメイン",
    "public domain",
]

# 翻訳作品を示すキーワード（これらがあれば翻訳作品と判断）
_TRANSLATION_KEYWORDS = [
    "翻訳者",
    "翻訳：",
    "翻訳: ",
    "訳者",
    "底本の底本",
]

# 注釈過多の閾値
_ANNOTATION_THRESHOLD = 20

_ANNOTATION_PATTERN = re.compile(r"［＃[^］]*］")

_REQUEST_TIMEOUT = 30


class Screener:
    def screen(self, candidate: WorkEntry) -> ScreenResult:
        """ScreenResult(status="ELIGIBLE"|"INELIGIBLE", reason=...) を返す。
        ネットワークエラーや判断不能の場合は safety bias で INELIGIBLE。
        """
        try:
            card_html = self._fetch_card_html(candidate.aozora_card_url)
        except Exception as exc:
            return ScreenResult(
                status="INELIGIBLE",
                reason=f"Card fetch error: {exc}",
            )

        if not self._check_public_domain(card_html):
            return ScreenResult(
                status="INELIGIBLE",
                reason="Public domain status could not be confirmed",
            )

        if self._detect_translation_work(card_html):
            return ScreenResult(
                status="INELIGIBLE",
                reason="Translation of a foreign work detected",
            )

        if self._check_annotation_heavy(card_html):
            return ScreenResult(
                status="INELIGIBLE",
                reason="Content dominated by annotations",
            )

        if self._check_us_distribution_risk(card_html):
            return ScreenResult(
                status="INELIGIBLE",
                reason="US distribution risk detected",
            )

        return ScreenResult(status="ELIGIBLE", reason="")

    # ------------------------------------------------------------------
    # 内部チェック
    # ------------------------------------------------------------------

    def _fetch_card_html(self, card_url: str) -> str:
        resp = requests.get(
            card_url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": "AozoraDailyTranslations/1.0"},
        )
        resp.raise_for_status()
        return resp.text

    def _check_public_domain(self, card_html: str) -> bool:
        """著作権保護期間満了キーワードが存在すれば True。
        判断できない場合は安全側（False）に倒す。
        """
        lower = card_html.lower()
        for kw in _PUBLIC_DOMAIN_KEYWORDS:
            if kw.lower() in lower:
                return True
        return False

    def _detect_translation_work(self, card_html: str) -> bool:
        """翻訳者・訳者が明記されていれば外国語翻訳と判断して True。"""
        for kw in _TRANSLATION_KEYWORDS:
            if kw in card_html:
                return True
        return False

    def _check_annotation_heavy(self, card_html: str) -> bool:
        """注釈記法 ［＃...］ の出現数が閾値を超えれば True。"""
        count = len(_ANNOTATION_PATTERN.findall(card_html))
        return count > _ANNOTATION_THRESHOLD

    def _check_us_distribution_risk(self, card_html: str) -> bool:
        """US 配布リスクフラグ。現時点では簡易実装（常に False）。
        将来的に青空文庫の US 権利情報フィールドを参照する。
        """
        return False

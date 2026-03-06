"""Agent 1: eligibility checks for Aozora Bunko works."""

from __future__ import annotations

import datetime
import re

import requests

from aozora.models import ScreenResult, WorkEntry

_PUBLIC_DOMAIN_KEYWORDS = [
    "著作権保護期間満了",
    "パブリックドメイン",
    "public domain",
]

_DEATH_YEAR_PATTERN = re.compile(r"没年[^0-9]*(\d{4})")

_TRANSLATION_KEYWORDS = [
    "翻訳",
    "訳者",
    "翻案",
    "外国作品",
]

_ANNOTATION_THRESHOLD = 20
_ANNOTATION_PATTERN = re.compile(r"［＃[^］]*］")
_REQUEST_TIMEOUT = 30


class Screener:
    def screen(self, candidate: WorkEntry) -> ScreenResult:
        """Return eligibility with a safety-biased rejection policy."""
        try:
            card_html = self._fetch_card_html(candidate.aozora_card_url)
        except Exception as exc:
            return ScreenResult(status="INELIGIBLE", reason=f"Card fetch error: {exc}")

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
            return ScreenResult(status="INELIGIBLE", reason="US distribution risk detected")

        return ScreenResult(status="ELIGIBLE", reason="")

    def _fetch_card_html(self, card_url: str) -> str:
        resp = requests.get(
            card_url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": "AozoraDailyTranslations/1.0"},
        )
        resp.raise_for_status()
        return resp.content.decode("utf-8", errors="replace")

    def _check_public_domain(self, card_html: str) -> bool:
        lower = card_html.lower()
        if any(kw.lower() in lower for kw in _PUBLIC_DOMAIN_KEYWORDS):
            return True

        match = _DEATH_YEAR_PATTERN.search(card_html)
        if match:
            death_year = int(match.group(1))
            return (datetime.datetime.now().year - death_year) > 70
        return False

    def _detect_translation_work(self, card_html: str) -> bool:
        return any(kw in card_html for kw in _TRANSLATION_KEYWORDS)

    def _check_annotation_heavy(self, card_html: str) -> bool:
        return len(_ANNOTATION_PATTERN.findall(card_html)) > _ANNOTATION_THRESHOLD

    def _check_us_distribution_risk(self, card_html: str) -> bool:
        text = card_html.lower()
        risk_patterns = [
            r"united states",
            r"\busa\b",
            r"u\.s\.",
            r"米国",
            r"アメリカ",
            r"rights reserved",
            r"distribution.*(restricted|prohibited)",
            r"copyright.*(remain|reserved)",
        ]
        return any(re.search(p, text) for p in risk_patterns)

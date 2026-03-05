"""Shared fixtures for all test modules."""

from __future__ import annotations

import pytest

from aozora.models import (
    FetchResult,
    QAGateConfig,
    StateJson,
    TranslationResult,
    WorkEntry,
)


@pytest.fixture
def valid_work() -> WorkEntry:
    return WorkEntry(
        aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
        aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128_15260.html",
        title_en="The Spider's Thread",
        author_en="Akutagawa Ryunosuke",
        title_ja="蜘蛛の糸",
        author_ja="芥川龍之介",
        genre="short",
        notes="Famous short story from 1918",
    )


@pytest.fixture
def valid_poem_work() -> WorkEntry:
    return WorkEntry(
        aozora_card_url="https://www.aozora.gr.jp/cards/001049/card42618.html",
        aozora_txt_url="https://www.aozora.gr.jp/cards/001049/files/42618_29555.html",
        title_en="Spring Rain",
        author_en="Yosa Buson",
        genre="poem",
    )


@pytest.fixture
def default_fetch_result() -> FetchResult:
    return FetchResult(
        raw_text_ja="日本語テキスト",
        clean_text_ja="日本語テキスト",
        P_ja=5,
        C_ja=1000,
    )


@pytest.fixture
def default_translation() -> TranslationResult:
    return TranslationResult(
        translation_en="Once upon a time, Buddha was walking in paradise.",
        introduction_en="This is a short story about compassion and greed by Akutagawa.",
        source="codex_cli",
    )


@pytest.fixture
def default_qa_config() -> QAGateConfig:
    return QAGateConfig()


@pytest.fixture
def initial_state() -> StateJson:
    return StateJson(next_index=0, status="active", skip_log=[])

"""Regression tests for fail-closed translation publishing."""

from __future__ import annotations

import json

import pytest

import aozora.run as run_module
from aozora.models import TranslationResult


def test_translate_raises_when_all_engines_fail(monkeypatch):
    monkeypatch.setattr(
        run_module,
        "_translate_chunk",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no codex")),
    )
    monkeypatch.setattr(
        run_module,
        "_ask_local_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no local llm")),
    )

    with pytest.raises(run_module.TranslationError, match="all translation engines failed"):
        run_module._translate("日本語の本文", "Title", "Author")


def test_run_does_not_publish_or_advance_on_failed_qa(tmp_path, monkeypatch):
    data = tmp_path / "DATA"
    logs = data / "logs"
    works_dir = tmp_path / "works"
    logs.mkdir(parents=True)
    works_dir.mkdir()
    (data / "works.json").write_text(
        json.dumps(
            [
                {
                    "aozora_card_url": "https://www.aozora.gr.jp/cards/1/card1.html",
                    "aozora_txt_url": "https://www.aozora.gr.jp/cards/1/files/1.html",
                    "title_en": "Test Work",
                    "author_en": "Test Author",
                    "genre": "short",
                }
            ]
        ),
        encoding="utf-8",
    )
    original_state = '{"next_index": 0, "status": "active", "skip_log": []}'
    (data / "state.json").write_text(original_state, encoding="utf-8")
    (data / "en_map.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(run_module, "ROOT", tmp_path)
    monkeypatch.setattr(run_module, "DATA", data)
    monkeypatch.setattr(run_module, "LOGS", logs)
    monkeypatch.setattr(run_module, "WORKS_DIR", works_dir)
    monkeypatch.setattr(run_module, "AUTO_FILL_TARGET", 0)
    monkeypatch.setattr(run_module, "_fetch_clean_ja", lambda _: "日本語本文" * 100)
    monkeypatch.setattr(
        run_module,
        "_translate",
        lambda *_: TranslationResult(
            translation_en="Automatic translation is temporarily unavailable.",
            introduction_en="",
            source="fallback",
        ),
    )

    with pytest.raises(run_module.TranslationError, match="failed QA gates"):
        run_module.run("2026-08-03")

    state = json.loads((data / "state.json").read_text(encoding="utf-8"))
    assert state["next_index"] == 0
    assert state["status"] == "active"
    assert list(works_dir.iterdir()) == []
    assert list(logs.iterdir()) == []
    assert not (tmp_path / "index.html").exists()

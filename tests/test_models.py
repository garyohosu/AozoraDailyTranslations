"""Tests for WorkEntry and StateJson data models (CLASS.md §1, SPEC.md §3.1)."""

from __future__ import annotations

import json

import pytest

from aozora.models import SkipLogEntry, StateJson, WorkEntry

# ---------------------------------------------------------------------------
# WorkEntry — フィールド検証
# ---------------------------------------------------------------------------


class TestWorkEntryValidation:
    """SPEC.md §3.1 のバリデーションルールをすべてカバーする。"""

    def test_valid_short_work(self):
        entry = WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128_15260.html",
            title_en="The Spider's Thread",
            author_en="Akutagawa Ryunosuke",
            genre="short",
        )
        assert entry.title_en == "The Spider's Thread"
        assert entry.genre == "short"

    def test_valid_poem_work(self):
        entry = WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/001049/card42618.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/001049/files/42618_29555.html",
            title_en="Spring Rain",
            author_en="Yosa Buson",
            genre="poem",
        )
        assert entry.genre == "poem"

    # --- genre ---

    def test_invalid_genre_novel_raises(self):
        with pytest.raises(ValueError, match="genre"):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="novel",
            )

    def test_invalid_genre_empty_raises(self):
        with pytest.raises(ValueError, match="genre"):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="",
            )

    # --- URL scheme ---

    def test_card_url_ftp_scheme_raises(self):
        with pytest.raises(ValueError, match="URL"):
            WorkEntry(
                aozora_card_url="ftp://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="short",
            )

    def test_txt_url_ftp_scheme_raises(self):
        with pytest.raises(ValueError, match="URL"):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="ftp://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="short",
            )

    def test_http_scheme_is_allowed(self):
        entry = WorkEntry(
            aozora_card_url="http://www.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="http://www.aozora.gr.jp/cards/000879/files/128.html",
            title_en="Test",
            author_en="Author",
            genre="short",
        )
        assert entry.aozora_card_url.startswith("http://")

    # --- URL host ---

    def test_card_url_wrong_host_raises(self):
        with pytest.raises(ValueError, match="URL"):
            WorkEntry(
                aozora_card_url="https://www.evil.com/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="short",
            )

    def test_aozora_subdomain_is_allowed(self):
        """cdn.aozora.gr.jp など任意のサブドメインを許可 (QA.md Q6-3)。"""
        entry = WorkEntry(
            aozora_card_url="https://cdn.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://cdn.aozora.gr.jp/cards/000879/files/128.html",
            title_en="Test",
            author_en="Author",
            genre="short",
        )
        assert "aozora.gr.jp" in entry.aozora_card_url

    def test_aozora_exact_host_is_allowed(self):
        entry = WorkEntry(
            aozora_card_url="https://aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://aozora.gr.jp/cards/000879/files/128.html",
            title_en="Test",
            author_en="Author",
            genre="short",
        )
        assert entry is not None

    def test_rejects_deceptive_host_suffix(self):
        with pytest.raises(ValueError, match="URL"):
            WorkEntry(
                aozora_card_url="https://aozora.gr.jp.evil.com/cards/000879/card128.html",
                aozora_txt_url="https://aozora.gr.jp.evil.com/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="short",
            )

    def test_rejects_prefix_spoofed_host(self):
        with pytest.raises(ValueError, match="URL"):
            WorkEntry(
                aozora_card_url="https://evil-aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://evil-aozora.gr.jp/cards/000879/files/128.html",
                title_en="Test",
                author_en="Author",
                genre="short",
            )

    # --- title_en / author_en ---

    def test_title_en_empty_raises(self):
        with pytest.raises(ValueError):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="",
                author_en="Author",
                genre="short",
            )

    def test_author_en_empty_raises(self):
        with pytest.raises(ValueError):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Title",
                author_en="",
                genre="short",
            )

    def test_title_en_max_200_chars(self):
        with pytest.raises(ValueError, match="200"):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="A" * 201,
                author_en="Author",
                genre="short",
            )

    def test_title_en_exactly_200_chars_ok(self):
        entry = WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
            title_en="A" * 200,
            author_en="Author",
            genre="short",
        )
        assert len(entry.title_en) == 200

    def test_author_en_max_200_chars(self):
        with pytest.raises(ValueError, match="200"):
            WorkEntry(
                aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
                aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
                title_en="Title",
                author_en="A" * 201,
                genre="short",
            )

    # --- optional fields ---

    def test_optional_fields_default_to_none_or_empty(self):
        entry = WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
            title_en="Title",
            author_en="Author",
            genre="short",
        )
        assert entry.title_ja is None or entry.title_ja == ""
        assert entry.author_ja is None or entry.author_ja == ""
        assert entry.notes is None or entry.notes == ""


# ---------------------------------------------------------------------------
# StateJson
# ---------------------------------------------------------------------------


class TestStateJsonLoad:
    def test_load_full_state(self, tmp_path):
        data = {
            "next_index": 2,
            "status": "active",
            "skip_log": [
                {
                    "date_jst": "2026-03-01",
                    "index": 0,
                    "card_url": "https://www.aozora.gr.jp/cards/test/card1.html",
                    "reason": "Translation of foreign work detected",
                }
            ],
        }
        path = tmp_path / "state.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        state = StateJson.load(str(path))

        assert state.next_index == 2
        assert state.status == "active"
        assert len(state.skip_log) == 1
        assert state.skip_log[0].reason == "Translation of foreign work detected"
        assert state.skip_log[0].index == 0

    def test_load_minimal_state_defaults(self, tmp_path):
        """status と skip_log は省略可能; デフォルトは active / []。"""
        data = {"next_index": 0}
        path = tmp_path / "state.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        state = StateJson.load(str(path))

        assert state.next_index == 0
        assert state.status == "active"
        assert state.skip_log == []

    def test_load_exhausted_status(self, tmp_path):
        data = {"next_index": 10, "status": "exhausted", "skip_log": []}
        path = tmp_path / "state.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        state = StateJson.load(str(path))
        assert state.status == "exhausted"

    def test_load_rejects_unknown_status(self, tmp_path):
        data = {"next_index": 10, "status": "rollback", "skip_log": []}
        path = tmp_path / "state.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="status"):
            StateJson.load(str(path))


class TestStateJsonSave:
    def test_save_round_trip(self, tmp_path):
        state = StateJson(next_index=5, status="active", skip_log=[])
        path = tmp_path / "state.json"
        state.save(str(path))

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["next_index"] == 5
        assert data["status"] == "active"
        assert data["skip_log"] == []

    def test_save_with_skip_log(self, tmp_path):
        entry = SkipLogEntry(
            date_jst="2026-03-05",
            index=2,
            card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
            reason="Annotation heavy",
        )
        state = StateJson(next_index=3, status="active", skip_log=[entry])
        path = tmp_path / "state.json"
        state.save(str(path))

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["skip_log"]) == 1
        assert data["skip_log"][0]["reason"] == "Annotation heavy"


class TestStateJsonExhausted:
    def test_is_exhausted_false_for_active(self):
        state = StateJson(next_index=0, status="active", skip_log=[])
        assert state.is_exhausted() is False

    def test_is_exhausted_true_for_exhausted(self):
        state = StateJson(next_index=0, status="exhausted", skip_log=[])
        assert state.is_exhausted() is True

    def test_set_exhausted_changes_status(self):
        state = StateJson(next_index=10, status="active", skip_log=[])
        state.set_exhausted()
        assert state.status == "exhausted"
        assert state.is_exhausted() is True

    def test_set_exhausted_idempotent(self):
        state = StateJson(next_index=0, status="exhausted", skip_log=[])
        state.set_exhausted()
        assert state.status == "exhausted"

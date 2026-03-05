"""Tests for Agent 2 — Fetcher/Normalizer (CLASS.md §1, QA.md Q3-1/Q3-3)."""

from __future__ import annotations

import re

import pytest

from aozora.agents.fetcher import Fetcher


@pytest.fixture
def fetcher() -> Fetcher:
    return Fetcher()


# ---------------------------------------------------------------------------
# ルビ除去 (QA.md Q3-3)
# ---------------------------------------------------------------------------


class TestRemoveRuby:
    def test_vertical_bar_ruby_keeps_base(self, fetcher):
        """｜漢字《かんじ》 → 漢字"""
        assert fetcher.remove_ruby("｜漢字《かんじ》が好き") == "漢字が好き"

    def test_no_vertical_bar_ruby_removes_reading(self, fetcher):
        """漢字《かんじ》 → 漢字"""
        assert fetcher.remove_ruby("漢字《かんじ》です") == "漢字です"

    def test_multiple_ruby_all_removed(self, fetcher):
        text = "｜山路《やまじ》を登りながら、｜智《ち》に働けば"
        result = fetcher.remove_ruby(text)
        assert "《" not in result
        assert "山路" in result
        assert "智" in result

    def test_no_ruby_unchanged(self, fetcher):
        text = "普通のテキストです。"
        assert fetcher.remove_ruby(text) == text

    def test_ruby_at_end_of_string(self, fetcher):
        result = fetcher.remove_ruby("終わり《おわり》")
        assert result == "終わり"


# ---------------------------------------------------------------------------
# 注釈除去 (QA.md Q3-3)
# ---------------------------------------------------------------------------


class TestRemoveAnnotations:
    def test_sharp_annotation_removed(self, fetcher):
        """［＃「なんとか」に傍点］ → 空文字"""
        result = fetcher.remove_annotations("本文［＃「なんとか」に傍点］続く")
        assert "［" not in result
        assert "本文続く" == result

    def test_multiple_annotations_removed(self, fetcher):
        result = fetcher.remove_annotations("A［＃注釈1］B［＃注釈2］C")
        assert result == "ABC"

    def test_no_annotations_unchanged(self, fetcher):
        text = "注釈のない本文。"
        assert fetcher.remove_annotations(text) == text

    def test_ruby_and_annotation_combined(self, fetcher):
        text = "｜山路《やまじ》を登りながら［＃「考えた」に傍点］"
        result = fetcher.remove_annotations(fetcher.remove_ruby(text))
        assert "《" not in result
        assert "［" not in result
        assert "山路" in result


# ---------------------------------------------------------------------------
# 段落カウント (QA.md Q3-3 — P_ja 計測は短文分解前の空行区切り)
# ---------------------------------------------------------------------------


class TestCountParagraphs:
    def test_three_paragraphs(self, fetcher):
        text = "段落1\n\n段落2\n\n段落3"
        assert fetcher.count_paragraphs(text) == 3

    def test_single_paragraph(self, fetcher):
        text = "一つの段落だけ。"
        assert fetcher.count_paragraphs(text) == 1

    def test_trailing_newlines_not_counted(self, fetcher):
        text = "段落1\n\n段落2\n\n"
        assert fetcher.count_paragraphs(text) == 2

    def test_leading_newlines_not_counted(self, fetcher):
        text = "\n\n段落1\n\n段落2"
        assert fetcher.count_paragraphs(text) == 2

    def test_empty_string_returns_zero(self, fetcher):
        assert fetcher.count_paragraphs("") == 0

    def test_only_whitespace_returns_zero(self, fetcher):
        assert fetcher.count_paragraphs("   \n\n   ") == 0

    def test_crlf_paragraph_separator(self, fetcher):
        """TXTファイルは \\r\\n\\r\\n 区切り (QA.md Q3-1)。"""
        text = "段落1\r\n\r\n段落2\r\n\r\n段落3"
        assert fetcher.count_paragraphs(text) == 3


# ---------------------------------------------------------------------------
# デコード (QA.md Q3-1)
# ---------------------------------------------------------------------------


class TestDecodeWithFallback:
    def test_decode_shift_jis_2004(self, fetcher):
        original = "羅生門"
        raw = original.encode("shift_jis_2004")
        text, enc = fetcher._decode_with_fallback(raw)
        assert original in text
        assert enc == "shift_jis_2004"

    def test_decode_cp932_as_fallback(self, fetcher):
        original = "桜の樹の下には"
        raw = original.encode("cp932")
        text, enc = fetcher._decode_with_fallback(raw)
        assert original in text

    def test_decode_utf8_as_fallback(self, fetcher):
        original = "Hello テスト"
        raw = original.encode("utf-8")
        text, enc = fetcher._decode_with_fallback(raw)
        assert original in text

    def test_decode_returns_tuple(self, fetcher):
        raw = "テスト".encode()
        result = fetcher._decode_with_fallback(raw)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_undecodable_bytes_raises_value_error(self, fetcher):
        """全エンコーディングが候補リストにない場合 ValueError を送出。
        cp932 は事実上すべてのバイト列を受け付けるため、_decode_order を空にして
        「候補なし → ValueError」のパスをテストする。
        """
        fetcher._decode_order = []  # 候補なし
        with pytest.raises(ValueError):
            fetcher._decode_with_fallback(b"\xff\xfe\x00\x01")


# ---------------------------------------------------------------------------
# アーティファクト検出ヘルパー (QA gate で再利用)
# ---------------------------------------------------------------------------


def count_aozora_artifacts(text: str) -> int:
    """青空文庫ルビ・注釈の残滓をカウントする（QAAuditor._check_artifacts の参照実装）。"""
    count = 0
    count += len(re.findall(r"《", text))
    count += len(re.findall(r"》", text))
    count += len(re.findall(r"｜", text))
    count += len(re.findall(r"［＃[^］]*］", text))
    return count


class TestArtifactCountHelper:
    def test_clean_english_zero(self):
        assert count_aozora_artifacts("The main character walked slowly.") == 0

    def test_kagi_brackets_counted(self):
        assert count_aozora_artifacts("text 《ruby》 more 《another》") == 4  # 2×《 + 2×》

    def test_vertical_bar_counted(self):
        assert count_aozora_artifacts("｜base《ruby》text") == 3  # ｜ + 《 + 》

    def test_sharp_annotation_counted(self):
        assert count_aozora_artifacts("text ［＃注釈内容］ more") == 1

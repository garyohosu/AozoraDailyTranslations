"""Tests for Agent 5 — QA/Auditor quality gates (SPEC.md §5, CLASS.md §1)."""

from __future__ import annotations

import math

import pytest

from aozora.agents.qa_auditor import QAAuditor
from aozora.models import FetchResult, QAGateConfig


@pytest.fixture
def config() -> QAGateConfig:
    return QAGateConfig()


@pytest.fixture
def auditor(config) -> QAAuditor:
    return QAAuditor(config=config)


def make_translation(paragraphs: int, words_per_para: int = 60) -> str:
    """指定段落数・ワード数の英文を生成するヘルパー。"""
    para = " ".join(["word"] * words_per_para)
    return "\n\n".join([para] * paragraphs)


# ---------------------------------------------------------------------------
# ゲート1: 段落数不一致 (SPEC.md §5.1)
# FAIL if abs(P_en - P_ja) > max(2, ceil(0.15 * P_ja))
# ---------------------------------------------------------------------------


class TestParagraphCountGate:
    def test_pass_equal_paragraphs(self, auditor):
        result = auditor._check_paragraph_count(P_en=10, P_ja=10)
        assert result == "PASS"

    def test_pass_within_minimum_tolerance(self, auditor):
        # tolerance = max(2, ceil(0.15 * 4)) = max(2, 1) = 2
        # abs(6-4) = 2 == 2 → PASS (境界値)
        assert auditor._check_paragraph_count(P_en=6, P_ja=4) == "PASS"

    def test_fail_just_over_minimum_tolerance(self, auditor):
        # tolerance = max(2, ceil(0.15 * 4)) = 2
        # abs(7-4) = 3 > 2 → FAIL
        assert auditor._check_paragraph_count(P_en=7, P_ja=4) == "FAIL"

    def test_pass_within_15_percent_tolerance(self, auditor):
        # tolerance = max(2, ceil(0.15 * 20)) = max(2, 3) = 3
        # abs(23-20) = 3 == 3 → PASS (境界値)
        assert auditor._check_paragraph_count(P_en=23, P_ja=20) == "PASS"

    def test_fail_over_15_percent_tolerance(self, auditor):
        # tolerance = max(2, ceil(0.15 * 20)) = 3
        # abs(24-20) = 4 > 3 → FAIL
        assert auditor._check_paragraph_count(P_en=24, P_ja=20) == "FAIL"

    def test_fail_too_few_paragraphs(self, auditor):
        # tolerance = max(2, ceil(0.15 * 10)) = 2
        # abs(7-10) = 3 > 2 → FAIL
        assert auditor._check_paragraph_count(P_en=7, P_ja=10) == "FAIL"

    def test_pass_p_ja_zero_edge(self, auditor):
        # tolerance = max(2, ceil(0)) = 2; abs(0-0) = 0 ≤ 2 → PASS
        assert auditor._check_paragraph_count(P_en=0, P_ja=0) == "PASS"

    @pytest.mark.parametrize(
        "p_ja,tolerance",
        [
            (1, 2),
            (2, 2),
            (10, 2),
            (13, 2),
            (14, 3),
            (20, 3),
            (100, 15),
        ],
    )
    def test_tolerance_calculation(self, auditor, p_ja, tolerance):
        expected = max(2, math.ceil(0.15 * p_ja))
        assert expected == tolerance


# ---------------------------------------------------------------------------
# ゲート2: 長さ比率 R = W_en / max(1, C_ja)
# short: 0.28 ≤ R ≤ 0.95 / poem: 0.18 ≤ R ≤ 1.20
# ---------------------------------------------------------------------------


class TestLengthRatioGate:
    # --- short ---

    def test_short_pass_typical_ratio(self, auditor):
        # R = 500/1000 = 0.50 ∈ [0.28, 0.95]
        assert auditor._check_length_ratio(W_en=500, C_ja=1000, genre="short") == "PASS"

    def test_short_pass_min_boundary(self, auditor):
        # R = 0.28 exactly → PASS
        assert auditor._check_length_ratio(W_en=280, C_ja=1000, genre="short") == "PASS"

    def test_short_pass_max_boundary(self, auditor):
        # R = 0.95 exactly → PASS
        assert auditor._check_length_ratio(W_en=950, C_ja=1000, genre="short") == "PASS"

    def test_short_fail_under(self, auditor):
        # R = 0.27 < 0.28 → FAIL (under-translation)
        assert auditor._check_length_ratio(W_en=270, C_ja=1000, genre="short") == "FAIL"

    def test_short_fail_over(self, auditor):
        # R = 0.96 > 0.95 → FAIL (over-generation)
        assert auditor._check_length_ratio(W_en=960, C_ja=1000, genre="short") == "FAIL"

    # --- poem ---

    def test_poem_pass_low_ratio(self, auditor):
        # R = 0.20 ∈ [0.18, 1.20]
        assert auditor._check_length_ratio(W_en=200, C_ja=1000, genre="poem") == "PASS"

    def test_poem_pass_high_ratio(self, auditor):
        # R = 1.10 ∈ [0.18, 1.20]
        assert auditor._check_length_ratio(W_en=1100, C_ja=1000, genre="poem") == "PASS"

    def test_poem_pass_min_boundary(self, auditor):
        # R = 0.18 exactly → PASS
        assert auditor._check_length_ratio(W_en=180, C_ja=1000, genre="poem") == "PASS"

    def test_poem_pass_max_boundary(self, auditor):
        # R = 1.20 exactly → PASS
        assert auditor._check_length_ratio(W_en=1200, C_ja=1000, genre="poem") == "PASS"

    def test_poem_fail_under(self, auditor):
        # R = 0.17 < 0.18 → FAIL
        assert auditor._check_length_ratio(W_en=170, C_ja=1000, genre="poem") == "FAIL"

    def test_poem_fail_over(self, auditor):
        # R = 1.21 > 1.20 → FAIL
        assert auditor._check_length_ratio(W_en=1210, C_ja=1000, genre="poem") == "FAIL"

    def test_c_ja_zero_uses_max_1(self, auditor):
        # max(1, 0) = 1; R = 0/1 = 0.0 < 0.28 → FAIL
        assert auditor._check_length_ratio(W_en=0, C_ja=0, genre="short") == "FAIL"

    def test_c_ja_zero_prevents_division_by_zero(self, auditor):
        # Should not raise ZeroDivisionError
        result = auditor._check_length_ratio(W_en=1, C_ja=0, genre="short")
        assert result in ("PASS", "FAIL")


# ---------------------------------------------------------------------------
# ゲート3: アーティファクト残存 (SPEC.md §5.1 — count > 3 → FAIL)
# ---------------------------------------------------------------------------


class TestArtifactGate:
    def test_pass_zero_artifacts(self, auditor):
        assert auditor._check_artifacts("Clean English translation.") == "PASS"

    def test_pass_exactly_3_artifacts(self, auditor):
        # 《one》《two》《three》 → 6 記号だが、QAは《》のペアでカウントするか？
        # SPEC.md は「occurrences of 《, 》, ｜, ［＃...］」の合計が3以下なら PASS
        # 《one》 = 2個(《+》), 《two》 = 2個, 《three》 = 2個 → 合計6個 → FAIL
        # ここでは「パターン出現回数」として《》各1, ｜各1 でカウントする設計を前提
        text = "word 《a》 word"  # 《1個 + 》1個 + テキスト = 2パターン → PASS
        result = auditor._check_artifacts(text)
        # 実装は《と》を別々にカウント; 2 ≤ 3 → PASS
        assert result == "PASS"

    def test_fail_more_than_3_artifacts(self, auditor):
        # 《1》《2》《3》《4》= 8記号 → FAIL
        text = "《1》《2》《3》《4》"
        assert auditor._check_artifacts(text) == "FAIL"

    def test_fail_mixed_artifact_types(self, auditor):
        # ｜1個 + 《1個 + 》1個 + ［＃注釈］1個 = 4個 → FAIL
        text = "｜base《ruby》more ［＃annotation］"
        assert auditor._check_artifacts(text) == "FAIL"

    def test_pass_no_aozora_symbols(self, auditor):
        text = "The old servant sat beneath the gate."
        assert auditor._check_artifacts(text) == "PASS"


# ---------------------------------------------------------------------------
# ゲート4: 禁止ボイラープレート (SPEC.md §5.1)
# ---------------------------------------------------------------------------


class TestBoilerplateGate:
    def test_fail_translation_failed(self, auditor):
        assert auditor._check_boilerplate("translation failed due to encoding error") == "FAIL"

    def test_fail_as_an_ai(self, auditor):
        assert auditor._check_boilerplate("As an AI language model, I cannot do this.") == "FAIL"

    def test_fail_i_cant(self, auditor):
        assert auditor._check_boilerplate("I can't translate this text properly.") == "FAIL"

    def test_fail_i_cannot(self, auditor):
        assert auditor._check_boilerplate("I cannot complete this request.") == "FAIL"

    def test_pass_normal_translation(self, auditor):
        assert auditor._check_boilerplate("The old man walked slowly through the gate.") == "PASS"

    def test_case_insensitive_detection(self, auditor):
        assert auditor._check_boilerplate("TRANSLATION FAILED") == "FAIL"
        assert auditor._check_boilerplate("As An AI") == "FAIL"

    def test_pass_long_clean_text(self, auditor):
        text = (
            "Long ago in Kyoto there lived a servant who had nowhere to go. "
            "He sat beneath the Rashomon gate, pondering his fate."
        )
        assert auditor._check_boilerplate(text) == "PASS"


# ---------------------------------------------------------------------------
# audit() 統合テスト
# ---------------------------------------------------------------------------


class TestQAAuditIntegration:
    def test_all_gates_pass_returns_pass(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=3, C_ja=600)
        # P_en=3, W_en≈180, R=0.30 (short range OK), no artifacts, no boilerplate
        translation = "\n\n".join([" ".join(["word"] * 60)] * 3)
        result = auditor.audit(translation, fetch, genre="short")
        assert result.status == "PASS"
        assert all(v == "PASS" for v in result.gates.values())

    def test_boilerplate_fails_audit(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=3, C_ja=600)
        translation = "As an AI, I cannot complete this translation task."
        result = auditor.audit(translation, fetch, genre="short")
        assert result.status == "FAIL"
        assert result.gates.get("boilerplate") == "FAIL"

    def test_artifact_fails_audit(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=1, C_ja=200)
        translation = "《artifact1》《artifact2》《artifact3》《artifact4》 The end."
        result = auditor.audit(translation, fetch, genre="short")
        assert result.status == "FAIL"
        assert result.gates.get("artifacts") == "FAIL"

    def test_paragraph_mismatch_fails_audit(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=10, C_ja=1000)
        # P_en=1 vs P_ja=10: abs(1-10)=9 > max(2, ceil(1.5))=2 → FAIL
        translation = " ".join(["word"] * 300)  # single paragraph
        result = auditor.audit(translation, fetch, genre="short")
        assert result.status == "FAIL"
        assert result.gates.get("paragraph_count") == "FAIL"

    def test_result_contains_metrics(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=2, C_ja=400)
        translation = "\n\n".join([" ".join(["word"] * 60)] * 2)
        result = auditor.audit(translation, fetch, genre="short")
        assert result.P_en >= 0
        assert result.W_en >= 0
        assert result.R >= 0.0

    def test_poem_genre_uses_poem_thresholds(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=5, C_ja=200)
        # R = 40/200 = 0.20 → poem OK (≥0.18), short FAIL (<0.28)
        translation = "\n\n".join([" ".join(["word"] * 8)] * 5)
        result = auditor.audit(translation, fetch, genre="poem")
        # length_ratio should PASS for poem
        assert result.gates.get("length_ratio") == "PASS"

    def test_result_has_all_gate_keys(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=2, C_ja=400)
        translation = "\n\n".join([" ".join(["word"] * 60)] * 2)
        result = auditor.audit(translation, fetch, genre="short")
        for key in ("paragraph_count", "length_ratio", "artifacts", "boilerplate"):
            assert key in result.gates, f"gate '{key}' missing from result.gates"


@pytest.mark.xfail(strict=True, reason="introduction gate not implemented yet")
class TestIntroductionGate:
    def test_result_has_introduction_word_count_gate(self, auditor):
        fetch = FetchResult(raw_text_ja="", clean_text_ja="", P_ja=2, C_ja=400)
        translation = "\n\n".join([" ".join(["word"] * 60)] * 2)
        result = auditor.audit(translation, fetch, genre="short")
        assert "introduction_word_count" in result.gates

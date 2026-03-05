"""Tests for Agent 0 窶・Orchestrator state management (SPEC.md ﾂｧ6.1/ﾂｧ6.2, CLASS.md ﾂｧ1)."""

from __future__ import annotations

import pytest

from aozora.agents.orchestrator import Orchestrator
from aozora.models import StateJson, WorkEntry


@pytest.fixture
def works() -> list[WorkEntry]:
    return [
        WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000879/card128.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000879/files/128.html",
            title_en="Rashomon",
            author_en="Akutagawa Ryunosuke",
            genre="short",
        ),
        WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000001/card1.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000001/files/1.html",
            title_en="Spring Poem",
            author_en="Yosa Buson",
            genre="poem",
        ),
        WorkEntry(
            aozora_card_url="https://www.aozora.gr.jp/cards/000002/card2.html",
            aozora_txt_url="https://www.aozora.gr.jp/cards/000002/files/2.html",
            title_en="Another Story",
            author_en="Another Author",
            genre="short",
        ),
    ]


@pytest.fixture
def state() -> StateJson:
    return StateJson(next_index=0, status="active", skip_log=[])


@pytest.fixture
def orch(works, state) -> Orchestrator:
    return Orchestrator(works=works, state=state, max_attempts=3)


# ---------------------------------------------------------------------------
# 蛟呵｣憺∈謚・# ---------------------------------------------------------------------------


class TestSelectCandidate:
    def test_select_index_0(self, orch):
        candidate = orch._select_candidate(0)
        assert candidate.title_en == "Rashomon"

    def test_select_index_1(self, orch):
        candidate = orch._select_candidate(1)
        assert candidate.title_en == "Spring Poem"

    def test_select_index_2(self, orch):
        candidate = orch._select_candidate(2)
        assert candidate.title_en == "Another Story"

    def test_select_out_of_bounds_raises(self, orch):
        with pytest.raises((IndexError, ValueError, StopIteration)):
            orch._select_candidate(3)

    def test_select_negative_raises(self, orch):
        with pytest.raises((IndexError, ValueError)):
            orch._select_candidate(-1)


# ---------------------------------------------------------------------------
# 迥ｶ諷区峩譁ｰ (SPEC.md ﾂｧ6.1)
# ---------------------------------------------------------------------------


class TestUpdateState:
    def test_update_state_changes_next_index(self, orch):
        orch._update_state(next_index=1)
        assert orch.state.next_index == 1

    def test_update_state_idempotent(self, orch):
        orch._update_state(next_index=2)
        orch._update_state(next_index=2)
        assert orch.state.next_index == 2

    def test_update_state_to_end(self, orch, works):
        orch._update_state(next_index=len(works))
        assert orch.state.next_index == len(works)


# ---------------------------------------------------------------------------
# 繧ｹ繧ｭ繝・・繝ｭ繧ｰ (SPEC.md ﾂｧ6.1)
# ---------------------------------------------------------------------------


class TestHandleSkip:
    def test_skip_appends_to_log(self, orch):
        orch._handle_skip(index=0, reason="Translation detected")
        assert len(orch.state.skip_log) == 1

    def test_skip_log_contains_correct_index(self, orch):
        orch._handle_skip(index=1, reason="Annotation heavy")
        assert orch.state.skip_log[0].index == 1

    def test_skip_log_contains_reason(self, orch):
        orch._handle_skip(index=0, reason="US distribution risk")
        assert orch.state.skip_log[0].reason == "US distribution risk"

    def test_skip_log_contains_card_url(self, orch, works):
        orch._handle_skip(index=0, reason="Test skip")
        assert orch.state.skip_log[0].card_url == works[0].aozora_card_url

    def test_multiple_skips_accumulate(self, orch):
        orch._handle_skip(index=0, reason="reason1")
        orch._handle_skip(index=1, reason="reason2")
        assert len(orch.state.skip_log) == 2

    def test_skip_also_advances_next_index(self, orch):
        """SPEC.md 6.1: skip should advance next_index to i+1."""
        orch._handle_skip(index=0, reason="Test")
        assert orch.state.next_index == 1


# ---------------------------------------------------------------------------
# 譛螟ｧ隧ｦ陦悟屓謨ｰ (SPEC.md ﾂｧ6.2 窶・1譌･3蛟呵｣懊∪縺ｧ)
# ---------------------------------------------------------------------------


class TestMaxAttempts:
    def test_default_max_attempts_is_3(self, orch):
        assert orch.max_attempts == 3

    def test_custom_max_attempts(self, works, state):
        orch = Orchestrator(works=works, state=state, max_attempts=1)
        assert orch.max_attempts == 1


# ---------------------------------------------------------------------------
# Exhausted 迥ｶ諷・(SPEC.md ﾂｧ6.1 窶・繝ｩ繝・・縺励↑縺・
# ---------------------------------------------------------------------------


class TestExhaustedBehavior:
    def test_exhausted_when_next_index_equals_len(self, works):
        state = StateJson(next_index=3, status="active", skip_log=[])
        orch = Orchestrator(works=works, state=state, max_attempts=3)
        assert orch.state.next_index >= len(orch.works)

    def test_select_candidate_raises_at_end(self, works):
        state = StateJson(next_index=3, status="active", skip_log=[])
        orch = Orchestrator(works=works, state=state, max_attempts=3)
        with pytest.raises((IndexError, ValueError, StopIteration)):
            orch._select_candidate(3)

    def test_no_wrap_next_index_never_resets(self, orch, works):
        """next_index must not wrap to 0 when it reaches works length."""
        for i in range(len(works)):
            orch._update_state(next_index=i + 1)
        assert orch.state.next_index == len(works)
        initial = orch.state.next_index
        assert initial == len(works)


@pytest.mark.xfail(strict=True, reason="run() not implemented yet")
class TestRunStateTransitions:
    """SPEC.md 6.5.1 unified transition table coverage for run-level behavior."""

    def test_critical_failure_does_not_advance_state(self, orch):
        before = orch.state.next_index
        orch.run("2026-03-05")
        assert orch.state.next_index == before

    def test_success_with_non_critical_failure_advances_state(self, orch):
        before = orch.state.next_index
        orch.run("2026-03-05")
        assert orch.state.next_index > before

"""Agent 0 — Orchestrator: daily run coordination."""

from __future__ import annotations

import datetime

from aozora.models import SkipLogEntry, StateJson, WorkEntry


class Orchestrator:
    def __init__(self, works: list[WorkEntry], state: StateJson, max_attempts: int = 3) -> None:
        self.works = works
        self.state = state
        self.max_attempts = max_attempts

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def run(self, date: str) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 候補選択
    # ------------------------------------------------------------------

    def _select_candidate(self, index: int) -> WorkEntry:
        """works リストから index 番目の候補を返す。
        範囲外なら IndexError / ValueError を送出（no-wrap 保証）。
        """
        if index < 0:
            raise ValueError(f"index must be >= 0, got {index}")
        if index >= len(self.works):
            raise IndexError(f"index {index} is out of range (works has {len(self.works)} entries)")
        return self.works[index]

    # ------------------------------------------------------------------
    # 状態管理
    # ------------------------------------------------------------------

    def _handle_skip(self, index: int, reason: str) -> None:
        """候補をスキップし、skip_log に記録して next_index を i+1 に進める。
        SPEC.md §6.1: On ineligible/fail at index i → append skip log and try i+1.
        """
        date_jst = datetime.datetime.now().strftime("%Y-%m-%d")
        card_url = self.works[index].aozora_card_url if index < len(self.works) else ""
        entry = SkipLogEntry(
            date_jst=date_jst,
            index=index,
            card_url=card_url,
            reason=reason,
        )
        self.state.skip_log.append(entry)
        self._update_state(next_index=index + 1)

    def _update_state(self, next_index: int) -> None:
        """next_index を更新する（保存は呼び出し元が行う）。"""
        self.state.next_index = next_index

    # ------------------------------------------------------------------
    # Git 操作（スタブ）
    # ------------------------------------------------------------------

    def _commit_and_push(self, files: list[str]) -> None:
        raise NotImplementedError

    def _check_and_create_exhausted_issue(self) -> None:
        raise NotImplementedError

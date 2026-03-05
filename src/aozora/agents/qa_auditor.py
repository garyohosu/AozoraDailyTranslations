"""Agent 5 — QA/Auditor: quality gate checks."""

from __future__ import annotations

import math
import re

from aozora.models import FetchResult, QAGateConfig, QAResult

# 青空文庫アーティファクトパターン（英訳後に残存してはいけない記号）
_ARTIFACT_PATTERNS = re.compile(r"《|》|｜|［＃[^］]*］")

# 禁止ボイラープレートフレーズ（大文字小文字を無視）
_DEFAULT_FORBIDDEN = [
    "translation failed",
    "as an ai",
    "i can't",
    "i cannot",
]


class QAAuditor:
    def __init__(self, config: QAGateConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def audit(
        self, translation_en: str, fetch_result: FetchResult, genre: str = "short"
    ) -> QAResult:
        """全ゲートを評価して QAResult を返す。
        いずれかのゲートが FAIL なら status="FAIL"。
        """
        # メトリクス計算
        paragraphs_en = [p.strip() for p in translation_en.split("\n\n") if p.strip()]
        P_en = len(paragraphs_en)
        W_en = len(translation_en.split())
        C_ja = fetch_result.C_ja
        R = W_en / max(1, C_ja)

        gates = {
            "paragraph_count": self._check_paragraph_count(P_en, fetch_result.P_ja),
            "length_ratio": self._check_length_ratio(W_en, C_ja, genre),
            "artifacts": self._check_artifacts(translation_en),
            "boilerplate": self._check_boilerplate(translation_en),
        }

        failed_gates = [k for k, v in gates.items() if v == "FAIL"]
        status = "FAIL" if failed_gates else "PASS"
        reason = f"Failed gates: {failed_gates}" if failed_gates else ""

        return QAResult(
            status=status,
            reason=reason,
            P_en=P_en,
            W_en=W_en,
            R=R,
            gates=gates,
        )

    # ------------------------------------------------------------------
    # ゲート実装
    # ------------------------------------------------------------------

    def _check_paragraph_count(self, P_en: int, P_ja: int) -> str:
        """SPEC.md §5.1: abs(P_en - P_ja) > max(2, ceil(0.15 * P_ja)) なら FAIL。"""
        tolerance = max(2, math.ceil(0.15 * P_ja))
        return "FAIL" if abs(P_en - P_ja) > tolerance else "PASS"

    def _check_length_ratio(self, W_en: int, C_ja: int, genre: str) -> str:
        """SPEC.md §5.1: R = W_en / max(1, C_ja) がしきい値外なら FAIL。"""
        R = W_en / max(1, C_ja)
        if genre == "poem":
            ok = self.config.poem_r_min <= R <= self.config.poem_r_max
        else:  # "short"
            ok = self.config.short_r_min <= R <= self.config.short_r_max
        return "PASS" if ok else "FAIL"

    def _check_artifacts(self, text: str) -> str:
        """SPEC.md §5.1: 青空文庫記号の残存が max_artifact_count 超なら FAIL。"""
        count = len(_ARTIFACT_PATTERNS.findall(text))
        return "FAIL" if count > self.config.max_artifact_count else "PASS"

    def _check_boilerplate(self, text: str) -> str:
        """SPEC.md §5.1: 禁止フレーズが含まれたら FAIL（大文字小文字無視）。"""
        lower = text.lower()
        for phrase in self.config.forbidden_phrases:
            if phrase.lower() in lower:
                return "FAIL"
        return "PASS"

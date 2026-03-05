"""Data models — WorkEntry, StateJson and related types."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse


def _validate_aozora_url(url: str, field_name: str) -> None:
    """scheme が http/https かつ host が aozora.gr.jp またはサブドメインであることを検証。"""
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"{field_name}: URL のパースに失敗しました: {url!r}") from exc
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{field_name}: URL scheme must be http or https: {url!r}")
    host = parsed.hostname or ""
    if host != "aozora.gr.jp" and not host.endswith(".aozora.gr.jp"):
        raise ValueError(f"{field_name}: URL host must be aozora.gr.jp or a subdomain: {url!r}")


@dataclass
class WorkEntry:
    aozora_card_url: str
    aozora_txt_url: str
    title_en: str
    author_en: str
    genre: str
    title_ja: Optional[str] = None
    author_ja: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.genre not in ("poem", "short"):
            raise ValueError(f"genre は 'poem' または 'short' でなければなりません: {self.genre!r}")
        _validate_aozora_url(self.aozora_card_url, "aozora_card_url")
        _validate_aozora_url(self.aozora_txt_url, "aozora_txt_url")
        if not self.title_en:
            raise ValueError("title_en は空にできません")
        if len(self.title_en) > 200:
            raise ValueError("title_en は 200 文字以内でなければなりません")
        if not self.author_en:
            raise ValueError("author_en は空にできません")
        if len(self.author_en) > 200:
            raise ValueError("author_en は 200 文字以内でなければなりません")


@dataclass
class SkipLogEntry:
    date_jst: str
    index: int
    card_url: str
    reason: str


@dataclass
class StateJson:
    next_index: int
    status: str
    skip_log: List[SkipLogEntry]

    @classmethod
    def load(cls, path: str) -> StateJson:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        skip_log = [
            SkipLogEntry(
                date_jst=e["date_jst"],
                index=e["index"],
                card_url=e["card_url"],
                reason=e["reason"],
            )
            for e in data.get("skip_log", [])
        ]
        status = data.get("status", "active")
        if status not in ("active", "exhausted"):
            raise ValueError(f"state.json: status must be 'active' or 'exhausted', got {status!r}")
        return cls(
            next_index=data["next_index"],
            status=status,
            skip_log=skip_log,
        )

    def save(self, path: str) -> None:
        data = {
            "next_index": self.next_index,
            "status": self.status,
            "skip_log": [
                {
                    "date_jst": e.date_jst,
                    "index": e.index,
                    "card_url": e.card_url,
                    "reason": e.reason,
                }
                for e in self.skip_log
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def is_exhausted(self) -> bool:
        return self.status == "exhausted"

    def set_exhausted(self) -> None:
        self.status = "exhausted"


@dataclass
class FetchResult:
    raw_text_ja: str
    clean_text_ja: str
    P_ja: int
    C_ja: int


@dataclass
class TranslationResult:
    translation_en: str
    introduction_en: str
    source: str


@dataclass
class ScreenResult:
    status: str  # "ELIGIBLE" | "INELIGIBLE"
    reason: str


@dataclass
class QAResult:
    status: str  # "PASS" | "FAIL"
    reason: str
    P_en: int
    W_en: int
    R: float
    gates: dict = field(default_factory=dict)


@dataclass
class QAGateConfig:
    max_artifact_count: int = 3
    short_r_min: float = 0.28
    short_r_max: float = 0.95
    poem_r_min: float = 0.18
    poem_r_max: float = 1.20
    forbidden_phrases: List[str] = field(
        default_factory=lambda: [
            "translation failed",
            "as an ai",
            "i can't",
            "i cannot",
        ]
    )


@dataclass
class PublishResult:
    work_page_path: str
    index_paths: List[str]
    seo_paths: List[str]


@dataclass
class AttemptLog:
    index: int
    card_url: str
    result: str  # "SUCCESS" | "SKIP"
    reason: str
    output_path: str


@dataclass
class RunLog:
    run_date: str
    run_datetime_jst: str
    attempts: List[AttemptLog]
    final_status: str
    api_cost_usd: float

    def save(self, path: str) -> None:
        data = {
            "run_date": self.run_date,
            "run_datetime_jst": self.run_datetime_jst,
            "attempts": [
                {
                    "index": a.index,
                    "card_url": a.card_url,
                    "result": a.result,
                    "reason": a.reason,
                    "output_path": a.output_path,
                }
                for a in self.attempts
            ],
            "final_status": self.final_status,
            "api_cost_usd": self.api_cost_usd,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

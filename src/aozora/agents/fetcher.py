"""Agent 2 — Fetcher/Normalizer."""

from __future__ import annotations

import re

import chardet

from aozora.models import FetchResult

DECODE_ORDER = ["shift_jis_2004", "cp932", "utf-8", "euc-jp"]

# 青空文庫のルビ・注釈パターン (QA.md Q3-3)
_RUBY_VERTICAL = re.compile(r"｜(.+?)《.+?》")  # ｜漢字《かんじ》 → 漢字
_RUBY_PLAIN = re.compile(r"《.+?》")  # 漢字《かんじ》 → 漢字（《》を削除）
_ANNOTATION = re.compile(r"［＃[^］]*］")  # ［＃...］ → 削除
_EXCESS_BLANK = re.compile(r"\n{3,}")


class Fetcher:
    max_retries: int = 3
    timeout_sec: int = 60
    _decode_order: list[str] = DECODE_ORDER  # テストで上書き可能

    def fetch(self, txt_url: str) -> FetchResult:
        raise NotImplementedError

    def _download_with_retry(self, url: str) -> bytes:
        raise NotImplementedError

    def _extract_text(self, data: bytes) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # テキスト正規化
    # ------------------------------------------------------------------

    def remove_ruby(self, text: str) -> str:
        """ルビ記法を除去して本文のみ残す。"""
        text = _RUBY_VERTICAL.sub(r"\1", text)  # ｜漢字《かんじ》 → 漢字
        text = _RUBY_PLAIN.sub("", text)  # 残った《かんじ》を削除
        return text

    def remove_annotations(self, text: str) -> str:
        """青空文庫の傍点・注釈記法 ［＃...］ を除去する。"""
        return _ANNOTATION.sub("", text)

    def count_paragraphs(self, text: str) -> int:
        """空行区切りで段落数をカウントする。\\r\\n にも対応。"""
        normalized = re.sub(r"\r\n", "\n", text)
        normalized = _EXCESS_BLANK.sub("\n\n", normalized)
        paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
        return len(paragraphs)

    # ------------------------------------------------------------------
    # エンコーディング検出
    # ------------------------------------------------------------------

    def _decode_with_fallback(self, raw: bytes) -> tuple[str, str]:
        """chardet 検出 → DECODE_ORDER でフォールバックデコードを試みる。

        chardet の結果が DECODE_ORDER に含まれない場合は無視する
        （誤検出で Hebrew 等の Latin 系に引っかかる問題を防ぐ）。
        すべて失敗した場合は ValueError を送出。
        """
        detected = (chardet.detect(raw).get("encoding") or "").lower()
        order = self._decode_order
        order_lower = [e.lower() for e in order]

        # chardet 結果を先頭に置くが、_decode_order に含まれるものに限る
        candidates: list[str] = []
        if detected in order_lower:
            candidates.append(detected)
        for enc in order:
            if enc.lower() not in [c.lower() for c in candidates]:
                candidates.append(enc)

        for enc in candidates:
            try:
                return raw.decode(enc), enc
            except (UnicodeDecodeError, LookupError):
                continue
        raise ValueError("全エンコーディングでデコードに失敗しました")

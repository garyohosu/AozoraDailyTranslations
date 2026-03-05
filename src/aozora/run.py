"""Daily runner for AozoraDailyTranslations.

Minimal production runner for OpenClaw cron:
- loads DATA/works.json + DATA/state.json
- picks next work
- fetches source text (best effort)
- translates (Codex CLI -> local LLM fallback -> safe placeholder)
- QA audit
- generates works/YYYY-MM-DD-slug/index.html
- regenerates top index.html
- updates state + run log
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from aozora.agents.qa_auditor import QAAuditor
from aozora.generators.work_page import WorkPageGenerator
from aozora.models import (
    FetchResult,
    QAGateConfig,
    RunLog,
    AttemptLog,
    StateJson,
    TranslationResult,
    WorkEntry,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "DATA"
LOGS = DATA / "logs"
WORKS_DIR = ROOT / "works"


def _today_jst() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


def _ensure_data_files() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    works = DATA / "works.json"
    state = DATA / "state.json"

    if not works.exists():
        works.write_text(
            json.dumps(
                [
                    {
                        "aozora_card_url": "https://www.aozora.gr.jp/cards/000879/card128.html",
                        "aozora_txt_url": "https://www.aozora.gr.jp/cards/000879/files/128_15261.html",
                        "title_en": "Rashomon",
                        "author_en": "Akutagawa Ryunosuke",
                        "title_ja": "羅生門",
                        "author_ja": "芥川龍之介",
                        "genre": "short",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if not state.exists():
        state.write_text(
            json.dumps(
                {"next_index": 0, "status": "active", "skip_log": []},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _load_works() -> List[WorkEntry]:
    raw = json.loads((DATA / "works.json").read_text(encoding="utf-8"))
    return [WorkEntry(**w) for w in raw]


def _slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "untitled"


def _fetch_clean_ja(txt_url: str, timeout: int = 30) -> str:
    r = requests.get(txt_url, timeout=timeout, headers={"User-Agent": "AozoraDailyTranslations/1.0"})
    r.raise_for_status()
    html = r.content.decode("cp932", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    text = re.sub(r"［＃[^］]*］", "", text)
    text = re.sub(r"《.+?》", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ask_codex(prompt: str, timeout: int = 600) -> str:
    res = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "codex failed")
    out = (res.stdout or "").strip()
    if not out:
        raise RuntimeError("codex empty output")
    return out


def _ask_local_llm(prompt: str) -> str:
    endpoints = [
        os.environ.get("OLLAMA_HOST", "").rstrip("/"),
        "http://192.168.11.2:11434",
        "http://172.25.192.1:11434",
        "http://localhost:11434",
    ]
    endpoints = [e for e in endpoints if e]
    last = None
    for ep in endpoints:
        try:
            resp = requests.post(
                f"{ep}/api/generate",
                json={"model": "phi3:mini", "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            out = (resp.json().get("response") or "").strip()
            if out:
                return out
        except Exception as e:
            last = e
    raise RuntimeError(f"local llm failed: {last}")


def _translate(clean_ja: str, title_en: str, author_en: str) -> TranslationResult:
    excerpt = clean_ja[:3500]
    prompt = (
        "Translate the following Japanese literary excerpt into natural modern English.\n"
        "Return JSON only with keys: translation_en, introduction_en.\n"
        f"title: {title_en}\nauthor: {author_en}\n\nTEXT:\n{excerpt}"
    )

    # primary: Codex CLI
    try:
        raw = _ask_codex(prompt, timeout=600)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        return TranslationResult(
            translation_en=str(data.get("translation_en", "")).strip(),
            introduction_en=str(data.get("introduction_en", "")).strip(),
            source="codex-cli",
        )
    except Exception:
        pass

    # fallback: local LLM
    try:
        raw = _ask_local_llm(prompt)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        return TranslationResult(
            translation_en=str(data.get("translation_en", "")).strip(),
            introduction_en=str(data.get("introduction_en", "")).strip(),
            source="local-llm",
        )
    except Exception:
        pass

    # last resort
    return TranslationResult(
        translation_en="Automatic translation is temporarily unavailable. Please check back later.",
        introduction_en="This page was generated, but translation failed in the current run.",
        source="fallback",
    )


def _write_index() -> None:
    works = sorted(WORKS_DIR.glob("*/index.html"), reverse=True)
    items = []
    for p in works[:50]:
        slug = p.parent.name
        date = slug[:10]
        title = slug[11:].replace("-", " ").title()
        items.append(f'<li><a href="./works/{slug}/index.html">{title}</a> <small>({date})</small></li>')
    html = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Aozora Daily Translations</title></head>"
        "<body><h1>Aozora Daily Translations</h1><ul>"
        + "\n".join(items)
        + "</ul></body></html>"
    )
    (ROOT / "index.html").write_text(html, encoding="utf-8")


def run(date: str) -> Dict:
    _ensure_data_files()
    works = _load_works()
    state = StateJson.load(str(DATA / "state.json"))

    if state.next_index >= len(works):
        state.set_exhausted()
        state.save(str(DATA / "state.json"))
        return {"status": "exhausted", "published": None}

    idx = state.next_index
    w = works[idx]

    clean = _fetch_clean_ja(w.aozora_txt_url)
    fetch = FetchResult(raw_text_ja=clean, clean_text_ja=clean, P_ja=max(1, clean.count("\n\n") + 1), C_ja=len(clean))
    tr = _translate(clean, w.title_en, w.author_en)

    qa = QAAuditor(QAGateConfig()).audit(tr.translation_en, fetch, genre=w.genre)
    if qa.status == "FAIL":
        tr = TranslationResult(
            translation_en=tr.translation_en,
            introduction_en=(tr.introduction_en or "") + " (QA warning)",
            source=tr.source,
        )

    gen = WorkPageGenerator()
    body = gen.generate(w, tr, date)
    slug = f"{date}-{_slugify(w.title_en)}"
    out = WORKS_DIR / slug / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")

    _write_index()

    state.next_index = idx + 1
    if state.next_index >= len(works):
        state.set_exhausted()
    state.save(str(DATA / "state.json"))

    log = RunLog(
        run_date=date,
        run_datetime_jst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        attempts=[
            AttemptLog(index=idx, card_url=w.aozora_card_url, result="SUCCESS", reason="", output_path=str(out))
        ],
        final_status="SUCCESS",
        api_cost_usd=0.0,
    )
    log.save(str(LOGS / f"{date}.json"))

    return {"status": "ok", "published": str(out), "source": tr.source, "qa": qa.status}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=_today_jst())
    args = ap.parse_args()
    res = run(args.date)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()

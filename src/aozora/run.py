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
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from aozora.agents.qa_auditor import QAAuditor
from aozora.generators.work_page import WorkPageGenerator
from aozora.models import (
    AttemptLog,
    FetchResult,
    QAGateConfig,
    RunLog,
    StateJson,
    TranslationResult,
    WorkEntry,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "DATA"
LOGS = DATA / "logs"
WORKS_DIR = ROOT / "works"

AOZORA_DEFAULT_SOURCE = "https://www.aozora.gr.jp/index_pages/person879.html"  # 芥川龍之介
AUTO_FILL_TARGET = int(os.environ.get("AOZORA_WORKS_TARGET", "200"))

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


def _load_works() -> list[WorkEntry]:
    raw = json.loads((DATA / "works.json").read_text(encoding="utf-8"))
    return [WorkEntry(**w) for w in raw]


def _save_works(works: list[WorkEntry]) -> None:
    payload = []
    for w in works:
        payload.append(
            {
                "aozora_card_url": w.aozora_card_url,
                "aozora_txt_url": w.aozora_txt_url,
                "title_en": w.title_en,
                "author_en": w.author_en,
                "title_ja": w.title_ja,
                "author_ja": w.author_ja,
                "genre": w.genre,
            }
        )
    (DATA / "works.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "untitled"


def _guess_genre(title_ja: str) -> str:
    t = title_ja or ""
    poem_hints = ["詩", "短歌", "俳句", "句集"]
    return "poem" if any(h in t for h in poem_hints) else "short"


def _has_non_ascii(text: str) -> bool:
    return any(ord(ch) > 127 for ch in (text or ""))


def _card_id_from_url(card_url: str) -> str:
    m = re.search(r"card(\d+)\.html$", card_url)
    return m.group(1) if m else "unknown"


def _extract_card_urls_from_person_page(url: str) -> list[str]:
    r = requests.get(url, timeout=30, headers={"User-Agent": "AozoraDailyTranslations/1.0"})
    r.raise_for_status()
    html = r.content.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/cards/" in href and re.search(r"card\d+\.html$", href):
            out.append(requests.compat.urljoin(url, href))
    # preserve order + dedupe
    seen = set()
    uniq = []
    for c in out:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return uniq


def _extract_labeled_value(soup: BeautifulSoup, label: str) -> str:
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue
        if th.get_text(" ", strip=True) == label:
            return td.get_text(" ", strip=True)
    return ""


def _extract_author_romaji(soup: BeautifulSoup) -> str:
    value = _extract_labeled_value(soup, "ローマ字表記：")
    return value.strip()


def _build_work_from_card(card_url: str):
    r = requests.get(card_url, timeout=30, headers={"User-Agent": "AozoraDailyTranslations/1.0"})
    r.raise_for_status()
    html = r.content.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    # Prefer structured metadata table on card page
    title_ja = _extract_labeled_value(soup, "作品名：")
    author_ja = _extract_labeled_value(soup, "著者名：")

    # Fallback to OG title: "作品名 (著者名)"
    if not title_ja or not author_ja:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            content = og["content"].strip()
            m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", content)
            if m:
                title_ja = title_ja or m.group(1).strip()
                author_ja = author_ja or m.group(2).strip()

    # Last fallback: avoid generic h1/h2 labels (図書カード:No.xxx / 作品データ)
    if not title_ja:
        title_tag = soup.find("title")
        tt = title_tag.get_text(" ", strip=True) if title_tag else ""
        title_ja = re.sub(r"^図書カード：", "", tt).strip()
    if not author_ja:
        author_ja = "Unknown"

    txt_url = ""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/files/" in href and href.endswith(".html"):
            txt_url = requests.compat.urljoin(card_url, href)
            break
    if not txt_url:
        return None

    # Guard against bad placeholders
    bad_title = (not title_ja) or title_ja.startswith("図書カード") or title_ja == "作品データ"
    bad_author = (not author_ja) or author_ja == "作品データ"
    if bad_title or bad_author:
        return None

    card_id = _card_id_from_url(card_url)
    title_en = title_ja if not _has_non_ascii(title_ja) else f"Aozora Work No.{card_id}"

    author_romaji = _extract_author_romaji(soup)
    if author_romaji:
        author_en = author_romaji
    else:
        author_en = author_ja if not _has_non_ascii(author_ja) else f"Author No.{card_id}"

    return WorkEntry(
        aozora_card_url=card_url,
        aozora_txt_url=txt_url,
        title_en=title_en,
        author_en=author_en,
        title_ja=title_ja,
        author_ja=author_ja,
        genre=_guess_genre(title_ja),
    )


def _autofill_works_if_needed(target_count: int = AUTO_FILL_TARGET) -> None:
    works = _load_works()

    # Drop malformed placeholders created by naive parsers / normalize old rows
    cleaned = []
    for w in works:
        if w.title_en.startswith("図書カード") or w.title_en == "作品データ":
            continue
        if w.author_en == "作品データ":
            continue

        # Backfill legacy rows where *_en is still Japanese text
        if _has_non_ascii(w.title_en) or _has_non_ascii(w.author_en):
            card_id = _card_id_from_url(w.aozora_card_url)
            # keep Japanese in *_ja, normalize *_en to ASCII-safe values
            if _has_non_ascii(w.title_en):
                w.title_en = f"Aozora Work No.{card_id}"
            if _has_non_ascii(w.author_en):
                w.author_en = f"Author No.{card_id}"
        cleaned.append(w)
    works = cleaned

    if len(works) >= target_count:
        _save_works(works)
        return

    existing_cards = {w.aozora_card_url for w in works}
    cards = _extract_card_urls_from_person_page(AOZORA_DEFAULT_SOURCE)

    for card in cards:
        if len(works) >= target_count:
            break
        if card in existing_cards:
            continue
        err = None
        try:
            w = _build_work_from_card(card)
        except Exception as exc:
            w = None
            err = exc
        if not w:
            _ = err  # keep loop resilient for noisy source pages
            continue
        works.append(w)
        existing_cards.add(w.aozora_card_url)

    _save_works(works)


def _fetch_clean_ja(txt_url: str, timeout: int = 30) -> str:
    r = requests.get(
        txt_url,
        timeout=timeout,
        headers={"User-Agent": "AozoraDailyTranslations/1.0"},
    )
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
    codex_err = None
    try:
        raw = _ask_codex(prompt, timeout=600)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        return TranslationResult(
            translation_en=str(data.get("translation_en", "")).strip(),
            introduction_en=str(data.get("introduction_en", "")).strip(),
            source="codex-cli",
        )
    except Exception as exc:
        codex_err = exc

    # fallback: local LLM
    local_err = None
    try:
        raw = _ask_local_llm(prompt)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        return TranslationResult(
            translation_en=str(data.get("translation_en", "")).strip(),
            introduction_en=str(data.get("introduction_en", "")).strip(),
            source="local-llm",
        )
    except Exception as exc:
        local_err = exc

    # last resort
    err_note = f"codex={codex_err}; local={local_err}"
    return TranslationResult(
        translation_en="Automatic translation is temporarily unavailable. Please check back later.",
        introduction_en=(
            "This page was generated, but translation failed in the current run. "
            + err_note[:180]
        ),
        source="fallback",
    )


def _write_index() -> None:
    works = sorted(WORKS_DIR.glob("*/index.html"), reverse=True)
    cards = []
    for p in works[:50]:
        slug = p.parent.name
        date = slug[:10]
        title = slug[11:].replace("-", " ").title()
        cards.append(
            f'<article class="col-12 col-md-6">'
            f'<a class="text-decoration-none text-dark" href="./works/{slug}/index.html">'
            f'<div class="work-card bg-white p-4 h-100">'
            f'<p class="text-secondary small mb-2">{date}</p>'
            f'<h3 class="h5 mb-2">{title}</h3>'
            f"<p class=\"text-muted mb-0\">Read today's translation</p>"
            f"</div></a></article>"
        )

    html = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Aozora Daily Translations</title>
  <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\">
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
  <link
    href=\"https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@700&family=Inter:wght@400;500;700&display=swap\"
    rel=\"stylesheet\"
  >
  <link rel=\"stylesheet\" href=\"./assets/style.css\">
</head>
<body class=\"bg-body-tertiary\">
  <header class=\"border-bottom bg-white\">
    <div class=\"container py-4\">
      <div class=\"d-flex justify-content-between align-items-center\">
        <h1 class=\"h3 mb-0 site-brand\">Aozora Daily Translations</h1>
        <span class=\"badge text-bg-dark\">Daily</span>
      </div>
      <p class=\"text-secondary mt-2 mb-0\">
        Modern English translations of Aozora Bunko public-domain works.
      </p>
    </div>
  </header>

  <main class=\"container my-4\">
    <div class=\"row g-3\">{cards}</div>
  </main>
</body>
</html>""".format(cards="\n".join(cards) if cards else '<p class="text-muted">No works yet.</p>')

    (ROOT / "index.html").write_text(html, encoding="utf-8")


def run(date: str) -> dict:
    _ensure_data_files()
    _autofill_works_if_needed(AUTO_FILL_TARGET)
    works = _load_works()
    state = StateJson.load(str(DATA / "state.json"))

    if state.next_index >= len(works):
        state.set_exhausted()
        state.save(str(DATA / "state.json"))
        return {"status": "exhausted", "published": None}

    idx = state.next_index
    w = works[idx]

    clean = _fetch_clean_ja(w.aozora_txt_url)
    fetch = FetchResult(
        raw_text_ja=clean,
        clean_text_ja=clean,
        P_ja=max(1, clean.count("\n\n") + 1),
        C_ja=len(clean),
    )
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
            AttemptLog(
                index=idx,
                card_url=w.aozora_card_url,
                result="SUCCESS",
                reason="",
                output_path=str(out),
            )
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
    sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

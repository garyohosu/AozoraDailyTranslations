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
EN_MAP_FILE = DATA / "en_map.json"


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


def _load_en_map() -> dict:
    if not EN_MAP_FILE.exists():
        return {}
    try:
        return json.loads(EN_MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_en_map(m: dict) -> None:
    EN_MAP_FILE.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


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

    if not _has_non_ascii(title_ja):
        title_en = title_ja
    else:
        title_en = _translate_label_ja_to_en(title_ja, "title")

    author_romaji = _extract_author_romaji(soup)
    if author_romaji:
        author_en = author_romaji
    elif not _has_non_ascii(author_ja):
        author_en = author_ja
    else:
        author_en = _translate_label_ja_to_en(author_ja, "author")

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

        # Backfill legacy rows where *_en is JP text or placeholder strings
        need_title = _has_non_ascii(w.title_en) or w.title_en.startswith("Aozora Work No.")
        need_author = _has_non_ascii(w.author_en) or w.author_en.startswith("Author No.")

        if need_title:
            w.title_en = _translate_label_ja_to_en(w.title_ja or w.title_en, "title")
        if need_author:
            # try roma label from card first
            try:
                rr = requests.get(
                    w.aozora_card_url,
                    timeout=20,
                    headers={"User-Agent": "AozoraDailyTranslations/1.0"},
                )
                rr.raise_for_status()
                ss = BeautifulSoup(rr.content.decode("utf-8", errors="ignore"), "html.parser")
                roma = _extract_author_romaji(ss)
            except Exception:
                roma = ""
            w.author_en = roma or _translate_label_ja_to_en(w.author_ja or w.author_en, "author")
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

    # Prefer the main body container and avoid bibliographic sections.
    main = soup.select_one(".main_text") or soup.find("div", id="honbun")
    text = main.get_text("\n") if main else soup.get_text("\n")

    text = re.sub(r"［＃[^］]*］", "", text)
    text = re.sub(r"《.+?》", "", text)

    # Split out bibliographic/production metadata that should not be translated.
    lines = [ln.strip() for ln in text.splitlines()]
    cutoff_markers = (
        "底本：",
        "初出：",
        "注記：",
        "入力：",
        "校正：",
        "作成日：",
        "更新日：",
        "青空文庫作成ファイル：",
        "このファイルは、インターネット図書館",
        "このファイルは、",
        "作品データ",
    )
    body_lines = []
    for ln in lines:
        if not ln:
            body_lines.append("")
            continue
        if any(ln.startswith(m) for m in cutoff_markers):
            break
        body_lines.append(ln)

    text = "\n".join(body_lines)
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


def _translate_label_ja_to_en(text_ja: str, kind: str = "title") -> str:
    txt = (text_ja or "").strip()
    if not txt:
        return ""

    en_map = _load_en_map()
    cache_key = f"{kind}:{txt}"
    cached = en_map.get(cache_key)
    if cached:
        return str(cached)

    prompt = (
        "Translate Japanese text into natural English. Return only translated text, no quotes.\n"
        "If person name, use common romanization.\n"
        f"kind={kind}\n"
        f"text={txt}"
    )

    result = None
    try:
        result = _ask_codex(prompt, timeout=120)
    except Exception:
        try:
            result = _ask_local_llm(prompt)
        except Exception:
            result = txt

    out = (result or txt).strip().splitlines()[0].strip('"').strip("'")
    if not out:
        out = txt
    en_map[cache_key] = out
    _save_en_map(en_map)
    return out


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
            "This page was generated, but translation failed in the current run. " + err_note[:180]
        ),
        source="fallback",
    )


def _read_work_title(work_index_path: Path, slug: str) -> str:
    try:
        html = work_index_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)
            if title:
                return title
    except Exception as exc:
        _ = exc
    return slug[11:].replace("-", " ").title()


def _write_index() -> None:
    works = sorted(WORKS_DIR.glob("*/index.html"), reverse=True)
    cards = []
    for idx, p in enumerate(works[:50]):
        slug = p.parent.name
        date = slug[:10]
        title = _read_work_title(p, slug)
        delay = min(idx * 100, 600)
        cards.append(
            f'<div data-aos="fade-up" data-aos-delay="{delay}">'
            f'<a class="az-card" href="./works/{slug}/index.html">'
            f'<span class="az-card-date">{date}</span>'
            f'<span class="az-card-title">{title}</span>'
            f'<span class="az-card-cta">Read translation →</span>'
            f'</a></div>'
        )

    all_cards = "\n".join(cards) if cards else '<p class="text-muted">No works yet.</p>'

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aozora Daily Translations</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/aos@2.3.4/dist/aos.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link
    href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@700&family=Crimson+Pro:ital,wght@0,400;0,600;1,400&family=Noto+Serif+JP:wght@300;400&display=swap"
    rel="stylesheet"
  >
  <link rel="stylesheet" href="./assets/style.css">
</head>
<body style="background:#FAF7F0; color:#2C2C3E; min-height:100vh;">

  <header style="background:#1A1A2E; position:relative; overflow:hidden;">
    <div class="az-watermark" aria-hidden="true">青空</div>

    <div class="max-w-5xl mx-auto px-6 pt-14 pb-20 relative" style="z-index:10;">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="az-jp-label">青空文庫 × English</p>
          <h1 class="az-site-title">
            Aozora Daily<br>Translations
          </h1>
          <p class="az-site-desc">
            One Japanese classic, translated fresh every day.<br>
            Public domain. Free forever.
          </p>
        </div>
        <span class="az-daily-badge">Daily</span>
      </div>
    </div>

    <div style="position:absolute; bottom:0; left:0; width:100%; line-height:0;" aria-hidden="true">
      <svg viewBox="0 0 1200 60" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg"
           style="display:block; width:100%; height:60px;">
        <path
          d="M0,40 C150,10 350,55 600,30 C850,5 1050,50 1200,35 L1200,60 L0,60 Z"
          fill="#FAF7F0"
        />
      </svg>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-6 py-12">
    <p class="az-section-label">Latest Translations</p>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">{all_cards}</div>
  </main>

  <footer class="max-w-5xl mx-auto px-6 pb-12">
    <div style="border-top:1px solid #E8E4DC; padding-top:2rem; margin-top:2rem;">
      <p class="az-footer-text">
        Translations generated from
        <a href="https://www.aozora.gr.jp/" target="_blank" rel="noopener" class="az-link">
          Aozora Bunko
        </a>
        public domain works. English translations: <strong>CC0 1.0 Universal</strong>.
      </p>
    </div>
  </footer>

  <script src="https://cdn.jsdelivr.net/npm/aos@2.3.4/dist/aos.js"></script>
  <script>AOS.init({{ once: true, duration: 650, easing: 'ease-out' }});</script>
</body>
</html>"""

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

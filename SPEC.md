# SPEC.md — Aozora Daily Translations

Repository: https://github.com/garyohosu/AozoraDailyTranslations.git  
Site name: **Aozora Daily Translations**  
Publishing: **GitHub Pages**  
Content: **English only** (no Japanese text displayed)  
Translation license (English output): **CC0**  
Cadence: **1 work per day** (short stories / poems)

---

## 1. Goal

Automatically publish **one** English translation per day from Aozora Bunko public-domain works (short stories / poems) to GitHub Pages as static HTML.

---

## 2. Non-Goals

- Displaying Japanese text on pages
- Serializing long novels (no chapter splitting)
- Full automatic discovery across Aozora Bunko (selection is from a curated candidate list)
- Guaranteeing perfect translation accuracy (auto-translation disclaimer is mandatory)

---

## 3. Inputs & Outputs

### 3.1 Inputs

- `DATA/works.json` (candidate list, curated)
  - `aozora_card_url` (bibliographic card URL)
  - `aozora_txt_url` (text source URL; zip/txt/html)
  - `title_ja`, `author_ja`
  - `genre` (`poem` or `short`)
  - optional metadata (Aozora IDs, notes)

- `DATA/state.json` (progress tracker)
  - next candidate index
  - skip history (optional)

- Run context
  - execution date (JST)
  - site settings (site title, base URL, etc.)

### 3.2 Outputs

- Work page (English only)
  - `/works/YYYY-MM-DD-<slug>/index.html`

- Home page (latest + archive)
  - `/index.html` (or generated from template)

- Optional author pages (recommended for SEO)
  - `/authors/<author-slug>/index.html`

- Supporting files
  - `/assets/` (CSS, favicon, etc.)
  - `/sitemap.xml`
  - `/robots.txt`
  - updated `DATA/state.json`

---

## 4. Legal & Compliance Requirements

### 4.1 Eligibility Rules (must be satisfied)

A work can be processed only if **all** are true:

- Aozora Bunko card indicates the work is **public domain in Japan** (copyright expired)
- Content type is **short story** or **poem**
- Source text can be fetched and parsed from Aozora Bunko distribution (zip/txt/html)

### 4.2 Exclusion Rules (must be excluded / skipped)

Skip a candidate if **any** is true:

- The work is a **Japanese translation of a foreign work** (translation-right risk)
- The content is dominated by annotations/commentary rather than the main text
- The copyright status cannot be determined reliably from the card

**Safety bias:** if uncertain, skip.

### 4.3 Mandatory Credits (on every work page)

Each work page must include a fixed credit block containing:

- `Source (Japanese text): Aozora Bunko (Public Domain in Japan)`
- `Work (Japanese title) / Author (Japanese name)`
- `Aozora Bunko card URL`
- `Input/Proofreading credits: See Aozora Bunko card`
- `English translation license: CC0`
- Auto-translation disclaimer:
  - e.g., “This translation is automatically generated and may contain errors. Please refer to the original Japanese text for authoritative meaning.”

---

## 5. Quality Requirements (Minimum Quality Gates)

Primary failure modes for daily automation:
- missing passages (under-translation)
- duplicated passages (over-generation)
- symbol/ruby artifacts breaking readability
- generic AI boilerplate

### 5.1 Required “Format Gates”

Fail and skip if any gate triggers:

- Paragraph count mismatch: Japanese vs English deviates beyond an acceptable threshold
- Length anomaly:
  - too short (likely missing content)
  - too long (likely duplication / runaway)
- Residual Aozora ruby/annotation artifacts exceed threshold (e.g., excessive `《》`, `｜`)
- Forbidden boilerplate appears:
  - “translation failed”, “as an AI”, “I can’t”, etc.

### 5.2 Recommended “Content Gates”

- Generate a short **Introduction** (100–150 words) per work for SEO and context
- Do not let the model invent title/author; they are injected from metadata

---

## 6. Operational Requirements

### 6.1 Progress Tracking

- `DATA/state.json` stores:
  - next index into `DATA/works.json`
  - optional skip log with date + reason
- On success: increment index and persist state
- On failure: try next candidate(s) within the same run

### 6.2 Retry Policy

Per daily run:
- attempt up to **3 candidates**
- if all fail, publish nothing that day and keep logs

### 6.3 Publishing Policy

- GitHub Actions generates files and **commits/pushes** to the repository
- GitHub Pages serves the latest published static content
- Prefer append-only updates for archives (avoid rewriting older pages unnecessarily)

---

## 7. AI Agent Decomposition

The system is implemented as multiple specialized agents with strict responsibilities to prevent drift.

### Agent 0 — Orchestrator
Responsibilities:
- Select today’s candidate from `works.json` using `state.json`
- Call agents in order; manage retries/skips
- Update state and logs
Inputs: `works.json`, `state.json`, date  
Outputs: generated site files, updated `state.json`, run logs

### Agent 1 — Screener (Eligibility)
Responsibilities:
- Verify public-domain status from Aozora card
- Detect translation-work risk and annotation-heavy works
Output: `ELIGIBLE` or `INELIGIBLE` + reason

### Agent 2 — Fetcher/Normalizer
Responsibilities:
- Download and extract text (zip/txt/html)
- Produce clean Japanese text for translation
- Record metrics (chars, paragraphs)
Outputs: `raw_text_ja`, `clean_text_ja`, metrics

### Agent 3 — Translator (First Pass)
Responsibilities:
- Translate `clean_text_ja` into English
- Preserve paragraph structure
- No fabrication
Output: `translation_en`

### Agent 4 — Editor (Readability)
Responsibilities:
- Improve English fluency without changing meaning
- Preserve line breaks/rhythm for poems
Output: `edited_translation_en`

### Agent 5 — QA/Auditor
Responsibilities:
- Apply quality gates (format + safety checks)
Output: `PASS` / `FAIL` + reason + metrics

### Agent 6 — Publisher
Responsibilities:
- Generate HTML pages and site updates:
  - work page
  - home page archive
  - optional author pages
  - sitemap/robots
Outputs: static files under `/works`, `/index.html`, etc.

---

## 8. Workflow Sequence (Daily)

1. Orchestrator selects candidate (from `works.json` by `state.json` index)
2. Screener checks eligibility
3. Fetcher downloads + normalizes Japanese text
4. Translator produces first-pass English
5. Editor refines the English
6. QA runs gates; on FAIL -> retry next candidate (max 3)
7. Publisher generates site files
8. Orchestrator updates state and pushes changes

---

## 9. Repository Artifacts (before detailed design)

Required:
- `SPEC.md` (this document)
- `DATA/works.json` (candidate list)
- `DATA/state.json` (progress tracker)
- `PROMPTS/` (agent prompts; to be defined in detailed design)
- `templates/` (HTML templates; to be defined in detailed design)
- `.github/workflows/daily.yml` (cron workflow; to be defined in detailed design)

---

## 10. Fixed Decisions (Locked for Detailed Design)

- Content: **English only**
- Output license: **CC0** for English translations
- Cadence: **1 short story / poem per day**
- Candidate selection: **curated list** (works.json), sequential consumption
- Daily retries: **up to 3 candidates**
- Work page includes:
  - 100–150 word introduction
  - translation body
  - mandatory credits + auto-translation disclaimer

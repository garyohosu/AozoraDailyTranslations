# SPEC.md — Aozora Daily Translations

Repository: https://github.com/garyohosu/AozoraDailyTranslations.git  
Site name: **Aozora Daily Translations**  
Publishing: **GitHub Pages**  
Content: **English only in rendered pages** (Japanese metadata may exist in source JSON only)  
Translation license (English output): **CC0**
Cadence: **1 work per day** (short stories / poems)
Translation engine: **Codex CLI (flat-rate plan) via `exec`, or local LLM as fallback**
Scheduler: **openClaw**

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
  - `title_en`, `author_en` (required for page display; English or romanized)
  - `title_ja`, `author_ja` (optional metadata; not rendered on pages)
  - `genre` (`poem` or `short`)
  - optional metadata (Aozora IDs, notes)

**Field validation rules for `works.json`:**
- `aozora_card_url`, `aozora_txt_url`: required; must be valid URLs with `http`/`https` scheme and host `aozora.gr.jp` or any subdomain of `aozora.gr.jp` (e.g., `www.aozora.gr.jp`, `cdn.aozora.gr.jp`)
- `title_en`, `author_en`: required; non-empty string; max 200 characters
- `title_ja`, `author_ja`: optional; string
- `genre`: required; must be exactly `"poem"` or `"short"` (enum)
- `notes`: optional; string
- On validation failure of any entry: log error and skip that entry at startup; do not abort entire run

**Example `DATA/works.json`:**
```json
[
  {
    "aozora_card_url": "https://www.aozora.gr.jp/cards/000879/card128.html",
    "aozora_txt_url": "https://www.aozora.gr.jp/cards/000879/files/128_15260.html",
    "title_en": "The Spider's Thread",
    "author_en": "Akutagawa Ryunosuke",
    "title_ja": "蜘蛛の糸",
    "author_ja": "芥川龍之介",
    "genre": "short",
    "notes": "Famous short story from 1918"
  },
  {
    "aozora_card_url": "https://www.aozora.gr.jp/cards/001049/card42618.html",
    "aozora_txt_url": "https://www.aozora.gr.jp/cards/001049/files/42618_29555.html",
    "title_en": "Lemon",
    "author_en": "Kajii Motojiro",
    "title_ja": "檸檬",
    "author_ja": "梶井基次郎",
    "genre": "short"
  }
]
```

- `DATA/state.json` (progress tracker)
  - `next_index`
  - optional `skip_log[]`
  - optional `status` (`active` / `exhausted`)

**Example `DATA/state.json`:**
```json
{
  "next_index": 2,
  "status": "active",
  "skip_log": [
    {
      "date_jst": "2026-03-01",
      "index": 0,
      "card_url": "https://www.aozora.gr.jp/cards/...",
      "reason": "Translation of foreign work detected"
    }
  ]
}
```

- Run context
  - execution date (JST)
  - site settings (site title, base URL, etc.)

### 3.2 Outputs

- Work page (English only)
  - `/works/YYYY-MM-DD-<slug>/index.html`
  - `<slug>` generation rules:
    - Convert `title_en` to lowercase
    - Replace spaces and special characters with hyphens
    - Remove leading/trailing hyphens
    - Maximum length: 50 characters
    - Example: "The Spider's Thread" → "the-spiders-thread"
  - **Slug collision:** Because the path includes `YYYY-MM-DD`, same-title works published on different days do not collide. During testing/manual runs on the same date, append `-2`, `-3`, etc. if collision is detected.

- Home page (latest + archive)
  - `/index.html` (or generated from template)

- Optional author pages (recommended for SEO)
  - `/authors/<author-slug>/index.html`
  - `<author-slug>` follows same rules as work slug

- Supporting files
  - `/assets/` (CSS, favicon, etc.)
  - `/sitemap.xml`
  - `/robots.txt` (default: `User-agent: *` / `Allow: /` / `Sitemap: <base_url>/sitemap.xml`)
  - updated `DATA/state.json`

---

## 4. Legal & Compliance Requirements

### 4.1 Eligibility Rules (must be satisfied)

A work can be processed only if **all** are true:

- Aozora Bunko card indicates the work is **public domain in Japan** (copyright expired)
- Content type is **short story** or **poem**
- Source text can be fetched and parsed from Aozora Bunko distribution (zip/txt/html)
- Distribution is legally safe for public web delivery on GitHub Pages (at minimum, no unresolved rights risk in the United States); if not confidently verifiable, do not publish

### 4.2 Exclusion Rules (must be excluded / skipped)

Skip a candidate if **any** is true:

- The work is a **Japanese translation of a foreign work** (translation-right risk)
- The content is dominated by annotations/commentary rather than the main text
- The copyright status cannot be determined reliably from the card
- Legal status for GitHub Pages distribution outside Japan (especially US access) is unclear

**Safety bias:** if uncertain, skip.

### 4.3 CC0 License Rationale

The English translation is generated entirely by AI (Codex CLI or local LLM) with no human authorship contribution. Under US copyright law, AI-generated output without human creative selection or arrangement is not eligible for copyright protection. Therefore, the English translations produced by this pipeline are released under **CC0 1.0 Universal** as a precautionary dedication, making the absence of copyright claims explicit.

This interpretation is applied per-project policy. Maintainers should reassess if human editorial effort becomes substantial.

### 4.4 Mandatory Credits (on every work page)

Each work page must include a fixed credit block containing:

- `Source (Japanese text): Aozora Bunko (Public Domain in Japan)`
- `Work (English/romanized title) / Author (English/romanized name)`
- `Aozora Bunko card URL`
- `Input & Proofreading: See Aozora Bunko card for volunteer contributors`
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

- Paragraph count mismatch:
  - Let `P_ja` = Japanese paragraph count and `P_en` = English paragraph count
  - Fail if `abs(P_en - P_ja) > max(2, ceil(0.15 * P_ja))`
- Length anomaly:
  - Let `C_ja` = Japanese character count (normalized) and `W_en` = English word count
  - Compute `R = W_en / max(1, C_ja)`
  - For `short`: fail if `R < 0.28` or `R > 0.95`
  - For `poem`: fail if `R < 0.18` or `R > 1.20`
  - *(Thresholds are empirically derived from typical translation ratios; adjust based on observed false positives/negatives)*
  - **Validation requirement:** Before first deployment, run the quality gates against at least 15 diverse works (mix of poems and short stories) and confirm false-positive rate < 10%. Record results in `DATA/threshold-calibration.md`.
- Residual Aozora ruby/annotation artifacts exceed threshold:
  - Count occurrences of `《`, `》`, `｜`, `［＃...］` patterns in final English body
  - Fail if total count > 3
- Forbidden boilerplate appears:
  - “translation failed”, “as an AI”, “I can’t”, etc.

### 5.2 Required “Content Gates”

- Generate a short **Introduction** (100–150 words) per work for SEO and context — this is the responsibility of **Agent 3 (Translator)**, generated alongside the translation body
- Do not let the model invent title/author; they are injected from metadata

---

## 6. Operational Requirements

### 6.1 Progress Tracking

- `DATA/state.json` stores:
  - `next_index` (next candidate index into `DATA/works.json`)
  - optional `skip_log[]` entries: `date_jst`, `index`, `card_url`, `reason`
  - optional `status` (`active` or `exhausted`)
- On success at index `i`: set `next_index = i + 1` and persist state
- On ineligible/fail at index `i`: append skip log and try `i + 1` within the same run
- If `next_index >= works.length`: set `status = exhausted` and publish nothing until `works.json` is extended manually (no automatic wrap)

### 6.2 Retry Policy

Per daily run:
- attempt up to **3 candidates**
- if all fail, publish nothing that day, persist advanced `next_index`, and keep logs

### 6.3 Publishing Policy

- **openClaw** triggers the daily workflow (cron schedule)
- The workflow generates files and **commits/pushes** to the repository
- **Concurrency:** openClaw must be configured to prevent concurrent runs (e.g., skip if previous run is still active). This prevents `state.json` write conflicts.
- **Locking implementation (required):** acquire an exclusive lock at startup using `DATA/run.lock`; if lock acquisition fails, terminate the run immediately without side effects.
- GitHub Pages serves the latest published static content
- Prefer append-only updates for archives (avoid rewriting older pages unnecessarily)

### 6.4 Logging Policy

- Persist machine-readable run logs at `DATA/logs/YYYY-MM-DD.json`
- Each log includes: run date/time (JST), attempted indices (max 3), per-candidate result/reason, selected output path (if success), and final status
- Keep logs in git history (no deletion by automation)

**Log schema example:**
```json
{
  "run_date": "2026-03-05",
  "run_datetime_jst": "2026-03-05T09:01:23+09:00",
  "attempts": [
    {
      "index": 2,
      "card_url": "https://www.aozora.gr.jp/cards/...",
      "result": "SKIP",
      "reason": "Translation of foreign work detected"
    },
    {
      "index": 3,
      "card_url": "https://www.aozora.gr.jp/cards/...",
      "result": "SUCCESS",
      "output_path": "/works/2026-03-05-the-spiders-thread/index.html"
    }
  ],
  "final_status": "published",
  "api_cost_usd": 0.42
}
```

### 6.5 Error Handling

**Network Errors:**
- Retry Aozora Bunko text fetches up to 3 times with exponential backoff (1s, 2s, 4s)
- If all retries fail, log error and skip to next candidate

**GitHub API Errors:**
- Rate limit exceeded: fail gracefully and log; do not retry that day
- Push conflicts: attempt to pull and rebase once; if unresolved, fail and alert

**Partial Failures:**
- **Critical outputs:** work page generation and push success for the commit that contains the work page.
- `state.json` may advance only when critical outputs succeed.
- If sitemap/robots.txt generation fails but work page succeeds: log warning and proceed.
- If home page generation fails: keep previous version and log warning.
- Non-critical failures (`sitemap.xml`, `robots.txt`, `index.html`) do not block publication; recover on subsequent runs.
- If work page generation fails or push fails: treat as candidate failure, do not advance `state.json`.

**Timeout Policy:**
- Per-agent timeout: 5 minutes (configurable)
- Total workflow timeout: 20 minutes
- On timeout: log error, skip candidate, continue to next

### 6.5.1 Unified Error-State Transition Table

This table is normative and overrides ambiguous interpretations in other documents.

| Candidate result (single attempt) | Advance `state.json.next_index` | Append `skip_log` | Continue same-day retry loop | Final status candidate |
|---|---|---|---|---|
| Ineligible by Screener | Yes (move to `i+1`) | Yes | Yes (if attempt < 3 and list not exhausted) | `SKIP` |
| Fetch failed after retries | Yes (move to `i+1`) | Yes | Yes (if attempt < 3 and list not exhausted) | `SKIP` |
| Translation/Editor/QA failed | Yes (move to `i+1`) | Yes | Yes (if attempt < 3 and list not exhausted) | `SKIP` |
| Work page generation failed (critical) | No | No (treat as candidate failure before publication) | Yes (if attempt < 3 and list not exhausted) | `FAIL` |
| Work page generated but push failed (critical) | No | No (publication not established) | Yes (if attempt < 3 and list not exhausted) | `FAIL` |
| Work page + push succeeded; non-critical files failed (`sitemap.xml`/`robots.txt`/`index.html`) | Yes (publish success path) | No | No (daily run ends on success) | `SUCCESS_WITH_WARNING` |
| Work page + push succeeded; all files succeeded | Yes (publish success path) | No | No (daily run ends on success) | `SUCCESS` |

Daily run-level outcomes:
- If one candidate reaches `SUCCESS` or `SUCCESS_WITH_WARNING`: set run `final_status = "published"`.
- If 3 attempts are consumed with no success: set run `final_status = "no_publication"` and persist advanced `next_index`.
- If `next_index >= works.length` at decision time: set `status = "exhausted"` and run `final_status = "exhausted"`.

### 6.6 Performance Requirements

- **Maximum daily runtime:** 20 minutes per workflow execution
- **API cost budget:**
  - Translation: Codex CLI flat-rate plan (no per-token cost); local LLM fallback is free
  - Estimated monthly cost: $0 for translation (flat-rate); other API costs TBD
- **Timeout settings:**
  - Text fetch: 60 seconds
  - Translation: 300 seconds (5 minutes)
  - HTML generation: 60 seconds

### 6.7 Monitoring & Alerts

- **openClaw notifications:**
  - Immediate notification on workflow failure
  - Notification when all 3 candidates fail in a single day
- **Weekly summary:**
  - Total works published
  - Skip count and reasons
  - API cost summary
- **Critical alerts:**
  - Status reaches `exhausted`: automatically open a GitHub Issue titled "works.json exhausted — manual extension required" and notify maintainer
  - 3 consecutive days with zero publications
  - API budget exceeds 80% of monthly limit

### 6.8 Rollback Strategy

**For incorrect/problematic publications:**
1. Manually revert the commit that added the problematic work
2. Update `DATA/state.json` to set `next_index` to the problematic work index `i` (do not decrement blindly)
3. Add entry to `skip_log` marking the problematic work
4. Re-run workflow to publish alternative candidate
5. Document incident in `DATA/logs/manual-interventions.md`

**For corrupted state:**
1. Restore `DATA/state.json` from git history
2. Verify consistency between state and published works
3. Manually adjust `next_index` if needed

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
- Verify distribution-risk gate for public web delivery (including US-rights uncertainty checks)
Output: `ELIGIBLE` or `INELIGIBLE` + reason

### Agent 2 — Fetcher/Normalizer
Responsibilities:
- Download and extract text (zip/txt/html)
- Produce clean Japanese text for translation
- Record metrics (chars, paragraphs)
Outputs: `raw_text_ja`, `clean_text_ja`, metrics

### Agent 3 — Translator (First Pass)
Responsibilities:
- Translate `clean_text_ja` into English using **Codex CLI (flat-rate plan) via `exec`**; fall back to **local LLM** if Codex CLI is unavailable or returns an error
- Preserve paragraph structure
- Generate the 100–150 word Introduction alongside the translation
- No fabrication; title/author are injected from metadata, not generated
Output: `translation_en`, `introduction_en`

**Agent data passing:** Agents exchange data via structured JSON files written to a temporary working directory for the current run (e.g., `tmp/run-YYYY-MM-DD/`). Exact schema to be defined in detailed design.

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

The Publisher is divided into specialized sub-agents for clarity:

**Agent 6A — Work Page Generator**
- Generate individual work HTML page
- Apply templates with metadata injection
- Ensure proper HTML escaping for XSS prevention
- Output: `/works/YYYY-MM-DD-<slug>/index.html`

**Agent 6B — Index/Archive Generator**
- Update home page with latest work
- Maintain chronological archive list
- Generate author index pages
- Output: `/index.html`, `/authors/<slug>/index.html`

**Agent 6C — Sitemap/SEO Generator**
- Generate `sitemap.xml` with all published works
- Update `robots.txt`
- Ensure proper canonical URLs
- Output: `/sitemap.xml`, `/robots.txt`

---

## 8. Workflow Sequence (Daily)

1. Orchestrator selects candidate (from `works.json` by `state.json` index)
2. Screener checks eligibility
3. Fetcher downloads + normalizes Japanese text (with retry logic)
4. Translator produces first-pass English
5. Editor refines the English
6. QA runs gates; on FAIL -> retry next candidate (up to 3 total attempts per day)
7. Publisher generates site files (Agent 6A → 6B → 6C)
8. Orchestrator updates state and pushes changes

---

## 9. Repository Artifacts (before detailed design)

Required:
- `SPEC.md` (this document)
- `DATA/works.json` (candidate list)
- `DATA/state.json` (progress tracker)
- `PROMPTS/` (agent prompts; to be defined in detailed design)
- `templates/` (HTML templates; to be defined in detailed design)
- openClaw schedule configuration (cron trigger; to be defined in detailed design)
- `DATA/threshold-calibration.md` (quality gate calibration results; populated pre-deployment)

---

## 10. Fixed Decisions (Locked for Detailed Design)

- Content: **English only**
- Rendered pages contain **no Japanese text** (Japanese metadata may remain in `DATA/*.json`)
- Output license: **CC0** for English translations
- Cadence: **1 short story / poem per day**
- Candidate selection: **curated list** (works.json), sequential consumption
- Daily retries: **up to 3 candidates per day**
- End-of-list behavior: **no wrap**; mark state as `exhausted` until list is manually extended (see rollback strategy)
- Work page includes:
  - 100–150 word introduction
  - translation body
  - mandatory credits + auto-translation disclaimer

---

## 11. Testing Strategy

### 11.1 Unit Tests

Each agent must have isolated unit tests:
- **Agent 1 (Screener):** Test with known public-domain and problematic works
- **Agent 2 (Fetcher):** Test with sample zip/txt/html files
- **Agent 3-4 (Translator/Editor):** Test with known Japanese passages
- **Agent 5 (QA):** Test quality gates with edge cases
- **Agent 6A-C (Publisher):** Test HTML generation, escaping, and sitemap structure

### 11.2 Integration Tests

End-to-end workflow tests:
- Full pipeline with 3 sample works (1 short story, 1 poem, 1 ineligible)
- State persistence and skip log accuracy
- Retry logic validation

### 11.3 Pre-Production Checklist

Before first deployment:
- [ ] Validate all quality gates with 15 diverse works (see `DATA/threshold-calibration.md`)
- [ ] Confirm HTML escaping prevents XSS
- [ ] Test exhausted state behavior
- [ ] Verify sitemap.xml validity
- [ ] Test rollback procedure

---

## 12. Security Considerations

### 12.1 Secret Management

- **GitHub Token:** Use repository secrets, never commit tokens
- **API Keys:** Store in GitHub Actions secrets with minimal required permissions
- Rotate tokens quarterly

### 12.2 Input Validation

- **URL validation:** Ensure `aozora_txt_url` host is `aozora.gr.jp` or ends with `.aozora.gr.jp`; allow only `http`/`https` scheme.
- **File size limits:** Reject downloads exceeding 5MB
- **Content sanitization:** Strip all HTML tags from Aozora source before translation

### 12.3 Output Security

- **XSS Prevention:** 
  - HTML-escape all user-provided content (`title_en`, `author_en`)
  - Use templating engine with auto-escaping (e.g., Jinja2 with autoescape)
- **Path traversal:** Validate slug generation cannot create paths outside `/works`
- **Content Security Policy:** Add CSP headers via meta tags in HTML templates

### 12.4 Dependency Security

- Pin all dependencies to specific versions
- Monthly dependency audits using GitHub Dependabot
- Auto-update security patches only

---

## 13. Notes

### 13.1 Google AdSense

全ページの `<head>` 内に以下のスクリプトを必ず挿入する。

```html
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6743751614716161"
     crossorigin="anonymous"></script>
```

- Agent 6A (Work Page Generator)・6B (Index/Archive Generator) のテンプレートに組み込む
- AdSense スクリプトは外部リソースのため、CSP の `script-src` に `https://pagead2.googlesyndication.com` を追加する

### 13.2 フロントエンド設計方針

各ページは CDN を活用したモダンな静的サイトとして構築する。

**採用する CDN リソース（例）:**

| 用途 | CDN |
|------|-----|
| CSS フレームワーク | Bootstrap 5（`cdn.jsdelivr.net`）または Tailwind CSS Play CDN |
| フォント | Google Fonts（Noto Serif / Inter 等） |
| アイコン | Font Awesome または Heroicons |

**デザイン要件:**

- レスポンシブデザイン（モバイルファースト）
- セマンティック HTML5（`<article>`, `<header>`, `<nav>`, `<footer>` 等）
- ダークモード対応（`prefers-color-scheme` メディアクエリ）
- 適切な `<meta>` OGP タグ（SNS シェア対応）
- ページ読み込み速度優先：CSS は `<head>` に、JS は `<body>` 末尾または `async`/`defer` で読み込む

**CSP 追加ルール（外部リソース対応）:**

```html
<meta http-equiv="Content-Security-Policy"
  content="default-src 'self';
           script-src 'self' https://pagead2.googlesyndication.com https://cdn.jsdelivr.net 'unsafe-inline';
           style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline';
           font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net;
           img-src 'self' https:;
           frame-src https://googleads.g.doubleclick.net;">
```

### 13.3 サイト言語：英語のみ

**このサイトに表示するすべてのテキストは英語とする。日本語はいかなる形でも表示しない。**

対象範囲:

| 要素 | 内容 |
|------|------|
| 作品本文 | 英語翻訳のみ（`translation_en`） |
| イントロダクション | 英語のみ（`introduction_en`、100–150 words） |
| ページタイトル・`<title>` | 英語（`title_en`、`author_en`） |
| ナビゲーション・フッター | 英語 |
| クレジット・免責事項 | 英語 |
| アーカイブ・著者ページの見出し | 英語 |
| `sitemap.xml`・`robots.txt` | 言語非依存（URL のみ） |
| `DATA/*.json` のメタデータ | `title_ja`・`author_ja` はソースファイルのみに存在し、HTML には一切出力しない |

Section 10（Fixed Decisions）の "Content: English only" と同じ決定を、実装レベルで再確認する。テンプレートエンジンが日本語フィールドを誤って出力しないよう、Agent 6A〜6C は `title_ja`・`author_ja` を参照禁止とする。

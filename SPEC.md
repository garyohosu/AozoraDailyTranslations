# SPEC.md — Aozora Daily Translations

Repository: https://github.com/garyohosu/AozoraDailyTranslations.git  
Site name: **Aozora Daily Translations**  
Publishing: **GitHub Pages**  
Content: **English only in rendered pages** (Japanese metadata may exist in source JSON only)  
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
  - `title_en`, `author_en` (required for page display; English or romanized)
  - `title_ja`, `author_ja` (optional metadata; not rendered on pages)
  - `genre` (`poem` or `short`)
  - optional metadata (Aozora IDs, notes)

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

- Home page (latest + archive)
  - `/index.html` (or generated from template)

- Optional author pages (recommended for SEO)
  - `/authors/<author-slug>/index.html`
  - `<author-slug>` follows same rules as work slug

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
- Distribution is legally safe for public web delivery on GitHub Pages (at minimum, no unresolved rights risk in the United States); if not confidently verifiable, do not publish

### 4.2 Exclusion Rules (must be excluded / skipped)

Skip a candidate if **any** is true:

- The work is a **Japanese translation of a foreign work** (translation-right risk)
- The content is dominated by annotations/commentary rather than the main text
- The copyright status cannot be determined reliably from the card
- Legal status for GitHub Pages distribution outside Japan (especially US access) is unclear

**Safety bias:** if uncertain, skip.

### 4.3 Mandatory Credits (on every work page)

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
- Residual Aozora ruby/annotation artifacts exceed threshold:
  - Count occurrences of `《`, `》`, `｜`, `［＃...］` patterns in final English body
  - Fail if total count > 3
- Forbidden boilerplate appears:
  - “translation failed”, “as an AI”, “I can’t”, etc.

### 5.2 Required “Content Gates”

- Generate a short **Introduction** (100–150 words) per work for SEO and context
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

- GitHub Actions generates files and **commits/pushes** to the repository
- GitHub Pages serves the latest published static content
- Prefer append-only updates for archives (avoid rewriting older pages unnecessarily)

### 6.4 Logging Policy

- Persist machine-readable run logs at `DATA/logs/YYYY-MM-DD.json`
- Each log includes: run date/time (JST), attempted indices (max 3), per-candidate result/reason, selected output path (if success), and final status
- Keep logs in git history (no deletion by automation)

### 6.5 Error Handling

**Network Errors:**
- Retry Aozora Bunko text fetches up to 3 times with exponential backoff (1s, 2s, 4s)
- If all retries fail, log error and skip to next candidate

**GitHub API Errors:**
- Rate limit exceeded: fail gracefully and log; do not retry that day
- Push conflicts: attempt to pull and rebase once; if unresolved, fail and alert

**Partial Failures:**
- If sitemap/robots.txt generation fails but work page succeeds: log warning and proceed
- If home page generation fails: keep previous version and log error
- Critical failures (work page generation): abort and do not update state

**Timeout Policy:**
- Per-agent timeout: 5 minutes (configurable)
- Total workflow timeout: 20 minutes
- On timeout: log error, skip candidate, continue to next

### 6.6 Performance Requirements

- **Maximum daily runtime:** 20 minutes per workflow execution
- **API cost budget:** 
  - Translation API: $0.50 per work (estimated)
  - Total monthly budget: $15 (30 days × $0.50)
- **Timeout settings:**
  - Text fetch: 60 seconds
  - Translation: 300 seconds (5 minutes)
  - HTML generation: 60 seconds

### 6.7 Monitoring & Alerts

- **GitHub Actions notifications:**
  - Immediate notification on workflow failure
  - Notification when all 3 candidates fail in a single day
- **Weekly summary:**
  - Total works published
  - Skip count and reasons
  - API cost summary
- **Critical alerts:**
  - Status reaches `exhausted` (notify maintainer to extend `works.json`)
  - 3 consecutive days with zero publications
  - API budget exceeds 80% of monthly limit

### 6.8 Rollback Strategy

**For incorrect/problematic publications:**
1. Manually revert the commit that added the problematic work
2. Update `DATA/state.json` to decrement `next_index` by 1
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
- `.github/workflows/daily.yml` (cron workflow; to be defined in detailed design)

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
- [ ] Validate all quality gates with 10 diverse works
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

- **URL validation:** Ensure `aozora_txt_url` points only to `aozora.gr.jp` domain
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

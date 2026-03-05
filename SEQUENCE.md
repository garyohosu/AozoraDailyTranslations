# SEQUENCE.md — Aozora Daily Translations

ユースケース（USECASE.md）を元にしたシーケンス図集。
各シナリオを網羅し、正常系・異常系・運用系に分類する。

---

## シナリオ一覧

| # | シナリオ | 分類 |
|---|----------|------|
| 1 | 日次ワークフロー 正常系（初回候補で公開成功） | 正常系 |
| 2 | スキップ1回 → 次候補で公開成功 | 準正常系 |
| 3 | QA失敗 → リトライで公開成功 | 準正常系 |
| 4 | 3候補すべて失敗（当日公開なし） | 異常系 |
| 5 | works.json 枯渇（exhausted） | 異常系 |
| 6 | Aozora Bunko 取得エラー（リトライ・指数バックオフ） | 異常系 |
| 7 | GitHub push エラー（コンフリクト） | 異常系 |
| 8 | 翻訳タイムアウト | 異常系 |
| 9 | Maintainer によるロールバック | 運用系 |
| 10 | Reader による作品閲覧 | 正常系 |

---

## 1. 日次ワークフロー 正常系

初回候補がスクリーニング・翻訳・QA をすべて通過し、公開まで完了するシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant OC as openClaw
    participant Orch as Agent 0<br/>Orchestrator
    participant Screen as Agent 1<br/>Screener
    participant Fetch as Agent 2<br/>Fetcher
    participant Trans as Agent 3<br/>Translator
    participant Edit as Agent 4<br/>Editor
    participant QA as Agent 5<br/>QA/Auditor
    participant Pub6A as Agent 6A<br/>Work Page
    participant Pub6B as Agent 6B<br/>Index/Archive
    participant Pub6C as Agent 6C<br/>Sitemap/SEO
    participant AZ as Aozora Bunko
    participant LLM as Codex CLI /<br/>Local LLM
    participant GH as GitHub

    OC->>Orch: trigger(date=YYYY-MM-DD)
    Orch->>Orch: load works.json, state.json<br/>→ next_index = i

    Orch->>Screen: screen(candidate[i])
    Screen->>AZ: GET aozora_card_url
    AZ-->>Screen: 200 OK, card HTML
    Screen->>Screen: 著作権切れ確認<br/>翻訳作品・注釈過多チェック<br/>US配信リスク評価
    Screen-->>Orch: ELIGIBLE

    Orch->>Fetch: fetch(aozora_txt_url)
    Fetch->>AZ: GET aozora_txt_url (zip/txt/html)
    AZ-->>Fetch: 200 OK, source data
    Fetch->>Fetch: ルビ《》｜除去<br/>注釈［＃…］除去<br/>段落分割・文字数計測
    Fetch-->>Orch: {clean_text_ja, P_ja, C_ja}

    Orch->>Trans: translate(clean_text_ja, metadata)
    Trans->>LLM: exec codex translate<br/>+ generate introduction
    LLM-->>Trans: translation_en, introduction_en
    Trans-->>Orch: {translation_en, introduction_en}

    Orch->>Edit: edit(translation_en, genre)
    Edit->>LLM: exec codex refine
    LLM-->>Edit: edited_translation_en
    Edit-->>Orch: edited_translation_en

    Orch->>QA: audit(edited_translation_en, metrics)
    QA->>QA: 段落数差チェック |P_en - P_ja| <= max(2, ceil(0.15*P_ja))<br/>長さ比 R = W_en / C_ja（short: 0.28–0.95）<br/>アーティファクト残存数 <= 3<br/>禁止定型文チェック
    QA-->>Orch: PASS {P_en, W_en, R}

    Orch->>Pub6A: generate_work_page(metadata, translation, intro)
    Pub6A->>Pub6A: slug生成・HTML構築<br/>クレジット・CC0・免責事項注入<br/>XSSエスケープ・CSP meta設定
    Pub6A-->>Orch: /works/YYYY-MM-DD-<slug>/index.html

    Orch->>Pub6B: update_index(work_metadata)
    Pub6B->>Pub6B: /index.html 最新作品追加<br/>アーカイブ一覧更新<br/>/authors/<slug>/index.html 更新
    Pub6B-->>Orch: updated /index.html, /authors/*/index.html

    Orch->>Pub6C: update_seo()
    Pub6C->>Pub6C: sitemap.xml に新URL追加<br/>robots.txt 確認・更新
    Pub6C-->>Orch: updated /sitemap.xml, /robots.txt

    Orch->>Orch: state.json: next_index = i+1, status=active<br/>DATA/logs/YYYY-MM-DD.json 保存（final_status=published）<br/>tmp/run-YYYY-MM-DD/ 削除
    Orch->>GH: git commit + push<br/>(work page + index + sitemap + state.json + DATA/logs)
    GH-->>Orch: push 完了
    Orch-->>OC: 完了通知（公開成功）
```

---

## 2. スキップ1回 → 次候補で公開成功

候補 i が不適格（翻訳作品検出）でスキップされ、候補 i+1 が正常公開されるシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant OC as openClaw
    participant Orch as Agent 0<br/>Orchestrator
    participant Screen as Agent 1<br/>Screener
    participant Fetch as Agent 2<br/>Fetcher
    participant Trans as Agent 3<br/>Translator
    participant Edit as Agent 4<br/>Editor
    participant QA as Agent 5<br/>QA/Auditor
    participant Pub as Agent 6A-C<br/>Publisher
    participant AZ as Aozora Bunko
    participant LLM as Codex CLI /<br/>Local LLM
    participant GH as GitHub

    OC->>Orch: trigger(date=YYYY-MM-DD)
    Orch->>Orch: next_index = i, attempt = 0

    Note over Orch,Screen: ── 候補 i：スキップ ──
    Orch->>Screen: screen(candidate[i])
    Screen->>AZ: GET card[i]
    AZ-->>Screen: card HTML
    Screen->>Screen: 外国語作品の日本語訳を検出
    Screen-->>Orch: INELIGIBLE<br/>reason="Translation of foreign work detected"
    Orch->>Orch: skip_log 追記 {date, index=i, reason}<br/>attempt=1, i=i+1

    Note over Orch,GH: ── 候補 i+1：公開成功 ──
    Orch->>Screen: screen(candidate[i+1])
    Screen->>AZ: GET card[i+1]
    AZ-->>Screen: card HTML
    Screen-->>Orch: ELIGIBLE

    Orch->>Fetch: fetch(candidate[i+1])
    Fetch->>AZ: GET txt[i+1]
    AZ-->>Fetch: source data
    Fetch-->>Orch: {clean_text_ja, metrics}

    Orch->>Trans: translate(clean_text_ja)
    Trans->>LLM: exec codex
    LLM-->>Trans: translation_en, introduction_en
    Trans-->>Orch: {translation_en, introduction_en}

    Orch->>Edit: edit(translation_en)
    Edit->>LLM: exec codex refine
    LLM-->>Edit: edited_translation_en
    Edit-->>Orch: edited_translation_en

    Orch->>QA: audit(edited_translation_en, metrics)
    QA-->>Orch: PASS

    Orch->>Pub: publish(work)
    Pub-->>Orch: generated files

    Orch->>Orch: state.json: next_index = i+2<br/>（スキップ分も加算済み）
    Orch->>Orch: DATA/logs/YYYY-MM-DD.json 保存<br/>final_status="published"
    Orch->>GH: commit + push（state.json + DATA/logs + generated files）
    GH-->>Orch: push 完了
    Orch-->>OC: 完了通知（公開成功）
```

---

## 3. QA失敗 → リトライで公開成功

候補 i の翻訳が品質ゲートで FAIL し、候補 i+1 で PASS して公開されるシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant OC as openClaw
    participant Orch as Agent 0<br/>Orchestrator
    participant Screen as Agent 1<br/>Screener
    participant Fetch as Agent 2<br/>Fetcher
    participant Trans as Agent 3<br/>Translator
    participant Edit as Agent 4<br/>Editor
    participant QA as Agent 5<br/>QA/Auditor
    participant Pub as Agent 6A-C<br/>Publisher
    participant AZ as Aozora Bunko
    participant LLM as Codex CLI /<br/>Local LLM
    participant GH as GitHub

    OC->>Orch: trigger(date=YYYY-MM-DD)
    Orch->>Orch: next_index = i, attempt = 0

    Note over Orch,QA: ── 候補 i：QA FAIL ──
    Orch->>Screen: screen(candidate[i])
    Screen-->>Orch: ELIGIBLE
    Orch->>Fetch: fetch(candidate[i])
    Fetch-->>Orch: {clean_text_ja, P_ja=40, C_ja=3200}

    Orch->>Trans: translate
    Trans->>LLM: exec codex
    LLM-->>Trans: translation_en (W_en=78, P_en=22)
    Trans-->>Orch: translation_en

    Orch->>Edit: edit
    Edit->>LLM: exec codex refine
    LLM-->>Edit: edited_translation_en
    Edit-->>Orch: edited_translation_en

    Orch->>QA: audit
    QA->>QA: 段落数差チェック: |22-40|=18 > max(2,6)=6 → FAIL
    QA-->>Orch: FAIL reason="Paragraph count mismatch: P_en=22, P_ja=40"
    Orch->>Orch: skip_log 追記 {reason="QA FAIL: paragraph mismatch"}<br/>attempt=1, i=i+1

    Note over Orch,GH: ── 候補 i+1：公開成功 ──
    Orch->>Screen: screen(candidate[i+1])
    Screen-->>Orch: ELIGIBLE
    Orch->>Fetch: fetch(candidate[i+1])
    Fetch-->>Orch: {clean_text_ja, P_ja=12, C_ja=1800}

    Orch->>Trans: translate
    Trans->>LLM: exec codex
    LLM-->>Trans: translation_en (W_en=680, P_en=12)
    Trans-->>Orch: translation_en

    Orch->>Edit: edit
    Edit->>LLM: exec codex refine
    LLM-->>Edit: edited_translation_en
    Edit-->>Orch: edited_translation_en

    Orch->>QA: audit
    QA->>QA: |12-12|=0 ✓<br/>R=680/1800=0.378 (short: 0.28–0.95) ✓<br/>アーティファクト=0 ✓<br/>定型文なし ✓
    QA-->>Orch: PASS

    Orch->>Pub: publish(work)
    Pub-->>Orch: generated files
    Orch->>Orch: state.json: next_index = i+2<br/>（QA FAIL 分も加算済み）
    Orch->>Orch: DATA/logs/YYYY-MM-DD.json 保存<br/>final_status="published"
    Orch->>GH: commit + push（state.json + DATA/logs + generated files）
    GH-->>Orch: push 完了
    Orch-->>OC: 完了通知
```

---

## 4. 3候補すべて失敗（当日公開なし）

3候補すべてが INELIGIBLE または QA FAIL となり、当日は公開されないシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant OC as openClaw
    participant Orch as Agent 0<br/>Orchestrator
    participant Screen as Agent 1<br/>Screener
    participant QA as Agent 5<br/>QA/Auditor
    participant AZ as Aozora Bunko
    participant LLM as Codex CLI /<br/>Local LLM
    participant GH as GitHub

    OC->>Orch: trigger(date=YYYY-MM-DD)
    Orch->>Orch: next_index = i, attempt = 0

    Note over Orch,Screen: ── 候補 i：INELIGIBLE ──
    Orch->>Screen: screen(candidate[i])
    Screen->>AZ: GET card[i]
    AZ-->>Screen: card HTML
    Screen-->>Orch: INELIGIBLE reason="Copyright status unclear"
    Orch->>Orch: skip_log 追記, attempt=1, i++

    Note over Orch,Screen: ── 候補 i+1：INELIGIBLE ──
    Orch->>Screen: screen(candidate[i+1])
    Screen->>AZ: GET card[i+1]
    AZ-->>Screen: card HTML
    Screen-->>Orch: INELIGIBLE reason="Annotation-heavy content"
    Orch->>Orch: skip_log 追記, attempt=2, i++

    Note over Orch,QA: ── 候補 i+2：QA FAIL ──
    Orch->>Screen: screen(candidate[i+2])
    Screen-->>Orch: ELIGIBLE
    Orch->>Orch: fetch → translate → edit（省略）
    Orch->>QA: audit
    QA-->>Orch: FAIL reason="Boilerplate detected: 'as an AI'"
    Orch->>Orch: skip_log 追記, attempt=3

    Note over Orch,GH: ── 3回失敗：公開なし ──
    Orch->>Orch: state.json: next_index = i+3<br/>（失敗分もインクリメント）
    Orch->>Orch: DATA/logs/YYYY-MM-DD.json 保存<br/>final_status="no_publication"
    Orch->>GH: commit + push（state.json + DATA/logs）
    GH-->>Orch: push 完了
    Orch-->>OC: 失敗通知（3候補すべて失敗）
    OC-->>OC: アラート送信
```

---

## 5. works.json 枯渇（exhausted）

`next_index` が `works.length` に達した際、未対応 Issue が無い場合のみ GitHub Issue を1回作成するシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant OC as openClaw
    participant Orch as Agent 0<br/>Orchestrator
    participant GH as GitHub
    participant Maint as Maintainer

    OC->>Orch: trigger(date=YYYY-MM-DD)
    Orch->>Orch: load state.json<br/>next_index = N, works.length = N<br/>→ next_index >= works.length

    Orch->>GH: gh issue list --state open<br/>--search "works.json exhausted — manual extension required"
    GH-->>Orch: open issue の有無

    alt 未対応Issueなし（初回遷移）
        Orch->>GH: gh issue create<br/>title="works.json exhausted — manual extension required"<br/>body="next_index=N, works.length=N\n最終公開日: YYYY-MM-DD\n対応: works.jsonに作品を追加しnext_indexをリセット"
        GH-->>Orch: Issue URL
    else 未対応Issueあり（継続実行）
        Orch->>Orch: Issue 作成をスキップ（1回のみ）
    end

    Orch->>Orch: state.json: status = "exhausted"
    Orch->>Orch: DATA/logs/YYYY-MM-DD.json 保存<br/>final_status="exhausted"
    Orch->>GH: commit + push（state.json + DATA/logs）
    GH-->>Orch: push 完了
    Orch-->>OC: 緊急アラート（exhausted）

    Note over Maint,GH: ── Maintainer 対応 ──
    GH-->>Maint: Issue 通知
    Maint->>GH: works.json に新規作品を追加
    Maint->>GH: state.json: next_index リセット / status = "active"
    Maint->>GH: Issue をクローズ
    GH-->>OC: 次回 trigger で通常フローに復帰
```

---

## 6. Aozora Bunko 取得エラー（リトライ・指数バックオフ）

テキスト取得が断続的に失敗し、指数バックオフで3回リトライするシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant Orch as Agent 0<br/>Orchestrator
    participant Fetch as Agent 2<br/>Fetcher
    participant AZ as Aozora Bunko

    Orch->>Fetch: fetch(aozora_txt_url)

    Note over Fetch,AZ: ── 1回目：失敗 ──
    Fetch->>AZ: GET aozora_txt_url
    AZ-->>Fetch: 503 Service Unavailable
    Fetch->>Fetch: wait 1s（バックオフ 1）

    Note over Fetch,AZ: ── 2回目：失敗 ──
    Fetch->>AZ: GET aozora_txt_url (retry 1)
    AZ-->>Fetch: timeout (60s超)
    Fetch->>Fetch: wait 2s（バックオフ 2）

    Note over Fetch,AZ: ── 3回目：失敗 ──
    Fetch->>AZ: GET aozora_txt_url (retry 2)
    AZ-->>Fetch: 500 Internal Server Error
    Fetch->>Fetch: wait 4s（バックオフ 3）

    Note over Fetch,AZ: ── 4回目（最終）：失敗 ──
    Fetch->>AZ: GET aozora_txt_url (retry 3)
    AZ-->>Fetch: connection refused

    Fetch-->>Orch: ERROR "fetch failed after 3 retries: connection refused"

    Orch->>Orch: skip_log 追記<br/>reason="Fetch error after 3 retries"<br/>attempt++, i++
    Note over Orch: 次候補へ（シナリオ2/3へ続く）

    Note over Fetch,AZ: ── 別ケース：3回目成功 ──
    rect rgb(230, 255, 230)
        Fetch->>AZ: GET aozora_txt_url (retry 2)
        AZ-->>Fetch: 200 OK, source data
        Fetch->>Fetch: テキスト正規化
        Fetch-->>Orch: {clean_text_ja, metrics}
        Note over Orch: 通常フロー継続（シナリオ1へ）
    end
```

---

## 7. GitHub push エラー（コンフリクト）

push 時にコンフリクトが発生し、pull-rebase を1回試み、`state.json` を決定的ルールで解消するシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant Orch as Agent 0<br/>Orchestrator
    participant GH as GitHub

    Note over Orch,GH: ── 公開ファイル生成済み、push 試行 ──
    Orch->>GH: git push origin main
    GH-->>Orch: 409 Conflict<br/>"Updates were rejected because the remote contains work"

    Note over Orch,GH: ── pull + rebase で解消試行 ──
    Orch->>GH: git fetch origin main
    GH-->>Orch: remote changes
    Orch->>Orch: git rebase origin/main

    alt state.json 競合あり
        Orch->>Orch: 競合解決ルールを適用<br/>next_index=max(local, remote)<br/>skip_log=(date_jst,index,reason) で重複排除して和集合<br/>status=どちらかが exhausted なら exhausted
    else 競合なし
        Orch->>Orch: rebase 継続
    end

    alt rebase 成功
        Orch->>Orch: DATA/logs/YYYY-MM-DD.json に警告追記<br/>"push_conflict_resolved"
        Orch->>GH: git push origin main（2回目）
        GH-->>Orch: push 完了
        Note over Orch: 公開成功
    else rebase 失敗（手動解消が必要）
        Orch->>Orch: rebase abort
        Orch->>Orch: ログ保存<br/>final_status="push_conflict_unresolved"
        Orch->>GH: gh issue create<br/>title="Push conflict: manual intervention required"
        Note over Orch: 当日公開なし、Maintainerへ通知
    end
```

---

## 8. 翻訳タイムアウト

Codex CLI 呼び出しが 300秒 (5分) を超過し、ローカルLLM フォールバックを試みるシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant Orch as Agent 0<br/>Orchestrator
    participant Trans as Agent 3<br/>Translator
    participant Codex as Codex CLI
    participant LocalLLM as Local LLM

    Orch->>Trans: translate(clean_text_ja)

    Note over Trans,Codex: ── Codex CLI タイムアウト ──
    Trans->>Codex: exec codex translate (timeout=300s)
    Note over Codex: ...300秒経過...
    Codex-->>Trans: TIMEOUT

    Note over Trans,LocalLLM: ── Local LLM フォールバック ──
    Trans->>LocalLLM: translate(clean_text_ja) [fallback]
    LocalLLM-->>Trans: translation_en, introduction_en

    Trans-->>Orch: {translation_en, introduction_en}<br/>※ source="local_llm" をメタデータに記録

    Orch->>Orch: ログに警告記録<br/>"codex_timeout: fell back to local_llm"
    Note over Orch: 翻訳フロー継続（シナリオ1の Edit 以降へ）

    alt Local LLM も失敗
        LocalLLM-->>Trans: ERROR
        Trans-->>Orch: ERROR "all translation engines failed"
        Orch->>Orch: skip_log 追記<br/>reason="Translation timeout/error"<br/>attempt++, i++
        Note over Orch: 次候補へ
    end
```

---

## 9. Maintainer によるロールバック

公開済み作品に問題が発覚し、手動でロールバックを実施するシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant Maint as Maintainer
    participant GH as GitHub
    participant OC as openClaw

    Note over Maint: 問題の作品を発見<br/>（誤訳・著作権リスク等）

    Maint->>GH: git log --oneline で対象コミット特定
    GH-->>Maint: commit hash (abc1234)

    Maint->>GH: git revert abc1234<br/>（作品ページ・index.html・sitemap.xml を除去）
    GH-->>Maint: revert commit 作成

    Maint->>GH: state.json を編集<br/>next_index-- （問題作品の index に戻す）<br/>skip_log に追記 {reason="manual rollback: [理由]"}
    Maint->>GH: git commit + push

    Maint->>GH: DATA/logs/manual-interventions.md に記録<br/>- 日時・対象作品・理由・対応手順

    GH-->>OC: push 検知（GitHub Pages 再デプロイ）

    Note over Maint,OC: ── 翌日 または 即時再実行 ──
    OC->>OC: 次回 trigger で通常フロー<br/>（問題作品はスキップ済み、次候補を処理）

    Note over Maint: 問題作品はスキップされ<br/>代替作品が自動公開される
```

---

## 10. Reader による作品閲覧

読者が GitHub Pages を通じて翻訳作品を閲覧するシナリオ。

```mermaid
sequenceDiagram
    autonumber
    participant R as Reader
    participant GHP as GitHub Pages
    participant SEO as 検索エンジン

    Note over SEO,GHP: ── 検索経由 ──
    SEO->>GHP: GET /sitemap.xml
    GHP-->>SEO: sitemap.xml（全作品URL一覧）
    SEO->>GHP: クローリング /works/YYYY-MM-DD-<slug>/
    GHP-->>SEO: 作品ページ HTML（canonical URL付き）

    Note over R,GHP: ── 直接閲覧 ──
    R->>GHP: GET /index.html
    GHP-->>R: ホームページ（最新作品 + アーカイブ一覧）

    R->>GHP: GET /works/YYYY-MM-DD-<slug>/index.html
    GHP-->>R: 作品ページ<br/>- Introduction（100–150 words）<br/>- 英語翻訳本文<br/>- Aozora Bunko クレジット<br/>- CC0 ライセンス表示<br/>- 自動翻訳免責事項

    alt 著者ページへ遷移
        R->>GHP: GET /authors/<author-slug>/index.html
        GHP-->>R: 著者ページ（同著者の作品一覧）
        R->>GHP: GET /works/YYYY-MM-DD-<slug2>/index.html
        GHP-->>R: 別作品ページ
    end
```

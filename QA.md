# QA.md — 実装上の不明点・疑問点

SPEC.md / USECASE.md / SEQUENCE.md / CLASS.md を精査して洗い出した、詳細設計前に決定が必要な疑問点を記録する。

ステータス凡例: `OPEN` / `RESOLVED` / `WONTFIX`

---

## カテゴリ一覧

1. [エージェント間通信](#1-エージェント間通信)
2. [外部ツール・サービス](#2-外部ツールサービス)
3. [文字コード・ファイル形式](#3-文字コードファイル形式)
4. [品質ゲート](#4-品質ゲート)
5. [エラーハンドリング・エッジケース](#5-エラーハンドリングエッジケース)
6. [セキュリティ](#6-セキュリティ)
7. [スラッグ・著者ページ](#7-スラッグ著者ページ)
8. [モニタリング・コスト](#8-モニタリングコスト)
9. [パフォーマンス・タイムアウト](#9-パフォーマンスタイムアウト)
10. [並行性・git操作](#10-並行性git操作)

---

## 1. エージェント間通信

### Q1-1 `tmp/` ファイルスキーマが未定義 `RESOLVED`

SPEC.md §7 に「Exact schema to be defined in detailed design」と明記されている。

**回答: 以下のスキーマで設計する。**

#### ディレクトリ構造

```
tmp/run-YYYY-MM-DD/
├── 00_context.json          # 実行コンテキスト（Orchestrator が起動時に生成）
├── 01_screen_result.json    # Agent 1 出力
├── 02_fetch_result.json     # Agent 2 出力（メトリクス）
├── 02_clean_text_ja.txt     # Agent 2 出力（本文テキスト、UTF-8）
├── 03_translation.json      # Agent 3 出力
├── 04_edited_translation.json # Agent 4 出力
├── 05_qa_result.json        # Agent 5 出力
└── 06_publish_result.json   # Agent 6 出力
```

ファイル名先頭の番号はエージェント番号と一致させ、処理順序を明示する。

#### `00_context.json`
```json
{
  "run_date": "2026-03-05",
  "run_datetime_jst": "2026-03-05T09:01:23+09:00",
  "candidate_index": 3,
  "attempt": 0,
  "work": {
    "aozora_card_url": "https://www.aozora.gr.jp/cards/.../card128.html",
    "aozora_txt_url":  "https://www.aozora.gr.jp/cards/.../files/128_15261.html",
    "title_en": "Rashomon",
    "author_en": "Akutagawa Ryunosuke",
    "title_ja": "羅生門",
    "author_ja": "芥川龍之介",
    "genre": "short",
    "notes": ""
  }
}
```

#### `01_screen_result.json`
```json
{
  "status": "ELIGIBLE",
  "reason": ""
}
```
`status`: `"ELIGIBLE"` | `"INELIGIBLE"`

#### `02_fetch_result.json`
```json
{
  "source_url": "https://www.aozora.gr.jp/cards/.../files/128_15261.html",
  "source_format": "html",
  "encoding_detected": "shift_jis_2004",
  "encoding_used": "shift_jis_2004",
  "P_ja": 6,
  "C_ja": 5635,
  "clean_text_path": "tmp/run-2026-03-05/02_clean_text_ja.txt"
}
```
`source_format`: `"html"` | `"zip"` | `"txt"`
`02_clean_text_ja.txt` は UTF-8 エンコードで書き出す。

#### `03_translation.json`
```json
{
  "source_engine": "codex_cli",
  "translation_en": "...(本文翻訳全文)...",
  "introduction_en": "...(100-150 words)...",
  "introduction_word_count": 132
}
```
`source_engine`: `"codex_cli"` | `"local_llm"`

#### `04_edited_translation.json`
```json
{
  "source_engine": "codex_cli",
  "edited_translation_en": "...(編集済み翻訳全文)..."
}
```

#### `05_qa_result.json`
```json
{
  "status": "PASS",
  "reason": "",
  "P_en": 6,
  "W_en": 1820,
  "R": 0.323,
  "artifact_count": 0,
  "gates": {
    "paragraph_count": "PASS",
    "length_ratio": "PASS",
    "artifacts": "PASS",
    "boilerplate": "PASS",
    "introduction_word_count": "PASS"
  }
}
```
`status`: `"PASS"` | `"FAIL"`

#### `06_publish_result.json`
```json
{
  "slug": "rashomon",
  "work_page_path": "works/2026-03-05-rashomon/index.html",
  "index_paths": ["index.html", "authors/akutagawa-ryunosuke/index.html"],
  "seo_paths": ["sitemap.xml", "robots.txt"],
  "all_generated_files": [
    "works/2026-03-05-rashomon/index.html",
    "index.html",
    "authors/akutagawa-ryunosuke/index.html",
    "sitemap.xml",
    "robots.txt"
  ]
}
```

#### `tmp/` の管理方針
- `.gitignore` に `tmp/` を追加（コミット対象外）
- **成功時**: Orchestrator がコミット後に `tmp/run-YYYY-MM-DD/` を削除
- **失敗時**: 削除せずに保持（デバッグ用）。翌日の実行時に前日以前の `tmp/run-*/` を自動クリーンアップ（7日以上経過したものを削除）
- **命名衝突**: 同日に手動再実行した場合は `tmp/run-YYYY-MM-DD_2/` のようにサフィックスを付与

---

### Q1-2 エージェントは同一プロセスか別プロセスか `OPEN`

- Orchestrator が各エージェントを「関数呼び出し」で使うのか、それとも各エージェントが独立したサブプロセス（Codex CLIのように）として起動されるのか。
- Codex CLI が `exec` 経由であることを考えると、Translator だけ別プロセス・それ以外は同一プロセス、という混在もありうる。
- 実行モデルを明確にしないと、タイムアウト制御・エラーハンドリングの実装方針が定まらない。

### Q1-3 `tmp/` の失敗時クリーンアップ `RESOLVED`

Q1-1 の回答に統合。失敗時は保持、翌日実行時に7日以上古い `tmp/run-*/` を自動削除する。

---

## 2. 外部ツール・サービス

### Q2-1 openClaw の実態が不明 `RESOLVED`

**回答: openClaw はローカルPCにインストール済みの専用スケジューラーソフトウェアである。**

- cron 相当の定時実行（JST 09:00）を openClaw が担う
- Secrets 管理・並行制御・通知は openClaw の機能を利用する
- GitHub Actions は使用しない

### Q2-2 Codex CLI の呼び出し形式 `OPEN`

- `exec` で呼び出すとあるが、具体的なコマンド形式が不明。
  - テキストはファイル経由（`--file`）か stdin か？
  - 出力は stdout か出力ファイルか？
  - モデルや温度などのパラメータはどこで指定するか？
- `PROMPTS/` の内容は「to be defined in detailed design」（SPEC.md §9）。プロンプトの渡し方（system prompt ファイル、インライン引数など）も未定。

### Q2-3 Local LLM の具体的実装 `OPEN`

- フォールバック先の「Local LLM」が何を指すか未定（Ollama? llama.cpp? その他?）。
- エンドポイント URL・モデル名・API 形式（OpenAI互換か独自か）の設定方法が未定義。
- 翻訳品質がメインの Codex CLI と同等かどうか不明。フォールバック時に QA ゲートを通過できる保証があるか？

### Q2-4 GitHub 操作に `gh` CLI が必要か `OPEN`

- SEQUENCE.md シナリオ5 に `gh issue list` / `gh issue create` コマンドが登場する。
- GitHub REST API を直接呼ぶか、`gh` CLI を使うかで依存関係・認証方式・エラーハンドリングが異なる。
- ランタイム環境（openClaw の実行環境）に `gh` が常にインストールされているという前提でよいか？

---

## 3. 文字コード・ファイル形式

### Q3-1 青空文庫の文字コード（Shift-JIS）処理 `RESOLVED`

**回答: `tools/test_aozora_encoding.py` による実験で以下を確認した（2026-03-05）。**

| 作品 | 形式 | chardet 検出 | confidence | デコード成功 |
|------|------|-------------|-----------|------------|
| 羅生門（XHTML形式）| html | shift_jis_2004 | 1.0 | ✓ |
| 桜の樹の下には（HTML形式）| html | cp932 | 1.0 | ✓ |
| 羅生門（ZIP/TXT形式）| zip | shift_jis_2004 | 1.0 | ✓ |

**決定したデコード仕様:**

1. chardet でエンコーディングを検出（confidence は参考値）
2. フォールバック順: `shift_jis_2004` → `cp932` → `utf-8` → `euc-jp`
3. 全て失敗した場合は Fetch エラーとして skip_log に記録

**HTML 本文抽出:**
- セレクタ: `<div class="main_text">`（両形式で存在を確認）
- `<ruby>` タグは `<rb>` 要素または `get_text()` 先頭部分のみを残す（ルビ読みを削除）
- XHTML 形式では `<ruby>` 子要素が独立した行に展開されるため、空行正規化とルビ断片フィルタリングが必要

**ZIP/TXT 処理:**
- ZIP エントリ名のデコード: `cp437` → `cp932` を試みる（失敗時はそのまま使用）
- TXT ファイル内のヘッダー（`-------` 区切り以前の説明文）を除去してから本文処理
- 段落区切り: `\r\n\r\n` を `\n\n` に正規化してから分割

### Q3-2 zip / txt / html の自動判別ロジック `RESOLVED`

**回答: 別リポジトリで実装済みのコマンドラインオプション（非対話形式）を流用する。**

- URL の拡張子（`.zip`, `.txt`, `.html`）で形式を判別
- Content-Type ヘッダーは参考値として記録するが、判定には使用しない
- 実装詳細は既存実装に準拠

### Q3-3 ルビ・注釈の除去範囲 `RESOLVED`

**回答: 翻訳精度向上のため、できるだけ短い文に分解して翻訳する方針とする。**

**決定した仕様:**

| 記法 | 処理 |
|------|------|
| `｜漢字《かんじ》` | `漢字` のみ残す（ルビを捨てる） |
| `漢字《かんじ》` | `漢字` のみ残す |
| `［＃「…」に傍点］` 等 | 完全に削除 |

**段落・文の分解方針:**
- 日本語の `。` 句点を文の区切りとして認識し、短文に分割して翻訳入力とする
- `\n\n`（空行）は段落区切り、`\n`（改行のみ）は同一段落内の行区切りとして扱う
- 詩は改行ごとに1行を独立した翻訳単位とする
- P_ja（段落数）のカウントは、短文分解「前」の元テキストの空行区切り段落数を使用する（QA ゲートのベースラインは元の段落構造で計測）

---

## 4. 品質ゲート

### Q4-1 Introduction の長さチェックが未定義 `OPEN`

- Agent 3 が生成する Introduction（100–150 words）に対して、QA ゲート（Agent 5）でワード数を検証するかどうかが SPEC.md に明記されていない。
- 生成が短すぎた（50 words）or 長すぎた（300 words）場合、PASS/FAIL のどちらにするか？
- Introduction は本文翻訳と同一の LLM 呼び出しで生成するか、別呼び出しか（タイムアウト・リトライへの影響が異なる）。

### Q4-2 「段落（paragraph）」の定義が曖昧 `OPEN`

- `P_ja` / `P_en` のカウント基準が未定義。
  - 日本語: 空行区切りか？字下げ（全角スペース開始）か？
  - 英語: 空行区切りか？
  - 詩: 1行を1段落として数えるか？連（stanza）単位か？
- カウント方法が揺れると QA ゲートの false positive 率が高くなる。`DATA/threshold-calibration.md` に定義を含めるべきでは？

### Q4-3 QA ゲートのしきい値は genre 別のみか `OPEN`

- 現在 `genre = "poem" | "short"` の2区分だが、詩でも字数が極端に少ない「俳句・短歌」は長さ比 `R` が別の分布になる可能性がある。
- `genre` を細分化するか（`haiku`, `tanka`, `poem`, `short`）、それとも現行2区分で `calibration.md` によるしきい値調整で対応するか？

---

## 5. エラーハンドリング・エッジケース

### Q5-1 ロールバック時の `next_index` 計算 `RESOLVED`

**回答: 短文が対象なので全体をやり直す方針とする。**

問題のある公開が発覚した場合のロールバック手順を以下に改訂する:

1. 問題のあるコミットを `git revert`（作品ページ・index.html・sitemap.xml を除去）
2. `state.json` の `next_index` を **問題作品の index 値にリセット**（`--` ではなく直接指定）
3. `state.json` の `skip_log` に当該 index を追記（`reason` に問題内容を記載）
4. 翌日の定時実行（または手動即時実行）で次候補が自動公開される
5. `DATA/logs/manual-interventions.md` にインシデントを記録

短文なので全体を再処理してもコストが低く、シンプルな「index を問題箇所に戻す + skip_log で当該作品をスキップ」で十分。`next_index--` という表現は SPEC.md から削除し、「`next_index = 問題作品のindex`」と明確化する。

### Q5-2 Fetch エラーは attempt カウントに含まれるか `OPEN`

- SEQUENCE.md シナリオ6（Aozora Bunko 取得エラー）では、3回リトライ後に `attempt++, i++` と記されている。
- これは「Fetch エラーも attempt 3回制限の1回」としてカウントされる、という理解でよいか？
- Fetch の3回リトライ（バックオフ1s/2s/4s）が候補1つで最大7秒かかり、3候補でも21秒程度なので許容範囲と思われるが、確認が必要。

### Q5-3 Publisher の部分失敗時の state.json 更新 `RESOLVED`

- クリティカル成果物は「作品ページ生成」と「その作品ページを含む push 成功」。
- `state.json` を進めてよい条件は上記クリティカル成果物が両方成功した場合のみ。
- `sitemap.xml` / `robots.txt` / `index.html` はノンクリティカル。失敗時は warning を記録して継続し、次回再生成で回収する。

### Q5-4 `works.json` バリデーション失敗エントリの skip_log 記録 `OPEN`

- SPEC.md §3.1 に「validation failure のエントリはスキップしログに記録、実行は abort しない」とある。
- このスキップは `state.json` の `skip_log` に記録されるか、それとも起動時の別ログに記録されるか？
- `next_index` はバリデーション失敗エントリもインクリメントするか（失敗エントリを飛ばして次を使うか）？

### Q5-5 exhausted 状態の初日確認時、issues の検索精度 `OPEN`

- SEQUENCE.md シナリオ5 で `gh issue list --search "works.json exhausted — manual extension required"` を実行するが、全文一致でないと別件 Issue がヒットする可能性がある。
- Issue タイトルに固定プレフィックス/ラベルを付けて確実に識別する仕組みが必要では？（例: label `exhausted` を付与してラベル検索する）

---

## 6. セキュリティ

### Q6-1 Codex CLI `exec` のコマンドインジェクション対策 `RESOLVED`

**回答: ローカルPCの閉じた環境での処理であり、外部からのコマンドインジェクションリスクは低い。ただし、青空文庫テキストがLLMへのプロンプトインジェクションを含む可能性はあるため、以下を実装する。**

**実装方針:**

1. **Codex CLI 呼び出し**: テキストは必ず `tmp/` にファイルとして書き出し、ファイルパスを引数で渡す。シェルコマンド文字列へのテキスト直接展開は禁止。`subprocess.run(args_list, shell=False)` を使用する。

2. **プロンプトインジェクション検査**: Agent 2 (Fetcher) が `clean_text_ja.txt` を生成する際、以下のパターンを検出してログに記録する（SUSPICIOUS でも翻訳は継続するが、QA ゲートで最終確認）:
   - `ignore (all) previous instructions`
   - `you are now a ...`
   - `<system>`, `</system>`, `[INST]`, `<<SYS>>`
   - 異常に長い単一行（> 500文字）

   → `tools/test_aozora_encoding.py` の `check_prompt_injection()` 関数を Fetcher に組み込む。

3. **インジェクション検出時の対応**: `02_fetch_result.json` に `injection_warnings: []` フィールドを追加し、検出内容を記録。QA ゲート（Agent 5）がこのフィールドを参照し、高リスクパターンの場合は FAIL とする。

実験結果（`tools/test_aozora_encoding.py`）: 羅生門・桜の樹の下には・羅生門ZIP の3作品はすべて CLEAN を確認済み。

### Q6-2 CSP meta タグの限界 `OPEN`

- SPEC.md §12.3 に「CSP headers via meta tags」とあるが、`<meta http-equiv="Content-Security-Policy">` では `frame-ancestors` ディレクティブは無効（HTTP レスポンスヘッダーでなければならない）。
- GitHub Pages はカスタム HTTP ヘッダーの設定をサポートしていない（2026年3月時点）。
- `frame-ancestors` が必要かどうかを確認し、不要なら meta タグで十分と明記、必要なら代替手段（`X-Frame-Options` 相当は meta タグ非対応）を検討すべき。

### Q6-3 `aozora.gr.jp` のサブドメイン許可範囲 `RESOLVED`

- 許可条件は FQDN 列挙ではなく host 末尾一致に統一する。
- 許可: `host == "aozora.gr.jp"` または `host.endswith(".aozora.gr.jp")`。
- scheme は `http` / `https` のみ許可。

---

## 7. スラッグ・著者ページ

### Q7-1 著者スラッグの衝突処理が未定義 `OPEN`

- `author_en` が異なるが slug が同一になる著者（例: "Akutagawa Ryunosuke" と "Akutagawa Ryūnosuke"）が存在した場合、同一の `/authors/<slug>/` に混在する。
- 作品ページと異なり著者ページには `YYYY-MM-DD` prefix がないため、衝突回避の仕組みが未定義。
- `works.json` 追加時に著者 slug を正規化する運用ガイドが必要か？

### Q7-2 `author_en` の表記順統一 `OPEN`

- 日本人著者の英語表記は「Last First（芥川 龍之介 → Akutagawa Ryunosuke）」が一般的だが、`works.json` の記入者によって「First Last」が混在する可能性がある。
- 著者ページの URL・一覧の整合性に影響するため、`works.json` 運用ガイドに表記順を明記すべき。

### Q7-3 slug の最大長 50 文字の切り詰め処理 `OPEN`

- タイトルが長い場合、50 文字で切り詰めると単語の途中で切れる可能性がある。
- 単語境界（ハイフン直前）で切り詰めるアルゴリズムを明示すべき（そのまま文字数で切ると `the-spiders-thr` のような不完全なスラッグになる）。

---

## 8. モニタリング・コスト

### Q8-1 週次サマリの送信主体・形式が未定義 `OPEN`

- SPEC.md §6.7 に「Weekly summary: total works published, skip count, API cost」とあるが、誰が・どうやって・どこに送るかが未定義。
- openClaw が対応しているか、別途 cron job が必要か？配信先（email? Slack? GitHub Discussions?）は？

### Q8-2 `api_cost_usd` のカウント方法 `OPEN`

- Codex CLI は flat-rate プラン（= トークンに関わらず定額）、Local LLM は無料。
- 現状では実質的に常に `0` となるが、フィールドが RunLog に存在する意味は将来の API 有料化を見越したものか？
- 将来 per-token 課金に移行した場合のカウント方法（Codex CLI がトークン数を返すか）を確認すべき。

### Q8-3 「3日連続公開なし」のカウント方法 `OPEN`

- SPEC.md §6.7 に「3 consecutive days with zero publications」でアラートとあるが、このカウントをどこで管理するか未定義。
- `DATA/logs/` の `final_status` を過去3日分読んでカウントするか、`state.json` にカウンタフィールドを追加するか？

---

## 9. パフォーマンス・タイムアウト

### Q9-1 タイムアウト制約の整合性 `OPEN`

- SPEC.md §6.5「per-agent timeout: 5分」×「最大3候補 × 7エージェント」= 理論上最大 105 分 vs SPEC.md §6.6「total workflow timeout: 20 分」
- 実際の想定は「翻訳ステップ（Agent 3）が最も時間を要し 5 分、他は数秒」という前提か？
- 20 分のハードリミットを超えた場合、実行中のエージェントを強制終了してどこまで `state.json` を更新するか明確化が必要。

---

## 10. 並行性・git操作

### Q10-1 並行実行防止の具体的メカニズムが未定義 `RESOLVED`

- 実装仕様: 起動時に `DATA/run.lock` の排他ロックを取得する。
- 取得失敗時は「先行実行あり」とみなして即終了（副作用なし）。
- ローカル cron 実行では `flock` 相当の排他を標準実装とする。

### Q10-2 push conflict 解決後の重複公開リスク `OPEN`

- SEQUENCE.md シナリオ7の conflict 解決ルール: `next_index = max(local, remote)`。
- しかし、conflict が起きた背景として「remote 側でも同時に別の公開が完了していた」ことが考えられる。
  - local 側が生成した作品ページ（index=5）をそのまま push すると、remote 側が既に index=5 を公開済みの場合、同じ日付パスに別内容のページが上書きされないか？
  - `YYYY-MM-DD` が含まれるパスなので同じ日に限り衝突するが、この状況は openClaw の並行防止で「起きてはならない前提」なのか、それとも rebase 解決で対処するのか明確化が必要。

### Q10-3 `state.json` の `rollback` ステータスの扱い `RESOLVED`

- `state.json.status` は `active` / `exhausted` の2値のみ。
- `rollback` は状態値としては持たず、手動運用手順として扱う。
- ロールバック時は `next_index = 問題作品 index` を直接設定し、`skip_log` に理由付きで追記する。

---

## 優先度サマリ

| 優先度 | 疑問点 | ステータス | 理由 |
|--------|--------|-----------|------|
| 高 | Q1-1 `tmp/` スキーマ | RESOLVED | 単体テスト・全エージェント実装の基礎 |
| 高 | Q2-1 openClaw の実態 | RESOLVED | 実行環境が確定しないと全設定が書けない |
| 高 | Q2-2 Codex CLI 呼び出し形式 | OPEN | Agent 3・4 の中心ロジック |
| 高 | Q3-1 Shift-JIS デコード | RESOLVED | データ取得の最初の壁 |
| 高 | Q3-3 段落定義 | RESOLVED | QA ゲートの判定精度に直結 |
| 高 | Q5-1 ロールバック手順の `next_index` 計算 | RESOLVED | 誤解があると誤ったデータ修復を招く |
| 高 | Q6-1 `exec` のインジェクション対策 | RESOLVED | セキュリティ基盤 |
| 中 | Q2-3 Local LLM 実装 | OPEN | フォールバック品質の保証 |
| 中 | Q3-2 ファイル形式判別 | RESOLVED | 既存実装を流用 |
| 中 | Q4-1 Introduction の QA | OPEN | 公開品質に影響 |
| 中 | Q4-2 段落カウント定義 | OPEN | しきい値キャリブレーション精度 |
| 中 | Q7-1 著者スラッグ衝突 | OPEN | works.json が増えると発生しやすい |
| 中 | Q9-1 タイムアウト整合性 | OPEN | ワークフロー設計の現実性 |
| 低 | Q8-1 週次サマリ | OPEN | 運用開始後でも定義可能 |
| 低 | Q8-2 api_cost_usd | OPEN | 現時点では常に 0 |

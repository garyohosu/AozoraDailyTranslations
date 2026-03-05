# Aozora Daily Translations

[![CI](https://github.com/garyohosu/AozoraDailyTranslations/actions/workflows/ci.yml/badge.svg)](https://github.com/garyohosu/AozoraDailyTranslations/actions/workflows/ci.yml)
[![Pages](https://github.com/garyohosu/AozoraDailyTranslations/actions/workflows/pages.yml/badge.svg)](https://github.com/garyohosu/AozoraDailyTranslations/actions/workflows/pages.yml)

青空文庫のパブリックドメイン作品を毎日1作品、自動翻訳して GitHub Pages に英語で公開するパイプライン。

- 候補不足時は `DATA/works.json` を自動補充（既定: 200件まで）

- **翻訳エンジン:** Codex CLI（フラットレートプラン）、フォールバックに Local LLM
- **スケジューラー:** openClaw（ローカル PC、JST 09:00 毎日）
- **公開先:** GitHub Pages（静的 HTML）
- **ライセンス:** 英語翻訳は CC0 1.0 Universal

---

## ディレクトリ構成

```
AozoraDailyTranslations/
├── DATA/
│   ├── works.json          # 候補作品リスト（キュレーション済み）
│   ├── state.json          # 進捗トラッカー（next_index / status）
│   └── logs/               # 日次実行ログ YYYY-MM-DD.json
├── src/aozora/
│   ├── models.py           # データモデル
│   ├── agents/             # 各エージェント実装
│   └── generators/         # HTML 生成
├── tests/                  # pytest テストスイート
├── tools/                  # 調査・実験スクリプト
├── SPEC.md                 # 仕様書
├── CLASS.md                # クラス図
└── .github/workflows/      # CI/CD（lint + test + Pages デプロイ）
```

---

## セットアップ

### 前提条件

- Python 3.8 以上（素子の実行環境に合わせる）
- [Codex CLI](https://github.com/openai/codex) インストール済み（フラットレートプラン）
- OpenClaw インストール済み（スケジューラー）
- GitHub リポジトリの Pages 設定: **Settings → Pages → Source = "GitHub Actions"**

### インストール

```bash
git clone https://github.com/garyohosu/AozoraDailyTranslations.git
cd AozoraDailyTranslations
pip install -e ".[dev]"
```

### データファイルの初期化

`DATA/` ディレクトリと初期ファイルを作成する。

```bash
mkdir -p DATA/logs

# works.json — 候補作品リスト（SPEC.md §3.1 のスキーマに従う）
cat > DATA/works.json << 'EOF'
[
  {
    "aozora_card_url": "https://www.aozora.gr.jp/cards/000879/card128.html",
    "aozora_txt_url":  "https://www.aozora.gr.jp/cards/000879/files/128_15261.html",
    "title_en":  "Rashomon",
    "author_en": "Akutagawa Ryunosuke",
    "title_ja":  "羅生門",
    "author_ja": "芥川龍之介",
    "genre": "short"
  }
]
EOF

# state.json — 初期状態
cat > DATA/state.json << 'EOF'
{
  "next_index": 0,
  "status": "active",
  "skip_log": []
}
EOF
```

---

## テスト

```bash
# 全テスト実行（カバレッジ付き）
pytest

# 特定モジュールのみ
pytest tests/test_qa_auditor.py -v

# lint チェック
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
```

---

## 手動実行

```bash
python -m aozora.run --date 2026-03-05
```

> `--date` を省略すると今日の JST 日付が使われます。

---

## openClaw によるスケジュール設定

openClaw はローカル PC で動作する専用スケジューラーです。
毎日 JST 09:00 にパイプラインをトリガーします。

### 基本設定手順（OpenClaw CLI / Linux・WSL向け）

```bash
openclaw cron add \
  --name "AozoraDailyTranslations daily" \
  --cron "0 9 * * *" \
  --tz "Asia/Tokyo" \
  --session isolated \
  --message "作業ディレクトリ /home/garyo/.openclaw/workspace/AozoraDailyTranslations で python3 -m aozora.run を実行。成功時は生成パスとcommit/push結果を要約、失敗時はエラー要点を3行で通知。"
```

- 重複起動防止は OpenClaw 側設定で有効化推奨
- パイプライン内部でも `DATA/run.lock` を使った排他制御を維持

### 動作確認

```bash
python3 -m aozora.run --date 2026-03-05
cat DATA/logs/$(date +%Y-%m-%d).json
```

---

## ワークフロー概要

```
openClaw (JST 09:00)
  │
  └─ Orchestrator
       ├─ 1. Screener   — 著作権・翻訳作品チェック
       ├─ 2. Fetcher    — 青空文庫からテキスト取得（最大3リトライ）
       ├─ 3. Translator — Codex CLI で英訳（失敗時 Local LLM）
       ├─ 4. Editor     — 英文校正
       ├─ 5. QAAuditor  — 品質ゲート（段落数・長さ比率・アーティファクト）
       └─ 6. Publisher
            ├─ 6A. WorkPageGenerator  → works/YYYY-MM-DD-slug/index.html
            ├─ 6B. IndexArchiveGenerator → index.html, authors/*/index.html
            └─ 6C. SitemapSEOGenerator   → sitemap.xml, robots.txt
```

1日最大3候補を試行。成功したら `DATA/state.json` を更新して `git push`。
GitHub Pages が自動デプロイ。

---

## ロールバック手順

誤った作品が公開された場合（SPEC.md §6.8）:

```bash
# 1. 問題コミットを revert
git revert <commit-hash>

# 2. state.json の next_index を問題作品の index に戻す
#    （例: index=5 が問題なら next_index=5 に設定）
#    skip_log にも当該 index を追記する

# 3. 変更をコミット・プッシュ
git add DATA/state.json
git commit -m "fix: rollback index=5, add to skip_log"
git push

# 4. DATA/logs/manual-interventions.md にインシデントを記録
```

---

## CI/CD

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `ci.yml` | push / PR → main | ruff lint + pytest (Python 3.11 / 3.12) |
| `pages.yml` | HTML/XML ファイル変更 → main | GitHub Pages デプロイ |

---

## ドキュメント

| ファイル | 内容 |
|----------|------|
| [SPEC.md](SPEC.md) | システム仕様・要件定義 |
| [CLASS.md](CLASS.md) | クラス図（Mermaid） |
| [SEQUENCE.md](SEQUENCE.md) | シーケンス図（10シナリオ） |
| [USECASE.md](USECASE.md) | ユースケース図 |
| [QA.md](QA.md) | 設計上の疑問点・決定事項 |

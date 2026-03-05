# USECASE.md — Aozora Daily Translations

ユースケース図（Mermaid記法）。SPEC.md を設計根拠とする。

---

## 1. アクター定義

| アクター | 種別 | 説明 |
|----------|------|------|
| Reader | 主アクター | 翻訳済み作品を閲覧する一般ユーザー |
| Maintainer | 主アクター | `works.json` の管理・障害対応を行う運営者 |
| openClaw | 主アクター（システム） | 日次ワークフローをトリガーするスケジューラー |
| Aozora Bunko | 外部システム | 日本語原文テキストの配信元 |
| Codex CLI / Local LLM | 外部システム | 翻訳・Introduction生成エンジン |
| GitHub Pages | 外部システム | 静的サイトのホスティング |

---

## 2. ユースケース全体図

```mermaid
graph LR
    %% Actors
    Reader((Reader))
    Maintainer((Maintainer))
    OC((openClaw))
    Aozora([Aozora Bunko])
    LLM([Codex CLI /\nLocal LLM])
    GHP([GitHub Pages])

    %% ---- Reader use cases ----
    subgraph UC_Reader["Reader"]
        R1(作品ページを読む)
        R2(アーカイブを閲覧する)
        R3(著者ページを閲覧する)
    end

    Reader --> R1
    Reader --> R2
    Reader --> R3
    R1 --> GHP
    R2 --> GHP
    R3 --> GHP

    %% ---- Daily workflow use cases ----
    subgraph UC_Daily["日次ワークフロー（openClaw トリガー）"]
        D1(候補作品を選択する)
        D2(適格性をスクリーニングする)
        D3(テキストを取得・正規化する)
        D4(英語翻訳を生成する)
        D5(翻訳を編集・推敲する)
        D6(品質ゲートを検証する)
        D7(作品ページを生成する)
        D8(インデックス・アーカイブを更新する)
        D9(サイトマップ・SEOを更新する)
        D10(state.json / logs を更新し同一コミットで push する)
    end

    OC --> D1
    D1 --> D2
    D2 --> D3
    D3 --> D4
    D4 --> D5
    D5 --> D6
    D6 --> D7
    D7 --> D8
    D8 --> D9
    D9 --> D10

    D3 --> Aozora
    D4 --> LLM
    D10 --> GHP

    %% ---- Maintainer use cases ----
    subgraph UC_Maint["Maintainer"]
        M1(works.json に作品を追加する)
        M2(問題のある公開をロールバックする)
        M3(state.json を手動修正する)
        M4(閾値キャリブレーションを実施する)
        M5(GitHub Issue に対応する)
    end

    Maintainer --> M1
    Maintainer --> M2
    Maintainer --> M3
    Maintainer --> M4
    Maintainer --> M5

    M1 -.再開トリガー.-> D1
    M5 -.exhausted 解消.-> M1
```

---

## 3. 日次ワークフロー シーケンス図

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

    OC->>Orch: 日次トリガー（JST 09:00）
    Orch->>Orch: works.json / state.json 読み込み<br/>next_index を取得

    loop 最大 3 候補まで retry
        Orch->>Screen: candidate (index i) を渡す
        Screen->>AZ: Aozora カードを取得
        AZ-->>Screen: カード HTML

        alt 不適格（翻訳作品 / 権利不明 / 注釈過多）
            Screen-->>Orch: INELIGIBLE + reason
            Orch->>Orch: skip_log に記録、i+1 へ
        else 適格
            Screen-->>Orch: ELIGIBLE

            Orch->>Fetch: テキスト取得を指示
            Fetch->>AZ: zip / txt / html を取得（最大 3 retry）
            AZ-->>Fetch: 原文データ
            Fetch->>Fetch: ルビ・注釈除去、clean_text_ja 生成
            Fetch-->>Orch: clean_text_ja + metrics

            Orch->>Trans: clean_text_ja を渡す
            Trans->>LLM: 翻訳 + Introduction 生成（exec）
            LLM-->>Trans: translation_en + introduction_en
            Trans-->>Orch: translation_en, introduction_en

            Orch->>Edit: translation_en を渡す
            Edit->>LLM: 英語流暢性改善
            LLM-->>Edit: edited_translation_en
            Edit-->>Orch: edited_translation_en

            Orch->>QA: 全成果物を渡す
            QA->>QA: Format Gates 検証<br/>（段落数差・長さ比・アーティファクト・定型文）

            alt QA FAIL
                QA-->>Orch: FAIL + reason
                Orch->>Orch: skip_log に記録、i+1 へ
            else QA PASS
                QA-->>Orch: PASS + metrics

                Orch->>Pub: 公開指示
                Pub->>Pub: 6A: 作品ページ HTML 生成
                Pub->>Pub: 6B: index.html / 著者ページ更新
                Pub->>Pub: 6C: sitemap.xml / robots.txt 更新
                Pub-->>Orch: 生成ファイル一覧

                Orch->>Orch: state.json 更新（next_index = i+1, status = active）
                Orch->>Orch: ログ保存 DATA/logs/YYYY-MM-DD.json（final_status=published）
                Orch->>GH: commit + push（生成ファイル + state.json + DATA/logs を同一コミット）
                GH-->>Orch: push 完了
                Note over OC,GH: ワークフロー完了（公開成功）
                break
            end
        end
    end

    alt 3 候補すべて失敗
        Orch->>Orch: state.json 更新（next_index 更新, status = active）
        Orch->>Orch: ログ保存 DATA/logs/YYYY-MM-DD.json（final_status=no_publication）
        Orch->>GH: commit + push（state.json + DATA/logs を同一コミット）
        Orch->>OC: 失敗通知（当日は公開なし）
    end
```

---

## 4. リトライ・スキップ フロー

```mermaid
flowchart TD
    Start([日次実行開始]) --> Load[works.json / state.json 読み込み]
    Load --> AlreadyExhausted{status == exhausted?}

    AlreadyExhausted -- Yes --> IssueCheck0{未対応の exhausted Issue が存在?}
    IssueCheck0 -- No --> CreateIssue0[GitHub Issue を1回作成\n管理者に通知]
    IssueCheck0 -- Yes --> SkipIssue0[Issue 作成をスキップ]
    CreateIssue0 --> SaveExhaustedLog0[DATA/logs/YYYY-MM-DD.json 保存\nfinal_status=exhausted]
    SkipIssue0 --> SaveExhaustedLog0
    SaveExhaustedLog0 --> PushExhausted0[commit + push（state.json + DATA/logs を同一コミット）]
    PushExhausted0 --> End([終了：公開なし])

    AlreadyExhausted -- No --> Init[attempt = 0\ni = next_index]

    Init --> TryCandidate[候補 i を処理]
    TryCandidate --> Screen{Screener\nELIGIBLE?}

    Screen -- INELIGIBLE --> LogSkip1[skip_log 記録\ni++, attempt++]
    Screen -- ELIGIBLE --> Fetch[Fetcher: テキスト取得]

    Fetch --> FetchOK{取得成功?}
    FetchOK -- No（3 retry 失敗）--> LogSkip2[skip_log 記録\ni++, attempt++]
    FetchOK -- Yes --> Translate[Translator → Editor]

    Translate --> QACheck{QA PASS?}
    QACheck -- FAIL --> LogSkip3[skip_log 記録\ni++, attempt++]
    QACheck -- PASS --> Publish[Publisher: ページ生成]

    Publish --> UpdateState[state.json: next_index = i+1\nstatus = active]
    UpdateState --> SaveLog[DATA/logs/YYYY-MM-DD.json 保存\nfinal_status=published]
    SaveLog --> PushSuccess[commit + push（生成ファイル + state.json + DATA/logs を同一コミット）]
    PushSuccess --> End2([終了：公開成功])

    LogSkip1 --> ExhaustCheck{i >= works.length?}
    LogSkip2 --> ExhaustCheck
    LogSkip3 --> ExhaustCheck

    ExhaustCheck -- Yes --> SetExhausted[state.status = exhausted]
    SetExhausted --> IssueCheck1{未対応の exhausted Issue が存在?}
    IssueCheck1 -- No --> CreateIssue1[GitHub Issue を1回作成]
    IssueCheck1 -- Yes --> SkipIssue1[Issue 作成をスキップ]
    CreateIssue1 --> SaveExhaustedLog1[DATA/logs/YYYY-MM-DD.json 保存\nfinal_status=exhausted]
    SkipIssue1 --> SaveExhaustedLog1
    SaveExhaustedLog1 --> PushExhausted1[commit + push（state.json + DATA/logs を同一コミット）]
    PushExhausted1 --> End3([終了：公開なし])

    ExhaustCheck -- No --> AttemptCheck{attempt >= 3?}
    AttemptCheck -- No --> TryCandidate
    AttemptCheck -- Yes --> NoPublish[state.json: next_index 更新\nstatus = active]
    NoPublish --> SaveNoPubLog[DATA/logs/YYYY-MM-DD.json 保存\nfinal_status=no_publication]
    SaveNoPubLog --> PushNoPub[commit + push（state.json + DATA/logs を同一コミット）]
    PushNoPub --> End4([終了：公開なし])
```

---

## 5. state.json ステートマシン

```mermaid
stateDiagram-v2
    [*] --> active : works.json 初期化

    active --> active : 公開成功\nnext_index++

    active --> active : スキップ（不適格 / QA FAIL）\nskip_log 追記、next_index++

    active --> exhausted : next_index >= works.length

    exhausted --> active : Maintainer が works.json を拡張\nnext_index をリセット

    %% rollback is a manual procedure, not a runtime state

    note right of exhausted
        active→exhausted 遷移時に
        GitHub Issue を1回だけ自動作成
        （未対応Issueがなければ作成）
        管理者の手動対応が必要
    end note

    note right of active
        Manual rollback procedure (no rollback status in state.json):
        1. 問題コミットを revert
        2. next_index = 問題作品の index i に設定（-- は禁止）
        3. skip_log に index=i を理由付きで追記
        4. 再実行
    end note
```

---

## 6. Maintainer ユースケース詳細

```mermaid
flowchart LR
    M((Maintainer))

    subgraph 通常運用
        A1[works.json に作品を追加\ngenre / URL / title_en 等を記入]
        A2[閾値キャリブレーション実施\n15作品でゲート検証\nDATA/threshold-calibration.md に記録]
    end

    subgraph 障害対応
        B1[GitHub Issue 対応\nexhausted 解消のため works.json 拡張]
        B2[問題公開のロールバック\n1. commit revert\n2. next_index = problematic_index\n3. skip_log 追記\n4. 再実行]
        B3[state.json 手動修正\ngit history から復元\nnext_index を調整]
        B4[DATA/logs/manual-interventions.md\nにインシデント記録]
    end

    M --> A1
    M --> A2
    M --> B1
    M --> B2
    M --> B3
    B2 --> B4
    B3 --> B4
    B1 --> A1
```

---

## 7. Reader ユースケース詳細

```mermaid
flowchart LR
    R((Reader))

    subgraph GitHub Pages
        P1[作品ページを読む\n/works/YYYY-MM-DD-slug/]
        P2[アーカイブを閲覧する\n/index.html]
        P3[著者ページを閲覧する\n/authors/author-slug/]
        P4[サイトマップを参照する\n/sitemap.xml]
    end

    R --> P2
    R --> P3
    P2 --> P1
    P3 --> P1
    P4 -.検索エンジン経由.-> P1

    P1 -. 表示される情報 .-> Info["- 翻訳本文\n- Introduction（100–150 words）\n- Aozora Bunko クレジット\n- CC0 ライセンス表示\n- 自動翻訳免責事項"]
```

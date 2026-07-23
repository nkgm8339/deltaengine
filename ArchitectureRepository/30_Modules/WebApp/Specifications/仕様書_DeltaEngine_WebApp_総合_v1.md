# 仕様書_DeltaEngine_WebApp_総合_v1
## — Phase 1 完了文書 —

**Document ID**: SPEC-WEB-001
**Version**: v1
**Status**: Fixed（Phase 1 凍結版）
**作成日**: 2026-07-16
**構成準拠**: Webサイト仕様書 標準構成（概要→詳細の掲載順序）
**下位文書**: WebSocketPayload仕様_v1 / UI仕様書_CommandCenter_v1 / 指示書_WebApp_v3

---

# 第1部【概要】

## 1. 現状の課題

DeltaEngineは全11モジュール（DataReceiver〜MT5 Adapter）の実装が完了し、CLIツール（`live_verify`）で稼働している。しかし以下の課題がある。

| # | 課題 |
|---|---|
| 1 | 分析結果の確認手段がCLI統計出力とDuckDBへのSQL照会のみで、**リアルタイムに市場状況を把握できない** |
| 2 | シグナル（BUY/SELL/WAIT）は生成されるが、**「なぜその判定なのか」の根拠（各Detectorスコア・合流状況）が見えない** |
| 3 | Footprint・OrderBook・CVD・Flowイベントを**同一画面で突き合わせる手段がない**ため、トレード判断に数字の読み解き時間がかかる |
| 4 | MT5には配信されるが、配信内容の**監視・検証用の画面が存在しない** |

## 2. プロジェクトの概要

| 項目 | 内容 |
|---|---|
| **目的** | Binance Futuresの注文フロー分析結果を、ブラウザ上のリアルタイム・コマンドセンターとして可視化する |
| **背景** | 上記課題1〜4。「BinanceのオーダーフローからMT5で勝つための意思決定支援システム」という本プロジェクトの最終目標に対し、可視化層が欠落している |
| **ゴール** | **トレーダーが3秒以内に状況を把握し、売買判断できること**（データ表示ツールではない） |
| **ターゲット** | プロジェクトオーナー本人（単一トレーダー・毎日数時間のトレード運用を想定） |
| **コンセプト** | コマンドセンター。視線の流れ（左：板の厚み → 中央：Footprint/Flow → 右：判定根拠）を設計の軸とする |
| **デザイン** | ダーク・プレミアム・高情報密度（参照: Apple / Bloomberg / Porsche）。カラー規則: 緑=買い / 赤=売り / 黄=注意 / 灰=無効 / 紫=情報。等幅フォント・tabular-nums |
| **キーワード（SEO）** | 該当なし（非公開の内部ツール。検索流入を想定しない） |
| **成果目標値（CV相当）** | ①3秒判断が成立するUI（CONFLUENCE・スコアバー・Flow Events） ②テスト235本green ③`docker-compose up`のみで起動 |
| **公開日** | Code実装完了・web検証合格をもってPhase 1リリースとする（外部公開はしない） |
| **予算** | 追加費用なし（自宅PC/VPS上でセルフホスト。クレジット節約方針を厳守） |
| **既存版の情報** | delta_command_center_v2.html（3カラム構成・v3.3モックにより全面置換済み） |

**設計三原則（本プロジェクトの憲法）**
1. 固定値・ダミー値禁止（全数値はPayload由来。無い値は「—」）
2. UI ≠ ドメインモデル（signal / market_state等はPayload文字列をそのまま描画）
3. SignalEngineが唯一の判定主体（UIに判定ロジックを置かない）

## 3. サイトマップ

シングルページ・アプリケーション（画面遷移なし）。

```
http://localhost:8080/
├── /            … コマンドセンター本体（index.html、唯一の画面）
├── /ws          … WebSocketエンドポイント（Payload v1配信）
└── /static/*    … 静的アセット（index.html のみ。外部依存なし）
```

## 4. ワイヤーフレーム

正はデザインモック `delta_command_center_v3_3.jsx` および UI仕様書_CommandCenter_v1 §1。

```
┌─────────────────────────────────────────────────────────────┐
│ TOP BAR: SYMBOL PRICE ▲% │ SIGNAL CONF │ ATR SPREAD LAT FPS │ LIVE 🐛 │
├────────────┬──────────────────────────────┬─────────────────┤
│ ORDER BOOK │ FOOTPRINT（主役・約58%）       │ MARKET STATE    │
│ heatmap+Σ  │  Bid×Ask / Delta / POC/VAH/VAL│ CONFLUENCE      │
│            ├──────────────────────────────┤ SIGNAL — WHY    │
│            │ FLOW EVENTS（リアルタイム）     │ （スコア→Composite）│
├────────────┴──────────────────────────────┴─────────────────┤
│ CVD+Δ / VOLUME / OI / LIQUIDATION（タブチャート）              │
└─────────────────────────────────────────────────────────────┘
＋ 🚨トースト(3秒) ／ 右下ALERTS履歴 ／ 左下Developer Overlay(非表示既定)
```

---

# 第2部【詳細】

## 5. スマホ対応

- **Phase 1**: PC横画面前提。Android ChromeでのPWA的閲覧（`http://サーバーIP:8080` 直開き）は動作可能だが、3カラムは縦画面に最適化されない
- **Phase 2（計画済み）**: WebViewラッパー（Capacitor等）方式を採用予定。必要改変は ①WS接続先の設定画面化 ②モバイル縦レイアウト（UI仕様書v1.1として追補）の2点のみ。バックエンド改変ゼロ（Payload仕様固定の効果）
- Kotlinネイティブ化は不採用（工数過大）

## 6. OS・ブラウザ対応

| 区分 | 対応 |
|---|---|
| PC OS | Windows 10/11・macOS（最新） |
| PCブラウザ | Google Chrome / Microsoft Edge / Firefox / Safari 各最新版 |
| モバイル | Android Chrome 最新版（Phase 2で正式対応） |
| 非対応 | Internet Explorer（対応しない。追加対応も行わない） |
| 技術要件 | WebSocket・CSS Grid/Flex・ES2020。ビルド工程なしのVanilla JSのため互換リスク最小 |

## 7. サーバー・ドメイン

- **サーバー**: 自宅PCまたはVPS上でセルフホスト。`docker-compose up` のみで起動（Python 3.12 / FastAPI / uvicorn、ポート8080）
- **契約・管理**: すべて発注者（オーナー）自身が保有・管理する。外部業者のサーバー・ドメインに依存しない
- **ドメイン**: Phase 1では不要（LAN内 `localhost` / プライベートIPアクセス）。外部アクセスが必要になった時点で独自ドメイン取得を検討（Phase 2）
- **依存データ**: `./config` と `./data` をボリュームマウントし、コンテナ再作成でもデータを保持

## 8. SSL化について

- **Phase 1**: 非SSL（http/ws）。LAN内・単一利用者・無認証の閉域運用を前提とするため
- **Phase 2（外部公開時）**: wss（TLS）＋認証を必須とする。リバースプロキシ（Caddy/nginx＋Let's Encrypt）方式を想定。Payload仕様への影響は認証情報の追加のみで、**v1.x（互換あり）の範囲で対応可能**（Version Policy §6準拠）
- 外部公開するまでポート8080をインターネットへ開放しないこと（運用禁止事項）

## 9. 原稿・素材の準備について

| 素材 | 準備 |
|---|---|
| 表示データ（価格・Footprint・スコア等） | 全てWebSocket Payload由来のリアルタイムデータ。**静的原稿は存在しない** |
| 文言（ラベル・凡例） | UI仕様書_CommandCenter_v1 に全て定義済み（英字ラベル） |
| フォント | システム等幅フォント（SF Mono / Cascadia / Roboto Mono）。Webフォント配信なし＝外部依存なし |
| アイコン・画像 | 絵文字（🚨🐛🔒）とCSS描画のみ。画像ファイルゼロ |
| ライセンス | 外部素材不使用のため権利処理不要 |

## 10. 運用・保守について

### 10.1 作業範囲（依頼範囲の明確化）

| 担当 | 範囲 |
|---|---|
| **web**（本セッション） | 仕様書・指示書・ADR等の文書作成／実装ZIPの検証（pytest・全ファイル・AST比較・float禁則grep・Payload仕様適合目視）／設計提案 |
| **Code** | 指示書_WebApp_v3 に基づく実装・テスト・完了3点セット提出（CompletionLog追記＋全体ZIP＋チャット報告） |
| **オーナー** | 設計変更の承認／Code・web間の成果物受け渡し／本番動作確認（`http://localhost:8080`） |

### 10.2 保守規律

- **ドキュメント**: Documentation-First。変更はADR・CHANGELOG・CompletionLogに記録
- **Payload互換性**: WebSocketPayload仕様_v1 §6 Version Policy準拠（追加のみv据え置き／Breaking はv2＋ADR＋HELLO通知／Deprecatedは最低2バージョン維持）
- **障害時**: UIは段階的縮退（Warning表示→劣化描画→メッセージ単位スキップ）で生存。WebSocket切断は指数バックオフで自動再接続
- **禁則の恒常監視**: `float(` 禁止・固定値禁止・UI判定ロジック禁止は全改修で検証対象

---

# 第3部 Phase 2 以降（スコープ外の決定場所）

| 項目 | 決定の場 |
|---|---|
| signal 4値化（LONG/SHORT/WAIT/AVOID） | ADR-008（予約） |
| market_state再定義 | ADR-009（予約） |
| Expected RR算出 | ADR-010（予約） |
| EconomicEventProvider（FOMC等） | ADR-011（予約） |
| DELTA/EXHAUSTION/ICEBERG Detector | ADR-012（予約） |
| モバイル対応（UI仕様書v1.1＋指示書_MobileApp_v1） | Phase 2 冒頭 |
| 外部公開（wss＋認証） | Phase 2（必要顕在化時） |

---

# 第4部 Phase 1 完了宣言

本仕様書の凍結をもって、**Phase 1（設計・仕様フェーズ）を完了**とする。

**Phase 1 成果物一覧**
1. デザインモック: delta_command_center_v3_3.jsx（3原則準拠・固定値ゼロ）
2. WebSocketPayload仕様_v1（Fixed・Version Policy・Backward Compatibility付）
3. UI仕様書_CommandCenter_v1（Fixed）
4. 指示書_WebApp_v3（コード全文埋め込み・テスト235目標・ADR予約番号付）
5. 本仕様書（総合・Phase 1完了文書）

**次のアクション**: Codeセッションへの指示書3点セット投入 → 実装 → web検証 → `docker-compose up` 本番動作確認。

---

# References

WebSocketPayload仕様 / UI仕様書_CommandCenter / 指示書_WebApp_v3 / SignalEngine / AIAnalysis（版数なしベース名、ADR-005準拠）

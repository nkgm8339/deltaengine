# 指示書_Heatmap_Phase1_データ層_v1
**作成日: 2026-07-29 / 発行: Claude(統括) / 対象: Claude Code**
**前提: 是正(Phase 0.5)完了。コミット`1ebdc7b`がベースライン。**

---

## 1. Phase 1 の目的

ADR-011「全量記録の原則」に準拠した orderbook 記録データ層を構築する。
ヒートマップ描画(Phase 2)は本フェーズの範囲外。**データが正しく全量残ること**だけを完成条件とする。

## 2. 要件(統括が確定済み)

| ID | 要件 |
|---|---|
| R1 | 記録内容は「REST深度スナップショット + 生`@depth`差分イベントの全量」とする。50段等のサンプリング記録は禁止 |
| R2 | Binance公式のローカル板同期手順(snapshot取得→`lastUpdateId`と差分`U`/`u`の突合→適用)に従い、gap検知時はsnapshot再取得とreset記録を行う |
| R3 | 数値はDecimal→str変換のみ。`float()`禁止(プロジェクト共通原則) |
| R4 | ADR-003準拠: 単一ループasyncio、スレッド禁止。writerはメモリバッファ+周期flush(間隔は設計提案で妥当値を提示)。fsyncはセグメントクローズ時のみ。毎フレームの同期write+flush+fsyncは禁止 |
| R5 | writer障害時はmarket dataパスを止めず、statusへエラー報告する(fail loudly、不完全レコードはappendしない) |
| R6 | 保存形式は append-only セグメント + manifest(sha256/bytes/count/seq range/close理由)。既存の未追跡prototype(persistent_depth_writer.py等)は評価の上で流用可。ただし無条件継承は禁止で、R1〜R5への適合を示すこと |
| R7 | 設定は一本化する。compose と テストで矛盾する設定(writer true/false)の解消を含む |
| R8 | テストは全てfixture駆動(録画済みデータ/synthetic)。ライブ接続を使うテストは禁止 |

## 3. 本指示書のタスク: P1-0 設計前提の提出(実装禁止)

実装に入る前に、統括が実物を検証できる材料を提出する。

### P1-0-a: 対象ファイル現物の提出

以下のファイルの**全文**を、1つのMarkdownファイル(ファイルパス見出し+コードブロック)にまとめて提出する。

1. `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py`
2. `Delta_Engine_Pro4web/webapp/main.py`(orderbook/writer関連の関数全体。該当が判断できない場合は全文)
3. `Delta_Engine_Pro4web/webapp/push_broker.py`(同上)
4. `Delta_Engine_Pro4web/tools/persistent_depth_prototype.py`
5. `Delta_Engine_Pro4web/tools/persistent_depth_recovery.py`
6. `Delta_Engine_Pro4web/tests/webapp/test_persistent_depth_writer.py`
7. `Delta_Engine_Pro4web/docker-compose.yml`
8. 現在のorderbook受信箇所(`@depth`購読〜book更新)のソース該当部(ファイルパス:行番号を明記)

### P1-0-b: sandbox編集可否の確認

是正時に「既存追跡ファイルの編集がsandboxエラーで不可」という事象が発生した。実装可否に直結するため、以下を確認して報告する。

- git追跡済みの**ソースファイル**(例: main.py)に対し、無害な編集(末尾に空行1行追加→即座に`git checkout`で戻す)が可能か
- 不可の場合はエラーメッセージ全文と、回避策の候補(あれば)

### P1-0-c: 既存prototypeのR1〜R5適合自己評価

persistent_depth_writer.py と prototype群について、R1〜R5の各項目に対し「適合/不適合/要修正」をファイル:行番号の根拠付きで表にする。主張のみで根拠がない評価は無効とする。

## 4. 報告フォーマット

```
[完了/失敗/停止] 指示書_Heatmap_Phase1_データ層_v1 (P1-0)

- P1-0-a: 提出ファイルのパス
- P1-0-b: 編集可否の結果(可/不可、エラー全文)
- P1-0-c: 適合評価表

## 逸脱事項
なければ「なし」
```

報告後は停止して指示を待つ。統括が現物を検証した後、P1-1(実装指示: アンカー付きbefore/after)を発行する。

## 5. 禁止事項

- ソースコードの実装・変更(P1-0-bの無害編集テストとその即時復元を除く)
- テスト実行、ライブ接続
- コミット、push
- Phase 2(描画)着手

# DeltaEngine 機能構造分解書

**Document ID**: ARC-003  
**Version**: v1.0  
**Status**: Working Baseline  
**最終更新**: 2026-07-23

## 1. 目的

DeltaEngineの機能を、責務・入出力・依存関係ごとに分解して把握するための正本候補である。
この文書は新しい売買ロジックを追加する仕様書ではなく、既存機能を安全に整理するための構造図である。

DeltaEngineの中心目的は、注文フローと価格反応のズレを時間軸で観測し、その後の値動きとの関係を実データで検証することである。各観測値は独立して扱い、説明できない単一スコアへ勝手に統合しない。

## 2. 分解の基本方針

1. **入力、計算、保存、表示を分離する。**
2. **5指標（CVD、Footprint、Imbalance、Absorption、Flow）を独立した観測機能として保つ。**
3. **Flow Price Responseは独立した時間窓分析として扱う。**
4. **価格・CVD・Deltaの8パターン、OI Context、Flow Eventは、それぞれ別の観測文脈として保つ。**
5. **観測事実と未検証の評価・売買判断を混同しない。**
6. **下位層から上位層への一方向依存とし、循環依存を作らない。**

## 3. 全体機能構造

```text
外部市場データ / リプレイ / MT5価格
              │
              ▼
      1. データ取得・受信
              │
              ▼
      2. 正規化・品質ガード
              │
              ├──────────────┐
              ▼              ▼
   3. 独立観測エンジン     4. 市場コンテキスト
   ├ CVD                    ├ OI Context
   ├ Footprint              ├ Order Book
   ├ Imbalance              └ 価格・スプレッド・遅延
   ├ Absorption
   └ Flow Event
              │
              ▼
      5. 時間軸・関係分析
      ├ Flow Price Response（30s〜30m）
      ├ 価格/CVD/Delta 8パターン
      └ Flow Event後の事後リターン追跡
              │
              ├──────────────┐
              ▼              ▼
      6. 保存・履歴         7. 配信・表示
      ├ DuckDB/Parquet       ├ WebSocket
      ├ 事後成績             ├ 3段チャート
      └ 監査ログ             ├ Flowイベント一覧
                             └ ガイド・詳細欄
              │
              ▼
      8. 運用監視・検証
      ├ Health / exception
      ├ ライブ・リプレイ回帰
      └ データ品質監査
```

## 4. 機能モジュール一覧

| ID | 機能 | 責務 | 主な実装位置 |
|---|---|---|---|
| F01 | データ取得・受信 | Binance REST/WebSocket、リプレイ、イベントキューから入力を受ける | `src/acquisition/` |
| F02 | 正規化・品質ガード | 約定・板・時刻・symbolを共通形式へ変換し、有限かつ正の価格・数量だけを通す | `src/normalization/` |
| F03 | 約定・出来高基盤 | 正規化済み約定を時系列処理し、足・出来高の基礎データを作る | `src/pipeline.py`, `src/database/` |
| F04 | CVD観測 | 買い/売り主導の累積デルタを独立計算する | `src/orderflow/cvd.py` |
| F05 | Footprint観測 | 価格帯ごとの約定分布を作る | `src/orderflow/footprint.py` |
| F06 | Imbalance観測 | 価格帯ごとの買い/売り偏りを検出する | `src/orderflow/imbalance.py` |
| F07 | Absorption観測 | 圧力に対して価格が進まない吸収状態を観測する | `src/orderflow/absorption.py` |
| F08 | Flow Event観測 | LARGE TRADE、SWEEP等の個別イベントを検出する | `src/orderflow/flow_detector.py` |
| F09 | Flow Price Response | 圧力継続と価格追随・停滞・逆行を30秒〜30分で分類する | `src/orderflow/flow_price_response.py` |
| F10 | 時間窓集約 | 複数時間窓を同時管理し、ライブ/リプレイの状態を揃える | `src/orderflow/multi_timeframe.py` |
| F11 | 価格/CVD/Delta 8パターン | 対象足と2本前の向き、Deltaの正負を観測評価へ変換する | `src/orderflow/divergence.py`, `webapp/` |
| F12 | OI Context | Binance OIを独立保存・時刻同期し、BUILDING等の事実だけを表示する | `src/oi_poller.py`, `src/database/` |
| F13 | Order Book | snapshotとdiffから同期済み板を再構築する | `src/orderflow/orderbook.py`, `tools/` |
| F14 | 事後追跡 | 発生後1/3/5/10分のリターンを保存し、観測結果を検証可能にする | `src/orderflow/flow_price_response.py`, `src/database/` |
| F15 | 保存・履歴 | DuckDB/Parquet、履歴API、監査データを管理する | `src/database/`, `webapp/history.py` |
| F16 | 配信 | ライブ状態・イベント・履歴をWebSocket/APIで渡す | `webapp/broker.py`, `webapp/push_broker.py` |
| F17 | 観測UI | 3段チャート、固定詳細欄、色/状態ガイド、イベントマーカーを表示する | `webapp/main.py`, `webapp/static/index.html` |
| F18 | 運用監視 | health、例外本文、停止状態、回帰確認を記録する | `src/monitor/`, `tools/` |
| F19 | 市場間観測 | Binance/HFMの価格・spread・追随遅延を比較する | `src/latency_observer/`, `tools/observe_hfm_binance.py` |

## 5. データの流れと境界

### 5.1 正常系

`取得 → 正規化 → 品質検査 → 独立観測 → 時間窓集約 → 保存/配信 → UI表示`

各段階は、前段の内部クラスへ直接依存せず、明示したデータ構造またはAPI境界を介して接続する。

### 5.2 品質異常時

- 非有限値、価格または数量が0以下の約定は正規化段階で拒否する。
- 無効な基準価格は事後追跡へ登録しない。
- 板のsnapshot欠落、diff欠落、gap、空板、交差板は集計対象にしない。
- 欠測OIは補間・0埋めせず、表示上は `—` とする。
- 失敗は黙って正常値へ置換せず、healthまたは監査ログへ残す。

## 6. 完成済み機能の保護境界

ユーザーから明示的な変更依頼がない限り、次の計算意味・操作・表示構造は変更しない。

- Flow Price Responseの分類条件、6時間窓、事後リターン。
- 3段チャート（ローソク足 / CVD+Delta / 出来高）。
- 価格・CVD・Deltaの8パターンとクリック選択、左右キー移動、固定詳細欄。
- Flow Eventマーカーの2時間メモリ、category表示切替、重複除外。
- OI Contextの独立性とBUILDING/UNWINDING/UNCHANGEDという表現。

ここでいう「細分化」は、これらを小さな責務として文書・コード上で見通しよく分けることを指し、観測ロジックを統合したり、売買シグナルへ変更したりすることを意味しない。

## 7. 今後の細分化候補

優先度の高い順に、次の単位で分離を検討する。

1. **契約モデル層**: 約定、足、Flow状態、OI、Flow Event、履歴結果の型を一か所に整理する。
2. **計算層と保存層の分離**: 各観測エンジンがDB実装へ直接依存しないようにする。
3. **ライブ経路とリプレイ経路の分離**: 共通の観測インターフェースを使い、入力だけを差し替える。
4. **配信モデルとUI描画の分離**: WebSocket payloadをUI固有の状態から独立させる。
5. **運用ツールの分離**: 市場間遅延観測、板レビュー、監査を本体パイプラインから隔離する。

## 8. 変更判断のチェックリスト

- その変更は観測事実の意味を変えないか。
- 既存のFlow Price Responseまたは3段チャートへ不要な変更を入れていないか。
- 指標を単一scoreや売買確率へ再統合していないか。
- 入力、計算、保存、表示のどの境界を変更するのか明記したか。
- ライブ、リプレイ、履歴、UIの各経路で同じ契約が保たれるか。
- 欠測・異常値を補間して、存在しない事実を作っていないか。

## 9. 関連文書

- `00_Master/PROJECT_MEMORY.md`
- `20_Architecture/SystemArchitecture_v3.0.md`
- `20_Architecture/ModuleDependency_v3.0.md`
- `30_Modules/WebApp/Specifications/UI_Spec_CommandCenter_v2.md`
- `30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`

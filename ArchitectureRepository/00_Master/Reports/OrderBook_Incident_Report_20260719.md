# ORDER BOOK 情報ゼロ インシデント報告書

**報告日**: 2026-07-19  
**対象**: DeltaEngine WebApp / Binance Futures ORDER BOOK  
**状態**: 解消済み

---

## 1. 事象

WebApp の ORDER BOOK パネルで bids / asks が完全に空となり、SPREAD は `—` のまま表示された。一方で、BTCUSDT の価格表示と Footprint は継続更新されていた。

## 2. 影響

- ORDER BOOK の買い板・売り板・累積数量が表示されない。
- bid/ask がないため SPREAD を算出できない。
- 価格、取引、Footprint、他の WebSocket 表示には影響しない。

## 3. 原因

Binance Futures REST API の `/fapi/v1/depth` 実レスポンスは `lastUpdateId`、`bids`、`asks` を返すが、イベント時刻フィールド `E` を返さない。

初期板スナップショットの変換処理が `raw_rest["E"]` を必須参照していたため `KeyError` が発生した。例外は起動継続のためログ警告として処理され、初期スナップショットは未適用となった。

その結果、状態を確立できない `OrderBookStateManager` が以後の WebSocket depth 差分を適用できず、CANDLE payload の `orderbook.bids` / `orderbook.asks` が空配列のままとなった。

### 見逃し要因

既存テストの REST 擬似レスポンスには実 API にはない `E` / `T` が含まれていた。このため、テストでは変換処理が成功し、実レスポンスとの契約差異を検出できなかった。

## 4. 修正

`src/acquisition/binance_rest.py` の `rest_to_depth_event()` を変更した。

- `E` があれば従来どおり利用する。
- `E` がなければ `T` を利用する。
- 両方ない実 REST 応答では、ローカル受信時刻（ミリ秒）を canonical event_time のメタデータとして設定する。

受信時刻は板の sequence ordering には用いず、`lastUpdateId` と WebSocket update ID による既存同期規則は不変である。

`tests/acquisition/test_binance_rest.py` に、`E` / `T` を持たない実 Binance 形式のレスポンスから snapshot を作成し、bids / asks が初期化される回帰テストを追加した。

## 5. 検証結果

| 検証 | 結果 |
|---|---|
| 実 Binance Futures `/fapi/v1/depth` 取得 | 成功 |
| snapshot の normalizer 受理 | 成功 |
| `OrderBookStateManager` 初期化 | 成功 |
| 実測板件数 | bids=20 / asks=20 |
| 全回帰テスト | 341 passed |
| WebApp 再ビルド・再起動後の ORDER BOOK | 正常表示 |

## 6. 実行環境上の補足

修正後も一時的に空表示が継続した。調査時点では Docker Desktop が停止しており、`localhost:8080` に待受プロセスもなかったため、修正前コンテナ／古い表示状態が参照されていた。

`DeltaEngine.bat stop` の後に `DeltaEngine.bat` を実行して Docker image を再ビルド・再起動した結果、ORDER BOOK は正常表示へ復帰した。

## 7. 再発防止

1. 外部 API のテスト fixture は実レスポンスの必須・任意フィールドを忠実に再現する。
2. REST snapshot に event timestamp がないケースを回帰テストとして維持する。
3. データ取得・変換・状態初期化の失敗は、`/api/stats` の snapshot/diff カウンタで確認可能にする。
4. 実装変更後は、Docker image を再ビルドしてから画面確認を行う。

## 8. 結論

本件は夜間流動性や WebSocket 全体停止ではなく、REST 初期スナップショット変換の実 API 仕様差異が原因であった。コード修正、実 API 検証、回帰テスト追加、再起動後の画面復旧確認まで完了している。

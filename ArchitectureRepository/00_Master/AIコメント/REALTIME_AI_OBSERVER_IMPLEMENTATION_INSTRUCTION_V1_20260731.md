# REALTIME AI OBSERVER IMPLEMENTATION INSTRUCTION V1

- 文書名: リアルタイムAI観測官 実装指示書V1
- 作成日: 2026-07-31
- 配置: `ArchitectureRepository/00_Master/実装指示書`
- 文書状態: IMPLEMENTATION INSTRUCTION DRAFT
- 現在の承認範囲: 指示書作成のみ
- 未承認: source実装、外部AI接続、API課金、runtime有効化、production配備、自動発注

---

## 0. この指示書の目的

DeltaEngineが確認した市場事実を、実戦中の利用者が短時間で理解できる日本語へ変換し、
固定された画面領域へリアルタイム表示する「AI観測官」を実装する。

AI観測官は売買シグナルを作らない。
現在進行中のSituationについて、次の四点を説明する。

1. 観測できた事実
2. 考えられるSituation候補
3. まだ確認できていないこと
4. 次に確認すべき成立条件と否定条件

AIは市場数値を計算しない。
Price、CVD、Delta、Flow Response、OI、Footprint、Heatmap、重要価格位置の判定は、
既存または別工程で承認された決定論的な観測器が行う。

---

## 1. 絶対原則

- AIへ生のtick列や画面画像だけを渡して自由判断させない
- AIへ渡すのは、source時刻とevidence IDを持つ構造化済み観測事実だけ
- AIは入力にない数値、event、方向、因果関係を追加しない
- 事実、解釈候補、未確認、次の条件を混ぜない
- AIコメントから直接注文しない
- AIコメントを既存Hook、Predicate、Strategy stateの成立証拠にしない
- AI timeoutまたは障害時も市場pipelineを止めない
- AI障害時は決定論的な定型文へ戻す
- stale、gap、clock skew中は新しい市場解釈を生成しない
- 同じSituationでコメントを連打しない
- 完成済みのFlow Response、3段チャート、CVD、Delta、OI、Footprintの計算を変更しない

---

## 2. 対象範囲

### 2.1 入力対象

- Data Health
- 現在価格
- Order Book Heatmapから生成された構造化Liquidity Event
- Session VWAPなどの重要価格位置
- Flow Response
- PRICE／CVD／Delta
- OI
- Footprint要約
- Time & Sales要約
- Hook／Predicate／Situationの状態遷移

### 2.2 出力対象

- 現在の観測コメント
- Situation名
- コメント対象時間軸
- コメント生成時刻
- 使用したevidence
- 成立条件
- 否定条件
- データ鮮度
- コメント履歴

### 2.3 対象外

- 自動注文
- 注文サイズ決定
- TP／SL決定
- 勝率または期待値の創作
- BUY／SELL確率
- 不透明な総合score
- AIによるCVD、Delta、VWAP、Heatmap計算
- AIによる欠測補完
- AI出力を正本市場データとして保存すること

---

## 3. 全体構造

```text
Market Sources
    ↓
Existing Deterministic Observers
    ↓
Hook／Predicate／Situation Engine
    ↓
Observation Snapshot Builder
    ↓
Comment Policy
    ├─ Deterministic Template Generator
    └─ AI Comment Adapter
             ↓
        Output Validator
             ↓
        WebSocket Publisher
             ↓
        Fixed AI Observer Panel
             ↓
        Audit Journal
```

AIは市場pipelineの同期処理経路へ入れない。
コメント生成はbounded queueを持つ非同期sidecarまたは独立workerとする。

---

## 4. Observation Snapshot

AIへ渡す唯一の市場入力として、`ObservationSnapshot`を定義する。

最低限必要なfield:

```json
{
  "schema_version": "1.0",
  "snapshot_id": "opaque-id",
  "symbol": "BTCUSDT",
  "market_time_utc": "2026-07-30T19:20:25.123Z",
  "display_time_jst": "2026-07-31T04:20:25.123+09:00",
  "generated_at_utc": "2026-07-30T19:20:25.150Z",
  "data_health": {
    "overall": "FRESH",
    "trade": "FRESH",
    "analysis": "FRESH",
    "book": "FRESH",
    "oi": "FRESH",
    "gaps": []
  },
  "horizons": {
    "candle": "1m",
    "flow_primary": "5m",
    "flow_onset": "1m",
    "flow_background": "15m",
    "cvd_lookback_bars": 20
  },
  "location": [],
  "liquidity": [],
  "flow_response": {},
  "price_cvd_delta": {},
  "oi_context": {},
  "footprint_summary": {},
  "tape_summary": {},
  "situation": {},
  "evidence": []
}
```

### 4.1 Snapshot規則

- snapshot生成境界は最後に受理したnormalized source event時刻
- future eventを含めない
- stale sourceの値を現在値として含めない
- 欠測を0で埋めない
- `NONE`、`MISSING`、`STALE`、`UNCLEAR`を区別する
- display用丸め値と判定用正本値を混同しない
- evidenceはsource event ID、時刻、stream IDを持つ
- AIへ不要な個人情報、秘密情報、API keyを渡さない

---

## 5. Data Health Gate

次のいずれかが発生した場合、新しい市場解釈コメントを停止する。

- required source stale
- book gap
- stream ID不整合
- source timestamp逆転
- clock skew許容外
- ObservationSnapshot不完全
- schema validation失敗

停止中に表示する定型文:

```text
市場コメント停止中
必要データが正常ではないため、新しい状況解釈を生成していません。
対象: BOOK STALE
最終正常時刻: 04:20:25 JST
```

復旧後は必要な観測窓が再完成するまで市場解釈を再開しない。

---

## 6. コメント発行Policy

AIを毎tick、毎約定、毎画面更新で呼ばない。

### 6.1 新規コメントを許可するevent

- 新しいSituationがarmed
- Situation stateがadvance
- Situationがresolved
- Situationがinvalidated
- direction candidateが反転
- 重要価格levelへ接近または接触
- levelを突破
- level突破後にacceptまたはreject
- liquidityがpersist、reload、pull、consumeへ遷移
- FlowがEFFECTIVE、STALLED、TRAPPEDへ遷移
- divergenceが開始、継続、解消
- data healthが悪化
- data healthが復旧
- 規定時間変化がなく、状況要約の更新が必要

### 6.2 同一Situationの更新

同じSituation IDでは新しいコメントを積み続けない。

- 現在コメントを更新
- state履歴はjournalへ追加
- UIでは最新一件を主表示
- 過去コメントは折り畳み履歴

### 6.3 cooldown

- cooldownはSituation単位
- data health悪化、order connection異常、direction reversalはcooldown対象外
- thresholdは設定fileで管理
- 初期値をproduction確定値として扱わない

---

## 7. コメント出力形式

AI出力は自由文章一個ではなく、次のschemaへ固定する。

```json
{
  "observation": "確認済み事実",
  "interpretation": "Situation候補",
  "unknowns": "未確認事項",
  "watch_next": "次の成立条件",
  "invalidation": "否定条件",
  "severity": "INFO",
  "evidence_ids": ["event-1", "event-2"]
}
```

### 7.1 画面表示

```text
04:20:25 JST　DATA FRESH
FAILED BREAKOUT候補　5m観測

観測
前日高値付近で買い成行が継続しています。
ask側の流動性は約定後も補充され、価格進行は小さい状態です。

解釈候補
買い吸収または上抜け失敗の準備状態です。
まだ下落確定ではありません。

未確認
5分BUY STALLEDの継続と、前日高値内側への回帰は未確認です。

次に見る条件
askを消費して高値上で維持すればBreakout Acceptance候補です。

否定条件
前日高値の内側へ戻り、売りが価格を下へ進めれば上抜け失敗候補が強まります。
```

### 7.2 禁止表現

- 必ず上がる
- 必ず下がる
- 勝率○％
- 今すぐ買え
- 今すぐ売れ
- AIが入力から確認できない主体断定
- 未検証の因果関係

---

## 8. 定型文Generator

AI接続より先に、同じObservationSnapshotから決定論的な定型文を生成する。

例:

```text
BUY_STALLED
+ ASK_LIQUIDITY_RELOADING
+ PRICE_FAILED_TO_PROGRESS
=
買い圧力は継続していますが、価格進行は止まり、
ask側の流動性が補充されています。
```

定型文Generatorの役割:

- source事実の接続が正しいか検証
- AIなしでも最低限の運用コメントを提供
- AI timeout時のfallback
- Replayの期待値比較
- AIが意味を変えていないか比較

---

## 9. AI Comment Adapter

### 9.1 入力

- schema validation済みObservationSnapshot
- 許可されたSituation用語
- 出力JSON schema
- 禁止事項
- 最大文字数

### 9.2 出力

- JSON schemaへ完全一致
- 日本語
- 簡潔
- 事実と解釈を分離
- evidence IDを維持

### 9.3 AIに許可すること

- 確認済み事実を読みやすい順序へ文章化
- Situation候補の平易な説明
- 未確認事項の明示
- 次の成立条件、否定条件の文章化

### 9.4 AIに許可しないこと

- 新しい数値計算
- 入力外の市場情報追加
- 過去会話から現在市場を補完
- コメント履歴を現在evidenceとして使用
- sourceの欠測補完
- 発注判断

---

## 10. Output Validator

AI出力を画面へ送る前に機械検証する。

検証項目:

- JSON schema一致
- 必須field存在
- evidence IDが入力集合内
- 未入力symbolを含まない
- 未入力価格を含まない
- 禁止表現を含まない
- 文字数上限
- snapshot ID一致
- stale snapshotではない
- 現在Situation ID一致

失敗時:

- AI出力を破棄
- 定型文へfallback
- validation failureをjournalへ記録
- 市場pipelineへ例外を伝播させない

---

## 11. UI仕様

### 11.1 配置

- 常設固定パネル
- データ有無でパネルを出し入れしない
- toastを主表示にしない
- 現在コメント一件を優先
- 履歴はパネル内部scroll
- 既存チャート、Footprint、Heatmapを覆わない

### 11.2 常設項目

- `AI OBSERVER`
- status: `LIVE / TEMPLATE / AI / STALE / ERROR`
- market time
- comment age
- Situation名
- 対象時間軸
- data health
- 観測
- 解釈候補
- 未確認
- 次に見る条件
- 否定条件

### 11.3 色

- 観測事実: 白
- 未確認: 黄
- data stale／error: 赤
- Situation候補: 既存UIと衝突しない中性色
- BUY／SELL色だけで意味を伝えない

---

## 12. WebSocket契約

additive messageとして`AI_OBSERVER_COMMENT`を追加する。

最低限のfield:

```json
{
  "type": "AI_OBSERVER_COMMENT",
  "schema_version": "1.0",
  "comment_id": "opaque-id",
  "snapshot_id": "opaque-id",
  "situation_id": "opaque-id",
  "market_time_utc": "2026-07-30T19:20:25.123Z",
  "generated_at_utc": "2026-07-30T19:20:25.500Z",
  "mode": "TEMPLATE",
  "status": "VALID",
  "content": {},
  "evidence_ids": []
}
```

既存messageを変更または置換しない。

---

## 13. Journal

全コメントについて次を保存する。

- comment ID
- snapshot ID
- Situation ID
- market time
- generated time
- mode
- model identifier
- prompt version
- schema version
- input hash
- evidence IDs
- output
- validation result
- fallback reason
- generation latency
- token usage
- estimated cost

API key、認証token、秘密情報は保存しない。

---

## 14. Replay

Replayでは現在時刻や未来データを混ぜない。

検証対象:

- comment時点までのevidenceだけを使用
- 同一Replay入力でTemplate出力が決定論的
- AI outputが入力事実を変更しない
- state advance順序
- stale／gap時の停止
- recovery後の再開
- cooldown
- duplicate抑制
- Situation invalidation

保存済みコメントをReplayの市場入力として使用しない。

---

## 15. 性能と費用

AI呼出は市場data pathから分離する。

必須制限:

- bounded input queue
- queue overflow policy
- generation timeout
- retry上限
- 同時実行数
- Situation単位cooldown
- 分間呼出上限
- 日次token上限
- 日次費用上限
- 最大入力文字数
- 最大出力文字数

queue overflow時は古い中間更新を破棄できるが、
data health異常、Situation resolution、invalidationを優先する。

---

## 16. Security

- API keyをrepositoryへ保存しない
- browserへAPI keyを送らない
- server側environment variableまたは承認済みsecret storeを使用
- promptへ不要なlocal path、口座情報、個人情報を含めない
- AI provider障害をmarket pipeline障害へ波及させない
- external AI接続には別途明示承認を必要とする

---

## 17. 実装Phase

### GO-A0: Baseline Audit

- 現在のHook、Predicate、Situation、WebSocket、UI構造を監査
- 変更対象fileを確定
- restore pointを作成
- test baselineを保存

### GO-A1: Observation Snapshot

- schema
- builder
- freshness
- evidence
- validation
- journal

AI接続なし。

### GO-A2: Deterministic Template

- 発行Policy
- 定型文
- duplicate抑制
- cooldown
- fallback

AI接続なし。

### GO-A3: WebSocketとUI

- additive message
- 固定AI Observer panel
- 履歴
- status
- stale表示

AI接続なし。

### GO-A4: AI Adapter Shadow Mode

- 外部AI接続
- output validation
- Template比較
- 画面ではTemplateを正本表示
- AI出力はshadow journalだけ

外部接続と費用の明示承認が必要。

### GO-A5: Replay Evaluation

- hallucination監査
- 事実一致率
- unknown明示率
- duplicate率
- latency
- cost
- failure fallback

### GO-A6: AI Display Activation

- validation済みAIコメントを表示
- Template fallback維持
- 注文接続なし

### GO-A7: Production Observation

- 長時間運転
- disconnect
- restart
- provider outage
- queue overflow
- daily cost limit
- journal完全性

---

## 18. Test Matrix

### Unit

- Snapshot schema
- freshness
- comment policy
- cooldown
- duplicate
- Template
- output validator

### Integration

- HookからSnapshot
- SnapshotからTemplate
- AI timeoutからfallback
- WebSocket
- UI更新
- journal

### Negative

- stale data
- book gap
- future timestamp
- evidence ID捏造
- 入力外価格
- 禁止表現
- malformed JSON
- provider timeout
- provider rate limit
- queue overflow

### Replay

- 同一入力の再現
- 未来情報混入なし
- Situation順序
- invalidation
- recovery

### Browser

- 固定位置
- panel重なりなし
- 横overflowなし
- コメント更新時のlayout shiftなし
- stale時表示
- AI／Template mode表示

---

## 19. 完成条件

次をすべて満たしたときだけ、AI観測官を完成扱いにできる。

1. AIなしのTemplate modeで正しい観測コメントが出る
2. stale、gap、clock skew時に市場解釈を停止する
3. AIが入力にない事実を追加した場合、validatorが拒否する
4. AI timeout時にTemplateへ戻る
5. コメントが市場pipelineを遅延または停止させない
6. 同じSituationでコメントを連打しない
7. 表示コメントからevidenceを追跡できる
8. Replayで未来情報を使用しない
9. model、prompt、input、output、費用を監査できる
10. 自動注文経路を持たない

---

## 20. Rollback

AI観測官は独立feature flagで無効化できること。

無効化時:

- 既存市場pipelineは継続
- 既存WebSocketは継続
- 既存UIは継続
- Flow Response、CVD、Delta、OI、Footprint、Heatmapは継続
- AI queueを安全に停止
- 未送信コメントを破棄
- journalをflush

---

## 21. 次の承認境界

この指示書作成はsource実装の承認を意味しない。

次に必要な明示承認は`GO-A0`である。

`GO-A0`ではbaseline監査だけを行い、
Observation Snapshot、Template、UI、AI接続、外部API利用、production配備はまだ行わない。

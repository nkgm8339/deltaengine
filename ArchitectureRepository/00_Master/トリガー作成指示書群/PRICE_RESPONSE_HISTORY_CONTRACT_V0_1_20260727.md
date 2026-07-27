# Price Response History Contract V0.1

作成日: 2026-07-27 JST  
状態: **お館様のA→D→E順次解決指示に基づくP3-C A契約**

## 1. 目的

Strategy Engineへ、source-time順の実価格履歴と、Condition Dictionary G09の
threshold-free price progressを供給する。完成済みFlow Price Response detectorの
分類・window・画面表示は変更しない。

## 2. Authoritative source

- 価格sampleはnormalizerが受理したnormalized tradeの`event_time`と`price`を正本とする。
- `FlowResponseSnapshot`は30秒以上の観測分類結果であり、100ms／1s／5sのraw価格履歴を
  置き換えない。
- symbol不一致、非有限価格、非正値価格は受理しない。
- source時刻逆転sampleは履歴へ追加しない。Replay／Liveとも同じProducerを使う。

## 3. 時刻・履歴

- sample timestampはUTC epoch nanoseconds。float timestamp変換は禁止する。
- snapshotの評価境界は、そのsnapshot生成を起こした最後の受理normalized event時刻とする。
  candleのbar start時刻を評価境界に使わない。
- 通常bar closeでは現在処理中tradeの`event_time`、finalizeでは最後の受理trade時刻を使う。
- 300秒履歴と、300秒境界直前のas-of sample 1件を保持する。
- 同一source timestampの複数tradeは受理順を維持し、as-of値は最後のtrade価格とする。
- snapshot評価時刻より未来のsampleはMarketStateSnapshotへ含めない。

## 4. G09 progress算式

対象windowはCondition Dictionary既存keyに一致する100ms、1s、5s、30s。

```text
base_price   = 評価時刻 - window 以下で最後に受理したtrade価格
latest_price = 評価時刻以下で最後に受理したtrade価格
delta_ticks  = (latest_price - base_price) / tick_size

upward_progress_ticks_window   = max(delta_ticks, 0)
downward_progress_ticks_window = max(-delta_ticks, 0)
```

- 単位はDecimal ticks。
- baselineとlatestが存在し、正のtick sizeがある場合だけ両方向keyを出力する。
- threshold、売買方向、composite FLAGはここで決めない。
- source gap／staleの最終可否はG01 quality conditionで別途gateする。

## 5. 5分価格履歴

300秒price sampleは既存`price_oi_joint_state_5m`のas-of価格計算へ使用する。
G09に存在しない新しい5m progress keyは追加しない。新Condition IDの無断作成を避ける。

## 6. Fail-closed

- window境界以前のbase sampleがない: key omit
- tick size欠測／非正: key omitまたは既存validationで拒否
- source時刻欠測: Producer観測を拒否
- future sample: snapshotから除外
- 不完全材料を0として補完しない

## 7. 非対象

G16 composite、CalibrationBook threshold、runtime有効化、発注権限、raw data、
完成済みFlow Price Response／3段チャート／8パターン／OI／UIは変更しない。

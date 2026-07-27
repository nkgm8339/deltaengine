# Engine Time / Source Time Contract V0.1

作成日: 2026-07-27 JST
状態: 実装反映済み（P3-C契約決定）

## 1. 目的

UTC由来時刻とエンジン内経過時間を同一の`engine_time_ns`へ混在させない。

## 2. 正本契約

- `MarketStateSnapshot.engine_time_ns`: エンジン時計。単調非減少のナノ秒。Replayは最初の受理イベントを原点としたsource時刻の経過量、Liveは`time.monotonic_ns()`。UTC epoch値を格納しない。
- `MarketStateSnapshot.source_time_ns`: UTC epochナノ秒。normalized eventまたはbarの`datetime`を整数演算で変換した値。欠測時は`None`。
- Strategy snapshotの評価境界は、そのsnapshot生成を起こした最後の受理normalized event時刻とする。closed candleの`bar_time`がbar開始時刻の場合、それを現在評価時刻へ流用しない。finalizeは最後の受理event時刻を使う。
- `TimeSample.engine_time_ns`: 既存schema互換の名称を維持するが、producer生成値はsource epochナノ秒。Adapterはsnapshotの`source_time_ns`を窓基準に使う。将来改名する。
- `IngestionAdapter`: `source_time_ns`が存在する場合はそれをCVD/OI/price窓の基準に使い、欠測時のみ旧fixture互換で`engine_time_ns`へフォールバックする。

## 3. 禁止事項

UTC epochを`engine_time_ns`へ格納しない。`time.time()`やfloat変換による時刻生成を行わない。engine/sourceを暗黙変換しない。

## 4. 検証不変条件

1. Replayの最初のbar以前のengine時刻は0以上。
2. 同一Replay内のengine時刻はsource時刻順に非減少。
3. source時刻はUTC epochとしてwindow境界を再現。
4. snapshotのsource時刻より未来の観測は条件へ混入しない。
5. 欠測source時刻はfail-closedまたは旧fixture fallbackに限定。

## 5. 変更根拠

P2配線でbarのUTC epochを`engine_time_ns`へ格納していたため、market_state既存契約（monotonic）と不一致だった。本仕様で二時計契約を固定し、producer/pipeline/adapterを揃えた。runtime有効化・発注権限・raw dataは変更しない。

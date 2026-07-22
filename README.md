# 注文フロー分析プラットフォーム - 実装

Phase5（CVD パス）の実装です。構成は
`../ArchitectureRepository/60_Implementation/DirectoryStructure_v3.0.md` に従います。

## Canonical specification

すべての仕様は、隣接する `../ArchitectureRepository/` ディレクトリにあります。
そこが唯一の正本です。`Delta_Engine_Pro4web/docs/` は意図的に置いていません。
編集可能な複製を作らないためです。Architecture Repository に書かれていない
動作は実装しないでください。

## Layout

```text
Delta_Engine_Pro4web/
├── config/     # YAML configuration
├── data/       # generated data (parquet/, duckdb/) — not committed
├── logs/
├── src/        # source (mirrors module boundaries)
│   ├── acquisition/    # M4 (skeleton only)
│   ├── normalization/  # M3 (skeleton only)
│   ├── orderflow/      # M2 (skeleton only)
│   ├── signal/         # out of scope (skeleton only)
│   ├── ai/             # out of scope (skeleton only)
│   ├── database/       # M5 (skeleton only)
│   ├── mt5/            # out of scope (skeleton only)
│   └── config.py       # M1 — config loading + startup validation
├── tests/      # mirrors src/
├── tools/      # operational scripts
└── README.md
```

## Requirements

Python 3.11 以上。依存関係のインストール:

```
pip install -r requirements.txt
```

## Board Review

ここでいう「録画」は画面動画ではなく、取引所から届いた約定・板更新・板Snapshotを
時刻順に保存したJSON Lines市場データです。

2026-07-22の監査で、旧
`data/recordings/btcusdt_session1_clean_strong.jsonl` は2,939行すべてが
`depthUpdate`差分で、初期`depthSnapshot`を含まないことが確認されました。
さらに数量0（板levelの削除命令）も除去済みです。この録画と、そこから作成した
`spread_jumps.jsonl`／`spread_jumps.csv`は研究へ使用しません。

基本手順:

1. `depthSnapshot`を含む同期済み録画だけを入力する。
2. snapshotと連続diffを`OrderBookStateManager`へ適用する。
3. 同期済み状態からbest bid／askと上位5段を作る。
4. gap後は新しいsnapshotまで集計しない。
5. 再構築したspreadと`spread_ma5`から候補を抽出する。

To refresh the anomaly exports, run:

```
python -m tools.update_spread_jumps --source data/recordings/btcusdt_board_synced.jsonl
```

Windows では `tools/run_update_spread_jumps.ps1` が、プロジェクトルートから同じコマンドを実行します。
旧出力を含む隔離理由は
`data/recordings/SPREAD_JUMPS_QUARANTINED.md`に保存しています。
新しい録画を作る`tools.live_capture`は通常WebAppと同じ保存DBを使うため、
通常WebAppを停止した管理時間帯だけに実行します。

読み方:

- `best_ask` が急に上へ飛んでいれば、売り板が薄くなった可能性があります。
- `best_bid` が急に下へ落ちていれば、買い板が弱くなった可能性があります。
- `spread` と `spread_jump` の両方が大きい行を、異常候補として残します。

## M1 — Configuration

設定ファイルを検証します。無効な設定なら起動時に失敗します。
これは実装指示と ErrorCodes_v3.1 E1001/E1002 に従っています。

```
python tools/check_config.py config/config.yaml
```

テスト実行:

```
pytest
```

## Implementation status

| M  | Scope                                   | Status       |
|----|-----------------------------------------|--------------|
| M1 | Skeleton + Config load/validation (v3.1)| done         |
| M2 | CVD calculator (`src/orderflow/`)       | done         |
| M3 | DataNormalizer (`src/normalization/`)   | done         |
| M4 | WebSocket + DataReceiver                | done*        |
| M5 | Storage (`src/database/`)               | done         |
| M6 | Deterministic replay integration        | done         |

\* M4: lifecycle/reconnect/queue/recording/replay implemented and tested against
an injected transport. The concrete `websockets`-based network adapter is the
remaining runtime piece (no network in unit tests).

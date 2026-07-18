# Order Flow Analysis Platform — Implementation

Phase5 (CVD path) implementation. Layout per
`../ArchitectureRepository/60_Implementation/DirectoryStructure_v3.0.md`.

## Canonical specification

All specifications live in the sibling `../ArchitectureRepository/` directory.
It is the single source of truth; `Delta_Engine_Pro4web/docs/` is intentionally absent so
there is no editable duplicate. Do not implement behavior that is not described
in the Architecture Repository.

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

Python 3.11+. Install dependencies:

```
pip install -r requirements.txt
```

## M1 — Configuration

Validate a configuration file (fails startup on invalid config, per the
implementation instruction and ErrorCodes_v3.1 E1001/E1002):

```
python tools/check_config.py config/config.yaml
```

Run tests:

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

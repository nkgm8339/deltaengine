# Documentation Index

`ArchitectureRepository` is the canonical home for DeltaEngine documentation.
Use the following locations to find materials added outside the original numbered
repository structure.

| Location | Contents |
| --- | --- |
| `00_Master/Instructions/` | Executable work instructions and implementation directives. |
| `00_Master/Handover/` | Handover packages and next-session implementation notes. |
| `00_Master/Guides/` | User and operational guides. |
| `00_Master/Reports/` | Analysis reports. |
| `00_Master/Archive/Packages/` | Historical documentation ZIP packages. |
| `00_Master/Archive/Duplicates/` | Retained duplicate source documents; not canonical. |
| `30_Modules/WebApp/Specifications/` | WebApp specifications, including the payload and UI contracts. |
| `30_Modules/WebApp/Design/` | WebApp design references, mockups, and design-change materials. |

## DeltaEngine座学

学習資料は `00_Master/座学/MD/座学_00_全10講ガイド.md` を入口とする。
Markdown版は`00_Master/座学/MD/`、PDF版は`00_Master/座学/`に配置している。

| 範囲 | 内容 |
| --- | --- |
| 第1〜3講 | 注文フロー、価格反応、黄色・紫、価格/CVD/Deltaの8パターン |
| 第4〜7講 | Footprint、Imbalance、Absorption、板・スプレッド |
| 第8〜10講 | 6時間窓と`5m → 1m → 15m`運用、事後成績、実戦観察ドリル |

## Canonical WebApp document set

The WebApp implementation set is organized as follows:

- `Specifications/UI_Spec_CommandCenter_v2.md` (current UI specification)
- `Specifications/WebSocketPayload_Spec_v1.md`
- `Specifications/UI_Spec_CommandCenter_v1.md` (historical; superseded by v2)
- `Specifications/仕様書_DeltaEngine_WebApp_総合_v1.md`
- `00_Master/Instructions/Shijisho_WebApp_v3.md`

For current UI behavior, `UI_Spec_CommandCenter_v2.md` takes precedence over the
historical v1 UI, aggregate specification, and implementation instruction.

`00_Master/Archive/Duplicates/Sogo_Spec_DeltaEngine_WebApp_v1.md` is byte-for-byte
identical to `Specifications/仕様書_DeltaEngine_WebApp_総合_v1.md` and is retained
only for provenance.

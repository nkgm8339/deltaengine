# Hook Detector / Trigger Observe — Stage 2C 着手承認

承認日: 2026-07-26
承認者: お館様
起草: Claude (web)

---

## 1. Stage 2B完了の確認

以下を検証し、Stage 2Bの完了を認める。

| 項目 | 状態 |
|---|---|
| crash-safe journal（XZ独立frame、fsync、FRAME_COMMIT） | 完了。boot前session 6,406 frame / 126,707 record全件回収、hash/sequence/件数一致、uncommitted tail 0 bytes |
| coverage/deadline延長台帳（append-only、fsync） | 完了。停止173秒を1回記録・延長処理済み |
| Windows自動復旧（Scheduled Task） | 完了。二度目の実機再起動で人手ゼロ復旧、LastTaskResult 0、GREEN確認 |
| A/C/D/E/F/G detector実装（56 Hook候補） | 完了。synthetic 14 passed、全体回帰516 passed |
| 全threshold UNCALIBRATED維持 | 維持。hook_thresholds.yaml: default_status UNCALIBRATED、thresholds空 |
| playbooks.yaml OBSERVE / execution_enabled false | 維持 |
| 既存UI・既存パイプライン無変更 | 維持。UI SHA-256一致 |
| C:空き容量 | compact後約18.38GB。元の6.77GBから大幅改善 |
| 回帰テスト | 516 passed in 61.10s |
| commit | 394cd83（push未実施） |

引き継ぎ文書§5の未回答3項目:

1. **ディスク容量見積もり**: 直接の数値見積もりは未提示だが、C:空き18.38GBへの改善により実質解決。DOM 72時間完了時に消費量を再確認する運用条件を付す（後述§4）
2. **較正ゲート定義**: 累計valid coverage、分布範囲、Hook別標本数の三重条件と明記済み
3. **停止時の延長ルール**: confirmed invalid intervalのみ重複なし延長、DOM上限72時間、liquidation上限7日と明記済み

## 2. Stage 2Cの定義

Stage 2Cは「収録完了→較正→observe発火解禁」の工程である。

### 2C-1: 収録完了判定

収録期限到達後、較正ゲート三重条件を判定する。

| stream | effective deadline | 較正ゲート |
|---|---|---|
| full (DOM + aggTrade) | 2026-07-29 13:34:16 JST | 累計valid coverage 72時間以上、分布範囲・Hook別標本数が較正に足る水準 |
| liquidation | 2026-08-09 13:34:16 JST | 累計valid coverage 14日以上、標本gate 4,000件以上かつside別1,000件以上 |

- liquidation標本gateに未達の場合: 未較正のまま報告し、該当Hook（E01-E06、C09）はUNCALIBRATEDを維持。他Hookの較正は先行可能
- full stream期限到達がliquidationより先であるため、2C-1はDOM較正とliquidation較正の二段階となる

### 2C-2: threshold較正

収録データの実測分布から、パーセンタイルベースでthresholdを初期化する。

- 較正対象: 標本数gateを通過した全Hook
- 較正方法: 実測分布のパーセンタイル（具体的なパーセンタイル値は較正時に提案）
- 出力: hook_thresholds.yamlへの書き込み、較正根拠レポート
- 較正済みHookのstatusをUNCALIBRATEDからCALIBRATEDへ変更

### 2C-3: リプレイ発火頻度検証

較正済みthresholdを使い、収録データに対してリプレイを実行し、発火頻度を確認する。

- 過剰発火（ノイズ）、過少発火（感度不足）がないことを検証
- 問題があればthresholdを調整し再リプレイ
- 発火頻度レポートをお館様に提出し、承認を得る

### 2C-4: observe発火解禁

お館様の承認後、較正済みHookのHookEvent発火を解禁する。

- playbooks.yaml: OBSERVE維持（変更なし）
- execution_enabled: false維持（変更なし）
- HookEvent発火: 較正済みHookのみ解禁
- UNCALIBRATED Hookは発火禁止を維持

## 3. Stage 2Cの禁止事項

- Playbook選抜、check移行、LIVE注文はStage 2Cのスコープ外
- execution_enabledをtrueにしない
- 既存パイプライン（Flow Price Response、3段チャート、8パターン）の計算・表示を変更しない
- 較正ゲート未達のHookに対してthresholdを手動設定しない
- 収録データの削除・修正・truncateを行わない

## 4. 運用条件

- **DOM収録72時間完了時点（2026-07-29 13:34 JST頃）に、C:ドライブの実消費量を報告する。** 残りliquidation収録期間（約11日）に対して空き容量が安全であることを確認する。安全基準: 残り空き8GB以上
- 各2C工程の完了時にお館様へ報告し、次工程への進行承認を得る
- 2C-1（収録完了判定）はfull streamとliquidation streamで時期が異なるため、それぞれ個別に報告する

## 5. 承認

Stage 2C着手を承認する。Stage 2C-1は収録期限到達を待つ待機フェーズであり、即時の実装作業は発生しない。

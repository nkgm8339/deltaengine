# v3.6.19 — 2026-07-25

## Changed

- 3段チャート上の固定観測領域を94px、26px／38px／26pxへ固定した。
- Flow Response 6窓を常時6列・カード高38pxとし、1段目11px、2段目14pxへ確定した。
- 2段目を`PR <pressure> · P <price> · V <relative volume>`へ短縮した。
- 3段チャート本体はchartwrap 426px、SVG 422pxを維持した。

## Fixed

- LivePipeline再起動時にFlow Responseの1800秒Volume baselineが失われ、
  30分間`V —`となる問題を修正した。
- 起動時に保存済み直近1800秒取引をDetectorだけへ時系列順で読み込み、
  過去snapshotを再配信・再保存せず既存`relative_volume`計算を復元する。
- 保存履歴が無い初回起動または復元失敗時はライブ蓄積へ安全にフォールバックする。

## Verification

- 全体回帰408 passed。
- 05M再起動直後の実Edgeで30s `V ×8.1`、3m `V ×4.1`、30m `V ×1.0`を確認した。
- 6カード38px、1段目11px、2段目14px、横overflowなし、browser errorなしを確認した。

---

# v3.6.18 — 2026-07-22

## Added

- TOP BARのBinance OI表示横へ円形の「？」ボタンを追加した。
- クリックすると、PRICE・CVD・Delta・OIを組み合わせた8ケースの評価表を
  中央ダイアログで確認できるようにした。
- ダイアログは閉じるボタン、背景クリック、Escapeキーで閉じられる。

## Interpretation boundary

- 今回定義した表は、PRICEとCVDが同方向の8ケースだけを収録する。
- PRICEとCVDは対象足と2本前を比較し、Deltaは対象足の正負、
  OIは対象足のOPENからCLOSEへの変化として読む。
- 表はユーザーが定義した日本語の観測評価をそのまま確認するための凡例であり、
  売買シグナル、確率、score、自動判定への新規入力ではない。
- 既存のPrice・CVD・Delta 8パターン、OI Context、Flow Price Response、
  3段チャートの計算と意味は変更していない。

## Tests

- WebApp対象テスト24 passed。
- 全体回帰340 passed in 13.60s。
- Edge実ブラウザでTOP BARの「？」、8行の表、日本語表示、
  Escapeキーによる閉鎖を確認した。

## Commit

- Delta_Engine_Pro4web: `9c4539d feat(webapp): add OI context and observation controls`

---

# v3.6.17 — 2026-07-22

## Added

- FLOW EVENTS設定へcategory別`CANDLE MARK` ON／OFFを追加した。
- LARGE TRADE、SWEEP、EXHAUSTION、UNFINISHED AUCTION、TAPEを個別に切替できる。
- 設定をlocalStorageへ保存し、再読込後も表示選択を維持する。

## Behavior

- OFFにしたcategoryは、現在足と過去足のマーカー、および選択足詳細から即時に隠す。
- 同じ足に複数categoryがある場合、OFFのcategoryだけを除外してONのマーカーは残す。
- eventデータは2時間メモリへ保持し続け、再びONにすると保持中のマーカーを復元する。

## Scope

- Flow Eventの検出、FLOW EVENTS一覧、alert、strength thresholdは変更していない。
- event履歴のDB、履歴API、localStorage保存は追加していない。
- Flow Price Response、3段チャート、8パターン、OIの計算と意味は変更していない。

## Tests

- WebApp対象テスト23 passed。
- 全体回帰339 passed in 13.56s。
- JavaScript構文チェック通過。
- Edge実ブラウザで5種類のcheckbox、TAPEのOFF、localStorage保存、ON復元、
  既存`PRICE × FLOW RESPONSE`見出しを確認した。

---

# v3.6.16 — 2026-07-22

## Added

- Binance USD-M Futures公式Open Interestを10秒間隔で取得し、exchange source time、
  local received time、symbol、raw OI、sourceをDuckDBとParquetへ永続保存する
  OI Context v1を追加した。
- TOP BARへ現在OI、直近1分変化率、直近5分変化率を追加した。
- 選択足の固定詳細へOI OPEN、CLOSE、CHANGE、CHANGE %、SAMPLESと
  BUILDING／UNWINDING／UNCHANGEDの事実表示を追加した。
- 再読込後に保存済みOIを復元するopen-interest history APIを追加した。
- OI Parquetは同一UTC時間のsampleを1時間1ファイルへupsertし、10秒ごとの
  one-rowファイル増殖を防止した。

## Data integrity

- Binance responseのtimeをsource timeとして使い、非正値、非有限値、symbol不一致を拒否する。
- 取得失敗や足境界sample欠損を補間、0埋め、forward-fillせず、画面では — とする。
- 20秒超をSTALE、60秒超を現在値非表示とした。
- リプレイ中はライブOI pollingとOI履歴hydrationを停止し、過去価格へ現在OIを混在させない。

## Scope

- OIは独立観測値であり、signal、score、Flow Price Response、8パターンへ入力しない。
- 3段チャートへ第4段、OI線、OIイベント、OIマーカーを追加していない。
- 完成済みのFlow Price Response、3段チャート、8パターンの計算を変更していない。

## Tests

- OI対象テスト42 passed。
- 全体回帰338 passed in 30.46s。
- Python構文、JavaScript構文、実WebSocket OI、DuckDB保存、履歴API復元、
  Edge実ブラウザDOMのOI現在値・1分差・3段チャート見出しを確認した。

---

# v3.6.15 — 2026-07-22

## Added

- Flow Eventの発生足へ2時間保持の小型マーカーを追加した。
- 同じ足のeventを集約し、複数時は `L+`、狭いzoomではdotへ縮退するようにした。
- 選択足の固定詳細へevent category、side、件数、最大strengthを追加した。

## Changed

- native Flow Eventを即時WebSocket配信へ接続し、本来のevent timeとpriceを保持した。
- bar-close ANALYSISのflow eventsにもevent timeとcategoryを含め、即時配信との重複を除外した。
- Flow Eventのcategory色を現在のLARGE TRADE／SWEEP／EXHAUSTION／UNFINISHED AUCTION／TAPEへ揃えた。

## Scope

- eventはmarket time基準で2時間だけブラウザメモリに保持する。
- DB、履歴API、localStorageは追加せず、再読込・再起動で消去する。
- Flow Price Response、CVD、Delta、Volume、8パターンの計算は変更していない。

## Tests

- 対象WebApp 29 passed、全体回帰325 passed in 18.66s。
- JavaScript構文、実ブラウザでの足単位集約、固定詳細、重複除外、2時間消去、固定header寸法を確認した。

---

# v3.6.14 — 2026-07-22

## Changed

- 3段チャートのヘッダーを固定高72pxの2行構成にし、ライブ文字列更新時の画面揺れを防止した。
- candleの右クリックで選択と固定詳細を解除できるようにした。左クリック選択、左右キー移動、wheel zoom、drag panは維持した。
- 左列を `FLOW EVENTS → ABSORPTION → IMBALANCE` の順に整理し、Order Bookを独立した右列に保った。
- 表示項目、状態、設定、操作案内、価格・CVD・Deltaの8パターンを英語へ統一し、自動翻訳を無効化した。

## Removed

- 前日比と誤解されるページ開始時基準の疑似変化率を撤去した。
- 旧 `SIGNAL — WHY`、CONFIDENCE、VETO、RISK、EXPECTED RR、detector scores、COMPOSITEを撤去した。

## Documentation

- 観測ツールとしての現行UIを正とする `UI_Spec_CommandCenter_v2.md` を新設した。
- `UI_Spec_CommandCenter_v1.md`を履歴資料へ移行し、PROJECT_MEMORYとCompletionLogを更新した。

## Tests

- 全体回帰321 passed。
- JavaScript構文、固定ヘッダー寸法、パネル順序、chart controls、英語表示、legacy UI撤去を確認した。

---

# v3.6.13 — 2026-07-21

## Fixed
- 価格0・数量0の約定が正規化を通過し、Flow Price Responseの基準価格0イベントを生成して、約60秒後の事後リターン計算で0除算しライブパイプラインを停止させる不具合を修正した。
- 正規化境界で価格・数量の0、負数、NaN、InfinityをE3001として拒否するようにした。
- FlowPriceResponseDetectorとFlowResponseOutcomeTrackerにも独立した正値ガードを追加し、異常約定や基準価格0スナップショットが直接渡されても状態窓・最大上下幅・保留中事後追跡を汚さないようにした。

## Data quality
- 修正前データで価格0かつ数量0の行1,557件、保存イベント82件中端点価格0のイベント6件を確認した。修正前の最大上下幅と異常端点イベントは研究対象外とする。
- 2026-07-21 18:30:41 JSTに修正版を再起動。再起動後2,732約定を直接検査し、非正値保存0件を確認した。
- `/api/health`はGREEN、pipeline例外0、ライブイベント遅延509msを確認した。

## Tests
- 対象テスト46 passed。
- 全体回帰320 passed in 14.15s。

---
# v3.6.10 — 2026-07-21

## Changed
- Imbalanceを5指標独立化step2の3本目として独立化。composite入力のs_imbをNone化し、旧スコアパネルのIMBALANCE行を撤去した。
- Stacked Imbalanceの方向・段数・価格帯と検出時のeffective min_volumeをANALYSIS payloadへ構造化して配信するようにした。
- 右カラムに壁一覧パネルを追加し、ratio_threshold／stack_count／min_volumeを歯車から即時再計算できるようにした。
- 壁が密集しても数字が重ならないよう、価格軸への絶対配置を廃止し、価格の高い順にBUY／SELL・価格帯・連続段数を1件1行の固定高カードで表示するようにした。

## Removed
- 段数を合算して0〜1 strengthへ丸めていた旧IMBALANCE PushFlowEvent配信を撤去した。

## Tests
- 全テスト350 passed。Imbalance composite除外、旧事件非発火、構造化walls payload、Python／JavaScript壁検出一致、UI契約・JavaScript構文を検証した。

---
# v3.6.9 — 2026-07-21

## Changed
- Footprintを5指標独立化step2の1本目として独立化。composite入力のs_fpをNone化し、旧スコアパネルのFOOTPRINT行を撤去した。
- FootprintパネルにVA%歯車を追加。配信済みの価格帯別bid/askからクライアント側でPOC／VAH／VALを再計算し、30〜95%の範囲で即時反映するようにした。
- 表示中バーの全価格帯からΣBID／ΣASK／DELTAをnative集計して表示し、不明瞭な矢印をBUY／SELLバッジへ変更した。VAH〜VALは半透明黄1px枠で連続表示する。
- 追従中は現値と完全一致し、かつ画面内に描画されている価格帯だけを透明内側の白1px枠で表示する。現値が画面外または価格帯に存在しない場合は再配置せず枠を表示しない。

## Tests
- 全テスト349 passed。Replay／Live共有経路のFootprint composite除外、既存期待値更新、VA再計算、全価格帯合算、現値完全一致、VA範囲枠、UI要素・JavaScript構文を検証した。

---
# v3.6.8 — 2026-07-21

## Changed
- CVD第1本目を独立化。composite入力の`s_cvd`を`None`化し、確定CVD系列から回帰／差分の傾きをクライアント側で算出する専用表示へ移設した。
- divergence配信をdirection文字列から全native値を持つobjectへ変更し、旧SIGNAL—WHYのCVD ±100行と旧divergence表示を撤去した。

## Fixed
- Replay／Live両系で非発火バー時にdivergenceを`None`へ戻し、過去イベントが残留して嘘表示になる不具合を修正した。

## Tests
- 全テスト349 passed（改修前348、差分+1）。CVD composite除外、Replay／Live残留回帰、native payload、UI契約と未丸め表示を検証した。

---
# v3.6.7 — 2026-07-20

## Added

- ADR-011_No_Decimation_Recording_v3.0.md: 全量記録の原則を制定。取得データをその場の関連性判断で間引かず、後から分析・再生できる形で全量記録する。「間引かない」を時間(後から見るため全量)/表示(蓄積を見せ方に従属させない)/加工(土台は取引所の生データ時系列、加工物は派生で再計算可)の三軸で定義。生は取引所から届いた未整形メッセージを最優先とし、欠損も隠蔽せず生のまま残す。実装は Order Book 永続化から段階的に着手。v3.6.0/M11 の板 out-of-scope 判断を原則レベルで見直すもの。
# CHANGELOG

All notable changes to this Architecture Repository are documented in this file.

The format follows the Keep a Changelog convention.

---

# v3.6.7 — 2026-07-20

## Changed

- 較正(課題5): `signal.stack_ref` 3 → 5、`imbalance.min_volume` 0.5 → 0.002 を実測較正で反映。stacked run 長 P80 / レベル総出来高 P25 に基づく(`tools/calibrate_refs.py`)。stack_ref=3 は 3スタック1本で ±100 到達=飽和のため是正。
- `signal.cvd_slope_ref` は 65.203 据え置き(課題6見送り)。サンプル 2,515 件で P80 推奨は 26.5 だが、65.203 → 26.5 は CVD 感度が約 2.46 倍に上がるため、課題5のみ反映して様子見とした。

## Unchanged

- コード無変更(config 値のみ)。テスト件数不変(348 passed)。DuckDB/Parquet スキーマ・正本モジュール仕様は無変更。

---

# v3.6.6 — 2026-07-19

## Added

- ADR-010_OrderBook_Resync_v3.0.md: 板同期の Resync Supervisor を決定。起動時 REST snapshot の無限リトライ(バックオフ 5/10/30s)と、gap 検出後の自動再同期を実装。lenient 同期アルゴリズム(ADR-007)は無変更。
- LiveStats / `/api/stats` / STATS 配信に `book_synced` / `book_resyncs` / `book_snapshot_fetch_failures` を追加。dev オーバーレイに BOOK / RESYNC 行を追加。

## Tests

- Resync Supervisor(起動リトライ・バックオフ上限・gap 後再同期・healthy 時非取得・キャンセル終了)、`is_initialized` プロパティ、stats 露出を追加。341 → 348 passed。

---

# v3.6.5 — 2026-07-19

## Added

- `00_Master/Reports/` を正式新設。web検証・お館様承認済みの設計レビュー等の報告書のみを格納する。
- Divergence Phase 0: MOD-012 の決定的な regular price/CVD divergence detector、Event/Enum 契約、bounded history、入力検証と診断カウンタ、設定、Replay/Live の shadow-mode 表示配線、ADR-009 を追加。SignalEngine と保存スキーマは変更しない。

## Tests

- Divergence Detector の BULLISH/BEARISH、同値pivot、入力拒否、bounded memory、filters、連続検出、決定的リプレイを追加。

---

# v3.6.4 — 2026-07-18

## Added

- SelfMonitor v1: src/monitor/health.py — 異常検知6種(SEQUENCE_GAP/BAR_MISSING/WS_RECONNECT/PROCESSING_LATENCY/MEMORY_RSS/PIPELINE_EXCEPTION)、GREEN/YELLOW/RED、JSONL日次ローテーション。HEALTH WSメッセージ(5秒)、UIヘルスドット+ポップアップ、GET /api/health、tools/diagnose.py、config monitor:節(15キー)。
- ライブ進行中バー配信: BAR_UPDATEメッセージ(webapp.bar_update_interval_sec、既定1秒)、CvdCalculator.current_bar_snapshot()、UI FOOTPRINT [FORMING]表示。チャート系列は確定バーのみ。
- tools/calibrate_refs.py: imbalance.min_volume(レベル総出来高P25)と signal.stack_ref(stacked run長P80、実運用と同一のImbalanceDetectorで計測)の推奨・--write反映。

## Fixed

- replayモード起動失敗(v3.6.3以前から存在): asyncio.create_task(run_in_executor Future)のTypeErrorを ensure_future に修正。回帰ガードテスト追加。

## Tests

- 291 → 320 passed (+29)。

---

# v3.6.3 — 2026-07-18

## Scope

Docker 本番起動確認クローズ + アプリバージョン表示機能(CHANGELOG 単一情報源)。

## Added (implementation)

- **アプリバージョン表示**: UI 右上隅(topbar 末尾)に現行バージョンを常時表示。
  - `webapp/version.py` 新規: CHANGELOG.md 最新エントリ見出し(`# vX.Y.Z`)をパースする `parse_version()` / 候補パス走査の `resolve_version()`。未検出時は `v?.?.?` フォールバック(起動阻害禁止)。
  - `webapp/main.py`: lifespan で起動時 1 回解決し `app.state.version` へ格納。`GET /api/version` 追加。
  - `webapp/static/index.html`: `#appver` 要素追加、起動時に `/api/version` を fetch。
  - `docker-compose.yml`: `../ArchitectureRepository/00_Master/CHANGELOG.md` を `/app/CHANGELOG.md:ro` にマウント(コンテナ内から単一情報源を参照)。
  - 回帰テスト 6 本(`tests/webapp/test_version.py`)。**285 → 291 passed**。
- **設計原則**: バージョンのコード手動転記を禁止。Documentation-First 規律(仕様書変更時の CHANGELOG 追記義務)により、ドキュメント更新 → 次回起動時に UI バージョンが自動昇格する。

## Fixed (environment)

- **Docker Desktop 復旧完了**: コンポーネントストア破損(exit code 14098)は DISM RestoreHealth で修復済みを確認。その後レジストリキー欠損(`SOFTWARE\Docker Inc.\Docker Desktop` 不在)が判明し、クリーン再インストール(旧 4.82.0 アンインストール → 残骸削除 → WSL ディストリビューション unregister → 4.81.0 再導入)で解消。`docker version`(Client/Server)+ `hello-world` 正常。
- **`docker-compose up` 本番起動確認**: `http://localhost:8080` で Delta Command Center 表示、フットプリント昇順表示(TaskF)、シグナル連続値(Phase1)、CONFLUENCE 点灯(TaskC)を目視合格。引継ぎ書の保留課題 7 をクローズ。

---

# v3.6.2 — 2026-07-18

## Scope

Phase1_v2.2 バグ修正 4 件 + TaskF(フットプリント順序契約)。実装+仕様書整合。

## Fixed (implementation — Phase1_v2.2)

- **Task A — IMBALANCE 飽和**: `imbalance.min_volume: null` が Decimal("0") 化されフィルタが無効になっていた問題を修正。null は E3002 警告+デフォルト 0.5 へフォールバック。分母ゼロは numerator ≥ min_volume の場合のみ ratio_cap 成立。webapp FlowEvent は strength 連続値化 `min(net/(stack_ref×2),1)` + 同方向 3 バークールダウン(net 増加時は即時発火)。
- **Task B — CVD「—」**: `tools/calibrate_cvd.py` 新規作成。直近 7 日 |delta| P80(397 サンプル)より `signal.cvd_slope_ref = 65.203` を較正・書込。cvd_unref(null/0 → score None → モジュール除外)は設計上の状態として仕様化。
- **Task C — CONFLUENCE 星ゼロ**: `push_broker.confluence()` の WAIT 全 False 短絡を撤廃。WAIT 中は composite 符号で方向判定。
- **Task D — 表示崩れ**: `index.html` — #alerthist を position:fixed から通常フロー配置へ(D-1)、フットプリント行ウィンドウ化(D-2)、タイトルに [CLOSED]+経過秒(D-3)。`main.py` — `/` 応答に `Cache-Control: no-cache` 付与(旧 UI キャッシュ問題の恒久対策)。
- **Task E — signal.enabled 監査**: 実態(常時稼働)に合わせ `enabled: true` に統一。
- **Task F — フットプリント順序契約違反**: `footprint.to_levels()` は昇順契約、WebSocketPayload仕様_v1 §4.3 / `compute_value_area()` は降順前提。`webapp/main.py` アダプタが変換せず素通しし、UI 価格軸反転・VAH/VAL 入替わり・板 MID との見かけ乖離が発生していた。アダプタ境界で `reversed()` により降順化。delta の負ゼロ表示(|d|<0.05 は符号なし 0.0)も修正。回帰テスト 2 本(payload 降順 + VAL<POC<VAH / reversed 配線ガード)。

## Changed (specifications)

- Imbalance v3.1 → **v3.2**: §5.2 判定ゲート順序化(分母ゼロ規則の numerator ゲート)、§5.4 WebApp FlowEvent(strength 式・クールダウン)新設、§6 min_volume デフォルト 0.5 / null→E3002。
- SignalEngine v3.1(rev. 2026-07-18): §4.1a cvd_unref 追記、§8 に cvd_unref 行追加、§10 の cvd_slope_ref 較正済み反映。

## Implementation

- `src/orderflow/imbalance.py` — `_qualify()` ゲート順序化
- `src/pipeline.py` — `_resolve_imbalance_min_volume()` / `_imbalance_should_fire()` / strength 連続値化
- `tools/calibrate_cvd.py` — 新規
- `webapp/push_broker.py` — confluence WAIT 短絡撤廃
- `webapp/main.py` — Cache-Control / footprint levels 降順化(TaskF)
- `webapp/static/index.html` — D-1/D-2/D-3 / 負ゼロ表示修正
- `config/config.yaml` — `imbalance.min_volume: 0.5` / `signal.cvd_slope_ref: 65.203` / `signal.enabled: true`
- pytest: 283 → **285**(TaskF 回帰 2 本追加)

---

# v3.6.1 — 2026-07-08

## Changed

- YAMLReference v3.2 → v3.3: `subscribe_streams` を `@aggTrade` → `@trade` に変更。Exchange Profile サンプルの `trade_id` を `a` → `t` に変更、`trade_id_fallback` を `a`（aggTrade 後方互換）に更新。

## Added

- ADR-006_TradeStream_Selection_v3.0.md: Binance Futures @trade ストリーム採用を決定。
- ADR-007_OrderBook_Initial_Sync_v3.0.md: Order Book 初期同期の lenient 方式を記録。

## Implementation

- `config.yaml`: `subscribe_streams` を `@trade` に変更。
- `binance.yaml`: `trade_id: t`、`trade_id_fallback: a`（後方互換）。
- `live_verify.py`: 実行時置換ロジック削除。
- `binance_ws.py`: docstring 更新。
- `ws_probe.py` / `ws_probe2.py`: デフォルトストリーム変更。
- `tests/test_config.py`: subscribe_streams アサーション更新。

---

# v3.6.0 — 2026-07-08

## Scope

Reference-only. No implementation, no module spec changes.

## Motivation

M9 Absorption requires normalized Order Book input as canonical records; DOM/Liquidity/DataDictionary terminology and DataNormalizer / DataReceiver / Absorption input-output declarations were already canonical, but the downstream record schema, JSON envelope, and exchange-profile mapping were absent. This release fills only that gap.

## Changed

- MarketDataSchema v3.1 → v3.2: Added Order Book Update Record, BookLevel, Order Book State sections.
- JSONSchema v3.1 → v3.2: Added §7 Order Book Update Event (snapshot / diff forms).
- YAMLReference v3.1 → v3.2: Added §4.1 Order Book Field Mapping (optional `order_book_mapping` block for exchange profiles). Added §2 note on depth stream activation condition.

## Unchanged

- DataNormalizer_v3.2, DataReceiver_v3.1, Absorption_v3.1: already declared order book inputs/outputs; no spec change required.
- ParquetSchema, DuckDBDDL: Order Book persistence intentionally out of scope (M11 approach: raw not persisted).
- All 30_Modules and 20_Architecture documents.

## Follow-up

Implementation is handled by a separate instruction ("指示書 B") covering `binance.yaml`, `src/normalization/normalizer.py`, `src/acquisition/binance_ws.py`, an Order Book state manager, and Absorption detector implementation.

---

# v3.5.3 — 2026-07-08

## Fixed

- YAMLReference §4 の Binance プロファイルサンプルを訂正: `trade_id: t` → `trade_id: a`。config.yaml が購読する `@aggTrade` ストリームのペイロードは個別約定IDフィールド `t` を持たず、集約取引IDは `a`。従来のサンプル(`t`)では aggTrade イベントが全件 normalizer 拒否され CVD が動作しない不整合があった。実装(config/profiles/binance.yaml)と一致させた。aggTrade/`a` の対応理由を §4 に併記。
- YAMLReference の版番号は据え置き(erratum: 単一サンプル値の訂正のため v3.1 のまま)。

---

# v3.5.2 — 2026-07-08

## Added

- JSONSchema に CVD Update Event・Candle Event を追加(CVD出力のモジュール間契約を定義)。
- EnumDefinitions に Timeframe enum を追加(1s/1m/5m/15m/1h/4h/1d)。
- YAMLReference に全モジュールの Config パラメータを網羅したサンプル、Exchange Profile スキーマ(§4)、Replay Mode 仕様(§5)、unknown キー拒否ポリシーを追加。
- WebSocket に Config パラメータ表(URL・再接続・タイムアウト等)を追加。
- Database に Config パラメータ表(batch_size・flush_interval)を追加。
- CVD にバー境界動作規則(delta はバーごとリセット、cvd は累積)・Tick/Bar CVD の出力構造・リプレイ対応を追加。
- DataNormalizer に Exchange Profile の検証規則を追加。

## Changed

- Sequence §3 を ADR-002/003 と整合(同期直列 → asyncio コルーチン並行に修正)。
- 上記新版の References を ADR-005 準拠(版数なしベース名)に移行。

## Removed

- EnumDefinitions_v3.0 / JSONSchema_v3.0 / YAMLReference_v3.0 / WebSocket_v3.1 / CVD_v3.1 / Database_v3.1 / DataNormalizer_v3.1 / Sequence_v3.0 / 指示書_Phase5_CVD実装_v2 — 各新版に差し替え。

結果: ファイル数は変動なし(40_Reference 55 / 30_Modules 11 / ADR 6 / 50_Test 3)。Phase5 M2〜M6 の足止め要因13件を解消。

---

# v3.5.1 — 2026-07-08

## Added

- `00_Master/ADR/ADR-005_Reference_Versioning_v3.0.md` — References 節は版数なしのベース名で記載する方針を決定。参照更新の連鎖を解消。
- ParquetSchema / DuckDBDDL に Candle スキーマ(candles テーブル)を追加。CVD 出力の保存先欠落を解消。
- `40_Reference/ErrorCodes_v3.1.md` — E3004(順序異常拒否)・E9002(キュー溢れ)を追加。

## Changed

- `40_Reference/MarketDataSchema_v3.1.md` — Tick Record を JSONSchema / ParquetSchema / DuckDBDDL / DataDictionary と整合(event_time / symbol / quantity(DECIMAL) / side(BUY,SELL))。Candle Record に timeframe を追加。
- `30_Modules/CVD_v3.1.md` — Bar CVD の集計時間足パラメータ `market.bar_timeframe`(初期値 1m)を追加。
- `30_Modules/DataNormalizer_v3.1.md`・`50_Test/TestSpecification_v3.2.md` — 正規化出力の用語を symbol / quantity に整合。
- `30_Modules/Database_v3.1.md` — Candle 保存を Storage Policy に明記。
- 上記新版の References は ADR-005 の版数なし方式に移行。

## Removed

- 各旧版(MarketDataSchema_v3.0 / ParquetSchema_v3.0 / DuckDBDDL_v3.0 / ErrorCodes_v3.0 / CVD_v3.0 / DataNormalizer_v3.0 / Database_v3.0 / TestSpecification_v3.1)— 新版に差し替え。

---

# v3.5 — 2026-07-07

## Added

- `00_Master/ADR/ADR-002_Module_Communication_v3.0.md` — モジュール間通信方式を決定。パイプライン段間は有界 asyncio.Queue、Order Flow Engine 内の4計算器へは直接呼び出し。
- `00_Master/ADR/ADR-003_Concurrency_Model_v3.0.md` — 並行性モデルを決定。単一プロセス asyncio イベントループ。重い処理は executor へ退避。
- `00_Master/ADR/ADR-004_DataNormalizer_Separation_v3.0.md` — Data Normalizer を独立モジュールとして分離することを決定。
- `30_Modules/DataNormalizer_v3.0.md` — MOD-010 新規。正規化規則・取引所プロファイル・重複破棄・reorder_tolerance(500ms)を定義。
- `30_Modules/MT5Adapter_v3.0.md` — MOD-011 新規。FR-006 対応。ローカルTCPソケットによる一方向配信(改行区切りJSON)。

## Changed

- `30_Modules/SignalEngine_v3.1.md` — 加重スコア方式+Absorption veto の統合ロジックを定義。§4.3 の veto 例示誤記を訂正済み(BUY方向を veto するのは Sell Absorption)。
- `30_Modules/Imbalance_v3.1.md` — 定量基準を追加。対角比較式・ratio_threshold 3.0・min_volume・分母ゼロ規則・Stacked=3連続。
- `30_Modules/Absorption_v3.1.md` — 定量基準を追加。停滞≤1tick・出来高 2.0×volume_ref・板補充の3条件と strength 計算式(0〜1)。
- `30_Modules/WebSocket_v3.1.md` — References に ExchangeConnectorReference を追加。DataReceiver 参照を v3.1 に整合。
- `30_Modules/DataReceiver_v3.1.md` — References に ExchangeConnectorReference・DataNormalizer を追加。DataDictionary 参照を v3.1 に整合。
- `30_Modules/AIAnalysis_v3.1.md` — References に AIAnalysisPipelineReference を追加。SignalEngine・DataDictionary 参照を v3.1 に整合。
- `50_Test/TestSpecification_v3.1.md` — テストベクタ28件を追加(CVD 4 / Footprint 2 / Imbalance 6 / Absorption 5 / SignalEngine 7 / DataNormalizer 4)。
- `50_Test/AcceptanceCriteria_v3.0.md`・`50_Test/Performance_v3.0.md`・`60_Implementation/CodingGuideline_v3.0.md` — References の TestSpecification 参照を v3.1 に整合。
- `00_Master/ADR/ADR-004_DataNormalizer_Separation_v3.0.md` — References の DataReceiver 参照を v3.1 に整合。
- `40_Reference/DuckDBDDL_v3.0.md`・`EnumDefinitions_v3.0.md`・`JSONSchema_v3.0.md`・`ErrorCodes_v3.0.md`・`ParquetSchema_v3.0.md` — References の DataDictionary 参照を v3.1 に整合(v3.4 統合時からの残存不整合を解消)。

## Removed

- `30_Modules/SignalEngine_v3.0.md`・`Imbalance_v3.0.md`・`Absorption_v3.0.md`・`WebSocket_v3.0.md`・`DataReceiver_v3.0.md`・`AIAnalysis_v3.0.md` — 各 v3.1 に差し替え。
- `50_Test/TestSpecification_v3.0.md` — v3.1 に差し替え。

結果: 30_Modules は 11ファイル、ADR は 5件。Phase4 残課題(優先順位1〜7)完了、Phase5(CVD実装)移行可能。

## Fixed

- `40_Reference/YAMLReference_v3.0.md` — References の DataDictionary 参照を v3.1 に整合(Work B 検証時に発見した残存不整合)。

---

# v3.4 — 2026-07-07

## Added

- `40_Reference/AIAnalysisPipelineReference_v3.0.md` — AI Analysis Pipeline の SSOT。MarketState分類・ConfidenceScore・RiskLevel・出力コントラクトを定義。
- `40_Reference/ExchangeConnectorReference_v3.0.md` — 取引所接続の SSOT。WebSocket接続ライフサイクル・フィード種別・再接続・Symbol規則を定義。

## Changed

- `40_Reference/DataDictionary_v3.1.md` — v3.0 と v3.1 を統合。REF-001 Document ID を継承。命名規則・時刻標準・エンティティ定義・派生メトリクス式を一本化。
- `40_Reference/DataQualityReference_v3.0.md` — DataQualityMetricsReference の内容を統合。メトリクス定義セクションを追加。
- `40_Reference/SecurityReference_v3.0.md` — DataSecurityReference の内容を統合。CIAトライアド・DataMasking・SecurityClassification を追加。

## Removed

40_Reference から 48 ファイルを削除。削除カテゴリは以下の通り。

- ITSM/ITIL 系（DataOperations* 14ファイル）— 既存 Reference と重複しプロジェクト固有性がない
- エンタープライズアーキテクチャパターン系（DataMesh / DataMicroservice / DataLake / DataLakehouse / DataWarehouse / DataProduct / DataVirtualization / DataSemanticLayer）— プロジェクト構成に該当しない
- ガバナンス組織系（DataGovernance / DataOwnership / DataStewardship / DataCatalog）— 単一開発者に組織ガバナンス体制は不要
- 汎用コンプライアンス系（DataCompliance / DataPrivacy / DataBusinessContinuity / DataMasterManagement）— 公開市場データのみを扱うため不要
- 冗長アーキテクチャ系（DataArchitecture / DataReferenceArchitecture / DataAPIArchitecture / DataAccessArchitecture / DataIntegrationArchitecture / DataIntegration / DataEventArchitecture）— 残存する具体的 Reference（DataStorageArchitecture / DataProcessingArchitecture / DataStreamArchitecture）で代替可能
- その他重複（DataQualityMetrics / DataSecurity / DataDictionary_v3.0 / Enum.md）— 上記 Changed に統合済み

結果: 40_Reference は 101ファイル → 55ファイル に整理。

---

# v3.0 — 初版

## Added

- Architecture Repository structure
- Master document
- Documentation Standard
- Repository governance
- AI First documentation policy
- Single Source of Truth (SSOT)
- Repository review policy

## Changed

- Reorganized documentation into layered architecture.
- Introduced Architecture Repository as the primary project asset.
# v3.6.11 — 2026-07-21

## Changed
- Absorptionをveto役から外し、classification／strength／price_low／price_highを独立ANALYSIS payloadとして配信するようにした。
- 右カラムに発火時のみ表示するAbsorptionパネルと、price_stall_ticks／volume_multiplierのサーバ即時更新UIを追加した。
- 旧ABSORPTIONスコア行とconfluence参加を撤去し、吸収イベント非発火時はpayload/UIとも沈黙するようにした。

## Tests
- 全テスト347 passed。vetoテスト失効4件、価格帯・set_params契約を追加。

---
# v3.6.12 — 2026-07-21

## Changed
- Flowをcompositeから切り離し、5イベントを平均せず`flow_events`としてANALYSIS payloadへ個別配信するようにした。
- Flow Eventsパネルへバー確定イベントを補完表示し、旧FLOWスコア行とconfluence参加を撤去した。
- composite／market_state／signal／confidence／confluenceなどの畳み装置を一括撤去し、5指標の独立payload・UIだけを残した。
- SignalEngineとAnalysisEngineは保存互換のNO_INPUT／NEUTRALスタブへ縮小し、TrendFilterと関連テストを削除した。

## Tests
- 全テスト284 passed。撤去対象テストを削除し、独立payload契約を維持した。

---

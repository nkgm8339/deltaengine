# [完了] 指示書_Heatmap_Phase1_実装_P1-2b

## 欠陥1

### main.py変数フロー

- `webapp/main.py:127-137`
  - `depth_history_recorder`には`SafeRecorder(DepthHistoryRecorder(...))`または`None`が代入される。
- `webapp/main.py:375`
  - `hook_capture`と`depth_history_recorder`から`_raw_taps`を作る。元の`depth_history_recorder`変数は上書きしない。
- `webapp/main.py:376`
  - 複数tap時だけ、別変数`_raw_tap`へ`RecorderTee(_raw_taps)`を代入する。
- `webapp/main.py:378`
  - pipelineへ渡すのは`_raw_tap`。
- `webapp/main.py:589-591`
  - shutdownで直接closeするのは元の`depth_history_recorder`、つまりSafeRecorder本体。

したがってmain.pyの変数フローは正しく、変更は不要だった。P1-2のTracebackは
main.pyの直接closeではなく、`src/pipeline.py:134-141`の`_RecorderFanout.close()`が
observationとして保持していたRecorderTeeへ`close()`を呼んだ箇所で発生していた。

### 適用

- 直接編集
- `src/acquisition/depth_history_recorder.py:159-175`
  - `RecorderTee.close()`を安全なno-opとして追加。
  - 配下tapは閉じず、main.pyが個別変数を使って所有・closeする。
- `tests/acquisition/test_depth_history_recorder.py:135-145`
  - `test_tee_close_is_noop`を追加。
  - `close()`を呼んでも例外がなく、配下tapの`close()`が呼ばれないことを確認。

### テスト

- depth history recorder: `7 passed in 0.14s`
- 全体: `694 passed, 1 failed, 1 skipped`
- 残存fail:
  - `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`
- 新規fail: なし

### コミット

- `e358a0f1696ad3065ce37fce1a75f62b43f46ab8`
- `fix(depth-history): RecorderTee.close no-op to prevent shutdown AttributeError (P1-2b)`

## 欠陥2（調査）

### 1. snapshot取得箇所とlastUpdateId

- `src/acquisition/binance_rest.py:49-75`
  - `fetch_depth_snapshot()`がBinance Futures REST
    `/fapi/v1/depth?symbol=...&limit=1000`を取得する。
  - `response.json()`の結果を加工せず`data`として返す。
  - `data.get("lastUpdateId")`をログへ出しており、生REST応答には
    `lastUpdateId`が含まれる。
- `src/pipeline.py:210`
  - `_book_resync_supervisor()`が生REST応答を`raw_snap`として受け取る。

### 2. depthSnapshot形式への加工箇所

- `src/pipeline.py:211`
  - `rest_to_depth_event(raw_snap, symbol)`を呼ぶ。
- `src/acquisition/binance_rest.py:124-146`
  - `rest_to_depth_event()`が以下へ変換する。
  - `e="depthSnapshot"`
  - `s=symbol`
  - `E=RESTのE/T、なければローカル受信時刻`
  - `u=raw_rest["lastUpdateId"]`
  - `b=raw_rest["bids"]`
  - `a=raw_rest["asks"]`
- `src/pipeline.py:120-128`
  - `_RecorderFanout.write_snapshot()`が変換後dictをコピーし、
    `_capture_reason`を追加してobservation tapへ渡す。

### 3. raw_recorderタップへ流れる形式

- `src/pipeline.py:210-220`
  - 取得順序は、生REST取得→`rest_to_depth_event()`変換→normalizer確認→
    `recorder.write_snapshot(depth_evt, reason=...)`。
- `src/pipeline.py:120-128`
  - raw_recorderに相当するobservation tapへ届くのは、
    `depthSnapshot`形式へ変換され、さらに`_capture_reason`が付いた後のdict。

結論: raw_recorderへ流れるsnapshotは加工後であり、生RESTレスポンスそのものではない。

### 4. uフィールドの正体

- `src/acquisition/binance_rest.py:143`
  - `"u": raw_rest["lastUpdateId"]`

結論: 加工形式の`u`は別の更新IDではなく、生RESTの`lastUpdateId`をそのまま保持している。

## 逸脱事項

なし。欠陥2は調査のみで実装変更しておらず、ライブ再起動も行っていない。

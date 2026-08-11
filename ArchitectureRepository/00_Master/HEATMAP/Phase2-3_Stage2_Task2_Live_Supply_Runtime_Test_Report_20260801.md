# Stage2 Task2 Live Supply Runtime Test Report

実施日: 2026-08-01  
対象: `Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py`のみ追記  
commit: 未実施、staging: 空

## 追加した実起動テスト全文（該当箇所）

```python
def test_live_runtime_uses_live_pump_when_replay_flag_is_false(monkeypatch) -> None:
    mock_config = _make_mock_config()
    mock_config.replay.enabled = False
    mock_pipeline = _make_mock_pipeline()
    book_run = AsyncMock()
    replay_run = AsyncMock()
    monkeypatch.delenv("HEATMAP_REPLAY_ENABLED", raising=False)

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.LatestBookProjectionPump.run", new=book_run), \
         patch("webapp.main.heatmap_replay_loop", new=replay_run), \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()), \
         patch("webapp.main.hfm_quote_tail_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    book_run.assert_awaited()
    replay_run.assert_not_awaited()


def test_live_runtime_uses_replay_task_when_replay_flag_is_true(monkeypatch) -> None:
    mock_config = _make_mock_config()
    mock_config.replay.enabled = False
    mock_pipeline = _make_mock_pipeline()
    book_run = AsyncMock()
    replay_run = AsyncMock()
    monkeypatch.setenv("HEATMAP_REPLAY_ENABLED", "true")

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.ensure_replay_source", new=MagicMock()), \
         patch("webapp.main.LatestBookProjectionPump.run", new=book_run), \
         patch("webapp.main.heatmap_replay_loop", new=replay_run), \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()), \
         patch("webapp.main.hfm_quote_tail_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    replay_run.assert_awaited()
    book_run.assert_not_awaited()
```

該当関数とassertは次のとおり。

- `test_live_runtime_uses_live_pump_when_replay_flag_is_false`: `book_run.assert_awaited()`、`replay_run.assert_not_awaited()`
- `test_live_runtime_uses_replay_task_when_replay_flag_is_true`: `replay_run.assert_awaited()`、`book_run.assert_not_awaited()`

両テストとも`mock_config.replay.enabled = False`を明示し、`TestClient(app)`で実lifespanを起動している。flag=true側は`ensure_replay_source`だけをMagicMock化し、供給者taskの選択・awaitを実挙動で確認している。

## 現行テストファイル計測

- SHA-256: `9E5099058CBD7DFD69C6108DEB349BC7CFE3DC72933E6AC08C9EAE25D7C00AB6`
- byte: `8302`
- LF: `252`
- CR: `0`
- `float(`走査: 出力なし（0件）

## pytest

追加テスト:

```text
............                                                             [100%]
12 passed in 1.72s
```

全体pytest:

```text
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
........................................................................ [ 45%]
......s................................................................. [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
............................F........................................... [ 90%]
........................................................................ [ 99%]
..                                                                       [100%]
================================== FAILURES ===================================
_ test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation _

    def test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation() -> None:
        html = HTML_PATH.read_text(encoding="utf-8")
        assert '<script src="/static/time_sales.js"></script>' in html
        assert "const PHASE5_FUSION_ENABLED = true;" in html
        assert 'id="fpdomstatus"' in html
        assert 'id="tape" class="panel"' in html
        assert 'id="tapeviewport" tabindex="0" role="grid"' in html
        assert 'id="tapedetail" role="status" aria-live="polite"' in html
        assert 'id="tapefilterstate"' in html
        assert 'id="tapegap"' in html
        assert 'id="tapecount"' in html
>       assert 'body.phase5-fusion #right>#left{display:none!important}' in html
E       assert 'body.phase5-fusion #right>#left{display:none!important}' in '<!DOCTYPE html>...'

tests\\webapp\\test_dom_tape_fusion_ui.py:30: AssertionError
=========================== short test summary info ============================
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
1 failed, 792 passed, 1 skipped in 125.41s (0:02:05)
```

新規failureはなく、既知failure 1件のみ。

## status / staging

```text
 M Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
```

`git diff --cached --name-only`: 空。変更対象は実際には既存のv3.3差分と同じ新規テストファイル内の追記のみで、保護ファイルは今回変更していない。


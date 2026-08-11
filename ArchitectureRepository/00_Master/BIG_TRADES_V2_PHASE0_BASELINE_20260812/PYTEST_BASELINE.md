# Big Trades V2 Phase 0 Pytest Baseline

- 実行日: 2026-08-12
- command: `python -m pytest -q`
- working directory: `C:\Users\user\desktop\deltaengine05m\Delta_Engine_Pro4web`
- exit code: 1
- duration: 334.12 seconds
- result: `846 passed, 1 failed, 1 skipped`

## Failure

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

assertion:

```text
assert 'body.phase5-fusion #right>#left{display:none!important}' in html
```

actual sourceには同一一行文字列はなく、`webapp/static/index.html:496`から複数行CSSとして`#right>#left{`が存在する。

## Source identity

- `tests/webapp/test_dom_tape_fusion_ui.py` SHA-256: `C903C259C5A2E6666B5E2837CF2896F3FAF2169FC6740C458511BEAAE88ED879`
- `webapp/static/index.html` SHA-256: `74FD573D6C5A57D30AC9B27A452E04F8B9DA849960E464B07E5822F9D546CD55`

## Baseline classification

- V2 source実装前に存在するfailure。
- 既存checkpoint記載の既知UI selector failureと一致。
- Big Trades V2由来のfailure: 0。
- 工程0では修正しない。

## Full summary

```text
1 failed, 846 passed, 1 skipped in 334.12s (0:05:34)
```

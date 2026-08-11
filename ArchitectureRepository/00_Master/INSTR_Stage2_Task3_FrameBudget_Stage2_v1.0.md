# 指示書: Phase 2-3 Stage 2 Task 3 — Stage 2 実装
# 16ms per-frame バジェット合否判定の追加

- バージョン: v1.0
- 作成: 2026-08-01
- 発行元: Claude(web / 統括)
- 宛先: Codex(実装担当)
- リポジトリ: DeltaEngine05M(`C:\Users\user\Desktop\DeltaEngine05M`)
- ブランチ: feature/footprint-dom-tape
- 基準HEAD: `6ae3f15`

---

## 0. 前提(Stage 1 調査結果)

- `webapp/static/orderbook_heatmap.js` に `renderTimes` 配列(上限240)と p95 算出が既存。
- p95 は `#heatmapstatus` へ表示済み。
- 16ms 合否判定は未実装。
- metrics API(サーバー送信/受信)はなし。本タスクでも新設しない。
- gate は `true`(動的フレーム供給は有効)。
- 性能関連の既存テストは 0 件。
- pytest: 792 passed / 1 failed(既知レイアウト selector 不一致) / 1 skipped。

---

## 1. スコープ

JS 側完結。変更ファイルは2つ、新規ファイルは1つ。

| # | ファイル | 種別 | 内容 |
|---|---------|------|------|
| D1 | `webapp/static/orderbook_heatmap.js` | 既存変更 | 定数追加 + 合否インジケータ表示 |
| T1 | `tests/webapp/test_heatmap_frame_budget.py` | 新規 | 構造保証テスト |

保護ファイル(`webapp/main.py`, `docker-compose.yml`, `tests/webapp/test_book_update.py`, `webapp/static/index.html`)および Task 1 成果物(`webapp/heatmap_frame_source.py`, そのテスト)、`src/heatmap/reconstruct.py` は変更禁止。

---

## 2. D1: `webapp/static/orderbook_heatmap.js` の変更

### D1-a: FRAME_BUDGET_MS 定数の追加

`renderTimes` の宣言を含む行を実物から特定し、その**直前**に以下を追加する。

**追加内容:**
```javascript
const FRAME_BUDGET_MS = 16;
```

アンカー特定手順: ファイル内で `renderTimes` を宣言している行(配列初期化。`= []` または `= new Array` 等を含む行)を探す。その行の直前に挿入。

### D1-b: 合否インジケータの表示追加

p95 値を `#heatmapstatus` に書き込んでいる箇所を実物から特定し、表示テキストに合否ラベルを追加する。

**変更方針:**

p95 を `#heatmapstatus` に反映している既存コードを探す。そのテキスト生成部分を以下の方針で拡張する。

- 既存の p95 表示テキストの末尾に、合否ラベルを付加する。
- p95 が `FRAME_BUDGET_MS` 以下なら ` [PASS]`、超過なら ` [OVER]` を付加する。
- 色変更: p95 が `FRAME_BUDGET_MS` 以下なら `#heatmapstatus` の `style.color` を `"#00cc00"`(緑)、超過なら `"#ff4444"`(赤)に設定する。

**before/after の形式で記述する。** 実物のアンカー文字列は Codex が特定し、before に転記したうえで after を適用すること。統括は受領時に実物との照合で正しさを検証する。

**構造要件:**
- `FRAME_BUDGET_MS` 定数を参照すること(マジックナンバー `16` をインラインで書かない)。
- `renderTimes` の p95 算出ロジック自体は変更しない。表示部分のみ拡張。

---

## 3. T1: `tests/webapp/test_heatmap_frame_budget.py`(新規)

JS ファイルの構造保証テスト。ブラウザ描画性能の実測は自動テスト困難なため、以下をファイル内容の文字列検査で保証する。

### テスト関数一覧

```python
"""Tests for 16ms frame-budget instrumentation in orderbook_heatmap.js."""
import pathlib
import pytest

JS_PATH = pathlib.Path(__file__).resolve().parents[2] / "webapp" / "static" / "orderbook_heatmap.js"


@pytest.fixture
def js_source():
    return JS_PATH.read_text(encoding="utf-8")


def test_frame_budget_constant_exists(js_source):
    """FRAME_BUDGET_MS = 16 が宣言されていること。"""
    assert "FRAME_BUDGET_MS" in js_source
    # 値が 16 であること(代入行を検査)
    assert "= 16" in js_source.split("FRAME_BUDGET_MS")[1].split(";")[0]


def test_pass_fail_indicator_exists(js_source):
    """合否インジケータ文字列が存在すること。"""
    assert "[PASS]" in js_source
    assert "[OVER]" in js_source


def test_no_hardcoded_budget_in_indicator(js_source):
    """合否判定で FRAME_BUDGET_MS 定数を参照し、マジックナンバー 16 を
    インラインで使っていないこと。比較演算子の前後に直接 16 が現れないことを検査。"""
    # FRAME_BUDGET_MS の宣言行を除外してから検査
    lines = js_source.splitlines()
    non_decl_lines = [
        ln for ln in lines if "FRAME_BUDGET_MS" not in ln or "const" not in ln
    ]
    indicator_context = [
        ln for ln in non_decl_lines
        if "[PASS]" in ln or "[OVER]" in ln or "FRAME_BUDGET" in ln
    ]
    for ln in indicator_context:
        # 合否判定行で数値リテラル 16 が直接使われていないこと
        # (FRAME_BUDGET_MS 経由であるべき)
        tokens = ln.replace("FRAME_BUDGET_MS", "").split()
        for token in tokens:
            stripped = token.strip("()<=>;,")
            assert stripped != "16", (
                f"マジックナンバー 16 がインラインで使用されている: {ln}"
            )


def test_render_times_buffer_limit(js_source):
    """renderTimes バッファ上限が 240 であること(既存仕様の退行防止)。"""
    assert "240" in js_source


def test_heatmapstatus_color_setting(js_source):
    """合否に応じた色設定が存在すること。"""
    assert "#00cc00" in js_source or "00cc00" in js_source
    assert "#ff4444" in js_source or "ff4444" in js_source
```

### テスト配置

`tests/webapp/test_heatmap_frame_budget.py` として新規作成。

### 禁止事項

- `float()` を使わない。
- `import` は標準ライブラリと pytest のみ。外部パッケージ禁止。

---

## 4. 検証パッケージ

実装完了後、以下を提出すること。

### 4-1. 受領物

| # | 項目 |
|---|------|
| R1 | `webapp/static/orderbook_heatmap.js` の変更後全文(SHA-256, バイト数, LF 行数) |
| R2 | `tests/webapp/test_heatmap_frame_budget.py` の全文(SHA-256, バイト数, LF 行数) |
| R3 | `python -m pytest tests/webapp/test_heatmap_frame_budget.py -v` の出力全文 |
| R4 | `python -m pytest -q -p no:cacheprovider` の最終サマリー行。failed がある場合は全件名列挙 |
| R5 | `git diff --name-only` の出力(変更ファイル一覧) |
| R6 | `git status --porcelain` の出力 |

### 4-2. 統括の検証基準

| # | 基準 | 判定方法 |
|---|------|----------|
| V1 | `FRAME_BUDGET_MS = 16` が `orderbook_heatmap.js` に存在 | R1 の文字列検査 |
| V2 | `[PASS]` / `[OVER]` ラベルが表示ロジックに存在 | R1 の文字列検査 |
| V3 | 合否判定で `FRAME_BUDGET_MS` を参照(16 のハードコード不可) | R1 の文字列検査 |
| V4 | `#heatmapstatus` の色設定(`#00cc00` / `#ff4444`)が存在 | R1 の文字列検査 |
| V5 | p95 算出ロジック・renderTimes バッファ上限 240 が既存のまま | R1 と HEAD 比較 |
| V6 | 新規テスト5件が全件 PASSED | R3 |
| V7 | 全体 pytest: passed >= 797, failed <= 1(既知), skipped <= 1 | R4 |
| V8 | `float(` が新規追加されていない | R1, R2 の走査 |
| V9 | 変更ファイルが `orderbook_heatmap.js` のみ、新規が `test_heatmap_frame_budget.py` のみ | R5, R6 |
| V10 | 保護ファイル・Task 1 成果物・`src/heatmap/reconstruct.py` に差分なし | R5 |

---

## 5. 注意事項

- `renderTimes` の p95 算出ロジックは変更しない。表示部分の拡張のみ。
- `#heatmapstatus` DOM 要素の ID・構造は変更しない。表示テキストと色のみ拡張。
- `webapp/static/index.html` は変更しない(gate は既に true)。
- before/after 差分のアンカー文字列は Codex が実物から特定し、before に実物を正確に転記すること。
- コミットは本指示書のスコープ外。検証合格後に統括が別途コミット指示書を発行する。

以上。

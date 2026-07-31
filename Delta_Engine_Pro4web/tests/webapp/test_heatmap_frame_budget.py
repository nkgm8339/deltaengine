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

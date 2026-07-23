from __future__ import annotations

import csv

from tools.observe_execution_costs import HEADER
from tools.report_execution_costs import build_report


def test_report_keeps_jpy_basis_separate_and_adds_known_fixed_cost(tmp_path) -> None:
    csv_path = tmp_path / "quotes.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for second, binance_mid, jpy_mid in (
            (1, 100.0, 16_000.0),
            (2, 101.0, 16_160.0),
            (3, 102.0, 16_320.0),
        ):
            ns = second * 1_000_000_000
            writer.writerow(["BINANCE_SENSOR", "BTCUSDT", "USDT", "", ns, binance_mid, binance_mid, ""])
            writer.writerow(["HFM_INFINITYX", "#BTCUSDx", "USD", "", ns, binance_mid - 1, binance_mid + 1, ""])
            writer.writerow(["GMO_LEVERAGE", "BTC_JPY", "JPY", "", ns, jpy_mid - 8, jpy_mid + 8, ""])
    config = tmp_path / "costs.yaml"
    config.write_text(
        "as_of: '2026-07-23'\n"
        "venues:\n"
        "  HFM_INFINITYX: {fixed_roundtrip_fee_bps: 0.5}\n"
        "  GMO_LEVERAGE: {fixed_roundtrip_fee_bps: 0.0}\n",
        encoding="utf-8",
    )
    report = build_report(csv_path, config)
    hfm = report["sources"]["HFM_INFINITYX"]
    assert hfm["median_immediate_roundtrip_bps"] > hfm["spread_roundtrip_bps"]["p50"]
    assert "venue_minus_binance_basis_bps" in report["versus_binance_sensor"]["HFM_INFINITYX"]
    gmo_basis = report["versus_binance_sensor"]["GMO_LEVERAGE"]
    assert "implied_jpy_per_usdt" in gmo_basis
    assert "venue_minus_binance_basis_bps" not in gmo_basis
    assert gmo_basis["implied_jpy_per_usdt"]["p50"] == 160.0

from tools.measure_binance_to_ui import Arrival, LatencyCollector


def test_exact_trade_id_match_builds_signed_internal_latency():
    collector = LatencyCollector()
    collector.direct[42] = Arrival(
        wall_ns=1_000_000_000,
        monotonic_ns=2_000_000_000,
        price=50000.0,
        exchange_time_ms=900,
    )
    collector.pending_ticks[42] = Arrival(
        wall_ns=1_075_000_000,
        monotonic_ns=2_075_000_000,
        price=50000.0,
    )

    collector._match(42, collector.pending_ticks, collector.tick_rows, "tick")
    row = collector.tick_rows[0]
    assert row["trade_id"] == 42
    assert row["internal_ms"] == 75.0
    assert row["direct_network_age_ms"] == 100.0
    assert row["delta_total_age_ms"] == 175.0

    report = collector.report(10)
    assert report["tick_internal_ms"]["median"] == 75.0

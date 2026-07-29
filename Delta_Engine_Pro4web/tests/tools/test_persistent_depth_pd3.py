from tools.persistent_depth_pd3 import Sizing, disk_write_decision, project_capacity, validate_soak


def test_capacity_projection_and_disk_fail_closed():
    sizing = Sizing(frames=10123, elapsed_seconds=1806.13, bytes_written=39864556)
    assert 79_000_000 < sizing.bytes_per_hour < 81_000_000
    assert project_capacity(sizing, 1, overhead_ratio=0.25) > 2_000_000_000
    assert disk_write_decision(10_000, 8_000, 2_000) == "ALLOW"
    assert disk_write_decision(9_999, 8_000, 2_000) == "FAIL_CLOSED"


def test_soak_requires_zero_writer_errors():
    assert validate_soak([{"state": "GREEN"}, {"state": "GREEN"}])["pass"]
    assert not validate_soak([{"state": "GREEN"}, {"writer_error": "disk"}])["pass"]


def test_multisegment_hydration_and_crash_tail_fail_closed(tmp_path):
    import pytest
    from tools.persistent_depth_recovery import read_segment, write_segment
    frames = [{"book_stream_id": "s", "book_sequence": i, "sync_state": "SYNCED", "bids": [{"price": "100", "qty": "1"}], "asks": [{"price": "101", "qty": "1"}]} for i in range(1, 21)]
    manifests = [write_segment(tmp_path, frames[offset:offset + 5], f"s-{offset}") for offset in range(0, 20, 5)]
    hydrated = [row for manifest in manifests for row in read_segment(tmp_path, manifest)]
    assert [row["book_sequence"] for row in hydrated] == list(range(1, 21))
    path = tmp_path / manifests[-1]["segment"]
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError, match="CHECKSUM"):
        read_segment(tmp_path, manifests[-1])

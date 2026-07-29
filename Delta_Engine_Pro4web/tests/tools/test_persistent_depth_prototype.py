from tools.persistent_depth_prototype import (
    benchmark,
    decode,
    encode_binary,
    encode_jsonl,
    encode_keyframe_diff,
)


def frames():
    return [
        {
            "book_stream_id": "stream-a",
            "book_sequence": index,
            "event_time": f"2026-07-29T00:00:0{index}Z",
            "projection_time": f"2026-07-29T00:00:0{index}Z",
            "last_update_id": index,
            "sync_state": "SYNCED",
            "bids": [{"price": "100", "qty": str(index)}],
            "asks": [{"price": "101", "qty": "2"}],
            "best_bid": "100",
            "best_ask": "101",
            "spread": "1",
        }
        for index in range(1, 8)
    ]


def test_all_pd1_candidates_round_trip_exactly():
    source = frames()
    for encoded in (encode_jsonl(source), encode_binary(source), encode_keyframe_diff(source, keyframe_every=3)):
        assert decode(encoded) == source
        assert encoded.source_count == len(source)


def test_pd1_benchmark_reports_all_candidates_and_no_silent_drop():
    result = benchmark(frames())
    assert {row["candidate"] for row in result} == {"JSONL_ZSTD", "BINARY_ZSTD", "KEYFRAME_DIFF_5"}
    assert all(row["round_trip"] and row["source_count"] == 7 and row["bytes"] > 0 for row in result)

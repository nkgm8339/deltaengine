from pathlib import Path

from webapp.persistent_depth_writer import PersistentDepthWriter


def payload(sequence, stream="s"):
    return {"book_stream_id": stream, "book_sequence": sequence, "sync_state": "SYNCED", "bids": [{"price": "100", "qty": "1"}], "asks": [{"price": "101", "qty": "2"}]}


def test_writer_rotates_segments_and_writes_manifest(tmp_path):
    writer = PersistentDepthWriter(tmp_path, "BTCUSDT", max_frames=2)
    for sequence in range(1, 5):
        writer.append(payload(sequence))
    writer.close()
    finals = sorted((tmp_path / "symbol=BTCUSDT").glob("*.jsonl"))
    manifests = sorted((tmp_path / "symbol=BTCUSDT").glob("*.manifest.json"))
    assert len(finals) == 2
    assert len(manifests) == 2
    assert not list((tmp_path / "symbol=BTCUSDT").glob("*.part"))


def test_writer_separates_streams(tmp_path):
    writer = PersistentDepthWriter(tmp_path, "BTCUSDT", max_frames=10)
    writer.append(payload(1, "a"))
    writer.append(payload(1, "b"))
    writer.close()
    names = [path.name for path in (tmp_path / "symbol=BTCUSDT").glob("*.jsonl")]
    assert any("stream=a" in name for name in names)
    assert any("stream=b" in name for name in names)

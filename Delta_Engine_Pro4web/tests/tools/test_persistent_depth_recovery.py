from pathlib import Path
import tempfile

import pytest

from tools.persistent_depth_recovery import read_segment, replay_segment, write_segment


def sample_frames():
    return [{"book_stream_id": "s", "book_sequence": i, "sync_state": "SYNCED", "bids": [{"price": "100", "qty": "1"}], "asks": [{"price": "101", "qty": "2"}]} for i in range(1, 5)]


def test_atomic_segment_manifest_checksum_and_replay_no_live_mixing():
    with tempfile.TemporaryDirectory(prefix="pd2-test-", dir=Path.cwd()) as temp:
        tmp_path = Path(temp)
        frames = sample_frames()
        manifest = write_segment(tmp_path, frames, "s")
        assert read_segment(tmp_path, manifest) == frames
        live = [{"book_stream_id": "live", "book_sequence": 99}]
        assert replay_segment(tmp_path, manifest, live_frames=live) == frames
        assert not list(tmp_path.glob("*.tmp"))


def test_truncated_tail_and_checksum_fail_closed():
    with tempfile.TemporaryDirectory(prefix="pd2-test-", dir=Path.cwd()) as temp:
        tmp_path = Path(temp)
        frames = sample_frames()
        manifest = write_segment(tmp_path, frames, "s")
        path = tmp_path / manifest["segment"]
        path.write_bytes(path.read_bytes()[:-3])
        with pytest.raises(ValueError, match="CHECKSUM"):
            read_segment(tmp_path, manifest)


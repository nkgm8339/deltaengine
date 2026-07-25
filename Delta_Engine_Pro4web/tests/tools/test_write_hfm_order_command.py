from pathlib import Path

import pytest

from tools.write_hfm_order_command import build_command, publish


def test_build_command_requires_stop_loss():
    with pytest.raises(ValueError):
        build_command({"command_id": "x", "side": "BUY"})


def test_publish_atomically_writes_command(tmp_path: Path):
    path = tmp_path / "command.txt"
    publish(path, {
        "command_id": "episode-1", "side": "SELL",
        "stop_loss": 60100, "take_profit": 59900,
    })
    assert path.read_text(encoding="utf-8") == "episode-1|SELL|60100.00000000|59900.00000000\n"

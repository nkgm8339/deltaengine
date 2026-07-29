from pathlib import Path


def test_pd4_compose_keeps_persistent_writer_disabled():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "PERSISTENT_DEPTH_HISTORY_ENABLED=false" in compose
    assert "persistent writer remains disabled" in compose

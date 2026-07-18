"""Tests for webapp.version — CHANGELOG 単一情報源のバージョン解決。"""
from pathlib import Path

from fastapi.testclient import TestClient

from webapp.version import FALLBACK_VERSION, parse_version, resolve_version


def test_parse_version_latest_entry_wins():
    text = (
        "# CHANGELOG\n\nheader prose\n\n---\n\n"
        "# v3.6.3 — 2026-07-18\n\nbody\n\n---\n\n"
        "# v3.6.2 — 2026-07-18\n\nolder\n"
    )
    assert parse_version(text) == "v3.6.3"


def test_parse_version_no_heading_returns_none():
    assert parse_version("# CHANGELOG\n\nno version here\n") is None


def test_resolve_version_from_file(tmp_path: Path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text("# CHANGELOG\n\n# v9.9.9 — 2099-01-01\n", encoding="utf-8")
    assert resolve_version([p]) == "v9.9.9"


def test_resolve_version_missing_file_falls_back(tmp_path: Path):
    assert resolve_version([tmp_path / "absent.md"]) == FALLBACK_VERSION


def test_resolve_version_first_hit_wins(tmp_path: Path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# v1.0.0 — x\n", encoding="utf-8")
    b.write_text("# v2.0.0 — y\n", encoding="utf-8")
    assert resolve_version([a, b]) == "v1.0.0"


def test_api_version_endpoint(monkeypatch, tmp_path: Path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text("# CHANGELOG\n\n# v3.6.3 — 2026-07-18\n", encoding="utf-8")
    import webapp.version as ver
    monkeypatch.setattr(ver, "_CANDIDATE_PATHS", (p,))

    from webapp.main import app
    # 他テストの lifespan 実行で残留した app.state.version をリセットし、
    # エンドポイント内のフォールバック解決パスを検証する
    app.state.version = None
    client = TestClient(app)
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.json() == {"version": "v3.6.3"}

"""アプリバージョン解決 — CHANGELOG.md を単一情報源とする。

設計(CHANGELOG v3.6.3):
- バージョンの正は ArchitectureRepository/00_Master/CHANGELOG.md の最新エントリ
  見出し(例: `# v3.6.3 — 2026-07-18`)。コードへの手動転記は行わない。
- Documentation-First 規律により仕様書変更時は CHANGELOG 追記が義務のため、
  ドキュメント更新 → 次回起動時に UI バージョンが自動で上がる。
- 探索パス:
  1. CHANGELOG.md            … Docker(docker-compose が /app/CHANGELOG.md に RO マウント)
  2. ../ArchitectureRepository/00_Master/CHANGELOG.md … ローカル実行(cwd=Delta_Engine_Pro4web/)
- 未検出・パース不能時は FALLBACK_VERSION(起動は阻害しない)。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("webapp.version")

FALLBACK_VERSION = "v?.?.?"

_CANDIDATE_PATHS: tuple[Path, ...] = (
    Path("CHANGELOG.md"),
    Path("../ArchitectureRepository/00_Master/CHANGELOG.md"),
)

# 行頭の `# v3.6.3` 形式のみ。ファイル先頭側の最初の一致が最新エントリ。
_VERSION_RE = re.compile(r"^#\s*(v\d+\.\d+\.\d+)\b", re.MULTILINE)


def parse_version(text: str) -> str | None:
    """CHANGELOG 本文から最新バージョン文字列を返す。無ければ None。"""
    m = _VERSION_RE.search(text)
    return m.group(1) if m else None


def resolve_version(paths: Iterable[Path] | None = None) -> str:
    """候補パスを順に走査し、最初に解決できたバージョンを返す。

    失敗しても例外は送出せず FALLBACK_VERSION を返す(起動阻害禁止)。
    """
    for p in paths if paths is not None else _CANDIDATE_PATHS:
        try:
            if not p.is_file():
                continue
            v = parse_version(p.read_text(encoding="utf-8"))
            if v is not None:
                logger.info("app version %s (source: %s)", v, p)
                return v
            logger.warning("CHANGELOG found but no version heading: %s", p)
        except OSError as exc:  # 権限・IO 障害等
            logger.warning("CHANGELOG read failed: %s (%s)", p, exc)
    logger.warning("app version unresolved; falling back to %s", FALLBACK_VERSION)
    return FALLBACK_VERSION

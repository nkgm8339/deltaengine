"""Authoritative DuckDB plus committed-recent-ring Big Trades history reads."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Optional

from src.database.big_trades_storage import (
    BigTradesContentCollision,
    BigTradesDuckDbStore,
)
from src.orderflow.big_trades.constants import UserAssessmentValue, ZoneLifecycle
from src.orderflow.big_trades.runtime import RuntimeRecord
from src.orderflow.big_trades.time_buckets import require_aware_utc


UTC = timezone.utc
ID_PATTERNS = {
    "event": re.compile(r"^bt2_[0-9a-f]{64}$"),
    "zone": re.compile(r"^btz2_[0-9a-f]{64}$"),
    "interaction": re.compile(r"^bti2_[0-9a-f]{64}$"),
    "link": re.compile(r"^btl2_[0-9a-f]{64}$"),
    "snapshot": re.compile(r"^btsnap2_[0-9a-f]{64}$"),
    "candle": re.compile(r"^btcobs2_[0-9a-f]{64}$"),
    "assessment": re.compile(r"^btassess2_[0-9a-f]{64}$"),
    "calibration": re.compile(r"^btcal1_[0-9a-f]{64}$"),
    "activation": re.compile(r"^bta1_[0-9a-f]{64}$"),
    "settings": re.compile(r"^bts1_[0-9a-f]{64}$"),
}


def validate_identifier(kind: str, value: str) -> str:
    pattern = ID_PATTERNS.get(kind)
    if pattern is None or not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"invalid {kind}_id")
    return value


def validate_limit(limit: int, maximum: int = 5000) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return limit


def parse_aware_time(value: str | datetime, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} must be ISO8601") from exc
    else:
        raise ValueError(f"{name} must be ISO8601")
    try:
        return require_aware_utc(parsed, name)
    except ValueError as exc:
        raise ValueError(f"{name} must be timezone-aware") from exc


def _sort_time(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("persisted source time is invalid")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class BigTradesHistoryService:
    """History queries with deterministic ordering, cursors, and lineage."""

    def __init__(
        self,
        store: BigTradesDuckDbStore,
        *,
        symbol: str,
        venue: str,
        max_limit: int = 5000,
        recent_records: Optional[Callable[[], Iterable[RuntimeRecord]]] = None,
    ) -> None:
        if not symbol or not venue:
            raise ValueError("symbol and venue must be non-empty")
        self.store = store
        self.symbol = symbol
        self.venue = venue
        self.max_limit = validate_limit(max_limit, 5000)
        self._recent_records = recent_records or (lambda: ())

    @property
    def source_identity(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "symbol": self.symbol,
            "venue": self.venue,
            "input_mode": "AGGREGATE_TRADES",
            "logic_version": "BTLOGIC-2.0",
        }

    def _recent(self, kind: str) -> tuple[RuntimeRecord, ...]:
        return tuple(record for record in self._recent_records() if record.kind == kind)

    @staticmethod
    def _merge_rows(
        durable: Iterable[Mapping[str, Any]],
        recent: Iterable[RuntimeRecord],
        *,
        id_field: str,
    ) -> tuple[dict[str, Any], ...]:
        merged: dict[str, dict[str, Any]] = {}
        hashes: dict[str, str] = {}
        for row in durable:
            identifier = str(row[id_field])
            merged[identifier] = dict(row)
            if row.get("content_hash") is not None:
                hashes[identifier] = str(row["content_hash"])
        for record in recent:
            row = dict(record.payload)
            identifier = str(row.get(id_field, record.record_id))
            candidate_hash = record.content_hash
            prior_hash = hashes.get(identifier)
            if prior_hash is not None and prior_hash != candidate_hash:
                raise BigTradesContentCollision(
                    f"history durable/recent collision for {identifier}"
                )
            if identifier not in merged:
                row.setdefault(id_field, identifier)
                row.setdefault("content_hash", candidate_hash)
                merged[identifier] = row
            hashes[identifier] = candidate_hash
        return tuple(merged.values())

    @staticmethod
    def _cursor_filter(
        rows: Iterable[dict[str, Any]],
        *,
        time_field: str,
        id_field: str,
        before_time: Optional[datetime],
        before_id: Optional[str],
    ) -> list[dict[str, Any]]:
        buffered = list(rows)
        if before_time is None:
            return buffered
        assert before_id is not None
        cursor = (before_time, before_id)
        return [
            row
            for row in buffered
            if (_sort_time(row[time_field]), str(row[id_field])) < cursor
        ]

    @staticmethod
    def _page(
        rows: Iterable[dict[str, Any]],
        *,
        time_field: str,
        id_field: str,
        limit: int,
    ) -> tuple[tuple[dict[str, Any], ...], Optional[dict[str, Any]]]:
        ordered = sorted(
            rows,
            key=lambda row: (_sort_time(row[time_field]), str(row[id_field])),
        )
        selected = tuple(ordered[-limit:])
        cursor = None
        if len(ordered) > len(selected) and selected:
            cursor = {
                "before_source_time": selected[0][time_field],
                "before_id": selected[0][id_field],
            }
        return selected, cursor

    @staticmethod
    def _validate_cursor(
        *,
        before_source_time: Optional[str | datetime],
        before_id: Optional[str],
        id_kind: str,
    ) -> tuple[Optional[datetime], Optional[str]]:
        if (before_source_time is None) != (before_id is None):
            raise ValueError("before_source_time and before_id must be supplied together")
        if before_source_time is None:
            return None, None
        return (
            parse_aware_time(before_source_time, "before_source_time"),
            validate_identifier(id_kind, before_id or ""),
        )

    def _assessment_rows(
        self,
        zone_id: Optional[str] = None,
        zone_ids: Optional[Iterable[str]] = None,
    ) -> tuple[dict[str, Any], ...]:
        if zone_id is None and zone_ids is None:
            return self.store.fetch_rows(
                "big_trade_user_assessments",
                order_by="assessed_at_utc ASC, assessment_id ASC",
            )
        if zone_id is not None:
            return self.store.fetch_rows(
                "big_trade_user_assessments",
                where="zone_id = ?",
                parameters=(zone_id,),
                order_by="assessed_at_utc ASC, assessment_id ASC",
            )
        identifiers = tuple(dict.fromkeys(zone_ids or ()))
        if not identifiers:
            return ()
        return self.store.fetch_rows(
            "big_trade_user_assessments",
            where="zone_id IN (" + ",".join("?" for _ in identifiers) + ")",
            parameters=identifiers,
            order_by="assessed_at_utc ASC, assessment_id ASC",
        )

    @staticmethod
    def _latest_assessment(
        rows: Iterable[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        buffered = tuple(dict(row) for row in rows)
        superseded = {
            str(row["supersedes_assessment_id"])
            for row in buffered
            if row.get("supersedes_assessment_id") is not None
        }
        candidates = [
            row for row in buffered if str(row["assessment_id"]) not in superseded
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda row: (_sort_time(row["assessed_at_utc"]), row["assessment_id"]),
        )

    def _zone_assessment_map(
        self, zone_ids: Optional[Iterable[str]] = None
    ) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self._assessment_rows(zone_ids=zone_ids):
            grouped.setdefault(str(row["zone_id"]), []).append(row)
        return {
            zone_id: latest
            for zone_id, rows in grouped.items()
            if (latest := self._latest_assessment(rows)) is not None
        }

    def _zone_state_map(
        self, zone_ids: Iterable[str]
    ) -> dict[str, tuple[str, Optional[str]]]:
        identifiers = tuple(dict.fromkeys(zone_ids))
        states = {
            zone_id: (ZoneLifecycle.ACTIVE.value, None) for zone_id in identifiers
        }
        if not identifiers:
            return states
        placeholders = ",".join("?" for _ in identifiers)
        interactions = self.store.fetch_rows(
            "big_trade_zone_interactions",
            where=f"zone_id IN ({placeholders})",
            parameters=identifiers,
            order_by="zone_id ASC, source_event_time ASC, ordinal ASC, interaction_id ASC",
        )
        for row in interactions:
            lifecycle, relation = states[row["zone_id"]]
            kind = row["interaction_type"]
            if kind == "SOURCE_GAP_STARTED":
                lifecycle = ZoneLifecycle.ACTIVE_WITH_GAP.value
            elif kind == "SOURCE_GAP_ENDED":
                lifecycle = ZoneLifecycle.ACTIVE.value
            elif kind == "ZONE_SESSION_CLOSED":
                lifecycle = ZoneLifecycle.SESSION_CLOSED.value
            if row.get("current_relation") is not None:
                relation = row["current_relation"]
            states[row["zone_id"]] = lifecycle, relation
        checkpoints = self.store.fetch_rows(
            "big_trade_zone_state_checkpoints",
            where=f"zone_id IN ({placeholders})",
            parameters=identifiers,
            order_by="zone_id ASC, source_bucket_time ASC",
        )
        for row in checkpoints:
            lifecycle, _ = states[row["zone_id"]]
            states[row["zone_id"]] = lifecycle, row["current_relation"]
        return states

    def list_events(
        self,
        *,
        limit: int = 500,
        before_source_time: Optional[str | datetime] = None,
        before_id: Optional[str] = None,
        side: Optional[str] = None,
        lifecycle: Optional[str] = None,
        assessment: Optional[str] = None,
    ) -> dict[str, Any]:
        limit = validate_limit(limit, self.max_limit)
        before_time, parsed_before_id = self._validate_cursor(
            before_source_time=before_source_time,
            before_id=before_id,
            id_kind="event",
        )
        if side is not None and side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if lifecycle is not None:
            lifecycle = ZoneLifecycle(lifecycle).value
        if assessment is not None:
            assessment = UserAssessmentValue(assessment).value
        where = "symbol = ? AND venue = ?"
        params: list[Any] = [self.symbol, self.venue]
        if side is not None:
            where += " AND side = ?"
            params.append(side)
        if before_time is not None:
            where += " AND (last_time < ? OR (last_time = ? AND event_id < ?))"
            params.extend((before_time, before_time, parsed_before_id))
        durable = self.store.fetch_rows(
            "big_trade_events",
            where=where,
            parameters=params,
            order_by="last_time DESC, event_id DESC",
            limit=self.max_limit + 1,
        )
        merged = self._merge_rows(
            durable,
            self._recent("EVENT_CREATED"),
            id_field="event_id",
        )
        rows = [
            row
            for row in merged
            if row.get("symbol") == self.symbol
            and row.get("venue") == self.venue
            and (side is None or row.get("side") == side)
        ]
        if assessment is not None or lifecycle is not None:
            zones = self.store.fetch_rows(
                "big_trade_reaction_zones",
                where="symbol = ? AND venue = ?",
                parameters=(self.symbol, self.venue),
            )
            event_zone = {row["origin_event_id"]: row["zone_id"] for row in zones}
            relevant_zone_ids = tuple(event_zone.get(row["event_id"]) for row in rows)
            relevant_zone_ids = tuple(item for item in relevant_zone_ids if item is not None)
            latest = self._zone_assessment_map(relevant_zone_ids)
            states = self._zone_state_map(relevant_zone_ids)
            rows = [
                row
                for row in rows
                if (
                    assessment is None
                    or (
                        latest.get(event_zone.get(row["event_id"], ""), {}).get(
                            "assessment"
                        )
                        or UserAssessmentValue.UNASSESSED.value
                    )
                    == assessment
                )
                and (
                    lifecycle is None
                    or (
                        event_zone.get(row["event_id"]) is not None
                        and states[event_zone[row["event_id"]]][0] == lifecycle
                    )
                )
            ]
        rows = self._cursor_filter(
            rows,
            time_field="last_time",
            id_field="event_id",
            before_time=before_time,
            before_id=parsed_before_id,
        )
        selected, cursor = self._page(
            rows, time_field="last_time", id_field="event_id", limit=limit
        )
        return {
            "source_identity": self.source_identity,
            "events": selected,
            "next_cursor": cursor,
        }

    def _lifecycle_and_relation(self, zone_id: str) -> tuple[str, Optional[str]]:
        interactions = self.store.fetch_rows(
            "big_trade_zone_interactions",
            where="zone_id = ?",
            parameters=(zone_id,),
            order_by="source_event_time ASC, ordinal ASC, interaction_id ASC",
        )
        lifecycle = ZoneLifecycle.ACTIVE.value
        relation = None
        for row in interactions:
            kind = row["interaction_type"]
            if kind == "SOURCE_GAP_STARTED":
                lifecycle = ZoneLifecycle.ACTIVE_WITH_GAP.value
            elif kind == "SOURCE_GAP_ENDED":
                lifecycle = ZoneLifecycle.ACTIVE.value
            elif kind == "ZONE_SESSION_CLOSED":
                lifecycle = ZoneLifecycle.SESSION_CLOSED.value
            if row.get("current_relation") is not None:
                relation = row["current_relation"]
        checkpoints = self.store.fetch_rows(
            "big_trade_zone_state_checkpoints",
            where="zone_id = ?",
            parameters=(zone_id,),
            order_by="source_bucket_time DESC",
            limit=1,
        )
        if checkpoints:
            relation = checkpoints[0]["current_relation"]
        return lifecycle, relation

    def list_zones(
        self,
        *,
        limit: int = 500,
        before_source_time: Optional[str | datetime] = None,
        before_id: Optional[str] = None,
        side: Optional[str] = None,
        lifecycle: Optional[str] = None,
        assessment: Optional[str] = None,
    ) -> dict[str, Any]:
        limit = validate_limit(limit, self.max_limit)
        before_time, parsed_before_id = self._validate_cursor(
            before_source_time=before_source_time,
            before_id=before_id,
            id_kind="zone",
        )
        if side is not None and side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if lifecycle is not None:
            lifecycle = ZoneLifecycle(lifecycle).value
        if assessment is not None:
            assessment = UserAssessmentValue(assessment).value
        durable = self.store.fetch_rows(
            "big_trade_reaction_zones",
            where=(
                "symbol = ? AND venue = ?"
                + (
                    " AND (zone_source_start < ? OR "
                    "(zone_source_start = ? AND zone_id < ?))"
                    if before_time is not None
                    else ""
                )
            ),
            parameters=(
                (self.symbol, self.venue, before_time, before_time, parsed_before_id)
                if before_time is not None
                else (self.symbol, self.venue)
            ),
            order_by="zone_source_start DESC, zone_id DESC",
            limit=self.max_limit + 1,
        )
        merged = self._merge_rows(
            durable,
            self._recent("ZONE_CREATED"),
            id_field="zone_id",
        )
        merged_zone_ids = tuple(row["zone_id"] for row in merged)
        latest_assessments = self._zone_assessment_map(merged_zone_ids)
        states = self._zone_state_map(merged_zone_ids)
        rows: list[dict[str, Any]] = []
        for row in merged:
            if row.get("symbol") != self.symbol or row.get("venue") != self.venue:
                continue
            if side is not None and row.get("origin_side") != side:
                continue
            actual_lifecycle, relation = states[row["zone_id"]]
            latest = latest_assessments.get(row["zone_id"])
            actual_assessment = (
                latest["assessment"] if latest else UserAssessmentValue.UNASSESSED.value
            )
            if lifecycle is not None and actual_lifecycle != lifecycle:
                continue
            if assessment is not None and actual_assessment != assessment:
                continue
            enriched = dict(row)
            enriched["lifecycle"] = actual_lifecycle
            enriched["current_relation"] = relation
            enriched["latest_user_assessment"] = latest
            rows.append(enriched)
        rows = self._cursor_filter(
            rows,
            time_field="zone_source_start",
            id_field="zone_id",
            before_time=before_time,
            before_id=parsed_before_id,
        )
        selected, cursor = self._page(
            rows,
            time_field="zone_source_start",
            id_field="zone_id",
            limit=limit,
        )
        return {
            "source_identity": self.source_identity,
            "zones": selected,
            "next_cursor": cursor,
        }

    def _one(self, table: str, id_field: str, identifier: str) -> dict[str, Any]:
        rows = self.store.fetch_rows(
            table,
            where=f"{id_field} = ?",
            parameters=(identifier,),
            limit=1,
        )
        if not rows:
            raise KeyError(identifier)
        return rows[0]

    def event_fills(
        self, event_id: str, *, limit: int = 500, after_ordinal: int = 0
    ) -> dict[str, Any]:
        validate_identifier("event", event_id)
        limit = validate_limit(limit, self.max_limit)
        if isinstance(after_ordinal, bool) or not isinstance(after_ordinal, int) or after_ordinal < 0:
            raise ValueError("after_ordinal must be a non-negative integer")
        self._one("big_trade_events", "event_id", event_id)
        rows = self.store.fetch_rows(
            "big_trade_event_fills",
            where="event_id = ? AND fill_ordinal > ?",
            parameters=(event_id, after_ordinal),
            order_by="fill_ordinal ASC",
            limit=limit,
        )
        return {"event_id": event_id, "fills": rows}

    def zone_interactions(
        self, zone_id: str, *, limit: int = 500, after_ordinal: int = 0
    ) -> dict[str, Any]:
        validate_identifier("zone", zone_id)
        limit = validate_limit(limit, self.max_limit)
        self._one("big_trade_reaction_zones", "zone_id", zone_id)
        rows = self.store.fetch_rows(
            "big_trade_zone_interactions",
            where="zone_id = ? AND ordinal > ?",
            parameters=(zone_id, after_ordinal),
            order_by="source_event_time ASC, ordinal ASC, interaction_id ASC",
            limit=limit,
        )
        return {"zone_id": zone_id, "interactions": rows}

    def zone_links(
        self, zone_id: str, *, limit: int = 500, after_ordinal: int = 0
    ) -> dict[str, Any]:
        validate_identifier("zone", zone_id)
        limit = validate_limit(limit, self.max_limit)
        self._one("big_trade_reaction_zones", "zone_id", zone_id)
        rows = self.store.fetch_rows(
            "big_trade_zone_event_links",
            where="zone_id = ? AND ordinal_for_zone > ?",
            parameters=(zone_id, after_ordinal),
            order_by="ordinal_for_zone ASC, link_id ASC",
            limit=limit,
        )
        return {"zone_id": zone_id, "linked_events": rows}

    def zone_snapshots(
        self, zone_id: str, *, limit: int = 500, after_horizon_seconds: int = 0
    ) -> dict[str, Any]:
        validate_identifier("zone", zone_id)
        limit = validate_limit(limit, self.max_limit)
        self._one("big_trade_reaction_zones", "zone_id", zone_id)
        rows = self.store.fetch_rows(
            "big_trade_result_snapshots",
            where="zone_id = ? AND horizon_seconds > ?",
            parameters=(zone_id, after_horizon_seconds),
            order_by="horizon_seconds ASC, snapshot_id ASC",
            limit=limit,
        )
        return {"zone_id": zone_id, "snapshots": rows}

    def zone_candles(
        self,
        zone_id: str,
        *,
        limit: int = 500,
        after_candle_id: Optional[str | datetime] = None,
    ) -> dict[str, Any]:
        validate_identifier("zone", zone_id)
        limit = validate_limit(limit, self.max_limit)
        self._one("big_trade_reaction_zones", "zone_id", zone_id)
        where = "zone_id = ?"
        params: list[Any] = [zone_id]
        if after_candle_id is not None:
            where += " AND candle_id > ?"
            params.append(parse_aware_time(after_candle_id, "after_candle_id"))
        rows = self.store.fetch_rows(
            "big_trade_zone_candle_observations",
            where=where,
            parameters=params,
            order_by="candle_id ASC, candle_observation_id ASC",
            limit=limit,
        )
        return {"zone_id": zone_id, "candles": rows}

    def zone_assessments(self, zone_id: str, *, limit: int = 500) -> dict[str, Any]:
        validate_identifier("zone", zone_id)
        limit = validate_limit(limit, self.max_limit)
        self._one("big_trade_reaction_zones", "zone_id", zone_id)
        rows = self.store.fetch_rows(
            "big_trade_user_assessments",
            where="zone_id = ?",
            parameters=(zone_id,),
            order_by="assessed_at_utc ASC, assessment_id ASC",
            limit=limit,
        )
        return {
            "zone_id": zone_id,
            "assessments": rows,
            "latest": self._latest_assessment(rows),
        }

    def zone_detail(self, zone_id: str) -> dict[str, Any]:
        validate_identifier("zone", zone_id)
        zone = self._one("big_trade_reaction_zones", "zone_id", zone_id)
        event = self._one("big_trade_events", "event_id", zone["origin_event_id"])
        interactions = self.zone_interactions(zone_id, limit=self.max_limit)["interactions"]
        links = self.zone_links(zone_id, limit=self.max_limit)["linked_events"]
        snapshots = self.zone_snapshots(zone_id, limit=self.max_limit)["snapshots"]
        candles = self.zone_candles(zone_id, limit=self.max_limit)["candles"]
        assessments = self.zone_assessments(zone_id, limit=self.max_limit)
        checkpoints = self.store.fetch_rows(
            "big_trade_zone_state_checkpoints",
            where="zone_id = ?",
            parameters=(zone_id,),
            order_by="source_bucket_time ASC",
        )
        lifecycle, current_relation = self._lifecycle_and_relation(zone_id)
        first_exit = next(
            (
                row
                for row in interactions
                if row["interaction_type"] in {"FIRST_EXIT_UP", "FIRST_EXIT_DOWN"}
            ),
            None,
        )
        interaction_counts = Counter(row["interaction_type"] for row in interactions)
        gaps: list[dict[str, Any]] = []
        open_gaps: dict[str, dict[str, Any]] = {}
        for row in interactions:
            gap_id = row.get("gap_epoch_id")
            if not gap_id:
                continue
            if row["interaction_type"] == "SOURCE_GAP_STARTED":
                open_gaps[gap_id] = {
                    "gap_epoch_id": gap_id,
                    "start_time": row["source_event_time"],
                    "end_time": None,
                }
            elif row["interaction_type"] == "SOURCE_GAP_ENDED":
                segment = open_gaps.pop(
                    gap_id,
                    {"gap_epoch_id": gap_id, "start_time": None, "end_time": None},
                )
                segment["end_time"] = row["source_event_time"]
                gaps.append(segment)
        gaps.extend(open_gaps.values())
        latest_checkpoint = checkpoints[-1] if checkpoints else None
        return {
            "source_identity": self.source_identity,
            "zone": {
                **zone,
                "lifecycle": lifecycle,
                "current_relation": current_relation,
                "final_relation": (
                    current_relation if lifecycle == ZoneLifecycle.SESSION_CLOSED.value else None
                ),
            },
            "origin_event": event,
            "fills_summary": {
                "fill_count": event["fill_count"],
                "first_trade_id": event["first_trade_id"],
                "last_trade_id": event["last_trade_id"],
                "aggregate_quantity": event["aggregate_quantity"],
                "aggregate_notional": event["aggregate_notional"],
                "vwap": event["vwap"],
                "price_level_count": event["price_level_count"],
            },
            "first_exit": first_exit,
            "excursions": {
                "max_above_ticks": max(
                    (row["max_above_ticks"] for row in snapshots),
                    default=Decimal("0"),
                ),
                "max_below_ticks": max(
                    (row["max_below_ticks"] for row in snapshots),
                    default=Decimal("0"),
                ),
            },
            "interaction_counts": dict(interaction_counts),
            "linked_event_summary": links,
            "horizon_snapshots": snapshots,
            "candle_observations": candles,
            "gap_segments": sorted(
                gaps,
                key=lambda row: row["start_time"] or datetime.min.replace(tzinfo=UTC),
            ),
            "latest_user_assessment": assessments["latest"],
            "latest_checkpoint": latest_checkpoint,
            "lineage_ids": {
                "event_id": event["event_id"],
                "zone_id": zone["zone_id"],
                "settings_id": zone["settings_id"],
                "calibration_id": zone["calibration_id"],
                "activation_id": zone["activation_id"],
                "logic_version": zone["logic_version"],
            },
        }

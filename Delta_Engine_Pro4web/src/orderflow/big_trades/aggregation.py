"""40 ms same-side execution clustering and immutable event construction."""

from __future__ import annotations

from typing import Optional

from .constants import (
    AGGREGATION_WINDOW_MS,
    ClusterCloseReason,
    MarkerPriceMode,
)
from .ids import content_hash, event_id_for_cluster
from .models import (
    BigTradeEvent,
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ExecutionCluster,
    FilterDecision,
)


class ExecutionClusterAggregator:
    def __init__(self, *, max_fills_per_cluster: int = 10_000) -> None:
        if (
            not isinstance(max_fills_per_cluster, int)
            or isinstance(max_fills_per_cluster, bool)
            or max_fills_per_cluster < 1
        ):
            raise ValueError("max_fills_per_cluster must be a positive integer")
        self.max_fills_per_cluster = max_fills_per_cluster
        self._fills: list[BigTradeFill] = []
        self._settings: Optional[BigTradesSettingsSnapshot] = None

    def process(
        self,
        trade: BigTradeFill,
        settings: BigTradesSettingsSnapshot,
    ) -> tuple[ExecutionCluster, ...]:
        self._validate_identity(trade, settings)
        if not self._fills:
            self._start(trade, settings)
            return ()

        reason = self._close_reason(trade, settings)
        if reason is None and len(self._fills) >= self.max_fills_per_cluster:
            reason = ClusterCloseReason.MAX_FILLS_EXCEEDED
        if reason is None:
            self._fills.append(trade)
            return ()

        closed = self._close(reason)
        self._start(trade, settings)
        return (closed,)

    def flush(self, reason: ClusterCloseReason = ClusterCloseReason.STREAM_ENDED) -> tuple[ExecutionCluster, ...]:
        if not self._fills:
            return ()
        return (self._close(reason),)

    def disconnect(self) -> tuple[ExecutionCluster, ...]:
        return self.flush(ClusterCloseReason.STREAM_DISCONNECTED)

    def force_settings_flush(self) -> tuple[ExecutionCluster, ...]:
        return self.flush(ClusterCloseReason.SETTINGS_FORCED_FLUSH)

    def _start(self, trade: BigTradeFill, settings: BigTradesSettingsSnapshot) -> None:
        self._fills = [trade]
        self._settings = settings

    def _close(self, reason: ClusterCloseReason) -> ExecutionCluster:
        assert self._settings is not None
        cluster = ExecutionCluster(tuple(self._fills), self._settings, reason)
        self._fills = []
        self._settings = None
        return cluster

    def _close_reason(
        self,
        trade: BigTradeFill,
        settings: BigTradesSettingsSnapshot,
    ) -> Optional[ClusterCloseReason]:
        previous = self._fills[-1]
        first = self._fills[0]
        assert self._settings is not None
        if trade.symbol != first.symbol or trade.venue != first.venue:
            return ClusterCloseReason.SYMBOL_CHANGED
        if trade.side != first.side:
            return ClusterCloseReason.SIDE_CHANGED
        if trade.session_id != first.session_id:
            return ClusterCloseReason.SESSION_CHANGED
        if trade.candle_id != first.candle_id:
            return ClusterCloseReason.CANDLE_CHANGED
        if trade.event_time_ms - previous.event_time_ms > AGGREGATION_WINDOW_MS:
            return ClusterCloseReason.TIME_GAP_EXCEEDED
        if trade.source_key < previous.source_key:
            raise ValueError("aggregator requires source-ordered trades")
        return None

    @staticmethod
    def _validate_identity(trade: BigTradeFill, settings: BigTradesSettingsSnapshot) -> None:
        if trade.symbol != settings.symbol or trade.venue != settings.venue:
            raise ValueError("trade identity does not match settings")

    @property
    def pending_fill_count(self) -> int:
        return len(self._fills)


def create_big_trade_event(
    cluster: ExecutionCluster,
    decision: FilterDecision,
) -> BigTradeEvent:
    if cluster.close_reason is ClusterCloseReason.MAX_FILLS_EXCEEDED:
        raise ValueError("cannot create BigTradeEvent from an invalid max-fills cluster")
    if not decision.accepted:
        raise ValueError("cannot create BigTradeEvent from a rejected cluster")
    mode = cluster.settings.marker_price_mode
    if mode is MarkerPriceMode.START_PRICE:
        marker_time = cluster.first_time
        marker_price = cluster.first_price
    elif mode is MarkerPriceMode.LAST_PRICE:
        marker_time = cluster.last_time
        marker_price = cluster.last_price
    else:
        marker_time = cluster.last_time
        marker_price = cluster.vwap

    event_id = event_id_for_cluster(cluster)
    payload = {
        "event_id": event_id,
        "logic_version": cluster.logic_version,
        "symbol": cluster.symbol,
        "venue": cluster.venue,
        "side": cluster.side,
        "input_mode": cluster.input_mode,
        "first_trade_id": cluster.first_trade_id,
        "last_trade_id": cluster.last_trade_id,
        "first_time": cluster.first_time,
        "last_time": cluster.last_time,
        "event_time": cluster.last_time,
        "marker_time": marker_time,
        "first_price": cluster.first_price,
        "last_price": cluster.last_price,
        "marker_price": marker_price,
        "low_price": cluster.low_price,
        "high_price": cluster.high_price,
        "vwap": cluster.vwap,
        "aggregate_quantity": cluster.aggregate_quantity,
        "aggregate_notional": cluster.aggregate_notional,
        "fill_count": cluster.fill_count,
        "price_level_count": cluster.price_level_count,
        "duration_ms": cluster.duration_ms,
        "close_reason": cluster.close_reason,
        "filter_mode": decision.filter_mode,
        "intensity": decision.intensity,
        "threshold_used": decision.threshold_used,
        "max_threshold_used": decision.max_threshold_used,
        "side_filter": cluster.settings.side_filter,
        "marker_price_mode": mode,
        "settings_id": cluster.settings.settings_id,
        "calibration_id": decision.calibration_id,
        "activation_id": cluster.settings.activation_id,
        "session_id": cluster.session_id,
        "candle_id": cluster.candle_id,
    }
    return BigTradeEvent(content_hash=content_hash(payload), **payload)

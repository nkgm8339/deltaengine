"""Retired Flow-only execution prototype and reusable HFM gateway plumbing.

The Flow-only state-to-side mapping was not an integrated Order Flow ENTRY GO
and is prohibited from LIVE execution. ``FlowExecutionController`` therefore
supports observation and ``order_check`` only. ``Mt5MarketOrderGateway`` keeps
the separately testable send plumbing for a future approved integrated GO.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Protocol


FLOW_STATE_TO_SIDE: dict[str, str] = {
    "BUY_EFFECTIVE": "BUY",
    "SELL_EFFECTIVE": "SELL",
    "BUY_TRAPPED": "SELL",
    "SELL_TRAPPED": "BUY",
}

EXECUTION_MODES = frozenset({"observe", "check", "live"})
FLOW_CONTROLLER_MODES = frozenset({"observe", "check"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if hasattr(value, "_asdict"):
        return {str(k): _json_safe(v) for k, v in value._asdict().items()}
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _pick_fields(value: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if value is None:
        return None
    return {field: _json_safe(getattr(value, field, None)) for field in fields}


def _event_lag_ms(source_time: str | None, received_at: str) -> int | None:
    if not source_time:
        return None
    try:
        source = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
        received = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if source.tzinfo is None:
        source = source.replace(tzinfo=timezone.utc)
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    return round((received - source).total_seconds() * 1000)


def _event_id(source_time: str, window_sec: int, previous: str, current: str) -> str:
    raw = f"{source_time}|{window_sec}|{previous}|{current}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


@dataclass(frozen=True)
class FlowTransition:
    kind: str
    window_sec: int
    previous_state: str | None
    state: str
    side: str | None


class FlowTransitionDetector:
    """Detect a first state transition without treating startup as an entry."""

    def __init__(self, window_sec: int) -> None:
        if window_sec <= 0:
            raise ValueError("window_sec must be positive")
        self.window_sec = int(window_sec)
        self.last_state: str | None = None

    def observe(self, state: str) -> FlowTransition:
        current = str(state).strip().upper()
        if not current:
            raise ValueError("state is empty")

        previous = self.last_state
        self.last_state = current
        if previous is None:
            return FlowTransition(
                kind="BASELINE",
                window_sec=self.window_sec,
                previous_state=None,
                state=current,
                side=None,
            )
        if previous == current:
            return FlowTransition(
                kind="UNCHANGED",
                window_sec=self.window_sec,
                previous_state=previous,
                state=current,
                side=None,
            )
        return FlowTransition(
            kind="ENTRY" if current in FLOW_STATE_TO_SIDE else "TRANSITION",
            window_sec=self.window_sec,
            previous_state=previous,
            state=current,
            side=FLOW_STATE_TO_SIDE.get(current),
        )


class AuditSink(Protocol):
    def append(self, record: Mapping[str, Any]) -> None: ...


class JsonlAuditLog:
    """Append-only, flushed JSONL audit trail."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: Mapping[str, Any]) -> None:
        payload = json.dumps(_json_safe(dict(record)), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())


class Mt5MarketOrderGateway:
    """Direct MetaTrader5 gateway with visible check and send results."""

    def __init__(
        self,
        *,
        terminal_path: str,
        symbol: str,
        volume: Decimal | str = Decimal("0.01"),
        deviation_points: int = 5000,
        magic: int = 520260726,
        mt5_module: Any | None = None,
    ) -> None:
        self.terminal_path = terminal_path
        self.symbol = symbol
        self.volume = Decimal(str(volume))
        self.deviation_points = int(deviation_points)
        self.magic = int(magic)
        self._mt5 = mt5_module
        self._lock = threading.Lock()

        if self.volume <= 0:
            raise ValueError("volume must be positive")
        if self.deviation_points < 0:
            raise ValueError("deviation_points must be non-negative")

    def _module(self) -> Any:
        if self._mt5 is None:
            import MetaTrader5 as mt5

            self._mt5 = mt5
        return self._mt5

    def _initialize(self) -> tuple[Any, dict[str, Any] | None]:
        mt5 = self._module()
        if not mt5.initialize(path=self.terminal_path):
            return mt5, {
                "stage": "MT5_INITIALIZE",
                "status": "REJECTED",
                "last_error": _json_safe(mt5.last_error()),
                "terminal_path": self.terminal_path,
            }
        return mt5, None

    def inspect(self) -> dict[str, Any]:
        with self._lock:
            mt5, error = self._initialize()
            if error:
                return error
            terminal = mt5.terminal_info()
            account = mt5.account_info()
            symbol = mt5.symbol_info(self.symbol)
            tick = mt5.symbol_info_tick(self.symbol) if symbol else None
            return {
                "stage": "MT5_INSPECT",
                "status": "READY" if terminal and account and symbol and tick else "REJECTED",
                "last_error": _json_safe(mt5.last_error()),
                "terminal": _pick_fields(
                    terminal,
                    (
                        "connected",
                        "trade_allowed",
                        "tradeapi_disabled",
                        "build",
                        "path",
                    ),
                ),
                "account": _pick_fields(
                    account,
                    (
                        "server",
                        "currency",
                        "trade_mode",
                        "trade_allowed",
                        "trade_expert",
                        "margin_mode",
                    ),
                ),
                "symbol": _pick_fields(
                    symbol,
                    (
                        "name",
                        "visible",
                        "trade_mode",
                        "trade_exemode",
                        "filling_mode",
                        "volume_min",
                        "volume_max",
                        "volume_step",
                        "digits",
                        "point",
                        "bid",
                        "ask",
                    ),
                ),
                "tick": _pick_fields(tick, ("time", "time_msc", "bid", "ask")),
                "positions_count": len(mt5.positions_get(symbol=self.symbol) or ()),
                "orders_count": len(mt5.orders_get(symbol=self.symbol) or ()),
            }

    @staticmethod
    def _volume_error(volume: Decimal, symbol_info: Any) -> str | None:
        try:
            minimum = Decimal(str(symbol_info.volume_min))
            maximum = Decimal(str(symbol_info.volume_max))
            step = Decimal(str(symbol_info.volume_step))
        except (AttributeError, InvalidOperation) as exc:
            return f"invalid symbol volume metadata: {exc}"
        if volume < minimum or volume > maximum:
            return f"volume {volume} outside [{minimum}, {maximum}]"
        if step <= 0:
            return f"invalid volume step {step}"
        if volume % step != 0:
            return f"volume {volume} is not aligned to step {step}"
        return None

    @staticmethod
    def _filling_type(mt5: Any, symbol_info: Any) -> int:
        flags = int(getattr(symbol_info, "filling_mode", 0))
        if flags & int(getattr(mt5, "SYMBOL_FILLING_FOK", 1)):
            return int(mt5.ORDER_FILLING_FOK)
        if flags & int(getattr(mt5, "SYMBOL_FILLING_IOC", 2)):
            return int(mt5.ORDER_FILLING_IOC)
        return int(mt5.ORDER_FILLING_RETURN)

    def execute(self, side: str, *, mode: str, context: Mapping[str, Any]) -> dict[str, Any]:
        requested_side = str(side).strip().upper()
        requested_mode = str(mode).strip().lower()
        if requested_side not in {"BUY", "SELL"}:
            raise ValueError(f"unsupported side: {side!r}")
        if requested_mode not in EXECUTION_MODES:
            raise ValueError(f"unsupported execution mode: {mode!r}")

        with self._lock:
            mt5, init_error = self._initialize()
            if init_error:
                return {**init_error, "mode": requested_mode, "context": _json_safe(context)}

            terminal = mt5.terminal_info()
            account = mt5.account_info()
            symbol_info = mt5.symbol_info(self.symbol)
            if terminal is None or account is None or symbol_info is None:
                return {
                    "stage": "MT5_PREFLIGHT",
                    "status": "REJECTED",
                    "mode": requested_mode,
                    "last_error": _json_safe(mt5.last_error()),
                    "terminal_present": terminal is not None,
                    "account_present": account is not None,
                    "symbol_present": symbol_info is not None,
                    "context": _json_safe(context),
                }

            if not bool(getattr(symbol_info, "visible", False)):
                if not mt5.symbol_select(self.symbol, True):
                    return {
                        "stage": "MT5_PREFLIGHT",
                        "status": "REJECTED",
                        "mode": requested_mode,
                        "reason": "symbol_select_failed",
                        "last_error": _json_safe(mt5.last_error()),
                        "context": _json_safe(context),
                    }
                symbol_info = mt5.symbol_info(self.symbol)

            volume_error = self._volume_error(self.volume, symbol_info)
            if volume_error:
                return {
                    "stage": "MT5_PREFLIGHT",
                    "status": "REJECTED",
                    "mode": requested_mode,
                    "reason": volume_error,
                    "context": _json_safe(context),
                }

            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                return {
                    "stage": "MT5_PREFLIGHT",
                    "status": "REJECTED",
                    "mode": requested_mode,
                    "reason": "tick_unavailable",
                    "last_error": _json_safe(mt5.last_error()),
                    "context": _json_safe(context),
                }

            request_price = float(tick.ask if requested_side == "BUY" else tick.bid)
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": float(self.volume),
                "type": mt5.ORDER_TYPE_BUY if requested_side == "BUY" else mt5.ORDER_TYPE_SELL,
                "price": request_price,
                "deviation": self.deviation_points,
                "magic": self.magic,
                "comment": (
                    f"DE05M_F{context.get('window_sec', '')}_"
                    f"{str(context.get('event_id', ''))[:12]}"
                ),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": self._filling_type(mt5, symbol_info),
            }
            common = {
                "mode": requested_mode,
                "side": requested_side,
                "symbol": self.symbol,
                "volume": str(self.volume),
                "hfm_bid": str(tick.bid),
                "hfm_ask": str(tick.ask),
                "request_price": str(request_price),
                "terminal_trade_allowed": bool(getattr(terminal, "trade_allowed", False)),
                "terminal_tradeapi_disabled": bool(getattr(terminal, "tradeapi_disabled", False)),
                "account_trade_allowed": bool(getattr(account, "trade_allowed", False)),
                "account_trade_expert": bool(getattr(account, "trade_expert", False)),
                "request": _json_safe(request),
                "context": _json_safe(context),
            }

            if requested_mode == "observe":
                return {
                    "stage": "ORDER_INTENT",
                    "status": "OBSERVED",
                    **common,
                }

            check = mt5.order_check(request)
            check_payload = _json_safe(check)
            check_retcode = getattr(check, "retcode", None) if check is not None else None
            check_ok = check is not None and int(check_retcode) in {
                0,
                int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
            }
            if not check_ok:
                return {
                    "stage": "MT5_ORDER_CHECK",
                    "status": "REJECTED",
                    "check": check_payload,
                    "last_error": _json_safe(mt5.last_error()),
                    **common,
                }

            if requested_mode == "check":
                return {
                    "stage": "MT5_ORDER_CHECK",
                    "status": "CHECK_OK",
                    "check": check_payload,
                    **common,
                }

            result = mt5.order_send(request)
            result_payload = _json_safe(result)
            result_retcode = getattr(result, "retcode", None) if result is not None else None
            done = int(getattr(mt5, "TRADE_RETCODE_DONE", 10009))
            partial = int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010))
            placed = int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))
            if result is None:
                result_status = "REJECTED"
            elif int(result_retcode) == done:
                result_status = "FILLED"
            elif int(result_retcode) == partial:
                result_status = "PARTIAL"
            elif int(result_retcode) == placed:
                result_status = "PLACED"
            else:
                result_status = "REJECTED"
            return {
                "stage": "MT5_ORDER_SEND",
                "status": result_status,
                "check": check_payload,
                "result": result_payload,
                "retcode": result_retcode,
                "order_ticket": getattr(result, "order", None) if result is not None else None,
                "deal_ticket": getattr(result, "deal", None) if result is not None else None,
                "fill_price": (
                    str(getattr(result, "price", ""))
                    if result is not None and getattr(result, "price", None) is not None
                    else None
                ),
                "last_error": _json_safe(mt5.last_error()),
                **common,
            }


class FlowExecutionController:
    """Retired Flow-only bridge, fail-closed against LIVE order submission."""

    def __init__(
        self,
        *,
        window_sec: int,
        mode: str,
        gateway: Mt5MarketOrderGateway,
        audit: AuditSink,
        history_size: int = 100,
    ) -> None:
        normalized_mode = str(mode).strip().lower()
        if normalized_mode not in EXECUTION_MODES:
            raise ValueError(f"unsupported execution mode: {mode!r}")
        if normalized_mode not in FLOW_CONTROLLER_MODES:
            raise ValueError(
                "Flow-only LIVE execution is prohibited; an approved integrated "
                "Order Flow ENTRY GO is required"
            )
        self.window_sec = int(window_sec)
        self.mode = normalized_mode
        self.gateway = gateway
        self.audit = audit
        self.detector = FlowTransitionDetector(self.window_sec)
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._lock = threading.RLock()
        self._sequence = 0
        self.latest_flow: dict[str, Any] | None = None
        self.latest_execution: dict[str, Any] | None = None
        self.upstream: dict[str, Any] = {
            "status": "STARTING",
            "updated_at": utc_now_iso(),
            "detail": None,
        }
        self.mt5_status: dict[str, Any] | None = None

    def _record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        safe = _json_safe(dict(record))
        self.audit.append(safe)
        self._history.appendleft(safe)
        return safe

    def set_upstream(self, status: str, detail: str | None = None) -> None:
        with self._lock:
            self.upstream = {
                "status": status,
                "updated_at": utc_now_iso(),
                "detail": detail,
            }

    def inspect_mt5(self) -> dict[str, Any]:
        result = self.gateway.inspect()
        with self._lock:
            self.mt5_status = {
                "updated_at": utc_now_iso(),
                **_json_safe(result),
            }
        return result

    def handle_envelope(self, envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
        if envelope.get("type") != "FLOW_RESPONSE":
            return []
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            return []
        windows = payload.get("windows")
        if not isinstance(windows, list):
            return []

        selected = None
        for item in windows:
            if isinstance(item, Mapping) and int(item.get("window_sec", -1)) == self.window_sec:
                selected = dict(item)
                break
        if selected is None:
            return []

        source_time = str(envelope.get("time") or "")
        received_at = utc_now_iso()
        selected.update(
            {
                "source_time": source_time,
                "received_at": received_at,
                "lag_ms": _event_lag_ms(source_time, received_at),
                "source_symbol": envelope.get("symbol"),
            }
        )

        with self._lock:
            self.latest_flow = _json_safe(selected)
            transition = self.detector.observe(str(selected.get("state") or ""))
            if transition.kind == "UNCHANGED":
                return []

            self._sequence += 1
            previous = transition.previous_state or "NONE"
            event_id = _event_id(source_time, self.window_sec, previous, transition.state)
            flow_record = self._record(
                {
                    "recorded_at": received_at,
                    "sequence": self._sequence,
                    "event_id": event_id,
                    "stage": "FLOW_BASELINE" if transition.kind == "BASELINE" else "FLOW_TRANSITION",
                    "status": transition.kind,
                    "window_sec": self.window_sec,
                    "previous_state": transition.previous_state,
                    "flow_state": transition.state,
                    "mapped_side": transition.side,
                    "flow": selected,
                }
            )
            records = [flow_record]
            if transition.kind != "ENTRY" or transition.side is None:
                return records

            intent = self._record(
                {
                    "recorded_at": utc_now_iso(),
                    "sequence": self._sequence,
                    "event_id": event_id,
                    "stage": "ORDER_INTENT",
                    "status": "CREATED",
                    "mode": self.mode,
                    "window_sec": self.window_sec,
                    "flow_state": transition.state,
                    "side": transition.side,
                    "signal_price": selected.get("last_price"),
                    "source_time": source_time,
                    "received_at": received_at,
                    "lag_ms": selected.get("lag_ms"),
                }
            )
            records.append(intent)
            execution = self.gateway.execute(
                transition.side,
                mode=self.mode,
                context={
                    "event_id": event_id,
                    "sequence": self._sequence,
                    "window_sec": self.window_sec,
                    "flow_state": transition.state,
                    "signal_price": selected.get("last_price"),
                    "source_time": source_time,
                    "received_at": received_at,
                    "lag_ms": selected.get("lag_ms"),
                },
            )
            execution_record = self._record(
                {
                    "recorded_at": utc_now_iso(),
                    "sequence": self._sequence,
                    "event_id": event_id,
                    **execution,
                }
            )
            self.latest_execution = execution_record
            records.append(execution_record)
            return records

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "generated_at": utc_now_iso(),
                "mode": self.mode,
                "window_sec": self.window_sec,
                "mapping": dict(FLOW_STATE_TO_SIDE),
                "upstream": _json_safe(self.upstream),
                "mt5": _json_safe(self.mt5_status),
                "latest_flow": _json_safe(self.latest_flow),
                "latest_execution": _json_safe(self.latest_execution),
                "history": _json_safe(list(self._history)),
            }

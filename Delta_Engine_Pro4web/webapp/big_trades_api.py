"""FastAPI routes for the additive Big Trades V2 backend surface."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from src.database.big_trades_storage import BigTradesStorageError
from src.orderflow.big_trades.artifacts import ArtifactError
from webapp.big_trades_backend import BigTradesBackend, BigTradesBackendUnavailable
from webapp.big_trades_protocol import big_trades_json_value


logger = logging.getLogger("webapp.big_trades.api")
router = APIRouter()


@dataclass(frozen=True)
class BigTradesApiError(Exception):
    status_code: int
    code: str
    reason: str
    subsystem: str


def _backend(request: Request) -> BigTradesBackend:
    backend = getattr(request.app.state, "big_trades_backend", None)
    if not isinstance(backend, BigTradesBackend):
        raise BigTradesApiError(
            503,
            "BT_BACKEND_UNAVAILABLE",
            "Big Trades backend is unavailable",
            "big_trades",
        )
    return backend


def _history_call(
    backend: BigTradesBackend,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    backend._require_enabled()
    assert backend.history is not None
    return getattr(backend.history, method_name)(*args, **kwargs)


async def _invoke(
    request: Request,
    callback: Callable[..., Any],
    *args: Any,
    subsystem: str,
    **kwargs: Any,
) -> JSONResponse:
    try:
        result = await asyncio.to_thread(callback, *args, **kwargs)
    except BigTradesBackendUnavailable as exc:
        raise BigTradesApiError(503, "BT_DISABLED", str(exc), subsystem) from exc
    except KeyError as exc:
        raise BigTradesApiError(404, "BT_NOT_FOUND", str(exc.args[0]), subsystem) from exc
    except (ValueError, TypeError) as exc:
        raise BigTradesApiError(422, "BT_VALIDATION_ERROR", str(exc), subsystem) from exc
    except (BigTradesStorageError, ArtifactError) as exc:
        logger.exception("Big Trades backend operation failed")
        raise BigTradesApiError(
            500,
            "BT_STORAGE_ERROR",
            str(exc),
            subsystem,
        ) from exc
    except BigTradesApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalized 5xx contract
        logger.exception("unexpected Big Trades backend failure")
        raise BigTradesApiError(
            500,
            "BT_INTERNAL_ERROR",
            str(exc),
            subsystem,
        ) from exc
    return JSONResponse(big_trades_json_value(result))


async def _json_object(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001 - malformed JSON is a client error
        raise BigTradesApiError(
            422,
            "BT_INVALID_JSON",
            "request body must be a JSON object",
            "request",
        ) from exc
    if not isinstance(body, dict):
        raise BigTradesApiError(
            422,
            "BT_INVALID_JSON",
            "request body must be a JSON object",
            "request",
        )
    return body


@router.get("/api/big-trades/health")
async def big_trades_health(request: Request) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).health,
        subsystem="health",
    )


@router.get("/api/history/big-trades/snapshot")
async def big_trades_snapshot(
    request: Request,
    event_limit: int = 500,
    zone_limit: int = 500,
) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).hydration_snapshot,
        event_limit=event_limit,
        zone_limit=zone_limit,
        subsystem="history",
    )


@router.get("/api/history/big-trades/events")
async def big_trade_events(
    request: Request,
    limit: int = 500,
    before_source_time: Optional[str] = None,
    before_id: Optional[str] = None,
    side: Optional[str] = None,
    lifecycle: Optional[str] = None,
    assessment: Optional[str] = None,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "list_events",
        limit=limit,
        before_source_time=before_source_time,
        before_id=before_id,
        side=side,
        lifecycle=lifecycle,
        assessment=assessment,
        subsystem="history",
    )


@router.get("/api/history/big-trades/events/{event_id}/fills")
async def big_trade_event_fills(
    request: Request,
    event_id: str,
    limit: int = 500,
    after_ordinal: int = 0,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "event_fills",
        event_id,
        limit=limit,
        after_ordinal=after_ordinal,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones")
async def big_trade_zones(
    request: Request,
    limit: int = 500,
    before_source_time: Optional[str] = None,
    before_id: Optional[str] = None,
    side: Optional[str] = None,
    lifecycle: Optional[str] = None,
    assessment: Optional[str] = None,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "list_zones",
        limit=limit,
        before_source_time=before_source_time,
        before_id=before_id,
        side=side,
        lifecycle=lifecycle,
        assessment=assessment,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones/{zone_id}")
async def big_trade_zone_detail(request: Request, zone_id: str) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "zone_detail",
        zone_id,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones/{zone_id}/interactions")
async def big_trade_zone_interactions(
    request: Request,
    zone_id: str,
    limit: int = 500,
    after_ordinal: int = 0,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "zone_interactions",
        zone_id,
        limit=limit,
        after_ordinal=after_ordinal,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones/{zone_id}/linked-events")
async def big_trade_zone_links(
    request: Request,
    zone_id: str,
    limit: int = 500,
    after_ordinal: int = 0,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "zone_links",
        zone_id,
        limit=limit,
        after_ordinal=after_ordinal,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones/{zone_id}/snapshots")
async def big_trade_zone_snapshots(
    request: Request,
    zone_id: str,
    limit: int = 500,
    after_horizon_seconds: int = 0,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "zone_snapshots",
        zone_id,
        limit=limit,
        after_horizon_seconds=after_horizon_seconds,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones/{zone_id}/candles")
async def big_trade_zone_candles(
    request: Request,
    zone_id: str,
    limit: int = 500,
    after_candle_id: Optional[str] = None,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "zone_candles",
        zone_id,
        limit=limit,
        after_candle_id=after_candle_id,
        subsystem="history",
    )


@router.get("/api/history/big-trades/zones/{zone_id}/assessments")
async def big_trade_zone_assessments(
    request: Request,
    zone_id: str,
    limit: int = 500,
) -> JSONResponse:
    backend = _backend(request)
    return await _invoke(
        request,
        _history_call,
        backend,
        "zone_assessments",
        zone_id,
        limit=limit,
        subsystem="history",
    )


@router.post("/api/big-trades/zones/{zone_id}/assessments", status_code=201)
async def create_big_trade_assessment(request: Request, zone_id: str) -> JSONResponse:
    body = await _json_object(request)
    response = await _invoke(
        request,
        _backend(request).create_assessment,
        zone_id,
        body,
        subsystem="assessment",
    )
    response.status_code = 201
    return response


@router.get("/api/big-trades/settings")
async def big_trade_settings(request: Request) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).get_settings,
        subsystem="settings",
    )


@router.put("/api/big-trades/settings", status_code=202)
async def update_big_trade_settings(request: Request) -> JSONResponse:
    body = await _json_object(request)
    response = await _invoke(
        request,
        _backend(request).put_settings,
        body,
        subsystem="settings",
    )
    response.status_code = 202
    return response


@router.get("/api/big-trades/settings/history")
async def big_trade_settings_history(request: Request) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).get_settings_history,
        subsystem="settings",
    )


@router.get("/api/big-trades/calibrations")
async def big_trade_calibrations(request: Request) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).list_calibrations,
        subsystem="calibration",
    )


@router.get("/api/big-trades/calibrations/{calibration_id}")
async def big_trade_calibration_detail(
    request: Request, calibration_id: str
) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).calibration_detail,
        calibration_id,
        subsystem="calibration",
    )


@router.post("/api/big-trades/calibrations/{calibration_id}/activate", status_code=202)
async def activate_big_trade_calibration(
    request: Request, calibration_id: str
) -> JSONResponse:
    response = await _invoke(
        request,
        _backend(request).activate_calibration,
        calibration_id,
        subsystem="activation",
    )
    response.status_code = 202
    return response


@router.get("/api/big-trades/activations")
async def big_trade_activations(request: Request) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).list_activations,
        subsystem="activation",
    )


@router.get("/api/big-trades/activations/{activation_id}")
async def big_trade_activation_detail(
    request: Request, activation_id: str
) -> JSONResponse:
    return await _invoke(
        request,
        _backend(request).activation_detail,
        activation_id,
        subsystem="activation",
    )


def install_big_trades_api(app: FastAPI) -> None:
    """Install additive routes and the explicit 4xx/5xx error envelope."""

    app.include_router(router)

    @app.exception_handler(BigTradesApiError)
    async def _big_trades_error_handler(
        _request: Request, error: BigTradesApiError
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error_code": error.code,
                "reason": error.reason,
                "affected_subsystem": error.subsystem,
            },
            status_code=error.status_code,
        )

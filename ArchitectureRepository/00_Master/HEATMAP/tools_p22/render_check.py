"""Manual full-recording check for the Phase 2-2 static renderer.

This CLI is intentionally separate from the test suite. It is the only place
where the validation recording is rendered at a full, inspection-sized
viewport.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
APPLICATION_ROOT = REPOSITORY_ROOT / "Delta_Engine_Pro4web"
DEFAULT_RECORDING = (
    APPLICATION_ROOT
    / "data_05M"
    / "phase2_0_d2_validation"
    / "20260730T043059"
    / "depth_history_raw"
    / "symbol=BTCUSDT"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "HEATMAP"
    / "tools_p22"
    / "rendered_heatmap_full.png"
)
DEFAULT_DOWNSAMPLED_OUTPUT = (
    REPOSITORY_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "HEATMAP"
    / "tools_p22"
    / "rendered_heatmap_downsampled.png"
)
DEFAULT_METRICS_OUTPUT = (
    REPOSITORY_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "HEATMAP"
    / "tools_p22"
    / "render_check_metrics.json"
)

if str(APPLICATION_ROOT) not in sys.path:
    sys.path.insert(0, str(APPLICATION_ROOT))

from src.heatmap.binner import bin_samples  # noqa: E402
from src.heatmap.reconstruct import DepthHistoryReader, DepthReconstructor  # noqa: E402
from src.heatmap.render_static import RenderReport, render_heatmap  # noqa: E402
from src.heatmap.transform import PixelViewport  # noqa: E402


_P50 = Decimal("50")
_P95 = Decimal("95")
_PERCENT = Decimal("100")
_FRAME_BUDGET_MS = Decimal("16")
_DOWNSAMPLE_PRICE_BIN_MULTIPLIER = Decimal("2")
_DOWNSAMPLE_TIME_COL_DIVISOR = 2
_FRAME_BUDGET_NOTE = (
    "The static PNG total_ms p95 comparison with 16 ms is reference-only. "
    "The strict dynamic frame-budget evaluation belongs to Phase 2-3."
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("value must be a Decimal") from exc
    if not parsed.is_finite() or parsed <= Decimal("0"):
        raise argparse.ArgumentTypeError("value must be a positive finite Decimal")
    return parsed


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * percentile / _PERCENT
    lower_index = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper_index = int(position.to_integral_value(rounding=ROUND_CEILING))
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - Decimal(lower_index)
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def _report_dict(report: RenderReport) -> dict[str, object]:
    return {
        "width": report.width,
        "height": report.height,
        "price_bins": report.price_bins,
        "time_cols": report.time_cols,
        "gap_columns": report.gap_columns,
        "bytes_written": report.bytes_written,
        "aggregation_ms": str(report.aggregation_ms),
        "transform_ms": str(report.transform_ms),
        "render_ms": str(report.render_ms),
        "total_ms": str(report.total_ms),
    }


def _series_summary(values: list[Decimal]) -> dict[str, str]:
    if not values:
        raise ValueError("timing summary requires at least one value")
    return {
        "min": str(min(values)),
        "p50": str(_percentile(values, _P50)),
        "p95": str(_percentile(values, _P95)),
        "max": str(max(values)),
    }


def _timing_summary(reports: list[RenderReport]) -> dict[str, dict[str, str]]:
    return {
        "transform_ms": _series_summary(
            [report.transform_ms for report in reports]
        ),
        "render_ms": _series_summary(
            [report.render_ms for report in reports]
        ),
        "total_ms": _series_summary(
            [report.total_ms for report in reports]
        ),
    }


def _render_runs(
    *,
    grid,
    viewport: PixelViewport,
    output_path: Path,
    runs: int,
    label: str,
) -> list[RenderReport]:
    reports: list[RenderReport] = []
    for run_number in range(1, runs + 1):
        report = render_heatmap(grid, viewport, output_path)
        reports.append(report)
        print(
            f"{label}_render={run_number}/{runs} "
            f"transform_ms={report.transform_ms} "
            f"render_ms={report.render_ms} "
            f"total_ms={report.total_ms}",
            file=sys.stderr,
            flush=True,
        )
    return reports


def _budget_status(total_ms_p95: Decimal) -> str:
    if total_ms_p95 <= _FRAME_BUDGET_MS:
        return "WITHIN_REFERENCE_BUDGET"
    return "EXCEEDS_REFERENCE_BUDGET"


def _render_metrics(
    *,
    reports: list[RenderReport],
    output_path: Path,
) -> dict[str, object]:
    timing_ms = _timing_summary(reports)
    total_ms_p95 = Decimal(timing_ms["total_ms"]["p95"])
    return {
        "runs": len(reports),
        "timing_ms": timing_ms,
        "reference_budget_ms": str(_FRAME_BUDGET_MS),
        "total_ms_p95_status": _budget_status(total_ms_p95),
        "budget_note": _FRAME_BUDGET_NOTE,
        "last_report": _report_dict(reports[-1]),
        "output_path": str(output_path),
        "png_bytes": reports[-1].bytes_written,
    }


def run_check(
    recording_dir: Path,
    *,
    interval_ms: int,
    price_bin: Decimal,
    viewport_width: int,
    viewport_height: int,
    runs: int,
    output_path: Path,
    downsampled_output_path: Path,
) -> dict[str, object]:
    if not recording_dir.is_dir():
        raise FileNotFoundError(recording_dir)

    reader = DepthHistoryReader(recording_dir)
    segments = reader.segments()
    skipped_count = len(reader.skipped_segments)
    reconstructor = DepthReconstructor(symbol="BTCUSDT", max_attempts=1)
    samples = tuple(
        reconstructor.sample_states(
            reader.iter_records(),
            interval_ms=interval_ms,
        )
    )
    if not samples:
        raise RuntimeError("recording produced no synchronized samples")

    grid = bin_samples(
        samples,
        price_bin=price_bin,
        max_time_cols=len(samples),
    )
    viewport = PixelViewport(
        left=Decimal("0"),
        top=Decimal("0"),
        width=Decimal(viewport_width),
        height=Decimal(viewport_height),
    )
    print(_FRAME_BUDGET_NOTE, file=sys.stderr, flush=True)
    reports = _render_runs(
        grid=grid,
        viewport=viewport,
        output_path=output_path,
        runs=runs,
        label="full",
    )
    render_metrics = _render_metrics(
        reports=reports,
        output_path=output_path,
    )

    result: dict[str, object] = {
        "recording_dir": str(recording_dir),
        "integrity": "PASS",
        "segments": len(segments),
        "skipped_segments": skipped_count,
        "samples": len(samples),
        "viewport": {
            "width": viewport_width,
            "height": viewport_height,
            "left": "0",
            "top": "0",
        },
        "grid": {
            "price_bins": grid.price_count,
            "time_cols": grid.time_count,
            "gap_columns": sum(grid.gap_columns),
        },
        "render": render_metrics,
        "counters": reconstructor.counters,
    }
    full_total_ms_p95 = Decimal(
        render_metrics["timing_ms"]["total_ms"]["p95"]
    )
    if full_total_ms_p95 <= _FRAME_BUDGET_MS:
        result["downsampled"] = None
        return result

    downsampled_price_bin = price_bin * _DOWNSAMPLE_PRICE_BIN_MULTIPLIER
    downsampled_time_cols = max(
        1,
        len(samples) // _DOWNSAMPLE_TIME_COL_DIVISOR,
    )
    downsampled_grid = bin_samples(
        samples,
        price_bin=downsampled_price_bin,
        max_time_cols=downsampled_time_cols,
    )
    downsampled_reports = _render_runs(
        grid=downsampled_grid,
        viewport=viewport,
        output_path=downsampled_output_path,
        runs=runs,
        label="downsampled",
    )
    result["downsampled"] = {
        "method": {
            "price_bin": str(downsampled_price_bin),
            "time_cols_limit": downsampled_time_cols,
            "price_bin_multiplier": str(_DOWNSAMPLE_PRICE_BIN_MULTIPLIER),
            "time_col_divisor": _DOWNSAMPLE_TIME_COL_DIVISOR,
        },
        "grid": {
            "price_bins": downsampled_grid.price_count,
            "time_cols": downsampled_grid.time_count,
            "gap_columns": sum(downsampled_grid.gap_columns),
        },
        "render": _render_metrics(
            reports=downsampled_reports,
            output_path=downsampled_output_path,
        ),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the Phase 2-2 validation recording and report p95 timing."
    )
    parser.add_argument(
        "recording_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_RECORDING,
    )
    parser.add_argument("--interval-ms", type=_positive_int, default=1_000)
    parser.add_argument("--price-bin", type=_decimal, default=Decimal("10"))
    parser.add_argument("--viewport-width", type=_positive_int, default=900)
    parser.add_argument("--viewport-height", type=_positive_int, default=600)
    parser.add_argument("--runs", type=_positive_int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--downsampled-output",
        type=Path,
        default=DEFAULT_DOWNSAMPLED_OUTPUT,
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=DEFAULT_METRICS_OUTPUT,
    )
    args = parser.parse_args(argv)
    result = run_check(
        args.recording_dir,
        interval_ms=args.interval_ms,
        price_bin=args.price_bin,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        runs=args.runs,
        output_path=args.output,
        downsampled_output_path=args.downsampled_output,
    )
    result["metrics_path"] = str(args.metrics_output)
    metrics_json = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_output.write_text(
        metrics_json + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"metrics_json={args.metrics_output}",
        file=sys.stderr,
        flush=True,
    )
    print(metrics_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

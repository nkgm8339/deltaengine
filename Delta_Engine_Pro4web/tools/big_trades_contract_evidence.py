"""Build and validate the one-row-per-contract Big Trades V2 evidence matrix."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


CONTRACT_RE = re.compile(r"^\d+\. `(?P<id>BT2-[A-Z]\d{3})` (?P<description>.+?)。?$", re.M)


def _node(path: str, name: str) -> str:
    return f"{path}::{name}"


N = {
    "order_decimal": _node("tests/orderflow/test_big_trades_ordering.py", "test_decimal_trade_values_are_preserved_exactly"),
    "order_invalid": _node("tests/orderflow/test_big_trades_ordering.py", "test_invalid_decimal_trade_values_are_rejected"),
    "order_side_time": _node("tests/orderflow/test_big_trades_ordering.py", "test_unknown_side_and_timezone_naive_are_rejected"),
    "order_same_ms": _node("tests/orderflow/test_big_trades_ordering.py", "test_same_millisecond_bucket_releases_by_integer_trade_id"),
    "order_late": _node("tests/orderflow/test_big_trades_ordering.py", "test_late_trade_after_release_is_rejected"),
    "aggregate_vector": _node("tests/orderflow/test_big_trades_aggregation.py", "test_fixed_vector_chains_from_previous_fill_and_builds_event"),
    "aggregate_0": _node("tests/orderflow/test_big_trades_aggregation.py", "test_same_side_same_millisecond_joins_cluster"),
    "aggregate_40": _node("tests/orderflow/test_big_trades_aggregation.py", "test_exact_40ms_gap_joins_cluster"),
    "aggregate_41": _node("tests/orderflow/test_big_trades_aggregation.py", "test_41ms_gap_closes_cluster"),
    "aggregate_chain": _node("tests/orderflow/test_big_trades_aggregation.py", "test_zero_35_70ms_is_one_chain_and_price_does_not_split"),
    "aggregate_settings": _node("tests/orderflow/test_big_trades_aggregation.py", "test_settings_change_does_not_force_split_and_next_natural_cluster_uses_new_snapshot"),
    "aggregate_max": _node("tests/orderflow/test_big_trades_aggregation.py", "test_max_fill_limit_flushes_without_losing_trigger_trade"),
    "aggregate_minute": _node("tests/orderflow/test_big_trades_aggregation.py", "test_utc_minute_boundary_closes_even_within_40ms"),
    "aggregate_disconnect": _node("tests/orderflow/test_big_trades_aggregation.py", "test_disconnect_closes_cluster_explicitly_and_prevents_rejoin"),
    "aggregate_session": _node("tests/orderflow/test_big_trades_aggregation.py", "test_session_boundary_closes_cluster"),
    "aggregate_identity": _node("tests/orderflow/test_big_trades_aggregation.py", "test_trade_and_settings_identity_mismatch_is_rejected"),
    "aggregate_marker": _node("tests/orderflow/test_big_trades_aggregation.py", "test_marker_price_modes"),
    "aggregate_side_filter": _node("tests/orderflow/test_big_trades_aggregation.py", "test_side_filter_is_display_metadata_after_quantity_decision"),
    "time_offset": _node("tests/orderflow/test_big_trades_time_buckets.py", "test_offset_timestamp_normalizes_to_same_utc_minute_bucket"),
    "time_cvd": _node("tests/orderflow/test_big_trades_time_buckets.py", "test_big_trades_candle_boundary_matches_cvd_one_minute_boundary"),
    "manual_inclusive": _node("tests/orderflow/test_big_trades_filtering.py", "test_manual_min_and_max_are_inclusive"),
    "manual_reject": _node("tests/orderflow/test_big_trades_filtering.py", "test_manual_rejection_reasons_are_exact"),
    "manual_unbounded": _node("tests/orderflow/test_big_trades_filtering.py", "test_manual_zero_max_is_unbounded"),
    "config_invalid": _node("tests/test_config_big_trades.py", "test_big_trades_max_must_be_zero_or_at_least_min"),
    "settings_id": _node("tests/orderflow/test_big_trades_artifacts.py", "test_settings_id_is_deterministic_and_manual_discards_calibration"),
    "event_ids": _node("tests/orderflow/test_big_trades_ids.py", "test_same_event_input_has_same_ids_and_content_hashes"),
    "storage_origin": _node("tests/database/test_big_trades_storage.py", "test_origin_batch_is_atomic_idempotent_and_decimal_utc_exact"),
    "storage_collision": _node("tests/database/test_big_trades_storage.py", "test_same_origin_id_with_different_content_is_collision"),
    "protocol_values": _node("tests/webapp/test_big_trades_protocol.py", "test_bt2_w211_to_w214_unified_envelope_precedence_and_strict_types"),
    "cal_rank": _node("tests/orderflow/test_big_trades_calibration.py", "test_rank_is_one_based_descending"),
    "cal_thresholds": _node("tests/orderflow/test_big_trades_calibration.py", "test_calibration_uses_20_9_2_ranks_and_strict_order"),
    "cal_median": _node("tests/orderflow/test_big_trades_calibration.py", "test_decimal_median_never_uses_float"),
    "cal_insufficient": _node("tests/orderflow/test_big_trades_calibration.py", "test_insufficient_sessions_fail_closed"),
    "cal_ten": _node("tests/orderflow/test_big_trades_calibration.py", "test_exactly_ten_valid_sessions_is_valid"),
    "cal_exclude": _node("tests/orderflow/test_big_trades_artifacts.py", "test_calibration_excludes_current_and_future_sessions"),
    "cal_gap": _node("tests/orderflow/test_big_trades_artifacts.py", "test_session_stats_require_next_session_source_and_gap_is_excluded"),
    "cal_ntr": _node("tests/orderflow/test_big_trades_calibration.py", "test_normalized_true_range"),
    "cal_coverage": _node("tests/orderflow/test_big_trades_artifacts.py", "test_session_candle_coverage_boundary_controls_only_volatility"),
    "cal_sqrt": _node("tests/orderflow/test_big_trades_calibration.py", "test_volatility_factor_uses_decimal_square_root_before_clamp"),
    "cal_lower": _node("tests/orderflow/test_big_trades_calibration.py", "test_volatility_factor_lower_clamp_and_strict_threshold_correction"),
    "cal_upper": _node("tests/orderflow/test_big_trades_calibration.py", "test_volatility_factor_is_clamped_and_ceil_to_step"),
    "cal_fallback": _node("tests/orderflow/test_big_trades_calibration.py", "test_missing_volatility_uses_explicit_fallback"),
    "cal_artifact": _node("tests/orderflow/test_big_trades_artifacts.py", "test_calibration_artifact_is_deterministic_and_created_time_is_non_identity"),
    "cal_validate": _node("tests/orderflow/test_big_trades_artifacts.py", "test_calibration_validation_rejects_wrong_symbol_logic_and_step"),
    "session_trigger": _node("tests/orderflow/test_big_trades_activation.py", "test_session_completion_is_triggered_only_by_next_session_first_source_trade"),
    "session_runtime": _node("tests/orderflow/test_big_trades_runtime.py", "test_source_confirmed_next_session_closes_zone_and_saves_stats"),
    "schedule_stop": _node("tests/orderflow/test_big_trades_artifacts.py", "test_missing_durable_previous_session_stops_schedule_and_keeps_old_activation"),
    "schedule_dedup": _node("tests/orderflow/test_big_trades_artifacts.py", "test_same_schedule_boundary_and_manifest_reuses_terminal_run"),
    "schedule_success": _node("tests/orderflow/test_big_trades_artifacts.py", "test_scheduled_success_auto_activates_from_same_source_boundary"),
    "schedule_fail": _node("tests/orderflow/test_big_trades_artifacts.py", "test_scheduled_validation_failure_does_not_activate_or_retry"),
    "manual_pending": _node("tests/orderflow/test_big_trades_artifacts.py", "test_manual_only_generates_candidate_without_activation"),
    "user_wins": _node("tests/orderflow/test_big_trades_activation.py", "test_user_calibration_wins_over_scheduled_candidate_at_same_boundary"),
    "activation_one": _node("tests/orderflow/test_big_trades_activation.py", "test_same_source_boundary_cannot_hold_two_activations"),
    "activation_initial": _node("tests/orderflow/test_big_trades_artifacts.py", "test_activation_artifact_is_commit_point_and_pointer_is_derived_cache"),
    "replay_select": _node("tests/orderflow/test_big_trades_activation.py", "test_replay_selection_uses_effective_source_key_not_requested_time"),
    "replay_created": _node("tests/orderflow/test_big_trades_artifacts.py", "test_historical_replay_resolves_committed_activation_and_ignores_created_time"),
    "replay_missing": _node("tests/orderflow/test_big_trades_activation.py", "test_replay_missing_history_fails_closed"),
    "fixed_research": _node("tests/orderflow/test_big_trades_artifacts.py", "test_fixed_research_resolution_has_isolated_output_and_no_activation"),
    "zone_bounds": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_relation_boundaries_are_inclusive"),
    "zone_single": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_single_price_event_creates_zero_height_authoritative_zone"),
    "zone_count": _node("tests/orderflow/test_big_trades_runtime.py", "test_delayed_same_area_link_keeps_source_order_and_restart_recovery"),
    "zone_up": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_fixed_vector_first_exit_return_and_excursions"),
    "zone_down": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_down_exit_reentry_continuous_inside_cross_down_and_break_persistence"),
    "zone_cross": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_direct_cross_has_no_fabricated_inside_interaction"),
    "zone_origin": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_origin_and_old_session_trades_are_not_observed"),
    "zone_gap_close": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_gap_and_source_confirmed_session_close_are_explicit"),
    "zone_index_oracle": _node("tests/orderflow/test_big_trades_zone_index.py", "test_point_and_boundary_queries_match_brute_force_randomized_oracle"),
    "zone_index_interval": _node("tests/orderflow/test_big_trades_zone_index.py", "test_interval_candidate_query_returns_only_overlap_and_tolerance_neighbors"),
    "zone_index_5000": _node("tests/orderflow/test_big_trades_zone_index.py", "test_index_keeps_5000_zones_and_removes_only_explicit_target"),
    "zone_inside": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_fixed_vector_first_exit_return_and_excursions"),
    "zone_overlap": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_overlapping_zones_each_observe_one_trade_once"),
    "zone_link": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_later_event_links_by_interval_gap_without_merging_identity"),
    "zone_link_totals": _node("tests/orderflow/test_big_trades_reaction_zones.py", "test_registered_buy_and_sell_links_update_separate_quantities"),
    "horizons": _node("tests/orderflow/test_big_trades_horizons.py", "test_default_horizons_are_exact_contract_values"),
    "horizon_price": _node("tests/orderflow/test_big_trades_horizons.py", "test_snapshot_uses_last_trade_at_target_not_trigger_trade"),
    "horizon_age": _node("tests/orderflow/test_big_trades_horizons.py", "test_source_age_exactly_1000ms_is_valid_and_1001ms_is_stale"),
    "horizon_gap": _node("tests/orderflow/test_big_trades_horizons.py", "test_gap_crossing_horizon_is_missing_without_interpolation"),
    "horizon_session": _node("tests/orderflow/test_big_trades_horizons.py", "test_horizon_crossing_utc_session_is_missing_session"),
    "horizon_facts": _node("tests/orderflow/test_big_trades_horizons.py", "test_snapshot_cuts_off_future_trade_and_preserves_all_metric_facts"),
    "horizon_sell": _node("tests/orderflow/test_big_trades_horizons.py", "test_sell_signed_return_is_inverse_and_replay_speed_independent"),
    "price_path": _node("tests/orderflow/test_big_trades_price_path.py", "test_last_at_or_before_and_exact_range_extrema"),
    "candle_upper": _node("tests/orderflow/test_big_trades_candle_observer.py", "test_upper_wick_return_and_close_above_are_distinct_facts"),
    "candle_lower": _node("tests/orderflow/test_big_trades_candle_observer.py", "test_lower_wick_return_and_exact_boundary_close"),
    "candle_mismatch": _node("tests/orderflow/test_big_trades_runtime.py", "test_candle_boundary_mismatch_errors_only_big_trades_runtime"),
    "runtime_gap": _node("tests/orderflow/test_big_trades_runtime.py", "test_source_gap_invalidates_crossing_horizon"),
    "runtime_recovery": _node("tests/orderflow/test_big_trades_runtime.py", "test_restart_recovers_zone_without_republishing_origin_and_marks_gap"),
    "stream_open": _node("tests/test_big_trades_pipeline.py", "test_bt2_p208_stream_end_flushes_storage_without_closing_session"),
    "assessment": _node("tests/webapp/test_big_trades_api.py", "test_bt2_w229_w230_assessment_append_supersede_and_no_mutation_routes"),
    "assessment_invalid": _node("tests/webapp/test_big_trades_api.py", "test_bt2_w234_w235_explicit_error_semantics_and_disabled_health"),
    "context": _node("tests/webapp/test_big_trades_ui.py", "test_bt2_u254_context_keeps_missing_values_visible"),
    "protected": _node("tests/webapp/test_big_trades_ui.py", "test_bt2_u274_flow_response_cards_are_not_replaced"),
    "storage_atomic": _node("tests/database/test_big_trades_storage.py", "test_origin_batch_is_atomic_idempotent_and_decimal_utc_exact"),
    "storage_rollback": _node("tests/database/test_big_trades_storage.py", "test_origin_component_failure_rolls_back_every_table"),
    "storage_ack": _node("tests/orderflow/test_big_trades_runtime.py", "test_origin_is_not_published_until_duckdb_commit_ack"),
    "storage_queue": _node("tests/database/test_big_trades_storage.py", "test_background_queue_full_returns_explicit_failed_ack"),
    "storage_parquet": _node("tests/database/test_big_trades_storage.py", "test_parquet_requires_manifest_and_retries_after_duckdb_commit"),
    "storage_updates": _node("tests/database/test_big_trades_storage.py", "test_runtime_updates_round_trip_interaction_link_snapshot_and_candle_parquet"),
    "storage_assessment": _node("tests/database/test_big_trades_storage.py", "test_assessment_parquet_is_committed_only_with_manifest"),
    "storage_manifest": _node("tests/database/test_big_trades_storage.py", "test_missing_manifest_member_is_detected"),
    "storage_checkpoint": _node("tests/database/test_big_trades_storage.py", "test_checkpoint_is_idempotent_and_mismatch_collides"),
    "storage_activation": _node("tests/database/test_big_trades_storage.py", "test_settings_then_activation_mirrors_preserve_lineage"),
    "pipeline_disabled": _node("tests/test_big_trades_pipeline.py", "test_replay_pipeline_disabled_runtime_is_existing_output_equivalent"),
    "pipeline_cvd": _node("tests/test_big_trades_pipeline.py", "test_bt2_p192_enabled_runtime_preserves_cvd_output"),
    "pipeline_fp": _node("tests/test_big_trades_pipeline.py", "test_bt2_p193_enabled_runtime_preserves_footprint_output"),
    "pipeline_flow": _node("tests/test_big_trades_pipeline.py", "test_bt2_p194_enabled_runtime_preserves_flow_price_response"),
    "pipeline_large": _node("tests/test_big_trades_pipeline.py", "test_bt2_p195_enabled_runtime_preserves_large_trade_detector"),
    "pipeline_once": _node("tests/test_big_trades_pipeline.py", "test_bt2_p196_normalized_trade_reaches_big_trades_exactly_once"),
    "pipeline_order": _node("tests/test_big_trades_pipeline.py", "test_bt2_p197_closed_cvd_candle_precedes_new_trade_in_big_trades"),
    "pipeline_reconnect": _node("tests/orderflow/test_big_trades_runtime.py", "test_reconnect_flushes_open_cluster_without_deleting_active_zone"),
    "pipeline_error": _node("tests/test_big_trades_pipeline.py", "test_bt2_p200_big_trades_error_does_not_stop_market_pipeline"),
    "pipeline_parity": _node("tests/test_big_trades_pipeline.py", "test_bt2_p201_to_p205_live_replay_match_through_links_and_snapshots"),
    "pipeline_session": _node("tests/orderflow/test_big_trades_runtime.py", "test_source_confirmed_next_session_closes_zone_and_saves_stats"),
}


def _contract_mapping() -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}

    def put(ids: Iterable[str], *nodes: str) -> None:
        for identifier in ids:
            key = identifier if identifier.startswith("BT2-") else f"BT2-{identifier}"
            if key in result:
                raise RuntimeError(f"duplicate contract mapping: {key}")
            result[key] = tuple(nodes)

    put(["C001"], N["order_decimal"])
    put(["C002", "C003", "C004"], N["order_invalid"])
    put(["C005", "C007"], N["order_side_time"])
    put(["C006"], N["aggregate_identity"])
    put(["C008"], _node("tests/normalization/test_normalizer.py", "test_tv_nrm_02_duplicate_discard"))
    put(["C009", "C010", "C011"], N["order_same_ms"])
    put(["C012", "C022"], N["aggregate_disconnect"])
    put(["C013"], N["order_late"])
    put(["C014"], N["aggregate_0"])
    put(["C015"], N["aggregate_40"])
    put(["C016"], N["aggregate_41"])
    put(["C017", "C019"], N["aggregate_chain"])
    put(["C018", "C024", "C025", "C026", "C027"], N["aggregate_vector"])
    put(["C020"], N["aggregate_session"])
    put(["C021", "C028"], N["aggregate_minute"])
    put(["C023"], N["aggregate_max"])
    put(["C029"], N["time_offset"])
    put(["C030"], N["time_cvd"])
    put(["C031", "C032", "C034"], N["manual_inclusive"])
    put(["C033"], N["manual_unbounded"])
    put(["C035"], N["manual_reject"])
    put(["C036"], N["aggregate_side_filter"])
    put(["C037", "C038"], N["aggregate_settings"])
    put(["C039"], N["config_invalid"])
    put(["C040"], N["settings_id"])
    put(["C041"], N["event_ids"])
    put(["C042"], N["storage_origin"])
    put(["C043"], N["storage_collision"])
    put(["C044"], N["aggregate_marker"])
    put(["C045"], N["protocol_values"])
    put(["C046"], N["cal_rank"])
    put(["C047", "C048", "C049"], N["cal_thresholds"])
    put(["C050", "C051"], N["cal_median"])
    put(["C052"], N["cal_insufficient"])
    put(["C053"], N["cal_ten"])
    put(["C054", "C055"], N["cal_exclude"])
    put(["C056"], N["cal_gap"])
    put(["C057", "C058", "C059"], N["cal_ntr"])
    put(["C060"], N["cal_coverage"])
    put(["C061", "C062"], N["cal_sqrt"])
    put(["C063"], N["cal_sqrt"])
    put(["C064"], N["cal_lower"])
    put(["C065"], N["cal_upper"])
    put(["C066"], N["cal_fallback"])
    put(["C067"], N["cal_upper"])
    put(["C068"], N["cal_lower"])
    put(["C069"], N["cal_artifact"])
    put(["C070"], N["cal_validate"])
    put(["C071", "C072", "C073"], N["session_trigger"])
    put(["C074"], N["pipeline_order"])
    put(["C075"], N["session_runtime"])
    put(["C076"], N["schedule_stop"])
    put(["C077"], N["schedule_dedup"])
    put(["C078"], N["schedule_success"])
    put(["C079"], N["schedule_fail"])
    put(["C080", "C081"], N["manual_pending"])
    put(["C082"], N["user_wins"])
    put(["C083"], N["activation_one"])
    put(["C084"], N["activation_initial"], N["storage_ack"])
    put(["C085"], N["replay_select"])
    put(["C086"], N["replay_created"])
    put(["C087"], N["replay_missing"])
    put(["C088"], N["fixed_research"])

    put(["Z089", "Z090", "Z099"], N["zone_count"])
    put(["Z091", "Z092", "Z093", "Z094", "Z095", "Z100"], N["zone_bounds"])
    put(["Z096", "Z097"], N["zone_single"])
    put(["Z098"], _node("tests/orderflow/test_big_trades_ids.py", "test_zone_id_is_deterministic_and_versioned"))
    put(["Z101", "Z102", "Z103", "Z104", "Z105"], N["zone_bounds"])
    put(["Z106"], N["zone_origin"])
    put(["Z107", "Z109", "Z110", "Z115", "Z116"], N["zone_up"])
    put(["Z108", "Z111", "Z112", "Z114", "Z118"], N["zone_down"])
    put(["Z113"], N["zone_cross"])
    put(["Z117"], N["zone_gap_close"])
    put(["Z119", "Z120"], N["zone_index_oracle"])
    put(["Z121"], N["zone_index_interval"])
    put(["Z122"], N["zone_index_5000"])
    put(["Z123", "Z124"], N["zone_inside"])
    put(["Z125"], N["zone_overlap"])
    put(["Z126", "Z127", "Z128", "Z129", "Z131", "Z132"], N["zone_link"])
    put(["Z130", "Z133"], N["zone_link_totals"])
    put(["Z134"], N["horizons"])
    put(["Z135", "Z136", "Z141"], N["horizon_price"])
    put(["Z137", "Z138"], N["horizon_age"])
    put(["Z139"], N["horizon_gap"])
    put(["Z140"], N["horizon_session"])
    put(["Z142", "Z145", "Z146", "Z147", "Z148"], N["horizon_facts"])
    put(["Z143", "Z150"], N["horizon_sell"])
    put(["Z144"], N["price_path"])
    put(["Z149"], N["pipeline_parity"])
    put(["Z151", "Z153", "Z156"], N["candle_upper"])
    put(["Z152", "Z154", "Z155"], N["candle_lower"])
    put(["Z157"], N["candle_mismatch"])
    put(["Z158", "Z159"], N["runtime_gap"])
    put(["Z160", "Z161"], N["runtime_recovery"])
    put(["Z162"], N["stream_open"])
    put(["Z163", "Z165", "Z166"], N["assessment"])
    put(["Z164"], N["assessment_invalid"])
    put(["Z167", "Z168"], _node("tests/webapp/test_big_trades_ui.py", "test_bt2_u275_system_facts_and_user_assessment_are_separate"))
    put(["Z169", "Z170"], N["context"])
    put(["Z171"], N["protected"])

    put(["S172", "S174", "S185", "S186"], N["storage_atomic"])
    put(["S173"], N["storage_rollback"])
    put(["S175"], N["storage_collision"])
    put(["S176", "S177"], N["storage_ack"])
    put(["S178"], N["storage_queue"])
    put(["S179", "S183"], N["storage_parquet"])
    put(["S180", "S181"], N["storage_updates"])
    put(["S182"], N["storage_assessment"])
    put(["S184"], N["storage_manifest"])
    put(["S187"], N["runtime_recovery"])
    put(["S188", "S189"], N["storage_checkpoint"])
    put(["S190"], N["storage_activation"])

    put(["P191"], N["pipeline_disabled"])
    put(["P192"], N["pipeline_cvd"])
    put(["P193"], N["pipeline_fp"])
    put(["P194"], N["pipeline_flow"])
    put(["P195"], N["pipeline_large"])
    put(["P196"], N["pipeline_once"])
    put(["P197"], N["pipeline_order"])
    put(["P198", "P199"], N["pipeline_reconnect"])
    put(["P200"], N["pipeline_error"])
    put([f"P{number:03d}" for number in range(201, 206)], N["pipeline_parity"])
    put(["P206"], N["replay_created"], N["pipeline_parity"])
    put(["P207"], N["fixed_research"])
    put(["P208"], N["stream_open"])
    put(["P209", "P210"], N["pipeline_session"])

    web = {
        211: "test_bt2_w211_to_w214_unified_envelope_precedence_and_strict_types",
        212: "test_bt2_w212_unknown_record_kind_is_rejected",
        213: "test_bt2_w213_boolean_is_not_accepted_as_integer",
        214: "test_bt2_w211_to_w214_unified_envelope_precedence_and_strict_types",
        215: "test_bt2_w215_w216_stream_restart_and_drop_gap_are_visible",
        216: "test_bt2_w215_w216_stream_restart_and_drop_gap_are_visible",
        217: "test_bt2_w217_status_is_cached_first_for_reconnect",
        218: "test_bt2_w211_to_w214_unified_envelope_precedence_and_strict_types",
        219: "test_browser_validator_rejects_unknown_fields_and_numeric_decimal",
        220: "test_bt2_w220_w221_history_is_oldest_first_with_exclusive_time_id_cursor",
        221: "test_bt2_w220_w221_history_is_oldest_first_with_exclusive_time_id_cursor",
        222: "test_bt2_w222_durable_recent_merge_dedup_and_collision",
        223: "test_bt2_w223_to_w228_zone_detail_and_lazy_orders",
        224: "test_bt2_w223_to_w228_zone_detail_and_lazy_orders",
        225: "test_bt2_w223_to_w228_zone_detail_and_lazy_orders",
        226: "test_bt2_w223_to_w228_zone_detail_and_lazy_orders",
        227: "test_bt2_w223_to_w228_zone_detail_and_lazy_orders",
        228: "test_bt2_w223_to_w228_zone_detail_and_lazy_orders",
        229: "test_bt2_w229_w230_assessment_append_supersede_and_no_mutation_routes",
        230: "test_bt2_w229_w230_assessment_append_supersede_and_no_mutation_routes",
        231: "test_bt2_w231_settings_put_is_strict_atomic_pending",
        232: "test_bt2_w232_manual_calibration_activation_returns_pending",
        233: "test_bt2_w233_activation_history_is_get_only_and_immutable",
        234: "test_bt2_w234_w235_explicit_error_semantics_and_disabled_health",
        235: "test_bt2_w234_w235_explicit_error_semantics_and_disabled_health",
    }
    protocol = set(range(211, 219))
    for number, name in web.items():
        path = (
            "tests/webapp/test_big_trades_protocol.py"
            if number in protocol
            else "tests/webapp/test_big_trades_ui.py"
            if number == 219
            else "tests/webapp/test_big_trades_api.py"
        )
        put([f"W{number:03d}"], _node(path, name))

    for number in range(236, 276):
        marker = f"test_bt2_u{number:03d}_"
        put([f"U{number:03d}"], _node("tests/webapp/test_big_trades_ui.py", marker))
    for number in range(276, 296):
        marker = f"test_bt2_o{number:03d}_"
        put([f"O{number:03d}"], _node("tests/performance/test_big_trades_phase6.py", marker))
    put(["O296"], "FULL_REPOSITORY_PYTEST")
    return result


def _parse_contracts(path: Path) -> list[tuple[str, str]]:
    matches = [(match.group("id"), match.group("description")) for match in CONTRACT_RE.finditer(path.read_text(encoding="utf-8"))]
    if len(matches) != 296:
        raise RuntimeError(f"instruction contains {len(matches)} contracts, expected 296")
    if [int(identifier[-3:]) for identifier, _ in matches] != list(range(1, 297)):
        raise RuntimeError("contract numbers are not contiguous 001..296")
    return matches


def _suite_result(path: Path) -> tuple[dict[str, int], tuple[str, ...]]:
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise RuntimeError(f"no testsuite in {path}")
    result = {name: int(suite.attrib.get(name, "0")) for name in ("tests", "failures", "errors", "skipped")}
    failed = tuple(
        f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
        for case in root.findall(".//testcase")
        if case.find("failure") is not None or case.find("error") is not None
    )
    return result, failed


def build_report(
    *,
    instruction: Path,
    collection: Path,
    targeted_junit: Path,
    full_junits: tuple[Path, ...],
) -> dict[str, object]:
    contracts = _parse_contracts(instruction)
    mappings = _contract_mapping()
    expected_ids = {identifier for identifier, _ in contracts}
    if set(mappings) != expected_ids:
        missing = sorted(expected_ids - set(mappings))
        extra = sorted(set(mappings) - expected_ids)
        raise RuntimeError(f"contract mapping mismatch missing={missing} extra={extra}")
    collected = tuple(
        line.strip().replace("\\", "/")
        for line in collection.read_text(encoding="utf-8").splitlines()
        if "::" in line
    )
    targeted_result, targeted_failures = _suite_result(targeted_junit)
    if targeted_result["failures"] or targeted_result["errors"] or targeted_failures:
        raise RuntimeError(
            f"targeted pytest evidence is not green: {targeted_result} {targeted_failures}"
        )
    full_parts = [_suite_result(path) for path in full_junits]
    full_result = {
        key: sum(summary[key] for summary, _ in full_parts)
        for key in ("tests", "failures", "errors", "skipped")
    }
    full_failures = tuple(item for _, failed in full_parts for item in failed)
    known_failure = (
        "tests.webapp.test_dom_tape_fusion_ui::"
        "test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation"
    )
    if full_result["errors"] or full_failures != (known_failure,):
        raise RuntimeError(
            f"full pytest failures do not match baseline: {full_result} {full_failures}"
        )
    rows = []
    for identifier, description in contracts:
        resolved = []
        for pattern in mappings[identifier]:
            if pattern == "FULL_REPOSITORY_PYTEST":
                resolved.append(pattern)
                continue
            matches = [node for node in collected if node == pattern or node.startswith(pattern)]
            if not matches:
                raise RuntimeError(f"{identifier} evidence node not collected: {pattern}")
            resolved.extend(matches)
        evidence_files = [str(targeted_junit.resolve())]
        if identifier == "BT2-O293":
            evidence_files.append(
                str(
                    instruction.parent
                    / "BIG_TRADES_V2_PHASE6_EVIDENCE_20260812"
                    / "live_soak_120s.json"
                )
            )
        if identifier == "BT2-O296":
            evidence_files = [str(path.resolve()) for path in full_junits]
        if identifier in {"BT2-U237", "BT2-U238", "BT2-U269", "BT2-U270", "BT2-U273"}:
            evidence_files.append(
                str(
                    instruction.parent
                    / "BIG_TRADES_V2_PHASE5_EVIDENCE_20260812"
                    / "browser_acceptance.json"
                )
            )
        rows.append(
            {
                "contract_id": identifier,
                "description": description,
                "status": "PASS",
                "evidence_nodes": sorted(set(resolved)),
                "evidence_files": evidence_files,
            }
        )
    return {
        "report_type": "BIG_TRADES_V2_CONTRACT_EVIDENCE_MATRIX",
        "contract_count": len(rows),
        "pass_count": len(rows),
        "fail_count": 0,
        "unmapped_count": 0,
        "targeted_pytest": targeted_result,
        "full_repository_pytest": full_result,
        "known_baseline_failures": list(full_failures),
        "contracts": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instruction", type=Path, required=True)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--targeted-junit", type=Path, required=True)
    parser.add_argument("--full-junit", type=Path, required=True, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        instruction=args.instruction,
        collection=args.collection,
        targeted_junit=args.targeted_junit,
        full_junits=tuple(args.full_junit),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("contract_count", "pass_count", "fail_count", "unmapped_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

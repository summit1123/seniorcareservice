"""Rolling monthly living-zone snapshots for the annual senior-driver fixture.

The monthly model deliberately separates the zone-fit window from the scored
month.  A month is evaluated with the trips in that calendar month, while the
DBSCAN/P90 living-zone basis only sees trips before the first day of that month.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.features.zone_features import (
    BUFFER_PERCENTILE,
    MAX_ZONE_BUFFER_M,
    MIN_ZONE_BUFFER_M,
    POINT_ROLES,
    build_customer_living_zone_criteria,
    classify_trip_against_living_zone,
    coerce_coordinate_pair,
    dbscan_point_record,
    grid_id,
    is_valid_point,
    nearest_center_distance_m,
    percentile,
    run_customer_dbscan,
)
from src.product.scoring_engine import (
    SeniorSafeMileageScoreInput,
    calculate_local_score_result,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_INPUT = ROOT / "data" / "fixtures" / "annual_persona_profiles.json"
DEFAULT_TRIP_INPUT = ROOT / "data" / "fixtures" / "annual_trip_logs.csv"
DEFAULT_EVENTS_INPUT = ROOT / "data" / "fixtures" / "monthly_scenario_events.json"
DEFAULT_CANDIDATE_RULES_INPUT = ROOT / "data" / "fixtures" / "candidate_rules.json"
DEFAULT_SNAPSHOT_OUTPUT = ROOT / "data" / "processed" / "monthly_zone_snapshots.json"
DEFAULT_SCORE_OUTPUT = ROOT / "data" / "processed" / "monthly_score_table.csv"

SNAPSHOT_SCHEMA_VERSION = "senior-monthly-living-zone-snapshots/v1"
SCORE_TABLE_SCHEMA_VERSION = "senior-monthly-score-table/v1"
ROLLING_WINDOW_DAYS = 60
DBSCAN_EPS = 0.012
DBSCAN_MIN_SAMPLES = 3
DEFAULT_WEIGHTS = {
    "w_mileage": 0.30,
    "w_in_zone": 0.30,
    "w_out_zone_safe": 0.20,
    "w_out_zone_change": 0.20,
}
REQUIRED_INTERPRETATIONS = (
    "existing_living_zone",
    "candidate_living_zone",
    "out_zone_safe_driving",
    "out_zone_pattern_change_risk",
)
RISK_EVENT_FIELDS = (
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
)
COERCE_FLOAT_FIELDS = {
    "start_gps_x",
    "start_gps_y",
    "end_gps_x",
    "end_gps_y",
    "trip_distance_km",
    "trip_duration_min",
    "avg_speed",
    "max_speed",
}
COERCE_INT_FIELDS = {
    "month",
    "trip_sequence",
    "night_drive_flag",
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
    "stop_count",
    "night_driving_signal",
    "sudden_braking_signal",
    "route_deviation_signal",
    "fatigue_indicator",
}


def read_annual_trip_rows(path: Path = DEFAULT_TRIP_INPUT) -> list[dict[str, Any]]:
    """Load annual fixture rows with typed numeric and date fields."""

    with path.open(newline="", encoding="utf-8") as csvfile:
        rows = []
        for row in csv.DictReader(csvfile):
            typed: dict[str, Any] = dict(row)
            for field in COERCE_FLOAT_FIELDS:
                typed[field] = float(typed[field])
            for field in COERCE_INT_FIELDS:
                typed[field] = int(typed[field])
            typed["service_date_dt"] = datetime.strptime(str(typed["service_date"]), "%Y-%m-%d").date()
            typed["trip_start_dt"] = datetime.strptime(str(typed["trip_start_time"]), "%Y-%m-%d %H:%M:%S")
            typed["trip_end_dt"] = datetime.strptime(str(typed["trip_end_time"]), "%Y-%m-%d %H:%M:%S")
            typed["night_flag"] = bool(typed["night_drive_flag"])
            rows.append(typed)
    return sorted(rows, key=lambda item: (str(item["customer_id"]), item["trip_start_dt"], str(item["trip_id"])))


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_selected_policy(path: Path = DEFAULT_CANDIDATE_RULES_INPUT) -> dict[str, Any]:
    """Return the selected deterministic policy weights used by the annual demo."""

    if not path.exists():
        return {
            "candidate_id": "local_default_policy",
            "weights": dict(DEFAULT_WEIGHTS),
            "thresholds": {
                "care_threshold": 70.0,
                "tier_threshold": {"S": 85, "A": 75, "B": 55, "C": 0},
            },
        }
    payload = read_json(path)
    selected = dict(payload["selected_candidate"])
    selected["weights"] = {key: float(value) for key, value in selected["weights"].items()}
    selected["thresholds"] = dict(selected["thresholds"])
    selected["thresholds"]["tier_threshold"] = {
        key: float(value) for key, value in selected["thresholds"]["tier_threshold"].items()
    }
    selected["thresholds"]["care_threshold"] = float(selected["thresholds"]["care_threshold"])
    return selected


def build_monthly_living_zone_outputs(
    *,
    profile_input: Path = DEFAULT_PROFILE_INPUT,
    trip_input: Path = DEFAULT_TRIP_INPUT,
    events_input: Path = DEFAULT_EVENTS_INPUT,
    candidate_rules_input: Path = DEFAULT_CANDIDATE_RULES_INPUT,
    year: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build monthly living-zone snapshots and the flat score table."""

    profile_payload = read_json(profile_input)
    events_payload = read_json(events_input)
    selected_policy = load_selected_policy(candidate_rules_input)
    weights = {key: float(value) for key, value in selected_policy["weights"].items()}
    rows = read_annual_trip_rows(trip_input)
    selected_year = int(year or profile_payload.get("year") or rows[0]["service_date_dt"].year)
    profiles_by_customer = {str(row["customer_id"]): row for row in profile_payload["drivers"]}
    events_by_customer_month = {
        (str(event["customer_id"]), int(event["month"])): event for event in events_payload["events"]
    }
    rows_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_customer[str(row["customer_id"])].append(row)

    snapshots: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    for customer_id, customer_rows in sorted(rows_by_customer.items()):
        profile = profiles_by_customer[customer_id]
        for month in range(1, 13):
            event = events_by_customer_month[(customer_id, month)]
            snapshot, score_row = build_customer_month_snapshot(
                customer_rows,
                profile=profile,
                event=event,
                month=month,
                year=selected_year,
                selected_policy_id=str(selected_policy["candidate_id"]),
                weights=weights,
            )
            snapshots.append(snapshot)
            score_rows.append(score_row)

    validate_monthly_outputs(snapshots, score_rows)
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "year": selected_year,
        "source_artifacts": {
            "profiles": relative_project_path(profile_input),
            "trips": relative_project_path(trip_input),
            "monthly_events": relative_project_path(events_input),
            "selected_policy": relative_project_path(candidate_rules_input),
        },
        "analysis_method": {
            "zone_model_backend": "rolling_60_day_dbscan_p90",
            "rolling_window_days": ROLLING_WINDOW_DAYS,
            "dbscan_eps": DBSCAN_EPS,
            "dbscan_min_samples": DBSCAN_MIN_SAMPLES,
            "buffer_percentile": BUFFER_PERCENTILE,
            "buffer_rule": "max(500m, min(P90, 2km))",
            "current_month_excluded_from_zone_fit": True,
            "baseline_policy": "January uses the pre-policy 60-day baseline trips; profile anchors are fallback only if DBSCAN cannot form a cluster.",
            "monthly_scores_are_evidence_not_discount_rates": True,
        },
        "selected_policy": {
            "candidate_id": selected_policy["candidate_id"],
            "weights": weights,
            "thresholds": selected_policy["thresholds"],
        },
        "driver_count": len(rows_by_customer),
        "months_per_driver": 12,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "by_driver_id": index_snapshots(snapshots, "driver_id"),
        "by_customer_id": index_snapshots(snapshots, "customer_id"),
    }
    return payload, score_rows


def build_customer_month_snapshot(
    customer_rows: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    event: dict[str, Any],
    month: int,
    year: int,
    selected_policy_id: str,
    weights: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    month_start = date(year, month, 1)
    month_end = next_month(month_start)
    basis_start = month_start - timedelta(days=ROLLING_WINDOW_DAYS)
    basis_rows = [
        row
        for row in customer_rows
        if basis_start <= row["service_date_dt"] < month_start
    ]
    current_rows = [
        row
        for row in customer_rows
        if month_start <= row["service_date_dt"] < month_end
    ]
    zone_model = build_rolling_zone_model(
        str(profile["customer_id"]),
        basis_rows,
        profile=profile,
    )
    if month == 1 and zone_model["basis_status"] == "rolling_60_day_dbscan":
        zone_model = dict(zone_model)
        zone_model["basis_status"] = "pre_policy_60_day_dbscan"
    basis_labeled = label_rows_with_monthly_zone(basis_rows, zone_model["criteria"], basis_rows)
    current_labeled = label_rows_with_monthly_zone(current_rows, zone_model["criteria"], basis_rows)
    interpretations = interpret_labeled_month_rows(current_labeled)
    score_input = build_month_score_input(basis_labeled, current_labeled)
    score_result = calculate_local_score_result(score_input, weights)
    monthly_distance_km = round(sum(float(row["trip_distance_km"]) for row in current_labeled), 2)
    interpretation_counts = dict(sorted(Counter(item["interpretation"] for item in interpretations).items()))
    reason_codes = build_month_reason_codes(
        interpretation_counts,
        score_result.risk_change_score,
        score_input,
        event,
    )
    score_row = build_month_score_row(
        current_labeled,
        score_input=score_input,
        score_result=score_result,
        zone_model=zone_model,
        event=event,
        month=month,
        year=year,
        selected_policy_id=selected_policy_id,
        interpretation_counts=interpretation_counts,
        reason_codes=reason_codes,
    )
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION + "/snapshot",
        "customer_id": str(profile["customer_id"]),
        "driver_id": str(profile["driver_id"]),
        "persona_type": str(profile["persona_type"]),
        "service_month": f"{year}-{month:02d}",
        "month": month,
        "basis_window": {
            "start_date": basis_start.isoformat(),
            "end_date": (month_start - timedelta(days=1)).isoformat(),
            "days": ROLLING_WINDOW_DAYS,
            "basis_trip_count": len(basis_rows),
            "scored_trip_count": len(current_rows),
            "basis_status": zone_model["basis_status"],
        },
        "leakage_guard": {
            "current_month_excluded_from_zone_fit": True,
            "current_month_trip_count_in_basis": count_current_month_leakage(basis_rows, year, month),
        },
        "living_zone": {
            "zone_model_backend": zone_model["zone_model_backend"],
            "cluster_count": len(zone_model["clusters"]),
            "centers": zone_model["centers"],
            "clusters": zone_model["clusters"],
            "buffer": {
                "departure_p90_raw_m": zone_model["departure_p90_raw_m"],
                "departure_p90_threshold_m": zone_model["departure_p90_threshold_m"],
                "departure_threshold_sample_count": zone_model["departure_threshold_sample_count"],
                "departure_threshold_percentile": BUFFER_PERCENTILE,
                "buffer_min_m": MIN_ZONE_BUFFER_M,
                "buffer_max_m": MAX_ZONE_BUFFER_M,
            },
        },
        "monthly_evidence": {
            "monthly_distance_km": monthly_distance_km,
            "trip_count": len(current_labeled),
            "in_zone_distance_ratio": score_input.recent_in_zone_ratio,
            "out_zone_distance_ratio": score_input.recent_out_zone_ratio,
            "out_zone_ratio_delta": score_input.out_zone_ratio_delta,
            "night_ratio_delta": score_input.night_ratio_delta,
            "risk_rate_delta_per_100km": score_input.risk_rate_delta_per_100km,
            "interpretation_counts": interpretation_counts,
            "reason_codes": reason_codes,
        },
        "scores": {
            "mileage_score": score_result.mileage_baseline_score,
            "in_zone_safe_driving_score": score_result.in_zone_safe_score,
            "out_zone_safe_driving_score": score_result.out_zone_safe_score,
            "out_zone_pattern_change_risk": score_result.risk_change_score,
            "monthly_integrated_evidence_score": score_result.senior_safe_mileage_score,
            "score_role": "annual_decision_evidence_not_monthly_discount",
        },
        "trip_interpretations": interpretations,
        "source_event": {
            "event_id": event["event_id"],
            "scenario_phase": event["scenario_phase"],
            "event_label_ko": event["event_label_ko"],
            "living_zone_interpretation_ko": event["living_zone_interpretation_ko"],
            "reason_code_hints": list(event["reason_code_hints"]),
        },
    }
    return snapshot, score_row


def build_rolling_zone_model(
    customer_id: str,
    basis_rows: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
) -> dict[str, Any]:
    records = [
        dbscan_point_record(row, role)
        for row in basis_rows
        for role in POINT_ROLES
        if is_valid_point(coerce_coordinate_pair(row, role))
    ]
    dbscan_result = run_customer_dbscan(records, eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES) if records else {}
    clusters = cluster_summaries(dbscan_result)
    centers = [
        {
            "center_longitude": cluster["center_longitude"],
            "center_latitude": cluster["center_latitude"],
        }
        for cluster in clusters
    ]
    basis_status = "rolling_60_day_dbscan"
    zone_model_backend = "rolling_60_day_dbscan_p90"

    if not centers:
        profile_model = profile_anchor_zone_model(customer_id, profile)
        centers = profile_model["centers"]
        clusters = profile_model["clusters"]
        basis_status = "profile_anchor_cold_start" if not basis_rows else "dbscan_no_cluster_profile_anchor"
        zone_model_backend = "profile_anchor_cold_start_p90"

    center_points = [
        (float(center["center_longitude"]), float(center["center_latitude"]))
        for center in centers
    ]
    distances = [
        nearest_center_distance_m(coerce_coordinate_pair(row, "end"), center_points)
        for row in basis_rows
        if center_points and is_valid_point(coerce_coordinate_pair(row, "end"))
    ]
    if not distances:
        distances = profile_destination_distances(profile, center_points)
    p90_raw = round(percentile(distances, BUFFER_PERCENTILE), 2) if distances else MIN_ZONE_BUFFER_M
    p90_threshold = round(max(MIN_ZONE_BUFFER_M, min(p90_raw, MAX_ZONE_BUFFER_M)), 2)
    departure_threshold = {
        "living_zone_departure_p90_raw_m": p90_raw,
        "living_zone_departure_p90_threshold_m": p90_threshold,
        "living_zone_departure_threshold_sample_count": len(distances),
        "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
    }
    criteria = build_customer_living_zone_criteria(
        customer_id,
        center_points,
        departure_threshold=departure_threshold,
        cluster_summaries=clusters,
    )
    return {
        "zone_model_backend": zone_model_backend,
        "basis_status": basis_status,
        "basis_trip_count": len(basis_rows),
        "dbscan_point_count": len(records),
        "centers": centers,
        "clusters": clusters,
        "criteria": criteria,
        "departure_p90_raw_m": p90_raw,
        "departure_p90_threshold_m": p90_threshold,
        "departure_threshold_sample_count": len(distances),
    }


def cluster_summaries(dbscan_result: dict[str, Any]) -> list[dict[str, Any]]:
    clusters = list(dbscan_result.get("clusters", [])) if dbscan_result else []
    summaries = [
        {key: value for key, value in cluster.items() if key != "points"}
        for cluster in clusters
    ]
    return sorted(summaries, key=lambda cluster: (-float(cluster["visit_frequency"]), int(cluster["cluster_id"])))


def profile_anchor_zone_model(customer_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    destinations = dict(profile.get("living_destinations", {}))
    home = destinations.get("home") or next(iter(destinations.values()))
    center = {
        "center_longitude": round(float(home["longitude"]), 6),
        "center_latitude": round(float(home["latitude"]), 6),
    }
    clusters = [
        {
            "cluster_id": 0,
            "center_longitude": center["center_longitude"],
            "center_latitude": center["center_latitude"],
            "point_count": 1,
            "visit_count": 0,
            "point_frequency": 1.0,
            "visit_frequency": 1.0,
            "start_point_count": 0,
            "end_point_count": 0,
            "avg_radius_m": 0.0,
            "median_radius_m": 0.0,
            "p90_radius_m": MIN_ZONE_BUFFER_M,
            "max_radius_m": MIN_ZONE_BUFFER_M,
            "radius_metric_m": MIN_ZONE_BUFFER_M,
            "boundary_min_longitude": center["center_longitude"],
            "boundary_max_longitude": center["center_longitude"],
            "boundary_min_latitude": center["center_latitude"],
            "boundary_max_latitude": center["center_latitude"],
            "boundary_width_m": 0.0,
            "boundary_height_m": 0.0,
            "boundary_area_km2": 0.0,
            "outer_extent_radius_m": MIN_ZONE_BUFFER_M,
            "source": "annual_profile_living_destinations",
        }
    ]
    return {"customer_id": customer_id, "centers": [center], "clusters": clusters}


def profile_destination_distances(profile: dict[str, Any], centers: list[tuple[float, float]]) -> list[float]:
    distances: list[float] = []
    for destination in dict(profile.get("living_destinations", {})).values():
        if destination.get("living_zone_role") == "outer":
            continue
        point = (float(destination["longitude"]), float(destination["latitude"]))
        if is_valid_point(point):
            distances.append(nearest_center_distance_m(point, centers))
    return distances


def label_rows_with_monthly_zone(
    rows: list[dict[str, Any]],
    criteria: dict[str, Any],
    basis_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    basis_destinations, basis_routes = basis_route_indexes(basis_rows)
    labeled: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        start = coerce_coordinate_pair(item, "start")
        end = coerce_coordinate_pair(item, "end")
        start_grid = grid_id(start[0], start[1])
        end_grid = grid_id(end[0], end[1])
        route_key = f"{start_grid}->{end_grid}"
        item["start_grid"] = start_grid
        item["end_grid"] = end_grid
        item["route_key"] = route_key
        item.update(classify_trip_against_living_zone(item, criteria))
        item["route_repeat_flag"] = int(route_key in basis_routes)
        item["new_destination_flag"] = int(end_grid not in basis_destinations)
        return_trip_types(item)
        labeled.append(item)
    return labeled


def basis_route_indexes(rows: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    destinations: set[str] = set()
    routes: set[str] = set()
    for row in rows:
        start = coerce_coordinate_pair(row, "start")
        end = coerce_coordinate_pair(row, "end")
        start_grid = grid_id(start[0], start[1])
        end_grid = grid_id(end[0], end[1])
        destinations.add(end_grid)
        routes.add(f"{start_grid}->{end_grid}")
    return destinations, routes


def return_trip_types(row: dict[str, Any]) -> None:
    for field in (
        "core_zone_flag",
        "buffer_zone_flag",
        "outer_zone_flag",
        "in_zone_flag",
        "out_zone_flag",
        "living_zone_outside_segment_flag",
        "route_repeat_flag",
        "new_destination_flag",
    ):
        row[field] = int(row.get(field, 0))


def interpret_labeled_month_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    destination_counts = Counter(str(row["end_grid"]) for row in rows)
    interpretations = []
    for row in rows:
        risk_count = trip_risk_event_count(row)
        is_night = bool(row.get("night_drive_flag"))
        if int(row.get("in_zone_flag", 0)):
            interpretation = "existing_living_zone"
        elif risk_count > 0 or is_night or int(row.get("route_deviation_signal", 0)):
            interpretation = "out_zone_pattern_change_risk"
        elif int(row.get("new_destination_flag", 0)) and destination_counts[str(row["end_grid"])] >= 2:
            interpretation = "candidate_living_zone"
        else:
            interpretation = "out_zone_safe_driving"
        interpretations.append(
            {
                "trip_id": str(row["trip_id"]),
                "destination_type": str(row.get("destination_type", "")),
                "destination_label_ko": str(row.get("destination_label_ko", "")),
                "zone_label_from_dbscan_p90": zone_label_from_flags(row),
                "interpretation": interpretation,
                "distance_km": round(float(row["trip_distance_km"]), 2),
                "risk_event_count": risk_count,
                "night_drive_flag": int(row.get("night_drive_flag", 0)),
                "route_repeat_flag": int(row.get("route_repeat_flag", 0)),
                "new_destination_flag": int(row.get("new_destination_flag", 0)),
            }
        )
    return interpretations


def zone_label_from_flags(row: dict[str, Any]) -> str:
    if int(row.get("core_zone_flag", 0)):
        return "core"
    if int(row.get("buffer_zone_flag", 0)):
        return "buffer"
    return "outer"


def build_month_score_input(
    basis_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
) -> SeniorSafeMileageScoreInput:
    current_total = total_distance(current_rows)
    basis_total = total_distance(basis_rows)
    current_out_zone = [row for row in current_rows if int(row.get("out_zone_flag", 0))]
    current_in_zone = [row for row in current_rows if int(row.get("in_zone_flag", 0))]
    basis_out_zone = [row for row in basis_rows if int(row.get("out_zone_flag", 0))]
    current_night_ratio = night_distance(current_rows) / current_total if current_total else 0.0
    basis_night_ratio = night_distance(basis_rows) / basis_total if basis_total else 0.0
    current_risk_rate = risk_events_per_100km(current_rows)
    basis_risk_rate = risk_events_per_100km(basis_rows)
    current_out_zone_ratio = total_distance(current_out_zone) / current_total if current_total else 0.0
    basis_out_zone_ratio = total_distance(basis_out_zone) / basis_total if basis_total else 0.0
    current_in_zone_km = total_distance(current_in_zone)
    current_out_zone_km = total_distance(current_out_zone)
    current_in_zone_night_ratio = night_distance(current_in_zone) / current_in_zone_km if current_in_zone_km else 0.0
    current_out_zone_night_ratio = (
        night_distance(current_out_zone) / current_out_zone_km if current_out_zone_km else 0.0
    )
    return SeniorSafeMileageScoreInput(
        annualized_recent_km=round(current_total * 12.0, 2),
        recent_trip_count=len(current_rows),
        recent_in_zone_ratio=round(1.0 - current_out_zone_ratio, 4) if current_total else 0.0,
        recent_out_zone_ratio=round(current_out_zone_ratio, 4),
        out_zone_ratio_delta=round(current_out_zone_ratio - basis_out_zone_ratio, 4),
        baseline_night_ratio=round(basis_night_ratio, 4),
        recent_night_ratio=round(current_night_ratio, 4),
        night_ratio_delta=round(current_night_ratio - basis_night_ratio, 4),
        baseline_risk_rate_per_100km=round(basis_risk_rate, 4),
        recent_risk_rate_per_100km=round(current_risk_rate, 4),
        risk_rate_delta_per_100km=round(current_risk_rate - basis_risk_rate, 4),
        recent_risk_signal_count=sum(trip_risk_event_count(row) for row in current_rows),
        recent_in_zone_km=round(current_in_zone_km, 2),
        recent_in_zone_night_ratio=round(current_in_zone_night_ratio, 4),
        recent_in_zone_risk_rate_per_100km=round(risk_events_per_100km(current_in_zone), 4),
        recent_out_zone_km=round(current_out_zone_km, 2),
        recent_out_zone_night_ratio=round(current_out_zone_night_ratio, 4),
        recent_out_zone_risk_rate_per_100km=round(risk_events_per_100km(current_out_zone), 4),
    )


def build_month_score_row(
    current_rows: list[dict[str, Any]],
    *,
    score_input: SeniorSafeMileageScoreInput,
    score_result: Any,
    zone_model: dict[str, Any],
    event: dict[str, Any],
    month: int,
    year: int,
    selected_policy_id: str,
    interpretation_counts: dict[str, int],
    reason_codes: list[str],
) -> dict[str, Any]:
    current_total = total_distance(current_rows)
    return {
        "schema_version": SCORE_TABLE_SCHEMA_VERSION,
        "customer_id": str(event["customer_id"]),
        "driver_id": str(event["driver_id"]),
        "persona_type": str(event["persona_type"]),
        "service_month": f"{year}-{month:02d}",
        "month": month,
        "selected_policy_id": selected_policy_id,
        "basis_status": zone_model["basis_status"],
        "basis_trip_count": zone_model["basis_trip_count"],
        "scored_trip_count": len(current_rows),
        "dbscan_cluster_count": len(zone_model["clusters"]),
        "living_zone_departure_p90_raw_m": zone_model["departure_p90_raw_m"],
        "living_zone_departure_p90_threshold_m": zone_model["departure_p90_threshold_m"],
        "living_zone_departure_threshold_sample_count": zone_model["departure_threshold_sample_count"],
        "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
        "monthly_total_distance_km": round(current_total, 2),
        "monthly_annualized_distance_km": score_input.annualized_recent_km,
        "in_zone_distance_km": score_input.recent_in_zone_km,
        "out_zone_distance_km": score_input.recent_out_zone_km,
        "in_zone_distance_ratio": score_input.recent_in_zone_ratio,
        "out_zone_distance_ratio": score_input.recent_out_zone_ratio,
        "out_zone_ratio_delta": score_input.out_zone_ratio_delta,
        "baseline_night_ratio": score_input.baseline_night_ratio,
        "monthly_night_ratio": score_input.recent_night_ratio,
        "night_ratio_delta": score_input.night_ratio_delta,
        "baseline_risk_rate_per_100km": score_input.baseline_risk_rate_per_100km,
        "monthly_risk_rate_per_100km": score_input.recent_risk_rate_per_100km,
        "risk_rate_delta_per_100km": score_input.risk_rate_delta_per_100km,
        "monthly_risk_signal_count": score_input.recent_risk_signal_count,
        "in_zone_night_ratio": score_input.recent_in_zone_night_ratio,
        "in_zone_risk_rate_per_100km": score_input.recent_in_zone_risk_rate_per_100km,
        "out_zone_night_ratio": score_input.recent_out_zone_night_ratio,
        "out_zone_risk_rate_per_100km": score_input.recent_out_zone_risk_rate_per_100km,
        "mileage_score": score_result.mileage_baseline_score,
        "in_zone_safe_driving_score": score_result.in_zone_safe_score,
        "out_zone_safe_driving_score": score_result.out_zone_safe_score,
        "out_zone_pattern_change_risk": score_result.risk_change_score,
        "monthly_integrated_evidence_score": score_result.senior_safe_mileage_score,
        "score_role": "annual_decision_evidence_not_monthly_discount",
        "existing_living_zone_trip_count": interpretation_counts.get("existing_living_zone", 0),
        "candidate_living_zone_trip_count": interpretation_counts.get("candidate_living_zone", 0),
        "out_zone_safe_driving_trip_count": interpretation_counts.get("out_zone_safe_driving", 0),
        "out_zone_pattern_change_risk_trip_count": interpretation_counts.get("out_zone_pattern_change_risk", 0),
        "dominant_interpretation": dominant_interpretation(interpretation_counts),
        "reason_codes": "|".join(reason_codes) if reason_codes else "NO_STRONG_RISK_CHANGE",
        "scenario_phase": event["scenario_phase"],
    }


def build_month_reason_codes(
    interpretation_counts: dict[str, int],
    risk_change_score: float,
    score_input: SeniorSafeMileageScoreInput,
    event: dict[str, Any],
) -> list[str]:
    codes = set(str(code) for code in event.get("reason_code_hints", []))
    if interpretation_counts.get("candidate_living_zone", 0):
        codes.add("CANDIDATE_LIVING_ZONE")
    if interpretation_counts.get("out_zone_safe_driving", 0):
        codes.add("OUT_ZONE_SAFE_DRIVING")
    if interpretation_counts.get("out_zone_pattern_change_risk", 0):
        codes.add("OUT_ZONE_PATTERN_CHANGE_RISK")
    if score_input.out_zone_ratio_delta > 0.12:
        codes.add("OUT_ZONE_RATIO_INCREASE")
    if score_input.night_ratio_delta > 0.08:
        codes.add("NIGHT_DRIVING_INCREASE")
    if score_input.risk_rate_delta_per_100km > 2.5:
        codes.add("RISK_EVENT_INCREASE")
    if risk_change_score < 20 and not interpretation_counts.get("out_zone_pattern_change_risk", 0):
        codes.add("NO_STRONG_RISK_CHANGE")
    return sorted(codes)


def dominant_interpretation(counts: dict[str, int]) -> str:
    if not counts:
        return "no_monthly_trip"
    ranked = sorted(counts.items(), key=lambda item: (-item[1], REQUIRED_INTERPRETATIONS.index(item[0])))
    return ranked[0][0]


def total_distance(rows: list[dict[str, Any]]) -> float:
    return sum(float(row.get("trip_distance_km", 0.0)) for row in rows)


def night_distance(rows: list[dict[str, Any]]) -> float:
    return sum(float(row.get("trip_distance_km", 0.0)) for row in rows if int(row.get("night_drive_flag", 0)))


def trip_risk_event_count(row: dict[str, Any]) -> int:
    return sum(int(row.get(field, 0)) for field in RISK_EVENT_FIELDS)


def risk_events_per_100km(rows: list[dict[str, Any]]) -> float:
    total_km = total_distance(rows)
    if total_km <= 0:
        return 0.0
    return sum(trip_risk_event_count(row) for row in rows) / total_km * 100.0


def count_current_month_leakage(rows: list[dict[str, Any]], year: int, month: int) -> int:
    return sum(1 for row in rows if row["service_date_dt"].year == year and row["service_date_dt"].month == month)


def next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def index_snapshots(snapshots: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        compact = {
            "service_month": snapshot["service_month"],
            "month": snapshot["month"],
            "basis_status": snapshot["basis_window"]["basis_status"],
            "basis_trip_count": snapshot["basis_window"]["basis_trip_count"],
            "scored_trip_count": snapshot["basis_window"]["scored_trip_count"],
            "living_zone": snapshot["living_zone"],
            "monthly_evidence": snapshot["monthly_evidence"],
            "scores": snapshot["scores"],
            "source_event": snapshot["source_event"],
        }
        indexed[str(snapshot[key])].append(compact)
    return {item_key: rows for item_key, rows in sorted(indexed.items())}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_monthly_outputs(
    snapshots: dict[str, Any],
    score_rows: list[dict[str, Any]],
    *,
    snapshot_output: Path = DEFAULT_SNAPSHOT_OUTPUT,
    score_output: Path = DEFAULT_SCORE_OUTPUT,
) -> dict[str, Path]:
    write_json(snapshot_output, snapshots)
    write_csv(score_output, score_rows)
    return {
        "monthly_zone_snapshots": snapshot_output,
        "monthly_score_table": score_output,
    }


def validate_monthly_outputs(
    snapshots: list[dict[str, Any]],
    score_rows: list[dict[str, Any]],
) -> None:
    if len(snapshots) != 360 or len(score_rows) != 360:
        raise ValueError(f"monthly outputs must contain 360 rows, got {len(snapshots)} snapshots/{len(score_rows)} scores")
    months_by_customer: dict[str, set[int]] = defaultdict(set)
    for snapshot, row in zip(snapshots, score_rows):
        customer_id = str(snapshot["customer_id"])
        months_by_customer[customer_id].add(int(snapshot["month"]))
        if snapshot["leakage_guard"]["current_month_trip_count_in_basis"] != 0:
            raise ValueError(f"{customer_id} {snapshot['service_month']} leaked current-month trips into zone fit")
        threshold = float(row["living_zone_departure_p90_threshold_m"])
        if not MIN_ZONE_BUFFER_M <= threshold <= MAX_ZONE_BUFFER_M:
            raise ValueError(f"{customer_id} {snapshot['service_month']} P90 buffer outside clamp: {threshold}")
        for field in (
            "mileage_score",
            "in_zone_safe_driving_score",
            "out_zone_safe_driving_score",
            "out_zone_pattern_change_risk",
            "monthly_integrated_evidence_score",
        ):
            value = float(row[field])
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{customer_id} {snapshot['service_month']} invalid score {field}={value}")
    invalid = {
        customer_id: sorted(months)
        for customer_id, months in months_by_customer.items()
        if months != set(range(1, 13))
    }
    if invalid:
        raise ValueError(f"each customer needs all 12 months: {invalid}")


def relative_project_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)

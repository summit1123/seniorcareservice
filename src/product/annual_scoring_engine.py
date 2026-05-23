"""Annual Senior Safe Mileage score aggregation from monthly evidence rows."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.features.monthly_living_zone import (
    DEFAULT_CANDIDATE_RULES_INPUT,
    DEFAULT_PROFILE_INPUT,
    DEFAULT_SCORE_OUTPUT,
    DEFAULT_SNAPSHOT_OUTPUT,
    load_selected_policy,
    read_json,
    relative_project_path,
    write_csv,
)
from src.features.zone_features import percentile
from src.product.ab_comparison import calculate_tier, care_decision
from src.product.scoring_engine import calculate_mileage_baseline_score, calculate_senior_safe_mileage_score


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNUAL_SCORE_OUTPUT = ROOT / "data" / "processed" / "annual_score_table.csv"
ANNUAL_SCORE_SCHEMA_VERSION = "senior-annual-score-table/v1"
RISK_AGGREGATION_METHOD = "max(weighted_annual_avg, trailing_quarter_avg, monthly_p90)"
RAW_RISK_TOP_20_THRESHOLD = 41.14
PROPOSAL_CARE_THRESHOLD = 70.0
PROPOSAL_SCORE_FLOOR = 55.0


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def build_annual_score_table(
    *,
    monthly_score_input: Path = DEFAULT_SCORE_OUTPUT,
    profile_input: Path = DEFAULT_PROFILE_INPUT,
    candidate_rules_input: Path = DEFAULT_CANDIDATE_RULES_INPUT,
) -> list[dict[str, Any]]:
    """Aggregate the 12 monthly evidence rows into one annual score per driver."""

    monthly_rows = read_csv_rows(monthly_score_input)
    profile_payload = read_json(profile_input)
    profiles_by_customer = {str(profile["customer_id"]): profile for profile in profile_payload["drivers"]}
    selected_policy = load_selected_policy(candidate_rules_input)
    weights = {key: float(value) for key, value in selected_policy["weights"].items()}
    thresholds = dict(selected_policy["thresholds"])
    tier_threshold = {key: float(value) for key, value in thresholds["tier_threshold"].items()}
    care_threshold = float(thresholds["care_threshold"])

    by_customer: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in monthly_rows:
        by_customer[str(row["customer_id"])].append(row)

    annual_rows: list[dict[str, Any]] = []
    for customer_id, rows in sorted(by_customer.items()):
        rows = sorted(rows, key=lambda row: int(row["month"]))
        if len(rows) != 12:
            raise ValueError(f"{customer_id} requires 12 monthly score rows, got {len(rows)}")
        profile = profiles_by_customer[customer_id]
        annual_rows.append(
            build_customer_annual_score_row(
                rows,
                profile=profile,
                selected_policy_id=str(selected_policy["candidate_id"]),
                weights=weights,
                care_threshold=care_threshold,
                tier_threshold=tier_threshold,
            )
        )
    validate_annual_score_rows(annual_rows)
    return annual_rows


def build_customer_annual_score_row(
    rows: list[dict[str, str]],
    *,
    profile: dict[str, Any],
    selected_policy_id: str,
    weights: dict[str, float],
    care_threshold: float,
    tier_threshold: dict[str, float],
) -> dict[str, Any]:
    annual_distance = sum_float(rows, "monthly_total_distance_km")
    annual_trip_count = sum_int(rows, "scored_trip_count")
    in_zone_distance = sum_float(rows, "in_zone_distance_km")
    out_zone_distance = sum_float(rows, "out_zone_distance_km")
    annual_mileage_score = calculate_mileage_baseline_score(annual_distance)
    annual_in_zone_score = weighted_average(rows, "in_zone_safe_driving_score", "in_zone_distance_km")
    annual_out_zone_score = (
        weighted_average(rows, "out_zone_safe_driving_score", "out_zone_distance_km")
        if out_zone_distance > 0
        else 100.0
    )
    annual_risk_score = annual_risk_change_score(rows)
    annual_score = calculate_senior_safe_mileage_score(
        mileage_baseline_score=annual_mileage_score,
        in_zone_safe_score=annual_in_zone_score,
        out_zone_safe_score=annual_out_zone_score,
        risk_change_score=annual_risk_score,
        weights=weights,
    )
    tier = calculate_tier(annual_score, tier_threshold)
    preventive_detected = annual_risk_score >= care_threshold or annual_score < PROPOSAL_SCORE_FLOOR
    decision = care_decision(preventive_detected, tier, annual_risk_score)
    interpretation_counts = annual_interpretation_counts(rows)
    reason_codes = annual_reason_codes(rows, annual_risk_score, decision)

    return {
        "schema_version": ANNUAL_SCORE_SCHEMA_VERSION,
        "customer_id": str(profile["customer_id"]),
        "driver_id": str(profile["driver_id"]),
        "persona_type": str(profile["persona_type"]),
        "selected_policy_id": selected_policy_id,
        "months_evaluated": len(rows),
        "annual_total_distance_km": round(annual_distance, 2),
        "annual_trip_count": annual_trip_count,
        "annual_in_zone_distance_km": round(in_zone_distance, 2),
        "annual_out_zone_distance_km": round(out_zone_distance, 2),
        "annual_in_zone_distance_ratio": round(in_zone_distance / annual_distance, 4) if annual_distance else 0.0,
        "annual_out_zone_distance_ratio": round(out_zone_distance / annual_distance, 4) if annual_distance else 0.0,
        "annual_living_zone_stability_score": round(
            min(100.0, max(0.0, (in_zone_distance / annual_distance * 100.0) if annual_distance else 0.0)),
            2,
        ),
        "annual_mileage_score": annual_mileage_score,
        "annual_in_zone_safe_driving_score": annual_in_zone_score,
        "annual_out_zone_safe_driving_score": annual_out_zone_score,
        "annual_out_zone_pattern_change_risk": annual_risk_score,
        "annual_senior_safe_mileage_score": annual_score,
        "annual_score_tier": tier,
        "annual_decision_signal": decision,
        "preventive_care_detected": int(preventive_detected),
        "care_threshold": round(care_threshold, 2),
        "tier_threshold_json": json.dumps(tier_threshold, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        "weights_json": json.dumps(weights, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        "risk_aggregation_method": RISK_AGGREGATION_METHOD,
        "weighted_annual_risk_avg": weighted_average(rows, "out_zone_pattern_change_risk", "monthly_total_distance_km"),
        "trailing_quarter_risk_avg": average([float(row["out_zone_pattern_change_risk"]) for row in rows[-3:]]),
        "monthly_p90_risk": round(percentile([float(row["out_zone_pattern_change_risk"]) for row in rows], 0.90), 2),
        "high_risk_month_count": sum(1 for row in rows if float(row["out_zone_pattern_change_risk"]) >= care_threshold),
        "candidate_living_zone_month_count": sum(
            1 for row in rows if int(float(row["candidate_living_zone_trip_count"])) > 0
        ),
        "out_zone_safe_month_count": sum(
            1 for row in rows if int(float(row["out_zone_safe_driving_trip_count"])) > 0
        ),
        "out_zone_pattern_change_risk_month_count": sum(
            1 for row in rows if int(float(row["out_zone_pattern_change_risk_trip_count"])) > 0
        ),
        "existing_living_zone_trip_count": interpretation_counts["existing_living_zone"],
        "candidate_living_zone_trip_count": interpretation_counts["candidate_living_zone"],
        "out_zone_safe_driving_trip_count": interpretation_counts["out_zone_safe_driving"],
        "out_zone_pattern_change_risk_trip_count": interpretation_counts["out_zone_pattern_change_risk"],
        "dominant_annual_interpretation": dominant_annual_interpretation(interpretation_counts),
        "annual_reason_codes": "|".join(reason_codes),
        "monthly_scores_are_evidence_not_discount_rates": 1,
    }


def annual_risk_change_score(rows: list[dict[str, str]]) -> float:
    values = [float(row["out_zone_pattern_change_risk"]) for row in rows]
    weighted = weighted_average(rows, "out_zone_pattern_change_risk", "monthly_total_distance_km")
    trailing_quarter = average(values[-3:])
    p90_value = percentile(values, 0.90)
    raw_risk = max(weighted, trailing_quarter, p90_value)
    return calibrate_risk_change_to_proposal_scale(raw_risk)


def calibrate_risk_change_to_proposal_scale(raw_risk: float) -> float:
    """Map the selected simulation gate to the proposal's 70-point care gate."""

    raw_risk = max(0.0, min(100.0, float(raw_risk)))
    if raw_risk < RAW_RISK_TOP_20_THRESHOLD:
        return round(raw_risk, 2)
    scaled = PROPOSAL_CARE_THRESHOLD + (
        (raw_risk - RAW_RISK_TOP_20_THRESHOLD) / (100.0 - RAW_RISK_TOP_20_THRESHOLD)
    ) * (100.0 - PROPOSAL_CARE_THRESHOLD)
    return round(max(PROPOSAL_CARE_THRESHOLD, min(100.0, scaled)), 2)


def weighted_average(rows: list[dict[str, str]], value_field: str, weight_field: str) -> float:
    total_weight = sum_float(rows, weight_field)
    if total_weight <= 0:
        return average([float(row[value_field]) for row in rows])
    value = sum(float(row[value_field]) * float(row[weight_field]) for row in rows) / total_weight
    return round(value, 2)


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def sum_float(rows: list[dict[str, str]], field: str) -> float:
    return sum(float(row[field]) for row in rows)


def sum_int(rows: list[dict[str, str]], field: str) -> int:
    return sum(int(float(row[field])) for row in rows)


def annual_interpretation_counts(rows: list[dict[str, str]]) -> Counter[str]:
    return Counter(
        {
            "existing_living_zone": sum_int(rows, "existing_living_zone_trip_count"),
            "candidate_living_zone": sum_int(rows, "candidate_living_zone_trip_count"),
            "out_zone_safe_driving": sum_int(rows, "out_zone_safe_driving_trip_count"),
            "out_zone_pattern_change_risk": sum_int(rows, "out_zone_pattern_change_risk_trip_count"),
        }
    )


def dominant_annual_interpretation(counts: Counter[str]) -> str:
    order = {
        "existing_living_zone": 0,
        "candidate_living_zone": 1,
        "out_zone_safe_driving": 2,
        "out_zone_pattern_change_risk": 3,
    }
    return sorted(counts.items(), key=lambda item: (-item[1], order[item[0]]))[0][0]


def annual_reason_codes(rows: list[dict[str, str]], annual_risk_score: float, decision: str) -> list[str]:
    """Build annual reason codes from annual evidence, not a raw monthly union.

    Monthly rows can legitimately contain mixed signals across 12 months.  For
    the annual report we only keep signals that survive aggregation, otherwise
    the same driver can show contradictory reasons such as both risk increase
    and no strong risk change.
    """

    codes: set[str] = set()
    annual_distance = sum_float(rows, "monthly_total_distance_km")
    high_risk_months = sum(1 for row in rows if float(row["out_zone_pattern_change_risk"]) >= 50.0)
    out_zone_increase_months = sum(1 for row in rows if float(row["out_zone_ratio_delta"]) >= 0.08)
    night_increase_months = sum(1 for row in rows if float(row["night_ratio_delta"]) >= 0.08)
    risk_event_increase_months = sum(1 for row in rows if float(row["risk_rate_delta_per_100km"]) >= 0.50)
    out_zone_safe_months = sum(1 for row in rows if int(float(row["out_zone_safe_driving_trip_count"])) > 0)
    candidate_zone_months = sum(1 for row in rows if int(float(row["candidate_living_zone_trip_count"])) > 0)
    low_risk_events = average([float(row["monthly_risk_signal_count"]) for row in rows]) <= 2.0

    if annual_distance <= 15000:
        codes.add("LOW_MILEAGE")
    if candidate_zone_months >= 2:
        codes.add("CANDIDATE_LIVING_ZONE")
    if high_risk_months >= 2 or annual_risk_score >= 50:
        codes.add("OUT_ZONE_PATTERN_CHANGE_RISK")
    if out_zone_increase_months >= 2:
        codes.add("OUT_ZONE_RATIO_INCREASE")
    if night_increase_months >= 2:
        codes.add("NIGHT_DRIVING_INCREASE")
    if risk_event_increase_months >= 2:
        codes.add("RISK_EVENT_INCREASE")
    if decision != "예방 케어" and out_zone_safe_months >= 3 and annual_risk_score < 45:
        codes.add("OUT_ZONE_SAFE_DRIVING")
    if low_risk_events and annual_risk_score < 35:
        codes.add("LOW_RISK_EVENTS")
    if annual_risk_score < 35 and high_risk_months == 0:
        codes.add("NO_STRONG_RISK_CHANGE")
    if out_zone_increase_months == 0 and annual_risk_score < 35:
        codes.add("NO_RECENT_OUT_ZONE_SPIKE")
    if decision == "예방 케어":
        codes.add("PREVENTIVE_CARE_REVIEW")
    if not codes:
        codes.add("NO_STRONG_RISK_CHANGE")

    priority = {
        "PREVENTIVE_CARE_REVIEW": 0,
        "OUT_ZONE_PATTERN_CHANGE_RISK": 1,
        "RISK_EVENT_INCREASE": 2,
        "OUT_ZONE_RATIO_INCREASE": 3,
        "NIGHT_DRIVING_INCREASE": 4,
        "CANDIDATE_LIVING_ZONE": 5,
        "OUT_ZONE_SAFE_DRIVING": 6,
        "LOW_RISK_EVENTS": 7,
        "LOW_MILEAGE": 8,
        "NO_RECENT_OUT_ZONE_SPIKE": 9,
        "NO_STRONG_RISK_CHANGE": 10,
    }
    return sorted(codes, key=lambda code: (priority.get(code, 99), code))


def validate_annual_score_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 30:
        raise ValueError(f"annual score table must contain 30 drivers, got {len(rows)}")
    for row in rows:
        if int(row["months_evaluated"]) != 12:
            raise ValueError(f"{row['customer_id']} annual score must aggregate 12 months")
        for field in (
            "annual_mileage_score",
            "annual_in_zone_safe_driving_score",
            "annual_out_zone_safe_driving_score",
            "annual_out_zone_pattern_change_risk",
            "annual_senior_safe_mileage_score",
        ):
            value = float(row[field])
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{row['customer_id']} invalid {field}: {value}")


def write_annual_score_table(
    rows: list[dict[str, Any]],
    output_path: Path = DEFAULT_ANNUAL_SCORE_OUTPUT,
) -> Path:
    write_csv(output_path, rows)
    return output_path


def build_annual_scoring_manifest(
    annual_rows: list[dict[str, Any]],
    *,
    monthly_score_input: Path = DEFAULT_SCORE_OUTPUT,
    monthly_snapshot_input: Path = DEFAULT_SNAPSHOT_OUTPUT,
    annual_score_output: Path = DEFAULT_ANNUAL_SCORE_OUTPUT,
) -> dict[str, Any]:
    risk_values = [float(row["annual_out_zone_pattern_change_risk"]) for row in annual_rows]
    score_values = [float(row["annual_senior_safe_mileage_score"]) for row in annual_rows]
    return {
        "schema_version": ANNUAL_SCORE_SCHEMA_VERSION + "/manifest",
        "source_artifacts": {
            "monthly_score_table": relative_project_path(monthly_score_input),
            "monthly_zone_snapshots": relative_project_path(monthly_snapshot_input),
        },
        "output_artifact": relative_project_path(annual_score_output),
        "driver_count": len(annual_rows),
        "months_per_driver": 12,
        "score_summary": {
            "annual_score_min": round(min(score_values), 2),
            "annual_score_max": round(max(score_values), 2),
            "risk_score_min": round(min(risk_values), 2),
            "risk_score_max": round(max(risk_values), 2),
            "preventive_care_detected_count": sum(int(row["preventive_care_detected"]) for row in annual_rows),
        },
    }

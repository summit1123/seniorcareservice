"""Annual A/B comparison for the React judge demo.

The existing baseline uses only annual evaluation-period mileage and vehicle
class. The proposed outcome still compares on the annual contract surface, but
uses monthly living-zone evidence to adjust each driver's annual discount rate.
This module intentionally does not force the proposed portfolio total to match
the existing mileage total; the difference is part of the simulation result.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.product.mileage_discount_table import lookup_existing_mileage_discount


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_INPUT = ROOT / "data" / "fixtures" / "annual_persona_profiles.json"
DEFAULT_ANNUAL_SCORE_INPUT = ROOT / "data" / "processed" / "annual_score_table.csv"
DEFAULT_MONTHLY_SCORE_INPUT = ROOT / "data" / "processed" / "monthly_score_table.csv"
DEFAULT_COMPARISON_OUTPUT = ROOT / "data" / "processed" / "annual_ab_comparison.csv"
DEFAULT_VIEW_MODEL_OUTPUT = ROOT / "data" / "fixtures" / "judge_demo_view_model.json"

COMPARISON_SCHEMA_VERSION = "senior-safe-mileage-annual-ab-comparison/v1"
VIEW_MODEL_SCHEMA_VERSION = "senior-safe-mileage-judge-demo-view-model/v1"
PROPOSED_DISCOUNT_RULE_ID = "annual_integrated_score_adjusted_discount/v4"
MAX_DISCOUNT_RATE_PCT = 42.0


@dataclass(frozen=True)
class ProposedDiscountOutcome:
    pricing_action: str
    care_required: bool
    rationale_code: str


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def build_annual_ab_comparison_rows(
    *,
    profile_input: Path = DEFAULT_PROFILE_INPUT,
    annual_score_input: Path = DEFAULT_ANNUAL_SCORE_INPUT,
) -> list[dict[str, Any]]:
    profile_payload = read_json(profile_input)
    annual_rows = read_csv_rows(annual_score_input)
    profiles_by_customer = {str(profile["customer_id"]): profile for profile in profile_payload["drivers"]}

    comparison_rows: list[dict[str, Any]] = []
    for annual in sorted(annual_rows, key=lambda row: str(row["customer_id"])):
        customer_id = str(annual["customer_id"])
        profile = profiles_by_customer[customer_id]
        base_premium = int(profile["base_premium_krw"])
        vehicle_class = str(profile["vehicle_class"])
        annual_distance = round(float(annual["annual_total_distance_km"]), 2)
        existing = lookup_existing_mileage_discount(annual_distance, vehicle_class)
        proposed = calculate_proposed_discount_outcome(
            annual_score=float(annual["annual_senior_safe_mileage_score"]),
            annual_score_tier=str(annual["annual_score_tier"]),
            annual_decision_signal=str(annual["annual_decision_signal"]),
        )
        existing_discount_amount = discount_amount(base_premium, existing.discount_rate_pct)
        same_input_contract = build_same_input_contract(
            customer_id=customer_id,
            year=int(profile_payload["year"]),
            annual_distance_km=annual_distance,
            vehicle_class=vehicle_class,
            base_premium_krw=base_premium,
        )

        comparison_rows.append(
            {
                "schema_version": COMPARISON_SCHEMA_VERSION,
                "customer_id": customer_id,
                "driver_id": str(profile["driver_id"]),
                "persona_type": str(profile["persona_type"]),
                "persona_display_name_ko": str(profile["persona_display_name_ko"]),
                "vehicle_class": vehicle_class,
                "base_premium_krw": base_premium,
                "annual_total_distance_km": annual_distance,
                "annual_distance_scope": "evaluation_period_only",
                "baseline_60_day_excluded_from_discount": 1,
                "existing_discount_table_id": existing.table_id,
                "existing_matched_tier_label": existing.matched_tier_label,
                "existing_discount_rate_pct": existing.discount_rate_pct,
                "existing_discount_amount_krw": existing_discount_amount,
                "existing_net_premium_krw": base_premium - existing_discount_amount,
                "proposed_discount_rule_id": PROPOSED_DISCOUNT_RULE_ID,
                "annual_senior_safe_mileage_score": round(float(annual["annual_senior_safe_mileage_score"]), 2),
                "annual_score_tier": str(annual["annual_score_tier"]),
                "annual_decision_signal": str(annual["annual_decision_signal"]),
                "annual_out_zone_pattern_change_risk": round(float(annual["annual_out_zone_pattern_change_risk"]), 2),
                "proposed_pricing_action": proposed.pricing_action,
                "preventive_care_required": int(proposed.care_required),
                "proposed_rationale_code": proposed.rationale_code,
                "annual_reason_codes": str(annual["annual_reason_codes"]),
                "same_input_contract_id": same_input_contract["contract_id"],
                "same_input_contract_json": json.dumps(
                    same_input_contract,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )

    apply_score_adjusted_proposed_rates(comparison_rows)
    validate_comparison_rows(comparison_rows)
    return comparison_rows


def calculate_proposed_discount_outcome(
    *,
    annual_score: float,
    annual_score_tier: str,
    annual_decision_signal: str,
) -> ProposedDiscountOutcome:
    if annual_decision_signal == "예방 케어":
        return ProposedDiscountOutcome(
            pricing_action="score_adjusted_discount_with_preventive_care",
            care_required=True,
            rationale_code="PREVENTIVE_CARE_DISCOUNT_REDUCED_AND_CARE",
        )

    if annual_decision_signal == "우대":
        rationale_code = "HIGH_INTEGRATED_SCORE_RECEIVES_RATE_UPLIFT"
    elif annual_decision_signal == "기본":
        rationale_code = "STANDARD_SCORE_RECEIVES_SMALL_RATE_ADJUSTMENT"
    else:
        rationale_code = "LOW_SCORE_RECEIVES_RATE_REDUCTION"
    return ProposedDiscountOutcome(
        pricing_action="annual_integrated_score_adjusted_discount",
        care_required=False,
        rationale_code=rationale_code,
    )


def discount_amount(base_premium_krw: int, discount_rate_pct: float) -> int:
    return int(round(base_premium_krw * float(discount_rate_pct) / 100.0))


def apply_score_adjusted_proposed_rates(rows: list[dict[str, Any]]) -> None:
    """Calculate proposed rates independently from the existing total budget.

    Existing mileage remains the baseline comparison. The proposed discount is
    anchored to the mileage tier, then adjusted by the annual integrated score:
    stable drivers receive an uplift, ordinary drivers receive a small
    adjustment, and preventive-care drivers keep a reduced discount instead of
    being presented as an extra reward case.
    """

    for row in rows:
        base_premium = int(row["base_premium_krw"])
        existing_rate = float(row["existing_discount_rate_pct"])
        existing_discount_amount = int(row["existing_discount_amount_krw"])
        proposed_rate = calculate_score_adjusted_discount_rate(
            existing_rate_pct=existing_rate,
            annual_score=float(row["annual_senior_safe_mileage_score"]),
            annual_score_tier=str(row["annual_score_tier"]),
            annual_decision_signal=str(row["annual_decision_signal"]),
            annual_out_zone_pattern_change_risk=float(row["annual_out_zone_pattern_change_risk"]),
        )
        proposed_discount_amount = discount_amount(base_premium, proposed_rate)
        row["proposed_discount_rate_pct"] = proposed_rate
        row["proposed_discount_amount_krw"] = proposed_discount_amount
        row["proposed_net_premium_krw"] = base_premium - proposed_discount_amount
        row["discount_rate_delta_pct"] = round(proposed_rate - existing_rate, 2)
        row["discount_amount_delta_krw"] = proposed_discount_amount - existing_discount_amount
        row["premium_delta_krw"] = (base_premium - proposed_discount_amount) - (base_premium - existing_discount_amount)


def calculate_score_adjusted_discount_rate(
    *,
    existing_rate_pct: float,
    annual_score: float,
    annual_score_tier: str,
    annual_decision_signal: str,
    annual_out_zone_pattern_change_risk: float,
) -> float:
    existing_rate = float(existing_rate_pct)
    score = max(0.0, min(100.0, float(annual_score)))
    risk = max(0.0, min(100.0, float(annual_out_zone_pattern_change_risk)))

    if annual_decision_signal == "예방 케어":
        risk_reduction = 9.0 + max(0.0, risk - 41.14) * 0.12
        rate = existing_rate - risk_reduction
    elif annual_decision_signal == "우대":
        tier_bonus = 5.0 if annual_score_tier == "S" else 3.5
        score_bonus = max(0.0, score - 75.0) * 0.08
        rate = existing_rate + tier_bonus + score_bonus
    else:
        score_adjustment = (score - 72.0) * 0.16
        risk_guard = 1.5 if risk >= 38.0 else 0.0
        rate = existing_rate + score_adjustment - risk_guard

    return round(max(1.0, min(MAX_DISCOUNT_RATE_PCT, rate)), 2)


def adjust_rounding_to_budget(amounts: list[int], rows: list[dict[str, Any]], budget: int) -> None:
    difference = int(budget) - sum(amounts)
    if difference == 0:
        return
    direction = 1 if difference > 0 else -1
    remaining = abs(difference)
    ordered_indexes = sorted(
        range(len(rows)),
        key=lambda index: float(rows[index]["annual_senior_safe_mileage_score"]),
        reverse=direction > 0,
    )
    cursor = 0
    while remaining > 0 and ordered_indexes:
        index = ordered_indexes[cursor % len(ordered_indexes)]
        max_amount = discount_amount(int(rows[index]["base_premium_krw"]), MAX_DISCOUNT_RATE_PCT)
        if direction > 0 and amounts[index] >= max_amount:
            cursor += 1
            if cursor > len(ordered_indexes) * 2:
                break
            continue
        if direction < 0 and amounts[index] <= 0:
            cursor += 1
            if cursor > len(ordered_indexes) * 2:
                break
            continue
        amounts[index] += direction
        remaining -= 1
        cursor += 1


def build_same_input_contract(
    *,
    customer_id: str,
    year: int,
    annual_distance_km: float,
    vehicle_class: str,
    base_premium_krw: int,
) -> dict[str, Any]:
    payload = {
        "customer_id": customer_id,
        "evaluation_year": year,
        "annual_total_distance_km": annual_distance_km,
        "vehicle_class": vehicle_class,
        "base_premium_krw": base_premium_krw,
        "period_role_scope": "evaluation",
        "baseline_60_day_usage": "living_zone_fit_only",
        "existing_model_inputs": ["annual_total_distance_km", "vehicle_class", "base_premium_krw"],
        "proposed_model_inputs": [
            "annual_total_distance_km",
            "vehicle_class",
            "base_premium_krw",
            "annual_senior_safe_mileage_score",
            "annual_out_zone_pattern_change_risk",
        ],
        "proposed_budget_rule": "score_adjusted_discount_without_portfolio_budget_forcing",
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    payload["contract_id"] = "same-annual-input:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return payload


def build_judge_demo_view_model(
    comparison_rows: list[dict[str, Any]],
    *,
    profile_input: Path = DEFAULT_PROFILE_INPUT,
    annual_score_input: Path = DEFAULT_ANNUAL_SCORE_INPUT,
    monthly_score_input: Path = DEFAULT_MONTHLY_SCORE_INPUT,
) -> dict[str, Any]:
    profile_payload = read_json(profile_input)
    annual_rows = read_csv_rows(annual_score_input)
    monthly_rows = read_csv_rows(monthly_score_input)
    profiles_by_customer = {str(profile["customer_id"]): profile for profile in profile_payload["drivers"]}
    annual_by_customer = {str(row["customer_id"]): row for row in annual_rows}
    comparison_by_customer = {str(row["customer_id"]): row for row in comparison_rows}
    monthly_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in monthly_rows:
        monthly_by_customer[str(row["customer_id"])].append(compact_monthly_row(row))

    drivers = []
    for customer_id in sorted(profiles_by_customer):
        profile = profiles_by_customer[customer_id]
        drivers.append(
            {
                "customer_id": customer_id,
                "driver_id": profile["driver_id"],
                "persona_type": profile["persona_type"],
                "persona_display_name_ko": profile["persona_display_name_ko"],
                "vehicle_class": profile["vehicle_class"],
                "base_premium_krw": profile["base_premium_krw"],
                "living_pattern": profile["living_pattern"],
                "care_context": profile["care_context"],
                "living_destinations": compact_destinations(profile["living_destinations"]),
                "annual_score": compact_annual_row(annual_by_customer[customer_id]),
                "ab_comparison": compact_comparison_row(comparison_by_customer[customer_id]),
                "monthly_evidence": sorted(monthly_by_customer[customer_id], key=lambda row: row["month"]),
            }
        )

    summary = build_comparison_summary(comparison_rows)
    return {
        "schema_version": VIEW_MODEL_SCHEMA_VERSION,
        "fixture_year": int(profile_payload["year"]),
        "source_artifacts": {
            "profiles": "data/fixtures/annual_persona_profiles.json",
            "monthly_score_table": "data/processed/monthly_score_table.csv",
            "monthly_zone_snapshots": "data/processed/monthly_zone_snapshots.json",
            "annual_score_table": "data/processed/annual_score_table.csv",
            "annual_ab_comparison": "data/processed/annual_ab_comparison.csv",
        },
        "product_frame": {
            "product_name_ko": "안심반경 시니어 마일리지",
            "existing_formula_ko": "연간 주행거리 + 차종 -> 기존 마일리지 할인율",
            "proposed_formula_ko": "연간 주행거리 + 12개월 생활권 안정성 + 생활권 밖 안전성 + 위험변화 -> 통합점수 등급별 연간 할인율 조정",
            "llm_boundary_ko": "LLM은 보험료를 산정하지 않고 계산된 근거를 보험사 직원용 설명문으로 바꾼다.",
        },
        "summary": summary,
        "persona_summaries": build_persona_summaries(drivers),
        "existing_tier_segments": build_existing_tier_segments(comparison_rows),
        "driver_options": [
            {
                "customer_id": driver["customer_id"],
                "driver_id": driver["driver_id"],
                "label": f"{driver['driver_id']} · {driver['persona_display_name_ko']}",
                "persona_type": driver["persona_type"],
                "annual_decision_signal": driver["ab_comparison"]["annual_decision_signal"],
                "existing_matched_tier_label": driver["ab_comparison"]["existing_matched_tier_label"],
            }
            for driver in drivers
        ],
        "drivers": drivers,
        "by_customer_id": {
            driver["customer_id"]: {
                "driver_id": driver["driver_id"],
                "persona_type": driver["persona_type"],
                "annual_decision_signal": driver["ab_comparison"]["annual_decision_signal"],
                "preventive_care_required": driver["ab_comparison"]["preventive_care_required"],
                "annual_total_distance_km": driver["ab_comparison"]["annual_total_distance_km"],
                "existing_discount_rate_pct": driver["ab_comparison"]["existing_discount_rate_pct"],
                "proposed_discount_rate_pct": driver["ab_comparison"]["proposed_discount_rate_pct"],
            }
            for driver in drivers
        },
    }


def compact_destinations(destinations: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {
            "label_ko": value["label_ko"],
            "living_zone_role": value["living_zone_role"],
            "longitude": value["longitude"],
            "latitude": value["latitude"],
        }
        for key, value in destinations.items()
    }


def compact_annual_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "annual_total_distance_km": float(row["annual_total_distance_km"]),
        "annual_trip_count": int(row["annual_trip_count"]),
        "annual_mileage_score": float(row["annual_mileage_score"]),
        "annual_in_zone_safe_driving_score": float(row["annual_in_zone_safe_driving_score"]),
        "annual_out_zone_safe_driving_score": float(row["annual_out_zone_safe_driving_score"]),
        "annual_senior_safe_mileage_score": float(row["annual_senior_safe_mileage_score"]),
        "annual_score_tier": row["annual_score_tier"],
        "annual_decision_signal": row["annual_decision_signal"],
        "annual_out_zone_pattern_change_risk": float(row["annual_out_zone_pattern_change_risk"]),
        "dominant_annual_interpretation": row["dominant_annual_interpretation"],
        "annual_reason_codes": split_codes(row["annual_reason_codes"]),
    }


def compact_comparison_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "annual_total_distance_km": float(row["annual_total_distance_km"]),
        "annual_distance_scope": row["annual_distance_scope"],
        "baseline_60_day_excluded_from_discount": bool(int(row["baseline_60_day_excluded_from_discount"])),
        "base_premium_krw": int(row["base_premium_krw"]),
        "existing_matched_tier_label": row["existing_matched_tier_label"],
        "existing_discount_rate_pct": float(row["existing_discount_rate_pct"]),
        "existing_discount_amount_krw": int(row["existing_discount_amount_krw"]),
        "existing_net_premium_krw": int(row["existing_net_premium_krw"]),
        "proposed_discount_rule_id": row["proposed_discount_rule_id"],
        "proposed_discount_rate_pct": float(row["proposed_discount_rate_pct"]),
        "proposed_discount_amount_krw": int(row["proposed_discount_amount_krw"]),
        "proposed_net_premium_krw": int(row["proposed_net_premium_krw"]),
        "discount_rate_delta_pct": float(row["discount_rate_delta_pct"]),
        "discount_amount_delta_krw": int(row["discount_amount_delta_krw"]),
        "premium_delta_krw": int(row["premium_delta_krw"]),
        "annual_senior_safe_mileage_score": float(row["annual_senior_safe_mileage_score"]),
        "annual_score_tier": row["annual_score_tier"],
        "annual_decision_signal": row["annual_decision_signal"],
        "annual_out_zone_pattern_change_risk": float(row["annual_out_zone_pattern_change_risk"]),
        "proposed_pricing_action": row["proposed_pricing_action"],
        "preventive_care_required": bool(int(row["preventive_care_required"])),
        "proposed_rationale_code": row["proposed_rationale_code"],
        "annual_reason_codes": split_codes(row["annual_reason_codes"]),
        "same_input_contract_id": row["same_input_contract_id"],
    }


def compact_monthly_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "service_month": row["service_month"],
        "month": int(row["month"]),
        "basis_status": row["basis_status"],
        "basis_trip_count": int(float(row["basis_trip_count"])),
        "scored_trip_count": int(float(row["scored_trip_count"])),
        "monthly_total_distance_km": float(row["monthly_total_distance_km"]),
        "mileage_score": float(row["mileage_score"]),
        "in_zone_safe_driving_score": float(row["in_zone_safe_driving_score"]),
        "out_zone_safe_driving_score": float(row["out_zone_safe_driving_score"]),
        "out_zone_pattern_change_risk": float(row["out_zone_pattern_change_risk"]),
        "dominant_interpretation": row["dominant_interpretation"],
        "reason_codes": split_codes(row["reason_codes"]),
        "scenario_phase": row["scenario_phase"],
    }


def build_comparison_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_premium_total = sum(int(row["base_premium_krw"]) for row in rows)
    existing_total = sum(int(row["existing_discount_amount_krw"]) for row in rows)
    proposed_total = sum(int(row["proposed_discount_amount_krw"]) for row in rows)
    return {
        "customer_count": len(rows),
        "same_input_contract_all_rows": all(
            str(row["same_input_contract_id"]).startswith("same-annual-input:") for row in rows
        ),
        "baseline_60_day_excluded_all_rows": all(int(row["baseline_60_day_excluded_from_discount"]) == 1 for row in rows),
        "total_base_premium_krw": base_premium_total,
        "avg_base_premium_krw": int(round(base_premium_total / len(rows))) if rows else 0,
        "existing_total_discount_krw": existing_total,
        "proposed_total_discount_krw": proposed_total,
        "discount_amount_delta_krw": proposed_total - existing_total,
        "preventive_care_count": sum(int(row["preventive_care_required"]) for row in rows),
        "decision_counts": dict(sorted(Counter(str(row["annual_decision_signal"]) for row in rows).items())),
        "existing_tier_count": len({str(row["existing_matched_tier_label"]) for row in rows}),
        "avg_existing_discount_rate_pct": average([float(row["existing_discount_rate_pct"]) for row in rows]),
        "avg_proposed_discount_rate_pct": average([float(row["proposed_discount_rate_pct"]) for row in rows]),
        "avg_annual_score": average([float(row["annual_senior_safe_mileage_score"]) for row in rows]),
    }


def build_persona_summaries(drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for driver in drivers:
        grouped[str(driver["persona_type"])].append(driver)
    summaries = []
    for persona_type in sorted(grouped):
        rows = grouped[persona_type]
        comparisons = [driver["ab_comparison"] for driver in rows]
        summaries.append(
            {
                "persona_type": persona_type,
                "persona_display_name_ko": rows[0]["persona_display_name_ko"],
                "customer_count": len(rows),
                "avg_annual_distance_km": average([row["annual_total_distance_km"] for row in comparisons]),
                "avg_annual_score": average([row["annual_senior_safe_mileage_score"] for row in comparisons]),
                "decision_counts": dict(sorted(Counter(row["annual_decision_signal"] for row in comparisons).items())),
                "preventive_care_count": sum(1 for row in comparisons if row["preventive_care_required"]),
                "avg_existing_discount_rate_pct": average([row["existing_discount_rate_pct"] for row in comparisons]),
                "avg_proposed_discount_rate_pct": average([row["proposed_discount_rate_pct"] for row in comparisons]),
            }
        )
    return summaries


def build_existing_tier_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["existing_matched_tier_label"])].append(row)
    segments = []
    for tier_label in sorted(grouped):
        tier_rows = grouped[tier_label]
        segments.append(
            {
                "existing_matched_tier_label": tier_label,
                "customer_count": len(tier_rows),
                "customer_ids": [str(row["customer_id"]) for row in tier_rows],
                "persona_counts": dict(sorted(Counter(str(row["persona_type"]) for row in tier_rows).items())),
                "proposed_decision_signal_counts": dict(
                    sorted(Counter(str(row["annual_decision_signal"]) for row in tier_rows).items())
                ),
                "proposed_discount_rate_range_pct": [
                    round(min(float(row["proposed_discount_rate_pct"]) for row in tier_rows), 2),
                    round(max(float(row["proposed_discount_rate_pct"]) for row in tier_rows), 2),
                ],
            }
        )
    return segments


def split_codes(value: str) -> list[str]:
    return [code for code in str(value).split("|") if code]


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(float(value) for value in values) / len(values), 2)


def validate_comparison_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 30:
        raise ValueError(f"annual A/B comparison must contain 30 drivers, got {len(rows)}")
    if not all(int(row["baseline_60_day_excluded_from_discount"]) == 1 for row in rows):
        raise ValueError("baseline rows must be excluded from discount amount calculation")
    if any("monthly_discount" in key for row in rows for key in row):
        raise ValueError("annual A/B output must not expose monthly discount fields")
    mixed_segments = [
        segment for segment in build_existing_tier_segments(rows)
        if segment["customer_count"] > 1 and len(segment["proposed_decision_signal_counts"]) > 1
    ]
    if not mixed_segments:
        raise ValueError("comparison must show at least one existing mileage tier split by proposed decisions")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return path


def build_and_write_annual_ab_outputs(
    *,
    profile_input: Path = DEFAULT_PROFILE_INPUT,
    annual_score_input: Path = DEFAULT_ANNUAL_SCORE_INPUT,
    monthly_score_input: Path = DEFAULT_MONTHLY_SCORE_INPUT,
    comparison_output: Path = DEFAULT_COMPARISON_OUTPUT,
    view_model_output: Path = DEFAULT_VIEW_MODEL_OUTPUT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = build_annual_ab_comparison_rows(
        profile_input=profile_input,
        annual_score_input=annual_score_input,
    )
    write_csv(comparison_output, rows)
    view_model = build_judge_demo_view_model(
        rows,
        profile_input=profile_input,
        annual_score_input=annual_score_input,
        monthly_score_input=monthly_score_input,
    )
    write_json(view_model_output, view_model)
    return rows, view_model


def main() -> int:
    rows, view_model = build_and_write_annual_ab_outputs()
    summary = view_model["summary"]
    print(f"wrote {len(rows)} annual A/B rows to {DEFAULT_COMPARISON_OUTPUT}")
    print(f"wrote judge demo view model to {DEFAULT_VIEW_MODEL_OUTPUT}")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

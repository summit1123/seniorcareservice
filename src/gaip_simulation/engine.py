"""Deterministic GAIP cohort, mobility, product-rule, and pricing sandbox."""

from __future__ import annotations

import hashlib
import csv
import io
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.product.mileage_discount_table import (
    PERSONAL_BUSINESS,
    PERSONAL_PASSENGER_EV_HYDROGEN,
    PERSONAL_PASSENGER_GENERAL,
    lookup_existing_mileage_discount,
)

from .clustering import dbscan_distinct_days, locate_product_zone, summarize_clusters


DEFAULT_SEED = 26_071_406
SCHEMA_VERSION = "masil-gaip-simulation/v1"
ARTIFACT_TIMESTAMP = "2026-07-14T00:00:00Z"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_VISIT_EVENTS_PATH = PROJECT_ROOT / "data" / "fixtures" / "gaip_visit_events.csv"

BASELINE_MONTHS = ("2025-11", "2025-12")
EVALUATION_MONTHS = tuple(f"2026-{month:02d}" for month in range(1, 13))
ALL_MONTHS = BASELINE_MONTHS + EVALUATION_MONTHS

# Fully synthetic Korean senior names (성+이름, mixed gender). These are stock
# senior-generation name patterns, not references to real people; the bundle
# metadata carries an explicit persona_naming_note disclaimer.
KOREAN_SENIOR_NAME_POOL: tuple[str, ...] = (
    "김순애", "박정호", "이말순", "최병철", "정옥분", "강복남", "조영자", "윤갑수",
    "장금례", "임종달", "한순덕", "오병수", "서말자", "신동철", "권점례", "황기석",
    "안순자", "송만복", "유정순", "전병국", "홍옥선", "고재술", "문분례", "양덕수",
    "배금순", "남정례", "심우섭", "노귀순", "하영철", "곽점순", "성일만", "차옥례",
    "주병호", "우금자", "구본달", "민영순", "류재복", "나종순", "진갑룡", "엄정자",
    "원병희", "채순임", "천기수", "방옥자", "공재만", "현말녀", "함덕례", "변종수",
    "염금분", "여상철", "추옥임", "도병선", "소순예", "석재구", "선분남", "설기순",
    "마종례", "길병옥", "연순복", "위갑례", "표만술", "명옥녀", "기정수", "반말숙",
    "라병순", "왕금희",
)

# Slight, deterministic per-persona age bias on top of the seeded 66-84 range.
PERSONA_AGE_BIAS: dict[str, int] = {
    "stable_local_safe": 0,
    "low_mileage_risky": 1,
    "safe_multi_hub": -1,
    "safe_wide_area": -1,
    "mobility_change_only": 1,
    "mobility_risk_cochange": 2,
}

# Synthetic semantic display labels for the generic hub labels. UI-only strings;
# the raw visit event CSV keeps the generic Routine Hub A/B/New Hub labels.
PERSONA_HUB_LABELS: dict[str, dict[str, str]] = {
    "stable_local_safe": {
        "Routine Hub A": "자택·마트 동선",
        "Routine Hub B": "경로당",
        "New Hub": "신규 외출지",
    },
    "low_mileage_risky": {
        "Routine Hub A": "자택 인근",
        "Routine Hub B": "시장",
        "New Hub": "야간 신규 목적지",
    },
    "safe_multi_hub": {
        "Routine Hub A": "자택(본가)",
        "Routine Hub B": "자녀 집",
        "New Hub": "새 모임 장소",
    },
    "safe_wide_area": {
        "Routine Hub A": "자택(농가)",
        "Routine Hub B": "읍내 마트·병원",
        "New Hub": "원거리 정기 방문지",
    },
    "mobility_change_only": {
        "Routine Hub A": "자택 인근",
        "Routine Hub B": "복지관",
        "New Hub": "병원 정기 경로",
    },
    "mobility_risk_cochange": {
        "Routine Hub A": "자택 인근",
        "Routine Hub B": "마트",
        "New Hub": "야간 외곽 경로",
    },
}

PERSONA_NAMING_NOTE = "이름·나이·장소 라벨은 전원 합성(실존 인물·장소 아님)"

PERSONA_TYPES: dict[str, dict[str, Any]] = {
    "stable_local_safe": {
        "display_name_ko": "안정 생활권·저주행 안전형",
        "summary_ko": "반복거점 중심의 저주행과 안정 행동이 함께 유지되는 기준 유형",
        "monthly_visits": 7,
        "hub_weights": {"Routine Hub A": 0.76, "Routine Hub B": 0.24},
    },
    "low_mileage_risky": {
        "display_name_ko": "저주행·위험행동 반복형",
        "summary_ko": "주행량은 적지만 주행 중 위험행동이 반복되는 비교 유형",
        "monthly_visits": 6,
        "hub_weights": {"Routine Hub A": 0.80, "Routine Hub B": 0.20},
    },
    "safe_multi_hub": {
        "display_name_ko": "복수 반복거점·안전형",
        "summary_ko": "서로 떨어진 두 반복거점을 오가면서 안전행동을 유지하는 유형",
        "monthly_visits": 10,
        "hub_weights": {"Routine Hub A": 0.56, "Routine Hub B": 0.44},
    },
    "safe_wide_area": {
        "display_name_ko": "광역 이동·안전형",
        "summary_ko": "이동범위는 넓지만 위치 자체와 무관하게 안전행동을 유지하는 유형",
        "monthly_visits": 8,
        "hub_weights": {"Routine Hub A": 0.54, "Routine Hub B": 0.46},
    },
    "mobility_change_only": {
        "display_name_ko": "이동맥락 변화·안전유지형",
        "summary_ko": "최근 이동맥락은 달라졌지만 위험행동 증가는 없는 비징벌 검증 유형",
        "monthly_visits": 8,
        "hub_weights": {"Routine Hub A": 0.72, "Routine Hub B": 0.28},
    },
    "mobility_risk_cochange": {
        "display_name_ko": "이동·위험행동 동시변화형",
        "summary_ko": "최근 이동맥락과 위험행동이 함께 달라져 사람 검토가 필요한 유형",
        "monthly_visits": 8,
        "hub_weights": {"Routine Hub A": 0.72, "Routine Hub B": 0.28},
    },
}

ENVIRONMENTS: dict[str, dict[str, Any]] = {
    "dense_urban": {
        "display_name_ko": "고밀도 도심형",
        "base_latitude": 37.55,
        "base_longitude": 126.96,
        "hub_separation_m": 1_200.0,
        "visit_dispersion_m": 72.0,
        "dbscan_eps_m": 180.0,
        "base_trip_distance_km": 4.8,
    },
    "suburban_mid_density": {
        "display_name_ko": "교외·중밀도형",
        "base_latitude": 37.39,
        "base_longitude": 127.10,
        "hub_separation_m": 4_800.0,
        "visit_dispersion_m": 190.0,
        "dbscan_eps_m": 420.0,
        "base_trip_distance_km": 12.0,
    },
    "wide_low_density": {
        "display_name_ko": "광역 저밀도형",
        "base_latitude": 36.55,
        "base_longitude": 127.74,
        "hub_separation_m": 16_000.0,
        "visit_dispersion_m": 540.0,
        "dbscan_eps_m": 950.0,
        "base_trip_distance_km": 27.0,
    },
}

VEHICLE_CLASS_ROTATION = (
    PERSONAL_PASSENGER_GENERAL,
    PERSONAL_PASSENGER_GENERAL,
    PERSONAL_PASSENGER_EV_HYDROGEN,
    PERSONAL_BUSINESS,
)

DEFAULT_PRODUCT_RULES: dict[str, Any] = {
    "weights": {
        "mileage_score": 30,
        "in_zone_safe_score": 30,
        "out_zone_safe_score": 20,
        "pattern_stability_score": 20,
    },
    "reward_threshold": 75.0,
    "reward_required_months": 9,
    "min_data_coverage_pct": 80.0,
    "care_thresholds": {
        "mobility_change_index": 0.25,
        "risky_behavior_change_index": 0.20,
        "unit": "normalized_ratio_0_to_1",
        "gate_logic": "AND",
    },
    "reward_bonus_discount_rate_pct": 3.0,
    "candidate_discount_cap_pct": 45.0,
    "core_radius_m": 500.0,
    "buffer_cap_m": 2_000.0,
    "core_radius_source_status": "korea_reference_product_minimum",
    "outer_zone_policy": "context_only_no_location_penalty",
    "pattern_stability_basis": "risky_behavior_change_index",
    "tariff_status": "illustrative_economics_sandbox_not_final_tariff",
    "rule_origin": "korea_reference_and_proposed_assumption_not_fit_to_any_partition",
    "decision_feature_contract": {
        "allowed_inputs": [
            "zone_available",
            "data_coverage_pct",
            "mileage_score",
            "in_zone_safe_score",
            "out_zone_safe_score",
            "pattern_stability_score",
            "mobility_change_index",
            "risky_behavior_change_index",
        ],
        "generation_only_fields_excluded": [
            "persona_type",
            "scenario_variant",
            "scenario_label",
            "visit_label",
            "scenario_truth",
            "expected_reward_state",
            "expected_care_state",
        ],
    },
}

_ALLOWED_VISIT_LABELS = ("Routine Hub A", "Routine Hub B", "New Hub")
_VISIT_EVENT_FIELDS = (
    "trip_id",
    "visit_event_id",
    "driver_id",
    "persona_type",
    "environment_id",
    "dataset_partition",
    "scenario_variant",
    "month",
    "period_role",
    "visit_date",
    "visit_label",
    "latitude",
    "longitude",
    "trip_distance_km",
    "risk_event_count",
    "data_coverage_pct",
    "source_status",
)


SCENARIO_VARIANTS: dict[str, dict[str, str]] = {
    "typical": {
        "label_ko": "일반 합성 사례",
        "purpose": "Persona and mobility-environment behavior under sufficient evidence.",
    },
    "no_zone_evidence_gap": {
        "label_ko": "생활권 근거 부족 사례",
        "purpose": "Exercise no-cluster hold behavior without inventing a routine hub.",
    },
    "low_data_coverage": {
        "label_ko": "데이터 사용률 부족 사례",
        "purpose": "Exercise minimum-data-coverage hold behavior without customer disadvantage.",
    },
}


def _stable_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 16)


def _offset_coordinate(latitude: float, longitude: float, meters: float, angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    north_m = meters * math.sin(angle)
    east_m = meters * math.cos(angle)
    latitude_delta = north_m / 111_320.0
    longitude_delta = east_m / (111_320.0 * max(0.2, math.cos(math.radians(latitude))))
    return latitude + latitude_delta, longitude + longitude_delta


def _choose_weighted(rng: random.Random, weights: Mapping[str, float]) -> str:
    threshold = rng.random() * sum(float(value) for value in weights.values())
    cumulative = 0.0
    for label, weight in weights.items():
        cumulative += float(weight)
        if threshold <= cumulative:
            return label
    return next(reversed(weights))


def _period_role(month: str) -> str:
    return "baseline" if month in BASELINE_MONTHS else "evaluation"


def _evaluation_month_number(month: str) -> int | None:
    return None if month in BASELINE_MONTHS else int(month.split("-")[1])


_PARTITION_ENV_COUNTS = (
    {
        "development": (2, 2, 1),
        "validation": (1, 1, 1),
        "holdout": (1, 0, 1),
    },
    {
        "development": (1, 2, 2),
        "validation": (1, 1, 1),
        "holdout": (1, 1, 0),
    },
    {
        "development": (2, 1, 2),
        "validation": (1, 1, 1),
        "holdout": (0, 1, 1),
    },
)


def _assign_driver_names(seed: int, driver_count: int) -> list[str]:
    """Deterministic unique synthetic name per driver via a seeded index shuffle.

    Uses a dedicated ``_stable_seed("naming", ...)`` stream so name assignment
    never consumes draws from the visit-generation RNG streams.
    """

    if driver_count > len(KOREAN_SENIOR_NAME_POOL):
        raise ValueError("synthetic name pool is smaller than the driver cohort")
    names = list(KOREAN_SENIOR_NAME_POOL)
    random.Random(_stable_seed("naming", seed)).shuffle(names)
    return names[:driver_count]


def _driver_age(driver_id: str, persona_type: str) -> int:
    """Deterministic synthetic age in 66-84 with a slight persona bias."""

    rng = random.Random(_stable_seed("naming", driver_id, "age"))
    base = 66 + rng.randrange(17)
    return min(84, max(66, base + PERSONA_AGE_BIAS.get(persona_type, 0)))


def _stratified_assignments(persona_index: int) -> list[tuple[str, str]]:
    """Return 5/3/2 split assignments balanced over every three personas."""

    environment_ids = list(ENVIRONMENTS)
    allocation: list[tuple[str, str]] = []
    pattern = _PARTITION_ENV_COUNTS[persona_index % len(_PARTITION_ENV_COUNTS)]
    for partition in ("development", "validation", "holdout"):
        for environment_id, count in zip(environment_ids, pattern[partition]):
            allocation.extend((environment_id, partition) for _ in range(count))
    return allocation


def _build_driver_contracts(seed: int) -> list[dict[str, Any]]:
    drivers: list[dict[str, Any]] = []
    persona_ids = list(PERSONA_TYPES)
    for persona_index, persona_type in enumerate(persona_ids):
        allocation = _stratified_assignments(persona_index)
        for sequence, (environment_id, dataset_partition) in enumerate(allocation, start=1):
            global_index = len(drivers)
            scenario_variant = {
                9: "no_zone_evidence_gap",
                19: "low_data_coverage",
            }.get(global_index, "typical")
            drivers.append(
                {
                    "driver_id": f"gaip-{global_index + 1:03d}",
                    "persona_type": persona_type,
                    "persona_display_name_ko": PERSONA_TYPES[persona_type]["display_name_ko"],
                    "persona_summary_ko": PERSONA_TYPES[persona_type]["summary_ko"],
                    "environment_id": environment_id,
                    "environment_display_name_ko": ENVIRONMENTS[environment_id]["display_name_ko"],
                    "dataset_partition": dataset_partition,
                    "scenario_variant": scenario_variant,
                    "scenario_label": SCENARIO_VARIANTS[scenario_variant]["label_ko"],
                    "persona_sequence": sequence,
                    "simulation_seed": _stable_seed(seed, persona_type, environment_id, sequence),
                    "vehicle_class": VEHICLE_CLASS_ROTATION[global_index % len(VEHICLE_CLASS_ROTATION)],
                    "base_premium_krw": 780_000 + (persona_index * 24_000) + ((global_index % 5) * 13_000),
                }
            )
    names = _assign_driver_names(seed, len(drivers))
    for index, driver in enumerate(drivers):
        driver["driver_name_ko"] = names[index]
        driver["age"] = _driver_age(str(driver["driver_id"]), str(driver["persona_type"]))
    return drivers


def _hub_centers(driver: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    environment = ENVIRONMENTS[str(driver["environment_id"])]
    sequence = int(driver["persona_sequence"])
    origin_lat, origin_lon = _offset_coordinate(
        float(environment["base_latitude"]),
        float(environment["base_longitude"]),
        1_800.0 * sequence,
        31.0 * sequence,
    )
    hub_b = _offset_coordinate(origin_lat, origin_lon, float(environment["hub_separation_m"]), 38.0)
    new_hub = _offset_coordinate(origin_lat, origin_lon, float(environment["hub_separation_m"]) * 1.65, 142.0)
    return {
        "Routine Hub A": (origin_lat, origin_lon),
        "Routine Hub B": hub_b,
        "New Hub": new_hub,
    }


def _month_visit_weights(persona_type: str, evaluation_month: int | None) -> dict[str, float]:
    base = dict(PERSONA_TYPES[persona_type]["hub_weights"])
    if persona_type in {"mobility_change_only", "mobility_risk_cochange"} and evaluation_month is not None and evaluation_month >= 8:
        return {"Routine Hub A": 0.36, "Routine Hub B": 0.19, "New Hub": 0.45}
    return base


def _risk_event_count(persona_type: str, evaluation_month: int | None, visit_index: int, rng: random.Random) -> int:
    if persona_type == "low_mileage_risky":
        return 3 + int((visit_index + rng.randint(0, 2)) % 3 == 0)
    if persona_type == "mobility_risk_cochange" and evaluation_month is not None and evaluation_month >= 8:
        return 1 + int(visit_index % 3 == 0)
    if persona_type == "mobility_change_only":
        return 0
    probability = 0.025 if persona_type != "safe_wide_area" else 0.045
    return int(rng.random() < probability)


def _trip_distance_km(
    persona_type: str,
    environment_id: str,
    visit_label: str,
    rng: random.Random,
) -> float:
    environment = ENVIRONMENTS[environment_id]
    multiplier = {
        "Routine Hub A": 0.72,
        "Routine Hub B": 1.18,
        "New Hub": 1.48,
    }[visit_label]
    if persona_type == "safe_wide_area":
        multiplier *= 1.28
    return round(float(environment["base_trip_distance_km"]) * multiplier * rng.uniform(0.84, 1.18), 2)


def _visit_date(month: str, visit_index: int, driver_sequence: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    day = 2 + ((visit_index * 3 + driver_sequence * 2) % 25)
    return date(year, month_number, day).isoformat()


def _generate_visits_for_driver(driver: Mapping[str, Any], seed: int) -> list[dict[str, Any]]:
    persona_type = str(driver["persona_type"])
    environment_id = str(driver["environment_id"])
    scenario_variant = str(driver.get("scenario_variant", "typical"))
    environment = ENVIRONMENTS[environment_id]
    centers = _hub_centers(driver)
    events: list[dict[str, Any]] = []

    for month_index, month in enumerate(ALL_MONTHS):
        evaluation_month = _evaluation_month_number(month)
        period_role = _period_role(month)
        rng = random.Random(_stable_seed(seed, driver["driver_id"], month))
        visit_count = max(5, int(PERSONA_TYPES[persona_type]["monthly_visits"]) + rng.choice((-1, 0, 0, 1)))
        weights = _month_visit_weights(persona_type, evaluation_month)
        for visit_index in range(visit_count):
            visit_label = _choose_weighted(rng, weights)
            center_lat, center_lon = centers[visit_label]
            radius = rng.uniform(0.08, 1.0) * float(environment["visit_dispersion_m"])
            latitude, longitude = _offset_coordinate(center_lat, center_lon, radius, rng.uniform(0, 360))
            trip_id = f"{driver['driver_id']}-{month.replace('-', '')}-{visit_index + 1:02d}"
            risk_event_count = _risk_event_count(persona_type, evaluation_month, visit_index, rng)
            visit_date = (
                f"{month}-15"
                if scenario_variant == "no_zone_evidence_gap" and period_role == "baseline"
                else _visit_date(month, visit_index, int(driver["persona_sequence"]))
            )
            data_coverage_pct = (
                round(62.0 + rng.random() * 6.0, 1)
                if scenario_variant == "low_data_coverage"
                else round(95.0 + rng.random() * 5.0, 1)
            )
            events.append(
                {
                    "trip_id": trip_id,
                    "visit_event_id": f"visit-{trip_id}",
                    "driver_id": driver["driver_id"],
                    "persona_type": persona_type,
                    "environment_id": environment_id,
                    "dataset_partition": driver["dataset_partition"],
                    "scenario_variant": scenario_variant,
                    "month": month,
                    "period_role": period_role,
                    "visit_date": visit_date,
                    "visit_label": visit_label,
                    "latitude": round(latitude, 6),
                    "longitude": round(longitude, 6),
                    "trip_distance_km": _trip_distance_km(persona_type, environment_id, visit_label, rng),
                    "risk_event_count": risk_event_count,
                    "data_coverage_pct": data_coverage_pct,
                    "source_status": "simulated",
                }
            )
    return events


def _mileage_score(monthly_distance_km: float) -> float:
    annualized = monthly_distance_km * 12.0
    if annualized <= 3_000:
        return 100.0
    if annualized <= 5_000:
        return 85.0
    if annualized <= 7_000:
        return 70.0
    if annualized <= 10_000:
        return 50.0
    return 30.0


def _safety_score(events: Sequence[Mapping[str, Any]]) -> float | None:
    if not events:
        return None
    distance = sum(float(event["trip_distance_km"]) for event in events)
    risk_events = sum(int(event["risk_event_count"]) for event in events)
    rate_per_100_km = (risk_events / max(distance, 1.0)) * 100.0
    return round(max(0.0, 100.0 - (rate_per_100_km * 8.0)), 2)


def classify_month(
    metrics: Mapping[str, Any],
    product_rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply product rules without allowing location alone to create a penalty."""

    rules = product_rules or DEFAULT_PRODUCT_RULES
    coverage = float(metrics.get("data_coverage_pct", 0.0))
    zone_available = bool(metrics.get("zone_available", False))
    weights = rules["weights"]
    total_weight = sum(float(value) for value in weights.values())
    if total_weight <= 0:
        raise ValueError("score weights must sum to a positive value")
    component_availability: dict[str, bool] = {}
    observed_components: list[tuple[float, float]] = []
    for key, weight in weights.items():
        value = metrics.get(key)
        observed = value is not None
        if observed:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                observed = False
            else:
                observed = math.isfinite(numeric_value)
                if observed:
                    observed_components.append((numeric_value, float(weight)))
        component_availability[key] = observed
    observed_weight = sum(weight for _value, weight in observed_components)
    score_evidence = {
        "observed_score_weight_pct": round((observed_weight / total_weight) * 100.0, 2),
        "component_availability": component_availability,
    }
    if not zone_available or coverage < float(rules["min_data_coverage_pct"]):
        return {
            "reward_state": "hold",
            "care_state": "hold",
            "integrated_score": None,
            "location_penalty": 0.0,
            "reason_codes": ["INSUFFICIENT_EVIDENCE"],
            **score_evidence,
        }

    if observed_weight <= 0:
        return {
            "reward_state": "hold",
            "care_state": "hold",
            "integrated_score": None,
            "location_penalty": 0.0,
            "reason_codes": ["INSUFFICIENT_SCORE_COMPONENTS"],
            **score_evidence,
        }

    integrated_score = sum(value * weight for value, weight in observed_components) / observed_weight
    reward_state = "reward" if integrated_score >= float(rules["reward_threshold"]) else "neutral"

    thresholds = rules["care_thresholds"]
    mobility_changed = float(metrics.get("mobility_change_index", 0.0)) >= float(thresholds["mobility_change_index"])
    risk_changed = float(metrics.get("risky_behavior_change_index", 0.0)) >= float(
        thresholds["risky_behavior_change_index"]
    )
    care_state = "care_review" if mobility_changed and risk_changed else "none"
    reason_codes = ["SUFFICIENT_EVIDENCE"]
    if observed_weight < total_weight:
        reason_codes.append("PARTIAL_SCORE_COMPONENTS_RENORMALIZED")
    if reward_state == "reward":
        reason_codes.append("REWARD_THRESHOLD_MET")
    if mobility_changed:
        reason_codes.append("MOBILITY_CONTEXT_CHANGED")
    if risk_changed:
        reason_codes.append("RISKY_BEHAVIOR_CHANGED")
    if care_state == "care_review":
        reason_codes.append("HUMAN_CARE_REVIEW_SUGGESTED")

    return {
        "reward_state": reward_state,
        "care_state": care_state,
        "integrated_score": round(integrated_score, 2),
        "location_penalty": 0.0,
        "reason_codes": reason_codes,
        **score_evidence,
    }


def pricing_sandbox(
    *,
    base_premium_krw: int,
    annual_distance_km: float,
    vehicle_class: str,
    annual_reward_state: str,
    product_rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a Korea mileage reference with a non-binding Masil candidate."""

    rules = product_rules or DEFAULT_PRODUCT_RULES
    lookup = lookup_existing_mileage_discount(annual_distance_km, vehicle_class)
    korea_rate = float(lookup.discount_rate_pct)
    bonus = float(rules["reward_bonus_discount_rate_pct"]) if annual_reward_state == "reward" else 0.0
    masil_rate = min(float(rules["candidate_discount_cap_pct"]), korea_rate + bonus)
    korea_net = int(round(int(base_premium_krw) * (1.0 - korea_rate / 100.0)))
    masil_net = int(round(int(base_premium_krw) * (1.0 - masil_rate / 100.0)))
    return {
        "base_premium_krw": int(base_premium_krw),
        "annual_distance_km": round(float(annual_distance_km), 2),
        "korea_mileage_discount_rate_pct": round(korea_rate, 2),
        "korea_mileage_net_premium_krw": korea_net,
        "masil_candidate_discount_rate_pct": round(masil_rate, 2),
        "masil_candidate_net_premium_krw": masil_net,
        "candidate_reward_bonus_rate_pct": round(bonus, 2),
        "candidate_surcharge_rate_pct": 0.0,
        "source_status": "illustrative_economics_sandbox_not_final_tariff",
    }


def _monthly_results(
    driver: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    hubs: Sequence[Mapping[str, Any]],
    product_rules: Mapping[str, Any],
) -> list[dict[str, Any]]:
    by_month: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    located: dict[str, dict[str, Any]] = {}
    for event in events:
        by_month[str(event["month"])].append(event)
        located[str(event["visit_event_id"])] = locate_product_zone(event, hubs)

    def raw_month_metrics(month: str) -> dict[str, Any]:
        rows = by_month[month]
        in_zone = [row for row in rows if located[str(row["visit_event_id"])]["zone"] in {"core", "buffer"}]
        out_zone = [row for row in rows if located[str(row["visit_event_id"])]["zone"] == "outer"]
        total_distance = sum(float(row["trip_distance_km"]) for row in rows)
        total_risk_events = sum(int(row["risk_event_count"]) for row in rows)
        risky_trip_count = sum(int(row["risk_event_count"]) > 0 for row in rows)
        return {
            "month": month,
            "period_role": _period_role(month),
            "trip_count": len(rows),
            "total_distance_km": round(total_distance, 2),
            "data_coverage_pct": round(sum(float(row["data_coverage_pct"]) for row in rows) / len(rows), 2),
            "outer_visit_share": round(len(out_zone) / len(rows), 4),
            "unmatched_baseline_zone_share": round(len(out_zone) / len(rows), 4),
            "risky_behavior_rate": round(risky_trip_count / len(rows), 4),
            "risky_events_per_100_km": round((total_risk_events / max(total_distance, 1.0)) * 100.0, 4),
            "mileage_score": _mileage_score(total_distance),
            "in_zone_trip_count": len(in_zone),
            "out_zone_trip_count": len(out_zone),
            "in_zone_safe_score": _safety_score(in_zone),
            "out_zone_safe_score": _safety_score(out_zone),
            "zone_available": bool(hubs),
        }

    raw = {month: raw_month_metrics(month) for month in ALL_MONTHS}
    baseline_risk = sum(raw[month]["risky_behavior_rate"] for month in BASELINE_MONTHS) / len(BASELINE_MONTHS)
    baseline_outer = sum(raw[month]["outer_visit_share"] for month in BASELINE_MONTHS) / len(BASELINE_MONTHS)

    results: list[dict[str, Any]] = []
    for month in ALL_MONTHS:
        metrics = dict(raw[month])
        metrics["mobility_change_index"] = round(
            max(0.0, metrics["unmatched_baseline_zone_share"] - baseline_outer),
            4,
        )
        metrics["risky_behavior_change_index"] = round(
            max(0.0, metrics["risky_behavior_rate"] - baseline_risk),
            4,
        )
        metrics["pattern_stability_score"] = round(
            max(0.0, 100.0 - metrics["risky_behavior_change_index"] * 100.0),
            2,
        )
        decision = classify_month(metrics, product_rules)
        if metrics["period_role"] == "baseline":
            decision = {
                **decision,
                "reward_state": "observation",
                "care_state": "observation",
                "reason_codes": ["BASELINE_OBSERVATION"],
            }
        results.append(
            {
                **metrics,
                **decision,
                "source_status": "derived_from_simulation",
            }
        )
    return results


def _annual_state(
    monthly_results: Sequence[Mapping[str, Any]],
    product_rules: Mapping[str, Any],
) -> tuple[str, str]:
    evaluation = [result for result in monthly_results if result["period_role"] == "evaluation"]
    reward_required_months = int(product_rules["reward_required_months"])
    if not 1 <= reward_required_months <= len(evaluation):
        raise ValueError("reward_required_months must be within the evaluation period")
    reward_months = sum(result["reward_state"] == "reward" for result in evaluation)
    reward_eligible_months = sum(result["reward_state"] != "hold" for result in evaluation)
    annual_reward = (
        "hold"
        if reward_eligible_months < reward_required_months
        else "reward" if reward_months >= reward_required_months else "neutral"
    )
    annual_care = (
        "hold"
        if evaluation and all(result["care_state"] == "hold" for result in evaluation)
        else "care_review" if any(result["care_state"] == "care_review" for result in evaluation) else "none"
    )
    return annual_reward, annual_care


def _driver_summary(
    driver: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    product_rules: Mapping[str, Any],
) -> dict[str, Any]:
    environment = ENVIRONMENTS[str(driver["environment_id"])]
    baseline_events = [event for event in events if event["period_role"] == "baseline"]
    clustering = dbscan_distinct_days(
        baseline_events,
        eps_m=float(environment["dbscan_eps_m"]),
        min_distinct_days=3,
    )
    hubs = summarize_clusters(
        baseline_events,
        clustering["labels"],
        core_radius_m=float(product_rules["core_radius_m"]),
        buffer_cap_m=float(product_rules["buffer_cap_m"]),
    )
    persona_hub_labels = PERSONA_HUB_LABELS[str(driver["persona_type"])]
    public_hubs = [
        {
            **{
                key: value
                for key, value in hub.items()
                if key not in {"centroid", "source_cluster_id"}
            },
            "display_label_ko": persona_hub_labels[str(hub["display_label"])],
        }
        for hub in hubs
    ]
    monthly = _monthly_results(driver, events, hubs, product_rules)
    evaluation = [result for result in monthly if result["period_role"] == "evaluation"]
    annual_reward, annual_care = _annual_state(monthly, product_rules)
    annual_distance = sum(float(result["total_distance_km"]) for result in evaluation)
    tariff = pricing_sandbox(
        base_premium_krw=int(driver["base_premium_krw"]),
        annual_distance_km=annual_distance,
        vehicle_class=str(driver["vehicle_class"]),
        annual_reward_state=annual_reward,
        product_rules=product_rules,
    )
    def mean_observed(key: str) -> float | None:
        values = [float(result[key]) for result in evaluation if result.get(key) is not None]
        return round(sum(values) / len(values), 2) if values else None

    averages = {
        key: mean_observed(key)
        for key in (
            "mileage_score",
            "in_zone_safe_score",
            "out_zone_safe_score",
            "pattern_stability_score",
            "risky_behavior_rate",
            "data_coverage_pct",
        )
    }
    return {
        **driver,
        **averages,
        "mobility_change_index": round(max(float(result["mobility_change_index"]) for result in evaluation), 4),
        "risky_behavior_change_index": round(
            max(float(result["risky_behavior_change_index"]) for result in evaluation),
            4,
        ),
        "annual_distance_km": round(annual_distance, 2),
        "total_trips": len(events),
        "annual_reward_state": annual_reward,
        "annual_care_state": annual_care,
        "reward_month_count": sum(result["reward_state"] == "reward" for result in evaluation),
        "care_review_month_count": sum(result["care_state"] == "care_review" for result in evaluation),
        "mobility": {
            "zone_status": "available" if hubs else "insufficient",
            "algorithm": "DBSCAN",
            "distance_metric": "haversine_m",
            "eps_m": float(environment["dbscan_eps_m"]),
            "min_distinct_days": 3,
            "repeated_hub_count": len(hubs),
            "routine_hubs": public_hubs,
            "new_hub_label_ko": persona_hub_labels["New Hub"],
            "basis_visit_count": len(baseline_events),
            "noise_visit_count": clustering["noise_count"],
            "noise_ratio_pct": round(
                (float(clustering["noise_count"]) / len(baseline_events)) * 100.0,
                1,
            ) if baseline_events else 0.0,
        },
        "tariff": tariff,
        "monthly_results": monthly,
        "source_status": "synthetic_driver_summary",
    }


def _selected_evidence(drivers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for driver in drivers:
        persona_type = str(driver["persona_type"])
        if persona_type in seen:
            continue
        seen.add(persona_type)
        for month in ("2026-07", "2026-10"):
            result = next(row for row in driver["monthly_results"] if row["month"] == month)
            selected.append(
                {
                    "driver_id": driver["driver_id"],
                    "persona_type": persona_type,
                    "environment_id": driver["environment_id"],
                    "dataset_partition": driver["dataset_partition"],
                    "month": month,
                    "reward_state": result["reward_state"],
                    "care_state": result["care_state"],
                    "integrated_score": result["integrated_score"],
                    "mobility_change_index": result["mobility_change_index"],
                    "risky_behavior_change_index": result["risky_behavior_change_index"],
                    "reason_codes": result["reason_codes"],
                    "source_status": "selected_synthetic_evidence",
                }
            )
    return selected


def _portfolio_results(drivers: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reward_counts = Counter(str(driver["annual_reward_state"]) for driver in drivers)
    care_counts = Counter(str(driver["annual_care_state"]) for driver in drivers)
    total_base = sum(int(driver["tariff"]["base_premium_krw"]) for driver in drivers)
    total_korea = sum(int(driver["tariff"]["korea_mileage_net_premium_krw"]) for driver in drivers)
    total_masil = sum(int(driver["tariff"]["masil_candidate_net_premium_krw"]) for driver in drivers)
    by_environment: dict[str, dict[str, Any]] = {}
    for environment_id in ENVIRONMENTS:
        subset = [driver for driver in drivers if driver["environment_id"] == environment_id]
        by_environment[environment_id] = {
            "driver_count": len(subset),
            "zone_available_count": sum(driver["mobility"]["zone_status"] == "available" for driver in subset),
            "mean_repeated_hub_count": round(
                sum(int(driver["mobility"]["repeated_hub_count"]) for driver in subset) / len(subset),
                2,
            ),
            "mean_annual_distance_km": round(
                sum(float(driver["annual_distance_km"]) for driver in subset) / len(subset),
                2,
            ),
        }

    partition_summaries: dict[str, dict[str, Any]] = {}
    for partition in ("development", "validation", "holdout"):
        subset = [driver for driver in drivers if driver["dataset_partition"] == partition]
        subset_events = [event for event in events if event["dataset_partition"] == partition]
        partition_summaries[partition] = {
            "driver_count": len(subset),
            "trip_count": len(subset_events),
            "persona_counts": dict(sorted(Counter(driver["persona_type"] for driver in subset).items())),
            "environment_counts": dict(sorted(Counter(driver["environment_id"] for driver in subset).items())),
            "reward_state_counts": dict(sorted(Counter(driver["annual_reward_state"] for driver in subset).items())),
            "care_state_counts": dict(sorted(Counter(driver["annual_care_state"] for driver in subset).items())),
            "mean_annual_distance_km": round(
                sum(float(driver["annual_distance_km"]) for driver in subset) / len(subset),
                2,
            ),
            "mean_data_coverage_pct": round(
                sum(float(driver["data_coverage_pct"]) for driver in subset) / len(subset),
                2,
            ),
            "interpretation_boundary": "Descriptive synthetic partition result; product rules were not fitted to this partition.",
            "source_status": "derived_from_simulation",
        }
    return {
        "reward_state_counts": dict(sorted(reward_counts.items())),
        "care_state_counts": dict(sorted(care_counts.items())),
        "economics_sandbox": {
            "base_premium_total_krw": total_base,
            "korea_mileage_reference_net_total_krw": total_korea,
            "masil_candidate_net_total_krw": total_masil,
            "candidate_vs_reference_delta_krw": total_masil - total_korea,
            "source_status": "illustrative_economics_sandbox_not_final_tariff",
        },
        "mobility_environment_summary": by_environment,
        "partition_summaries": partition_summaries,
        "total_trip_count": len(events),
        "source_status": "derived_from_simulation",
    }


def _validation_results(
    drivers: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    product_rules: Mapping[str, Any],
) -> dict[str, Any]:
    persona_counts = Counter(str(driver["persona_type"]) for driver in drivers)
    environment_counts = Counter(str(driver["environment_id"]) for driver in drivers)
    partition_counts = Counter(str(driver["dataset_partition"]) for driver in drivers)
    scenario_variant_counts = Counter(str(driver["scenario_variant"]) for driver in drivers)
    typical_drivers = [driver for driver in drivers if driver["scenario_variant"] == "typical"]
    no_zone_drivers = [driver for driver in drivers if driver["scenario_variant"] == "no_zone_evidence_gap"]
    low_coverage_drivers = [driver for driver in drivers if driver["scenario_variant"] == "low_data_coverage"]
    months_by_driver = {
        str(driver["driver_id"]): {str(row["month"]) for row in driver["monthly_results"]}
        for driver in drivers
    }

    outer_base = {
        "zone_available": True,
        "data_coverage_pct": 100.0,
        "mileage_score": 90.0,
        "in_zone_safe_score": 94.0,
        "out_zone_safe_score": 96.0,
        "pattern_stability_score": 92.0,
        "mobility_change_index": 0.0,
        "risky_behavior_change_index": 0.0,
        "outer_visit_share": 0.0,
    }
    outer_more = {**outer_base, "outer_visit_share": 0.8}
    outer_before = classify_month(outer_base, product_rules)
    outer_after = classify_month(outer_more, product_rules)
    mobility_only = classify_month(
        {**outer_base, "mobility_change_index": 0.50, "risky_behavior_change_index": 0.0},
        product_rules,
    )
    cochange = classify_month(
        {**outer_base, "mobility_change_index": 0.50, "risky_behavior_change_index": 0.40},
        product_rules,
    )
    no_zone = classify_month({**outer_base, "zone_available": False}, product_rules)
    allowed_inputs = set(product_rules["decision_feature_contract"]["allowed_inputs"])
    generation_only = set(product_rules["decision_feature_contract"]["generation_only_fields_excluded"])
    evaluation_rows = [
        row
        for driver in drivers
        for row in driver["monthly_results"]
        if row["period_role"] == "evaluation"
    ]
    reward_required_months = int(product_rules["reward_required_months"])
    partial_reward_evidence = [
        *(
            {
                "period_role": "evaluation",
                "reward_state": "reward",
                "care_state": "none",
            }
            for _ in range(reward_required_months - 1)
        ),
        *(
            {
                "period_role": "evaluation",
                "reward_state": "hold",
                "care_state": "hold",
            }
            for _ in range(len(EVALUATION_MONTHS) - reward_required_months + 1)
        ),
    ]

    checks = [
        {
            "check_id": "cohort_shape",
            "result_status": "passed" if len(drivers) == 60 and set(persona_counts.values()) == {10} else "failed",
            "evidence": {"driver_count": len(drivers), "persona_counts": dict(persona_counts)},
        },
        {
            "check_id": "environment_balance",
            "result_status": "passed" if set(environment_counts.values()) == {20} else "failed",
            "evidence": dict(environment_counts),
        },
        {
            "check_id": "deterministic_partition_shape",
            "result_status": "passed"
            if partition_counts == Counter({"development": 30, "validation": 18, "holdout": 12})
            else "failed",
            "evidence": dict(partition_counts),
        },
        {
            "check_id": "partition_stratification",
            "result_status": "passed"
            if all(
                Counter(
                    driver["persona_type"]
                    for driver in drivers
                    if driver["dataset_partition"] == partition
                )
                == Counter({persona: expected for persona in PERSONA_TYPES})
                and Counter(
                    driver["environment_id"]
                    for driver in drivers
                    if driver["dataset_partition"] == partition
                )
                == Counter({environment: environment_expected for environment in ENVIRONMENTS})
                for partition, expected, environment_expected in (
                    ("development", 5, 10),
                    ("validation", 3, 6),
                    ("holdout", 2, 4),
                )
            )
            else "failed",
            "evidence": {
                partition: {
                    "persona_counts": dict(
                        Counter(
                            driver["persona_type"]
                            for driver in drivers
                            if driver["dataset_partition"] == partition
                        )
                    ),
                    "environment_counts": dict(
                        Counter(
                            driver["environment_id"]
                            for driver in drivers
                            if driver["dataset_partition"] == partition
                        )
                    ),
                }
                for partition in ("development", "validation", "holdout")
            },
        },
        {
            "check_id": "fourteen_months_per_driver",
            "result_status": "passed" if all(months == set(ALL_MONTHS) for months in months_by_driver.values()) else "failed",
            "evidence": {"expected_month_count": 14, "drivers_checked": len(months_by_driver)},
        },
        {
            "check_id": "explicit_evidence_gap_scenarios",
            "result_status": "passed"
            if scenario_variant_counts == Counter({"typical": 58, "no_zone_evidence_gap": 1, "low_data_coverage": 1})
            and len(no_zone_drivers) == 1
            and no_zone_drivers[0]["mobility"]["zone_status"] == "insufficient"
            and no_zone_drivers[0]["annual_reward_state"] == "hold"
            and no_zone_drivers[0]["annual_care_state"] == "hold"
            and len(low_coverage_drivers) == 1
            and float(low_coverage_drivers[0]["data_coverage_pct"]) < float(product_rules["min_data_coverage_pct"])
            and low_coverage_drivers[0]["annual_reward_state"] == "hold"
            and low_coverage_drivers[0]["annual_care_state"] == "hold"
            else "failed",
            "evidence": {
                "scenario_variant_counts": dict(scenario_variant_counts),
                "no_zone_driver_ids": [driver["driver_id"] for driver in no_zone_drivers],
                "low_coverage_driver_ids": [driver["driver_id"] for driver in low_coverage_drivers],
            },
        },
        {
            "check_id": "one_visit_event_per_trip",
            "result_status": "passed"
            if len(events) == len({event["trip_id"] for event in events}) == len({event["visit_event_id"] for event in events})
            else "failed",
            "evidence": {"trip_count": len(events), "visit_event_count": len(events)},
        },
        {
            "check_id": "outer_zone_neutrality",
            "result_status": "passed" if outer_before == outer_after and outer_after["location_penalty"] == 0 else "failed",
            "evidence": {"before": outer_before, "after": outer_after},
        },
        {
            "check_id": "care_gate_requires_cochange",
            "result_status": "passed"
            if mobility_only["care_state"] == "none" and cochange["care_state"] == "care_review"
            else "failed",
            "evidence": {"mobility_only": mobility_only["care_state"], "cochange": cochange["care_state"]},
        },
        {
            "check_id": "risky_behavior_change_is_normalized",
            "result_status": "passed"
            if all(0.0 <= float(row["risky_behavior_rate"]) <= 1.0 for row in evaluation_rows)
            and all(0.0 <= float(row["risky_behavior_change_index"]) <= 1.0 for row in evaluation_rows)
            else "failed",
            "evidence": {
                "minimum_change_index": min(float(row["risky_behavior_change_index"]) for row in evaluation_rows),
                "maximum_change_index": max(float(row["risky_behavior_change_index"]) for row in evaluation_rows),
                "unit": product_rules["care_thresholds"]["unit"],
            },
        },
        {
            "check_id": "pattern_stability_uses_risky_behavior_change",
            "result_status": "passed"
            if product_rules["pattern_stability_basis"] == "risky_behavior_change_index"
            and all(
                float(row["pattern_stability_score"])
                == round(max(0.0, 100.0 - float(row["risky_behavior_change_index"]) * 100.0), 2)
                for row in evaluation_rows
            )
            else "failed",
            "evidence": {
                "basis": product_rules["pattern_stability_basis"],
                "rows_checked": len(evaluation_rows),
            },
        },
        {
            "check_id": "missing_zone_component_is_not_perfect_safety",
            "result_status": "passed"
            if all(
                (row["in_zone_trip_count"] > 0) == (row["in_zone_safe_score"] is not None)
                and (row["out_zone_trip_count"] > 0) == (row["out_zone_safe_score"] is not None)
                and 0.0 < float(row["observed_score_weight_pct"]) <= 100.0
                for row in evaluation_rows
            )
            else "failed",
            "evidence": {
                "rows_checked": len(evaluation_rows),
                "missing_out_zone_score_rows": sum(
                    row["out_zone_safe_score"] is None for row in evaluation_rows
                ),
                "policy": "missing_component_is_null_and_observed_weights_are_renormalized",
            },
        },
        {
            "check_id": "mobility_only_change_does_not_reduce_reward_score",
            "result_status": "passed"
            if all(
                float(row["pattern_stability_score"]) == 100.0
                for driver in typical_drivers
                if driver["persona_type"] == "mobility_change_only"
                for row in driver["monthly_results"]
                if row["period_role"] == "evaluation" and float(row["mobility_change_index"]) > 0.0
            )
            else "failed",
            "evidence": {
                "persona_type": "mobility_change_only",
                "policy": product_rules["outer_zone_policy"],
            },
        },
        {
            "check_id": "no_zone_hold_without_penalty",
            "result_status": "passed"
            if no_zone["reward_state"] == "hold" and no_zone["care_state"] == "hold" and no_zone["location_penalty"] == 0
            else "failed",
            "evidence": no_zone,
        },
        {
            "check_id": "generation_label_leakage_guard",
            "result_status": "passed" if allowed_inputs.isdisjoint(generation_only) else "failed",
            "evidence": {
                "decision_feature_keys": sorted(allowed_inputs),
                "excluded_generation_only_fields": sorted(generation_only),
                "rule_origin": product_rules["rule_origin"],
                "reason_code_source": "declared_metrics_and_gates_only",
            },
        },
        {
            "check_id": "annual_reward_required_months",
            "result_status": "passed"
            if reward_required_months == 9
            and _annual_state(partial_reward_evidence, product_rules)[0] == "hold"
            and all(
                (
                    driver["annual_reward_state"] == "reward"
                    and int(driver["reward_month_count"]) >= reward_required_months
                )
                or (
                    driver["annual_reward_state"] == "neutral"
                    and int(driver["reward_month_count"]) < reward_required_months
                    and sum(
                        row["reward_state"] != "hold"
                        for row in driver["monthly_results"]
                        if row["period_role"] == "evaluation"
                    ) >= reward_required_months
                )
                or (
                    driver["annual_reward_state"] == "hold"
                    and sum(
                        row["reward_state"] != "hold"
                        for row in driver["monthly_results"]
                        if row["period_role"] == "evaluation"
                    ) < reward_required_months
                )
                for driver in drivers
            )
            else "failed",
            "evidence": {
                "reward_required_months": reward_required_months,
                "evaluation_month_count": len(EVALUATION_MONTHS),
                "partial_evidence_policy": "hold_when_eligible_months_are_below_required_months",
            },
        },
        {
            "check_id": "persona_behavior_contract",
            "result_status": "passed"
            if all(
                driver["annual_reward_state"] == "reward"
                for driver in typical_drivers
                if driver["persona_type"] == "stable_local_safe"
            )
            and all(
                driver["annual_reward_state"] == "neutral"
                for driver in typical_drivers
                if driver["persona_type"] == "low_mileage_risky"
            )
            and all(
                driver["annual_care_state"] == "none"
                for driver in typical_drivers
                if driver["persona_type"] == "mobility_change_only"
            )
            and all(
                driver["annual_care_state"] == "care_review"
                for driver in typical_drivers
                if driver["persona_type"] == "mobility_risk_cochange"
            )
            else "failed",
            "evidence": {
                persona: {
                    "reward_states": dict(
                        Counter(
                            driver["annual_reward_state"]
                            for driver in typical_drivers
                            if driver["persona_type"] == persona
                        )
                    ),
                    "care_states": dict(
                        Counter(
                            driver["annual_care_state"]
                            for driver in typical_drivers
                            if driver["persona_type"] == persona
                        )
                    ),
                }
                for persona in PERSONA_TYPES
            },
        },
    ]
    return {
        "result_status": "passed" if all(check["result_status"] == "passed" for check in checks) else "failed",
        "checks": checks,
        "claim_boundary": "Synthetic checks establish deterministic rule behavior only; real-world outcomes require separate evidence.",
    }


def _serialize_visit_events_csv(events: Sequence[Mapping[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_VISIT_EVENT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for event in events:
        writer.writerow({field: event[field] for field in _VISIT_EVENT_FIELDS})
    return stream.getvalue()


def _artifact_reference(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _build_bundle_and_events(
    seed: int,
    *,
    raw_events_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:

    product_rules = json.loads(json.dumps(DEFAULT_PRODUCT_RULES))
    contracts = _build_driver_contracts(seed)
    all_events: list[dict[str, Any]] = []
    driver_summaries: list[dict[str, Any]] = []
    for contract in contracts:
        events = _generate_visits_for_driver(contract, seed)
        all_events.extend(events)
        driver_summaries.append(_driver_summary(contract, events, product_rules))

    persona_counts = Counter(driver["persona_type"] for driver in driver_summaries)
    environment_counts = Counter(driver["environment_id"] for driver in driver_summaries)
    partition_counts = Counter(driver["dataset_partition"] for driver in driver_summaries)
    scenario_variant_counts = Counter(driver["scenario_variant"] for driver in driver_summaries)
    repeated_pairs = Counter((event["driver_id"], event["visit_label"]) for event in all_events)
    validation = _validation_results(driver_summaries, all_events, product_rules)
    raw_csv = _serialize_visit_events_csv(all_events)
    raw_csv_sha256 = hashlib.sha256(raw_csv.encode("utf-8")).hexdigest()

    bundle = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "artifact_timestamp": ARTIFACT_TIMESTAMP,
            "simulation_seed": seed,
            "project": "FourSure · Masil",
            "competition_context": "GAIP 2026",
            "synthetic_data": True,
            "persona_naming_note": PERSONA_NAMING_NOTE,
            "decision_scope": "product_design_and_human_review_support_only",
            "partition_policy": "deterministic_stratified_development_validation_holdout",
            "rule_origin": product_rules["rule_origin"],
            "metric_units": {
                "mobility_change_index": "normalized_ratio_0_to_1",
                "risky_behavior_change_index": "normalized_ratio_0_to_1",
                "score_components": "points_0_to_100",
                "data_coverage_pct": "percent_0_to_100",
                "discount_rate_pct": "percentage_points",
            },
            "source_artifacts": {
                "raw_visit_events": {
                    "path": _artifact_reference(raw_events_path),
                    "format": "csv",
                    "row_count": len(all_events),
                    "sha256": raw_csv_sha256,
                    "contains_synthetic_coordinates": True,
                    "ui_loading_policy": "summary_bundle_only",
                }
            },
            "disclaimer": "Synthetic scenario results are not observed loss outcomes and do not set premiums, underwriting, or care decisions.",
        },
        "source_status_legend": {
            "korea_reference_product_minimum": "Domestic proposal reference retained without redefining DBSCAN distance.",
            "simulated": "Deterministically generated synthetic event.",
            "simulated_environment_assumption": "Synthetic mobility-density setting used for scenario coverage.",
            "synthetic_driver_summary": "Driver-level aggregate derived entirely from synthetic events.",
            "selected_synthetic_evidence": "Small synthetic monthly slice selected for UI explanation.",
            "derived_from_simulation": "Calculated from synthetic events and declared rules.",
            "illustrative_economics_sandbox_not_final_tariff": "Non-binding product economics comparison.",
            "not_run": "Candidate listed for a future controlled comparison; no result asserted.",
        },
        "periods": {
            "baseline_months": list(BASELINE_MONTHS),
            "evaluation_months": list(EVALUATION_MONTHS),
            "total_month_count": 14,
        },
        "cohort": {
            "driver_count": len(driver_summaries),
            "persona_count": len(PERSONA_TYPES),
            "persona_counts": dict(persona_counts),
            "environment_counts": dict(environment_counts),
            "partition_counts": dict(partition_counts),
            "scenario_variant_counts": dict(scenario_variant_counts),
            "partition_contract": {
                "development": 30,
                "validation": 18,
                "holdout": 12,
                "purpose": "Report robustness by untouched synthetic partitions; no partition is claimed as real-world evidence.",
            },
            "allocation_rule": "Each persona has 10 drivers using a rotating 4/3/3 environment allocation.",
            "scenario_variants": [
                {
                    "scenario_variant": key,
                    "scenario_label": value["label_ko"],
                    "purpose": value["purpose"],
                    "driver_count": scenario_variant_counts.get(key, 0),
                }
                for key, value in SCENARIO_VARIANTS.items()
            ],
            "personas": [
                {"persona_type": key, **value}
                for key, value in PERSONA_TYPES.items()
            ],
            "environments": [
                {
                    "environment_id": key,
                    "display_name_ko": value["display_name_ko"],
                    "source_status": "simulated_environment_assumption",
                }
                for key, value in ENVIRONMENTS.items()
            ],
        },
        "algorithm": {
            "reference": {
                "name": "DBSCAN",
                "purpose": "Detect recurrent hubs from baseline visit events.",
                "distance_metric": "haversine_m",
                "min_distinct_days": 3,
                "environment_eps_m": {
                    key: float(value["dbscan_eps_m"])
                    for key, value in ENVIRONMENTS.items()
                },
                "parameter_status": "simulation_candidate_not_product_locked",
                "no_cluster_policy": "insufficient_evidence_hold_without_invented_hub",
            },
            "product_zone": {
                "core_radius_m": float(product_rules["core_radius_m"]),
                "core_radius_status": product_rules["core_radius_source_status"],
                "buffer_rule": "per_hub_max_core_min_radial_p90_cap",
                "buffer_cap_m": float(product_rules["buffer_cap_m"]),
                "outer_policy": product_rules["outer_zone_policy"],
                "separation_note": "Core radius and radial P90 are product-zone values, not DBSCAN eps.",
            },
            "offline_comparison_candidates": [
                {"name": "HDBSCAN", "result_status": "not_run"},
                {"name": "Grid Count", "result_status": "not_run"},
            ],
        },
        "product_rules": product_rules,
        "trip_visit_summary": {
            "trip_count": len(all_events),
            "visit_event_count": len(all_events),
            "one_visit_event_per_trip": True,
            "repeated_driver_hub_pairs": sum(count >= 2 for count in repeated_pairs.values()),
            "visit_labels": list(_ALLOWED_VISIT_LABELS),
            "same_day_duplicate_support_policy": "Visits remain events; distinct days determine DBSCAN core support.",
            "source_status": "simulated",
        },
        "drivers": driver_summaries,
        "selected_monthly_evidence": _selected_evidence(driver_summaries),
        "portfolio_results": _portfolio_results(driver_summaries, all_events),
        "validation_results": validation,
    }
    return bundle, all_events, raw_csv


def build_gaip_simulation_bundle(seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Return the UI-sized deterministic GAIP simulation summary bundle."""

    bundle, _events, _raw_csv = _build_bundle_and_events(
        seed,
        raw_events_path=DEFAULT_RAW_VISIT_EVENTS_PATH,
    )
    return bundle


def write_gaip_simulation_bundle(
    path: str | Path,
    *,
    seed: int = DEFAULT_SEED,
    raw_events_path: str | Path | None = None,
) -> Path:
    destination = Path(path)
    raw_destination = Path(raw_events_path) if raw_events_path is not None else destination.with_name("gaip_visit_events.csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_destination.parent.mkdir(parents=True, exist_ok=True)
    bundle, _events, raw_csv = _build_bundle_and_events(seed, raw_events_path=raw_destination)
    raw_destination.write_text(raw_csv, encoding="utf-8")
    destination.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return destination

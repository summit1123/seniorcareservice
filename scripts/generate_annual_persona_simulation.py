#!/usr/bin/env python3
"""Generate deterministic senior-driver persona fixtures.

This fixture is the input surface for the React judge demo. It expands the
validated six-persona contract from the earlier model fixture into a full
annual scenario: 30 synthetic senior drivers, a pre-policy 60-day baseline
window, 12 evaluation months of trips, and one monthly scenario event per
driver/month.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.persona_agent import CustomerDrivingPattern, CustomerIdentity, PersonaAgent
from src.product.mileage_discount_table import (
    PERSONAL_BUSINESS,
    PERSONAL_PASSENGER_EV_HYDROGEN,
    PERSONAL_PASSENGER_GENERAL,
    lookup_existing_mileage_discount,
)


SCHEMA_VERSION = "senior-annual-persona-simulation/v1"
DEFAULT_YEAR = 2026
BASELINE_WINDOW_DAYS = 60
DEFAULT_PROFILE_OUTPUT = ROOT / "data" / "fixtures" / "annual_persona_profiles.json"
DEFAULT_TRIP_OUTPUT = ROOT / "data" / "fixtures" / "annual_trip_logs.csv"
DEFAULT_EVENTS_OUTPUT = ROOT / "data" / "fixtures" / "monthly_scenario_events.json"

VEHICLE_CLASS_ROTATION = (
    PERSONAL_PASSENGER_GENERAL,
    PERSONAL_PASSENGER_GENERAL,
    PERSONAL_PASSENGER_EV_HYDROGEN,
    PERSONAL_PASSENGER_GENERAL,
    PERSONAL_BUSINESS,
)

BASE_PREMIUM_BY_PERSONA = {
    "stable_local_low_mileage": 820_000,
    "stable_outer_safe": 910_000,
    "recent_outer_risk_change": 880_000,
    "in_zone_risky_low_mileage": 850_000,
    "medical_visit_pattern": 930_000,
    "irregular_family_support": 950_000,
}

AVG_TRIP_DISTANCE_BY_PERSONA = {
    "stable_local_low_mileage": 21.0,
    "stable_outer_safe": 32.0,
    "recent_outer_risk_change": 24.0,
    "in_zone_risky_low_mileage": 20.0,
    "medical_visit_pattern": 29.0,
    "irregular_family_support": 35.0,
}

TRIP_FIELDS = [
    "customer_id",
    "driver_id",
    "persona_type",
    "scenario_id",
    "scenario_variant",
    "simulation_seed",
    "period_role",
    "service_month",
    "month",
    "service_date",
    "trip_id",
    "trip_sequence",
    "trip_start_time",
    "trip_end_time",
    "start_gps_x",
    "start_gps_y",
    "end_gps_x",
    "end_gps_y",
    "zone_label",
    "destination_type",
    "destination_label_ko",
    "trip_purpose",
    "trip_distance_km",
    "trip_duration_min",
    "avg_speed",
    "max_speed",
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
    "risk_signal_codes",
    "monthly_scenario_event_id",
    "scenario_phase",
    "synthetic_context_note_ko",
]

DESTINATION_LABELS = {
    "home": "자택",
    "market": "마트",
    "clinic": "병원",
    "family_home": "자녀집",
    "pharmacy": "약국",
    "leisure": "근교 외출지",
    "unknown_outer": "신규 외부 목적지",
}

DESTINATION_PURPOSES = {
    "home": "귀가",
    "market": "생활 장보기",
    "clinic": "진료/검진",
    "family_home": "가족 돌봄",
    "pharmacy": "처방/약국",
    "leisure": "주간 외출",
    "unknown_outer": "최근 외부 이동",
}

RISK_EVENT_FIELDS = (
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
)


def stable_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    threshold = rng.random()
    cumulative = 0.0
    fallback = next(iter(weights))
    for key, weight in weights.items():
        cumulative += float(weight)
        fallback = key
        if threshold <= cumulative:
            return key
    return fallback


def normalize_weights(weights: dict[int | str, float]) -> dict[int | str, float]:
    total = sum(max(0.0, float(value)) for value in weights.values())
    if total <= 0:
        raise ValueError("weight total must be positive")
    return {key: round(max(0.0, float(value)) / total, 6) for key, value in weights.items()}


def allocate_labels(total: int, weights: dict[str, float]) -> list[str]:
    normalized = normalize_weights(weights)
    raw = {key: total * float(value) for key, value in normalized.items()}
    counts = {key: int(value) for key, value in raw.items()}
    remainder = total - sum(counts.values())
    ranked = sorted(raw, key=lambda key: (raw[key] - counts[key], key), reverse=True)
    for key in ranked[:remainder]:
        counts[key] += 1
    labels: list[str] = []
    for key in normalized:
        labels.extend([key] * counts[key])
    return labels


def offset_coordinate(
    center_x: float,
    center_y: float,
    meters: float,
    angle_degrees: float,
) -> tuple[float, float]:
    radians = angle_degrees * math.pi / 180
    north_m = meters * math.sin(radians)
    east_m = meters * math.cos(radians)
    lat_delta = north_m / 111_320
    lon_delta = east_m / (111_320 * max(0.2, math.cos(center_y * math.pi / 180)))
    return center_x + lon_delta, center_y + lat_delta


def bounded_offset_coordinate(
    center_x: float,
    center_y: float,
    meters: float,
    angle_degrees: float,
    rng: random.Random,
) -> tuple[float, float]:
    point = offset_coordinate(center_x, center_y, meters, angle_degrees)
    if in_fixture_coordinate_range(point):
        return point
    for _ in range(24):
        point = offset_coordinate(center_x, center_y, meters, rng.uniform(0, 360))
        if in_fixture_coordinate_range(point):
            return point
    return (
        min(127.30, max(126.70, point[0])),
        min(37.75, max(37.35, point[1])),
    )


def in_fixture_coordinate_range(point: tuple[float, float]) -> bool:
    return 126.70 <= point[0] <= 127.30 and 37.35 <= point[1] <= 37.75


def jitter_point(point: tuple[float, float], rng: random.Random, jitter_m: float = 80.0) -> tuple[float, float]:
    return bounded_offset_coordinate(point[0], point[1], rng.uniform(5, jitter_m), rng.uniform(0, 360), rng)


def month_weight_curve(persona_type: str) -> dict[int, float]:
    base = {
        1: 0.078,
        2: 0.073,
        3: 0.082,
        4: 0.083,
        5: 0.087,
        6: 0.082,
        7: 0.084,
        8: 0.088,
        9: 0.086,
        10: 0.087,
        11: 0.083,
        12: 0.087,
    }
    weights = dict(base)
    if persona_type == "recent_outer_risk_change":
        for month in (1, 2, 3, 4):
            weights[month] *= 0.90
        for month in (9, 10, 11, 12):
            weights[month] *= 1.32
    elif persona_type == "medical_visit_pattern":
        for month in (3, 6, 9, 12):
            weights[month] *= 1.12
    elif persona_type == "irregular_family_support":
        for month in (5, 8, 11):
            weights[month] *= 1.22
    elif persona_type == "stable_outer_safe":
        for month in (4, 8, 10):
            weights[month] *= 1.10
    normalized = normalize_weights(weights)
    return {int(month): float(weight) for month, weight in normalized.items()}


def monthly_behavior(persona_type: str, month: int) -> dict[str, Any]:
    if persona_type == "stable_local_low_mileage":
        return {
            "zone_mix": {"core": 0.76, "buffer": 0.21, "outer": 0.03},
            "night_drive_ratio": 0.02,
            "risk_event_rate_per_100km": 0.7,
            "scenario_phase": "stable_reference",
            "event_label_ko": "생활권 안 반복 주행",
            "living_zone_interpretation_ko": "자택·마트·병원 중심의 반복 이동이 유지됨",
            "reason_code_hints": ["STABLE_IN_ZONE_DRIVING", "LOW_RISK_EVENTS"],
        }
    if persona_type == "stable_outer_safe":
        return {
            "zone_mix": {"core": 0.50, "buffer": 0.24, "outer": 0.26},
            "night_drive_ratio": 0.04,
            "risk_event_rate_per_100km": 1.1,
            "scenario_phase": "safe_outer_repeat",
            "event_label_ko": "생활권 밖 반복 목적지 안정",
            "living_zone_interpretation_ko": "외부 이동이 있으나 반복 목적지와 주간 주행 중심임",
            "reason_code_hints": ["OUT_ZONE_SAFE", "LOW_NIGHT_DRIVING"],
        }
    if persona_type == "recent_outer_risk_change":
        if month < 9:
            return {
                "zone_mix": {"core": 0.69, "buffer": 0.23, "outer": 0.08},
                "night_drive_ratio": 0.03,
                "risk_event_rate_per_100km": 0.9,
                "scenario_phase": "pre_change_baseline",
                "event_label_ko": "평소 생활권 중심",
                "living_zone_interpretation_ko": "상반기에는 외부 목적지와 야간 신호가 제한적임",
                "reason_code_hints": ["LOW_MILEAGE", "NO_RECENT_OUT_ZONE_SPIKE"],
            }
        return {
            "zone_mix": {"core": 0.38, "buffer": 0.20, "outer": 0.42},
            "night_drive_ratio": 0.28,
            "risk_event_rate_per_100km": 6.8,
            "scenario_phase": "recent_risk_change",
            "event_label_ko": "최근 외부·야간 위험변화",
            "living_zone_interpretation_ko": "9월 이후 신규 외부 목적지와 야간/급제동 신호가 함께 증가함",
            "reason_code_hints": ["OUT_ZONE_RATIO_INCREASE", "NIGHT_DRIVING_INCREASE", "HARSH_BRAKE_INCREASE"],
        }
    if persona_type == "in_zone_risky_low_mileage":
        risk_rate = 4.3 if month < 7 else 6.4
        return {
            "zone_mix": {"core": 0.72, "buffer": 0.25, "outer": 0.03},
            "night_drive_ratio": 0.05,
            "risk_event_rate_per_100km": risk_rate,
            "scenario_phase": "in_zone_risk_watch",
            "event_label_ko": "생활권 안 위험행동 관찰",
            "living_zone_interpretation_ko": "생활권 안 이동이 많지만 과속·급감속 이벤트가 반복됨",
            "reason_code_hints": ["IN_ZONE_RISK_EVENTS", "FAVORABLE_WITHHELD_FOR_RISK"],
        }
    if persona_type == "medical_visit_pattern":
        return {
            "zone_mix": {"core": 0.44, "buffer": 0.30, "outer": 0.26},
            "night_drive_ratio": 0.03,
            "risk_event_rate_per_100km": 1.2,
            "scenario_phase": "medical_context_repeat",
            "event_label_ko": "정기 병원 목적지 반복",
            "living_zone_interpretation_ko": "외부 이동의 상당 부분이 반복 병원 목적지로 해석됨",
            "reason_code_hints": ["REPEATED_MEDICAL_DESTINATION", "OUT_ZONE_STABLE_PATTERN"],
        }
    if month in {5, 8, 11}:
        return {
            "zone_mix": {"core": 0.42, "buffer": 0.22, "outer": 0.36},
            "night_drive_ratio": 0.09,
            "risk_event_rate_per_100km": 2.4,
            "scenario_phase": "family_support_outer_month",
            "event_label_ko": "가족 돌봄 외부 이동 증가",
            "living_zone_interpretation_ko": "자녀집 방문이 늘지만 위험행동 증가는 제한적임",
            "reason_code_hints": ["FAMILY_SUPPORT_CONTEXT", "OUT_ZONE_INCREASE_WITH_LOW_RISK"],
        }
    return {
        "zone_mix": {"core": 0.54, "buffer": 0.25, "outer": 0.21},
        "night_drive_ratio": 0.06,
        "risk_event_rate_per_100km": 1.8,
        "scenario_phase": "family_support_normal",
        "event_label_ko": "가족·생활 목적지 혼합",
        "living_zone_interpretation_ko": "생활 목적지와 가족 지원 이동이 혼재함",
        "reason_code_hints": ["FAMILY_SUPPORT_CONTEXT", "NO_STRONG_RISK_CHANGE"],
    }


def baseline_behavior(persona_type: str) -> dict[str, Any]:
    """Return the pre-policy 60-day behavior used only to fit January's zone."""

    behavior = dict(monthly_behavior(persona_type, 4))
    behavior["zone_mix"] = dict(behavior["zone_mix"])
    behavior["reason_code_hints"] = list(behavior["reason_code_hints"])
    behavior["scenario_phase"] = "pre_policy_60_day_baseline"
    behavior["event_label_ko"] = "사전 60일 생활권 관찰"
    behavior["living_zone_interpretation_ko"] = "평가기간 전 60일 주행으로 1월 생활권 기준을 생성함"
    return behavior


def destination_weights_for(persona_type: str, zone_label: str, scenario_phase: str) -> dict[str, float]:
    if zone_label == "core":
        return {"home": 0.24, "market": 0.42, "clinic": 0.18, "pharmacy": 0.16}
    if zone_label == "buffer":
        if persona_type == "medical_visit_pattern":
            return {"clinic": 0.50, "pharmacy": 0.24, "market": 0.18, "home": 0.08}
        return {"market": 0.34, "clinic": 0.26, "pharmacy": 0.20, "home": 0.20}
    if persona_type == "recent_outer_risk_change" and scenario_phase == "recent_risk_change":
        return {"unknown_outer": 0.46, "family_home": 0.32, "clinic": 0.22}
    if persona_type == "medical_visit_pattern":
        return {"clinic": 0.72, "pharmacy": 0.14, "family_home": 0.14}
    if persona_type in {"stable_outer_safe", "irregular_family_support"}:
        return {"family_home": 0.55, "clinic": 0.25, "leisure": 0.20}
    return {"family_home": 0.42, "clinic": 0.32, "leisure": 0.26}


def build_destinations(identity: CustomerIdentity, rng: random.Random) -> dict[str, dict[str, Any]]:
    seed = identity.living_zone_seed
    center_x = float(seed["center_gps_x"])
    center_y = float(seed["center_gps_y"])
    persona_type = identity.persona_type
    clinic_radius = 8_500 if persona_type == "medical_visit_pattern" else 1_700
    destinations = {
        "home": {
            "label_ko": DESTINATION_LABELS["home"],
            "longitude": center_x,
            "latitude": center_y,
            "living_zone_role": "core",
        },
        "market": destination_record(center_x, center_y, 900, rng.uniform(0, 360), rng, "market", "core"),
        "clinic": destination_record(center_x, center_y, clinic_radius, rng.uniform(0, 360), rng, "clinic", "buffer"),
        "family_home": destination_record(center_x, center_y, 11_500, rng.uniform(0, 360), rng, "family_home", "outer"),
        "pharmacy": destination_record(center_x, center_y, 650, rng.uniform(0, 360), rng, "pharmacy", "core"),
        "leisure": destination_record(center_x, center_y, 7_800, rng.uniform(0, 360), rng, "leisure", "outer"),
        "unknown_outer": destination_record(center_x, center_y, 15_500, rng.uniform(0, 360), rng, "unknown_outer", "outer"),
    }
    return destinations


def destination_record(
    center_x: float,
    center_y: float,
    meters: float,
    angle_degrees: float,
    rng: random.Random,
    destination_type: str,
    living_zone_role: str,
) -> dict[str, Any]:
    lon, lat = bounded_offset_coordinate(center_x, center_y, meters, angle_degrees, rng)
    return {
        "label_ko": DESTINATION_LABELS[destination_type],
        "longitude": round(lon, 6),
        "latitude": round(lat, 6),
        "living_zone_role": living_zone_role,
    }


def vehicle_class_for(index: int) -> str:
    return VEHICLE_CLASS_ROTATION[index % len(VEHICLE_CLASS_ROTATION)]


def base_premium_for(persona_type: str, index: int, rng: random.Random) -> int:
    base = BASE_PREMIUM_BY_PERSONA[persona_type]
    return int(round((base + rng.randrange(-35_000, 45_001, 5_000) + index * 3_000) / 1000) * 1000)


def generate_annual_fixture(
    seed: int | None = None,
    year: int = DEFAULT_YEAR,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    persona_agent = PersonaAgent()
    template_seed = int(persona_agent.load_template()["simulation_seed"])
    simulation_seed = seed if seed is not None else template_seed
    identities = sorted(persona_agent.load_customer_identities(), key=lambda row: row.customer_id)
    patterns = {pattern.customer_id: pattern for pattern in persona_agent.load_customer_driving_patterns()}

    profiles: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    trips: list[dict[str, Any]] = []

    for zero_index, identity in enumerate(identities):
        rng = random.Random(stable_seed(simulation_seed, identity.customer_id, "profile"))
        pattern = patterns[identity.customer_id]
        destinations = build_destinations(identity, rng)
        annual_target = round(float(pattern.annualized_mileage_target_km), 2)
        vehicle_class = vehicle_class_for(zero_index)
        mileage_lookup = lookup_existing_mileage_discount(annual_target, vehicle_class).to_dict()
        profile = build_profile(
            identity=identity,
            pattern=pattern,
            destinations=destinations,
            annual_target=annual_target,
            vehicle_class=vehicle_class,
            base_premium_krw=base_premium_for(identity.persona_type, zero_index, rng),
            mileage_lookup=mileage_lookup,
        )
        profiles.append(profile)

        customer_trips, customer_events = generate_customer_year(
            identity=identity,
            pattern=pattern,
            destinations=destinations,
            annual_target=annual_target,
            simulation_seed=simulation_seed,
            year=year,
        )
        trips.extend(customer_trips)
        events.extend(customer_events)

    profile_payload = {
        "schema_version": "senior-annual-persona-profiles/v1",
        "simulation_seed": simulation_seed,
        "year": year,
        "baseline_observation_window": baseline_observation_window(year),
        "evaluation_period": {
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
            "months": 12,
        },
        "customer_count": len(profiles),
        "customer_count_per_persona": 5,
        "source_fixtures": {
            "persona_templates": "data/fixtures/persona_templates.yaml",
            "senior_customers": "data/fixtures/senior_customers.json",
            "customer_driving_parameters": "data/fixtures/customer_driving_parameters.json",
            "mileage_discount_table": "data/fixtures/mileage_discount_table.json",
        },
        "drivers": profiles,
        "persona_counts": dict(sorted(Counter(profile["persona_type"] for profile in profiles).items())),
        "mileage_tier_counts": dict(sorted(Counter(profile["existing_mileage_lookup"]["matched_tier_label"] for profile in profiles).items())),
    }
    events_payload = build_events_payload(events, trips, profiles, simulation_seed, year)
    validate_annual_fixture(profile_payload, trips, events_payload)
    return profile_payload, trips, events_payload


def build_profile(
    *,
    identity: CustomerIdentity,
    pattern: CustomerDrivingPattern,
    destinations: dict[str, dict[str, Any]],
    annual_target: float,
    vehicle_class: str,
    base_premium_krw: int,
    mileage_lookup: dict[str, Any],
) -> dict[str, Any]:
    profile = identity.persona_profile
    return {
        "customer_id": identity.customer_id,
        "driver_id": identity.driver_id,
        "persona_type": identity.persona_type,
        "persona_display_name_ko": profile.display_name_ko,
        "scenario_id": identity.scenario_id,
        "scenario_variant": identity.scenario_variant,
        "vehicle_class": vehicle_class,
        "base_premium_krw": base_premium_krw,
        "annual_mileage_target_km": annual_target,
        "expected_care_decision": identity.expected_care_decision,
        "expected_reason_codes": identity.expected_reason_codes,
        "existing_mileage_lookup": mileage_lookup,
        "living_destinations": destinations,
        "living_pattern": {
            "home_anchor": "synthetic_living_zone_center",
            "weekly_outing_frequency_ko": weekly_frequency_label(pattern),
            "primary_destinations": sorted(pattern.destination_weights),
            "outer_trip_tendency": outer_tendency_label(identity.persona_type),
            "risk_behavior_tendency": risk_tendency_label(identity.persona_type),
        },
        "care_context": {
            "product_role": profile.product_role,
            "message_focus": profile.care_context["care_message_focus"],
            "false_positive_or_negative_risk": profile.care_context.get(
                "false_positive_risk",
                profile.care_context.get("false_negative_risk", ""),
            ),
        },
    }


def weekly_frequency_label(pattern: CustomerDrivingPattern) -> str:
    annual_trip_estimate = (pattern.trip_count["baseline"] + pattern.trip_count["recent"]) * 365 / 90
    weekly = annual_trip_estimate / 52
    if weekly < 3:
        return "주 2회 내외"
    if weekly < 5:
        return "주 3~4회"
    if weekly < 7:
        return "주 5~6회"
    return "주 7회 이상"


def outer_tendency_label(persona_type: str) -> str:
    return {
        "stable_local_low_mileage": "생활권 안 중심",
        "stable_outer_safe": "반복 외부 목적지 안정",
        "recent_outer_risk_change": "하반기 외부 목적지 증가",
        "in_zone_risky_low_mileage": "생활권 안 중심",
        "medical_visit_pattern": "반복 병원 목적 외부 이동",
        "irregular_family_support": "가족 돌봄 외부 이동 변동",
    }[persona_type]


def risk_tendency_label(persona_type: str) -> str:
    return {
        "stable_local_low_mileage": "위험행동 낮음",
        "stable_outer_safe": "위험행동 낮음",
        "recent_outer_risk_change": "하반기 야간/급제동 증가",
        "in_zone_risky_low_mileage": "생활권 안 과속/급감속 반복",
        "medical_visit_pattern": "주간 병원 이동 중심, 위험행동 낮음",
        "irregular_family_support": "외부 이동은 변동하나 위험행동 제한적",
    }[persona_type]


def generate_customer_year(
    *,
    identity: CustomerIdentity,
    pattern: CustomerDrivingPattern,
    destinations: dict[str, dict[str, Any]],
    annual_target: float,
    simulation_seed: int,
    year: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    month_weights = month_weight_curve(identity.persona_type)
    trip_sequence = 1
    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    baseline_rows = generate_customer_baseline(
        identity=identity,
        destinations=destinations,
        annual_target=annual_target,
        simulation_seed=simulation_seed,
        evaluation_year=year,
        starting_sequence=trip_sequence,
    )
    rows.extend(baseline_rows)
    trip_sequence += len(baseline_rows)

    monthly_targets = {
        month: round(annual_target * month_weights[month], 2)
        for month in range(1, 13)
    }
    target_adjustment = round(annual_target - sum(monthly_targets.values()), 2)
    monthly_targets[12] = round(monthly_targets[12] + target_adjustment, 2)

    for month in range(1, 13):
        rng = random.Random(stable_seed(simulation_seed, identity.customer_id, year, month))
        behavior = monthly_behavior(identity.persona_type, month)
        monthly_distance = monthly_targets[month]
        avg_trip_distance = AVG_TRIP_DISTANCE_BY_PERSONA[identity.persona_type]
        trip_count = max(5, int(round(monthly_distance / avg_trip_distance + rng.choice([-1, 0, 0, 1]))))
        month_event_id = f"monthly_{identity.customer_id}_{year}_{month:02d}"
        month_rows = generate_month_trips(
            identity=identity,
            destinations=destinations,
            year=year,
            month=month,
            monthly_distance=monthly_distance,
            trip_count=trip_count,
            behavior=behavior,
            rng=rng,
            starting_sequence=trip_sequence,
            month_event_id=month_event_id,
            simulation_seed=simulation_seed,
            period_role="evaluation",
        )
        rows.extend(month_rows)
        trip_sequence += len(month_rows)
        events.append(
            build_month_event(
                identity=identity,
                year=year,
                month=month,
                month_event_id=month_event_id,
                monthly_distance=monthly_distance,
                trip_count=len(month_rows),
                behavior=behavior,
                month_rows=month_rows,
            )
        )

    return rows, events


def generate_customer_baseline(
    *,
    identity: CustomerIdentity,
    destinations: dict[str, dict[str, Any]],
    annual_target: float,
    simulation_seed: int,
    evaluation_year: int,
    starting_sequence: int,
) -> list[dict[str, Any]]:
    window = baseline_observation_window(evaluation_year)
    days_by_month: dict[tuple[int, int], list[int]] = defaultdict(list)
    start_date = date.fromisoformat(window["start_date"])
    end_date = date.fromisoformat(window["end_date"])
    cursor = start_date
    while cursor <= end_date:
        days_by_month[(cursor.year, cursor.month)].append(cursor.day)
        cursor += timedelta(days=1)

    baseline_distance = round(annual_target * BASELINE_WINDOW_DAYS / 365.0, 2)
    behavior = baseline_behavior(identity.persona_type)
    rows: list[dict[str, Any]] = []
    sequence = starting_sequence
    allocated_distance = 0.0
    month_items = sorted(days_by_month.items())
    for item_index, ((baseline_year, baseline_month), allowed_days) in enumerate(month_items):
        rng = random.Random(
            stable_seed(simulation_seed, identity.customer_id, "baseline", baseline_year, baseline_month)
        )
        if item_index == len(month_items) - 1:
            month_distance = round(baseline_distance - allocated_distance, 2)
        else:
            month_distance = round(baseline_distance * len(allowed_days) / BASELINE_WINDOW_DAYS, 2)
            allocated_distance += month_distance
        avg_trip_distance = AVG_TRIP_DISTANCE_BY_PERSONA[identity.persona_type]
        trip_count = max(4, int(round(month_distance / avg_trip_distance + rng.choice([-1, 0, 0, 1]))))
        month_rows = generate_month_trips(
            identity=identity,
            destinations=destinations,
            year=baseline_year,
            month=baseline_month,
            monthly_distance=month_distance,
            trip_count=trip_count,
            behavior=behavior,
            rng=rng,
            starting_sequence=sequence,
            month_event_id=f"baseline_{identity.customer_id}_{baseline_year}_{baseline_month:02d}",
            simulation_seed=simulation_seed,
            period_role="baseline",
            allowed_days=allowed_days,
        )
        rows.extend(month_rows)
        sequence += len(month_rows)
    return rows


def generate_month_trips(
    *,
    identity: CustomerIdentity,
    destinations: dict[str, dict[str, Any]],
    year: int,
    month: int,
    monthly_distance: float,
    trip_count: int,
    behavior: dict[str, Any],
    rng: random.Random,
    starting_sequence: int,
    month_event_id: str,
    simulation_seed: int,
    period_role: str = "evaluation",
    allowed_days: list[int] | None = None,
) -> list[dict[str, Any]]:
    zone_labels = allocate_labels(trip_count, behavior["zone_mix"])
    rng.shuffle(zone_labels)
    night_indices = set(rng.sample(range(trip_count), night_trip_count(trip_count, behavior["night_drive_ratio"], behavior["scenario_phase"])))
    distances = allocate_distances(monthly_distance, trip_count, rng)
    event_plan = risk_event_plan(
        monthly_distance=monthly_distance,
        risk_event_rate_per_100km=float(behavior["risk_event_rate_per_100km"]),
        trip_count=trip_count,
        persona_type=identity.persona_type,
        rng=rng,
    )
    day_numbers = monthly_trip_days(year, month, trip_count, rng, allowed_days=allowed_days)

    rows: list[dict[str, Any]] = []
    for index in range(trip_count):
        sequence = starting_sequence + index
        zone_label = zone_labels[index]
        destination_type = weighted_choice(
            rng,
            destination_weights_for(identity.persona_type, zone_label, str(behavior["scenario_phase"])),
        )
        start_dt = trip_start_datetime(year, month, day_numbers[index], index in night_indices, rng)
        distance_km = distances[index]
        avg_speed = average_speed(identity.persona_type, str(behavior["scenario_phase"]), zone_label, rng)
        duration_min = round(max(5.0, distance_km / avg_speed * 60), 1)
        end_dt = start_dt + timedelta(minutes=duration_min)
        event_counts = event_plan[index]
        max_speed = round(min(120.0, avg_speed + rng.uniform(10, 22) + sum(event_counts.values()) * 5.5), 1)
        start_point, end_point = trip_points(destinations, destination_type, sequence, rng)
        night_flag = int(start_dt.hour >= 22 or start_dt.hour < 6)
        signals = risk_signals(
            persona_type=identity.persona_type,
            scenario_phase=str(behavior["scenario_phase"]),
            zone_label=zone_label,
            destination_type=destination_type,
            night_flag=night_flag,
            event_counts=event_counts,
            duration_min=duration_min,
        )
        rows.append(
            {
                "customer_id": identity.customer_id,
                "driver_id": identity.driver_id,
                "persona_type": identity.persona_type,
                "scenario_id": identity.scenario_id,
                "scenario_variant": identity.scenario_variant,
                "simulation_seed": simulation_seed,
                "period_role": period_role,
                "service_month": f"{year}-{month:02d}",
                "month": month,
                "service_date": start_dt.date().isoformat(),
                "trip_id": f"{period_role}_trip_{identity.customer_id}_{sequence:04d}",
                "trip_sequence": sequence,
                "trip_start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "trip_end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "start_gps_x": round(start_point[0], 6),
                "start_gps_y": round(start_point[1], 6),
                "end_gps_x": round(end_point[0], 6),
                "end_gps_y": round(end_point[1], 6),
                "zone_label": zone_label,
                "destination_type": destination_type,
                "destination_label_ko": DESTINATION_LABELS[destination_type],
                "trip_purpose": DESTINATION_PURPOSES[destination_type],
                "trip_distance_km": distance_km,
                "trip_duration_min": duration_min,
                "avg_speed": round(distance_km / duration_min * 60, 1),
                "max_speed": max_speed,
                "night_drive_flag": night_flag,
                "speeding_count": event_counts["speeding_count"],
                "harsh_accel_count": event_counts["harsh_accel_count"],
                "harsh_brake_count": event_counts["harsh_brake_count"],
                "sharp_turn_count": event_counts["sharp_turn_count"],
                "stop_count": stop_count(zone_label, distance_km, rng),
                "night_driving_signal": signals["night_driving_signal"],
                "sudden_braking_signal": signals["sudden_braking_signal"],
                "route_deviation_signal": signals["route_deviation_signal"],
                "fatigue_indicator": signals["fatigue_indicator"],
                "risk_signal_codes": signals["risk_signal_codes"],
                "monthly_scenario_event_id": month_event_id,
                "scenario_phase": behavior["scenario_phase"],
                "synthetic_context_note_ko": behavior["living_zone_interpretation_ko"],
            }
        )
    return rows


def monthly_trip_days(
    year: int,
    month: int,
    trip_count: int,
    rng: random.Random,
    *,
    allowed_days: list[int] | None = None,
) -> list[int]:
    last_day = calendar.monthrange(year, month)[1]
    day_pool = sorted(set(allowed_days or range(1, last_day + 1)))
    if not day_pool or day_pool[0] < 1 or day_pool[-1] > last_day:
        raise ValueError(f"invalid allowed day window for {year}-{month:02d}: {allowed_days}")
    days: list[int] = []
    for index in range(trip_count):
        base_index = min(len(day_pool) - 1, int(index * len(day_pool) / trip_count))
        day_index = max(0, min(len(day_pool) - 1, base_index + rng.choice([-1, 0, 0, 1])))
        day = day_pool[day_index]
        days.append(day)
    return sorted(days)


def night_trip_count(trip_count: int, night_ratio: float, scenario_phase: str) -> int:
    count = int(round(trip_count * night_ratio))
    if scenario_phase == "recent_risk_change":
        return max(1, count)
    return count


def allocate_distances(monthly_distance: float, trip_count: int, rng: random.Random) -> list[float]:
    weights = [rng.uniform(0.72, 1.28) for _ in range(trip_count)]
    total = sum(weights)
    distances = [round(monthly_distance * weight / total, 2) for weight in weights[:-1]]
    last_distance = round(monthly_distance - sum(distances), 2)
    if last_distance <= 0:
        last_distance = round(monthly_distance / trip_count, 2)
        distances = [round((monthly_distance - last_distance) / (trip_count - 1), 2)] * (trip_count - 1)
    distances.append(last_distance)
    return distances


def risk_event_plan(
    *,
    monthly_distance: float,
    risk_event_rate_per_100km: float,
    trip_count: int,
    persona_type: str,
    rng: random.Random,
) -> list[dict[str, int]]:
    rows = [{field: 0 for field in RISK_EVENT_FIELDS} for _ in range(trip_count)]
    target_events = int(round(monthly_distance * risk_event_rate_per_100km / 100))
    if target_events <= 0:
        return rows
    if persona_type == "recent_outer_risk_change":
        mix = {"speeding_count": 0.26, "harsh_accel_count": 0.16, "harsh_brake_count": 0.45, "sharp_turn_count": 0.13}
    elif persona_type == "in_zone_risky_low_mileage":
        mix = {"speeding_count": 0.24, "harsh_accel_count": 0.20, "harsh_brake_count": 0.40, "sharp_turn_count": 0.16}
    else:
        mix = {"speeding_count": 0.18, "harsh_accel_count": 0.18, "harsh_brake_count": 0.46, "sharp_turn_count": 0.18}
    event_trip_indices = [rng.randrange(trip_count) for _ in range(max(target_events, 1))]
    for event_index in range(target_events):
        field = weighted_choice(rng, mix)
        rows[event_trip_indices[event_index % len(event_trip_indices)]][field] += 1
    return rows


def trip_start_datetime(year: int, month: int, day: int, night: bool, rng: random.Random) -> datetime:
    if night:
        hour = rng.choice([22, 23])
    else:
        hour = rng.choice([8, 9, 10, 11, 13, 14, 15, 16, 18, 19])
    minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
    return datetime(year, month, day, hour, minute)


def average_speed(persona_type: str, scenario_phase: str, zone_label: str, rng: random.Random) -> float:
    if zone_label == "outer":
        speed = rng.uniform(34, 48)
    elif zone_label == "buffer":
        speed = rng.uniform(22, 34)
    else:
        speed = rng.uniform(16, 28)
    if persona_type == "recent_outer_risk_change" and scenario_phase == "recent_risk_change":
        speed += rng.uniform(5, 9)
    return round(speed, 1)


def trip_points(
    destinations: dict[str, dict[str, Any]],
    destination_type: str,
    sequence: int,
    rng: random.Random,
) -> tuple[tuple[float, float], tuple[float, float]]:
    home = (float(destinations["home"]["longitude"]), float(destinations["home"]["latitude"]))
    destination = (
        float(destinations[destination_type]["longitude"]),
        float(destinations[destination_type]["latitude"]),
    )
    if destination_type == "home" or sequence % 2 == 0:
        return jitter_point(destination, rng), jitter_point(home, rng)
    return jitter_point(home, rng), jitter_point(destination, rng)


def stop_count(zone_label: str, distance_km: float, rng: random.Random) -> int:
    base = {"core": 4, "buffer": 3, "outer": 1}[zone_label]
    return max(0, int(round(base + distance_km / 9 + rng.choice([-1, 0, 0, 1]))))


def risk_signals(
    *,
    persona_type: str,
    scenario_phase: str,
    zone_label: str,
    destination_type: str,
    night_flag: int,
    event_counts: dict[str, int],
    duration_min: float,
) -> dict[str, Any]:
    event_total = sum(event_counts.values())
    sudden_braking = int(event_counts["harsh_brake_count"] > 0)
    route_deviation = int(
        zone_label == "outer"
        and (
            destination_type == "unknown_outer"
            or scenario_phase == "recent_risk_change"
            or (persona_type == "irregular_family_support" and destination_type == "family_home")
        )
    )
    fatigue = int(night_flag and (duration_min >= 50 or event_total > 0))
    codes: list[str] = []
    if night_flag:
        codes.append("NIGHT_DRIVING")
    if sudden_braking:
        codes.append("SUDDEN_BRAKING")
    if route_deviation:
        codes.append("ROUTE_DEVIATION")
    if fatigue:
        codes.append("FATIGUE_INDICATOR")
    return {
        "night_driving_signal": night_flag,
        "sudden_braking_signal": sudden_braking,
        "route_deviation_signal": route_deviation,
        "fatigue_indicator": fatigue,
        "risk_signal_codes": "|".join(codes) if codes else "none",
    }


def build_month_event(
    *,
    identity: CustomerIdentity,
    year: int,
    month: int,
    month_event_id: str,
    monthly_distance: float,
    trip_count: int,
    behavior: dict[str, Any],
    month_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    risk_event_count = sum(int(row[field]) for row in month_rows for field in RISK_EVENT_FIELDS)
    outer_count = sum(1 for row in month_rows if row["zone_label"] == "outer")
    night_count = sum(int(row["night_drive_flag"]) for row in month_rows)
    return {
        "event_id": month_event_id,
        "customer_id": identity.customer_id,
        "driver_id": identity.driver_id,
        "persona_type": identity.persona_type,
        "scenario_id": identity.scenario_id,
        "service_month": f"{year}-{month:02d}",
        "month": month,
        "scenario_phase": behavior["scenario_phase"],
        "event_label_ko": behavior["event_label_ko"],
        "monthly_distance_km": round(sum(float(row["trip_distance_km"]) for row in month_rows), 2),
        "monthly_distance_target_km": monthly_distance,
        "trip_count": trip_count,
        "zone_mix_target": behavior["zone_mix"],
        "observed_outer_trip_ratio": round(outer_count / trip_count, 4),
        "night_drive_ratio_target": behavior["night_drive_ratio"],
        "observed_night_trip_ratio": round(night_count / trip_count, 4),
        "risk_event_rate_target_per_100km": behavior["risk_event_rate_per_100km"],
        "observed_risk_event_count": risk_event_count,
        "living_zone_interpretation_ko": behavior["living_zone_interpretation_ko"],
        "reason_code_hints": behavior["reason_code_hints"],
        "ui_timeline_role": "monthly_living_zone_evidence",
    }


def build_events_payload(
    events: list[dict[str, Any]],
    trips: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    simulation_seed: int,
    year: int,
) -> dict[str, Any]:
    annual_distance_by_customer: dict[str, float] = defaultdict(float)
    trip_count_by_customer: dict[str, int] = defaultdict(int)
    for row in trips:
        if row.get("period_role") != "evaluation":
            continue
        annual_distance_by_customer[str(row["customer_id"])] += float(row["trip_distance_km"])
        trip_count_by_customer[str(row["customer_id"])] += 1
    return {
        "schema_version": "senior-monthly-scenario-events/v1",
        "simulation_seed": simulation_seed,
        "year": year,
        "baseline_observation_window": baseline_observation_window(year),
        "annual_distance_scope": "evaluation_period_only_excludes_pre_policy_baseline",
        "event_count": len(events),
        "customer_count": len(profiles),
        "months_per_customer": 12,
        "events": events,
        "annual_summary_by_customer": {
            profile["customer_id"]: {
                "driver_id": profile["driver_id"],
                "persona_type": profile["persona_type"],
                "annual_distance_km": round(annual_distance_by_customer[profile["customer_id"]], 2),
                "trip_count": trip_count_by_customer[profile["customer_id"]],
                "existing_mileage_tier": profile["existing_mileage_lookup"]["matched_tier_label"],
                "expected_care_decision": profile["expected_care_decision"],
            }
            for profile in profiles
        },
    }


def baseline_observation_window(year: int) -> dict[str, Any]:
    end_date = date(year, 1, 1) - timedelta(days=1)
    start_date = end_date - timedelta(days=BASELINE_WINDOW_DAYS - 1)
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": BASELINE_WINDOW_DAYS,
        "period_role": "baseline",
        "usage": "living_zone_fit_and_pattern_comparison_only",
        "excluded_from_annual_mileage_and_discount_amounts": True,
    }


def validate_annual_fixture(
    profile_payload: dict[str, Any],
    trips: list[dict[str, Any]],
    events_payload: dict[str, Any],
) -> None:
    profiles = profile_payload["drivers"]
    if len(profiles) != 30:
        raise ValueError(f"annual profile fixture must contain 30 drivers, got {len(profiles)}")
    persona_counts = Counter(profile["persona_type"] for profile in profiles)
    invalid_counts = {persona: count for persona, count in persona_counts.items() if count != 5}
    if invalid_counts:
        raise ValueError(f"each persona must have five drivers; invalid_counts={invalid_counts}")
    for profile in profiles:
        destinations = profile["living_destinations"]
        required = {"home", "clinic", "market", "family_home"}
        if not required.issubset(destinations):
            raise ValueError(f"{profile['customer_id']} missing required destinations")

    rows_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trips:
        rows_by_customer[str(row["customer_id"])].append(row)
        validate_trip_row(row)
    if set(rows_by_customer) != {profile["customer_id"] for profile in profiles}:
        raise ValueError("annual trip logs must cover the same 30 customers as profiles")
    for customer_id, rows in rows_by_customer.items():
        roles = {str(row["period_role"]) for row in rows}
        if roles != {"baseline", "evaluation"}:
            raise ValueError(f"{customer_id} must have baseline and evaluation trip rows; roles={sorted(roles)}")
        evaluation_rows = [row for row in rows if row["period_role"] == "evaluation"]
        baseline_rows = [row for row in rows if row["period_role"] == "baseline"]
        evaluation_months = {int(row["month"]) for row in evaluation_rows}
        if evaluation_months != set(range(1, 13)):
            raise ValueError(
                f"{customer_id} must have evaluation trips in all 12 months; months={sorted(evaluation_months)}"
            )
        validate_baseline_window(customer_id, baseline_rows, int(profile_payload["year"]))

    events = events_payload["events"]
    if len(events) != 30 * 12:
        raise ValueError(f"monthly_scenario_events must contain 360 events, got {len(events)}")
    event_months_by_customer: dict[str, set[int]] = defaultdict(set)
    for event in events:
        event_months_by_customer[str(event["customer_id"])].add(int(event["month"]))
    for profile in profiles:
        if event_months_by_customer[profile["customer_id"]] != set(range(1, 13)):
            raise ValueError(f"{profile['customer_id']} must have one monthly scenario event for each month")

    annual_distance_by_customer = {
        customer_id: round(
            sum(float(row["trip_distance_km"]) for row in rows if row["period_role"] == "evaluation"),
            2,
        )
        for customer_id, rows in rows_by_customer.items()
    }
    tier_labels = {
        lookup_existing_mileage_discount(
            annual_distance,
            next(profile["vehicle_class"] for profile in profiles if profile["customer_id"] == customer_id),
        ).matched_tier_label
        for customer_id, annual_distance in annual_distance_by_customer.items()
    }
    if len(tier_labels) < 6:
        raise ValueError(f"annual mileage distribution must cover at least six existing tiers, got {sorted(tier_labels)}")


def validate_baseline_window(customer_id: str, rows: list[dict[str, Any]], year: int) -> None:
    if not rows:
        raise ValueError(f"{customer_id} must have pre-policy baseline trip rows")
    window = baseline_observation_window(year)
    start_date = date.fromisoformat(window["start_date"])
    end_date = date.fromisoformat(window["end_date"])
    for row in rows:
        service_date = date.fromisoformat(str(row["service_date"]))
        if not start_date <= service_date <= end_date:
            raise ValueError(f"{customer_id} baseline row outside 60-day window: {service_date.isoformat()}")


def validate_trip_row(row: dict[str, Any]) -> None:
    start_dt = datetime.strptime(str(row["trip_start_time"]), "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(str(row["trip_end_time"]), "%Y-%m-%d %H:%M:%S")
    if row.get("period_role") not in {"baseline", "evaluation"}:
        raise ValueError(f"{row['trip_id']} period_role must be baseline or evaluation")
    if start_dt >= end_dt:
        raise ValueError(f"{row['trip_id']} has invalid time order")
    if start_dt.date().isoformat() != row["service_date"]:
        raise ValueError(f"{row['trip_id']} service_date must match trip_start_time")
    if int(row["month"]) != start_dt.month:
        raise ValueError(f"{row['trip_id']} month must match trip_start_time")
    for key in ("start_gps_x", "end_gps_x"):
        if not 126.70 <= float(row[key]) <= 127.30:
            raise ValueError(f"{row['trip_id']} {key} outside synthetic coordinate range")
    for key in ("start_gps_y", "end_gps_y"):
        if not 37.35 <= float(row[key]) <= 37.75:
            raise ValueError(f"{row['trip_id']} {key} outside synthetic coordinate range")
    if float(row["trip_distance_km"]) <= 0 or float(row["trip_duration_min"]) <= 0:
        raise ValueError(f"{row['trip_id']} distance and duration must be positive")
    expected_avg_speed = float(row["trip_distance_km"]) / float(row["trip_duration_min"]) * 60
    if abs(expected_avg_speed - float(row["avg_speed"])) > 1.0:
        raise ValueError(f"{row['trip_id']} avg_speed mismatch")
    for key in (*RISK_EVENT_FIELDS, "stop_count"):
        if int(row[key]) < 0:
            raise ValueError(f"{row['trip_id']} {key} must be non-negative")
    for key in ("night_drive_flag", "night_driving_signal", "sudden_braking_signal", "route_deviation_signal", "fatigue_indicator"):
        if int(row[key]) not in {0, 1}:
            raise ValueError(f"{row['trip_id']} {key} must be 0 or 1")
    if int(row["night_drive_flag"]) != int(row["night_driving_signal"]):
        raise ValueError(f"{row['trip_id']} night_driving_signal must mirror night_drive_flag")
    if int(row["sudden_braking_signal"]) != int(int(row["harsh_brake_count"]) > 0):
        raise ValueError(f"{row['trip_id']} sudden_braking_signal must follow harsh_brake_count")


def write_outputs(
    profile_payload: dict[str, Any],
    trips: list[dict[str, Any]],
    events_payload: dict[str, Any],
    *,
    profile_output: Path,
    trip_output: Path,
    events_output: Path,
) -> None:
    profile_output.parent.mkdir(parents=True, exist_ok=True)
    with profile_output.open("w", encoding="utf-8") as file:
        json.dump(profile_payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    trip_output.parent.mkdir(parents=True, exist_ok=True)
    with trip_output.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=TRIP_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(trips)
    events_output.parent.mkdir(parents=True, exist_ok=True)
    with events_output.open("w", encoding="utf-8") as file:
        json.dump(events_payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate annual senior persona trip simulation fixtures.")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILE_OUTPUT), help="Annual persona profile JSON output path")
    parser.add_argument("--trips", default=str(DEFAULT_TRIP_OUTPUT), help="Annual trip CSV output path")
    parser.add_argument("--events", default=str(DEFAULT_EVENTS_OUTPUT), help="Monthly scenario events JSON output path")
    parser.add_argument("--seed", type=int, default=None, help="Override simulation seed")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="Simulation year")
    args = parser.parse_args(argv)

    profiles, trips, events = generate_annual_fixture(seed=args.seed, year=args.year)
    write_outputs(
        profiles,
        trips,
        events,
        profile_output=Path(args.profiles),
        trip_output=Path(args.trips),
        events_output=Path(args.events),
    )
    print(f"wrote {profiles['customer_count']} annual persona profiles to {args.profiles}")
    print(f"wrote {len(trips)} annual trip rows to {args.trips}")
    print(f"wrote {events['event_count']} monthly scenario events to {args.events}")
    print(f"covered mileage tiers: {', '.join(sorted(profiles['mileage_tier_counts']))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

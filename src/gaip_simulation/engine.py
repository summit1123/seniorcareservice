"""Deterministic GAIP cohort, mobility, product-rule, and pricing sandbox."""

from __future__ import annotations

import hashlib
import csv
import io
import json
import math
import os
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

# ---------------------------------------------------------------------------
# Archetype-driven cohort. The rich person/behaviour archetypes live in
# ``personas.py``; this engine samples them into individual drivers and derives
# every outcome from the generated coordinates and events (no label leakage).
# ---------------------------------------------------------------------------
from . import personas

_ARCHETYPES_BY_ID: dict[str, dict[str, Any]] = {
    archetype["id"]: archetype for archetype in personas.ARCHETYPES
}

PERSONA_NAMING_NOTE = "이름·나이·장소 라벨은 전원 합성(실존 인물·장소 아님)"

# Synthetic semantic display labels for the generic living-zone hubs. UI-only
# strings; the raw visit event CSV keeps the generic Routine Hub A/B/New Hub
# vocabulary. Every value here is an approved synthetic label (no real place).
HOME_ZONE_LABEL_KO = "자택 인근"
# Keyed by the 6 behaviour designed_types.
SECONDARY_ZONE_LABELS_KO: dict[str, str] = {
    "multi_zone": "두 번째 생활권",
}
NEW_HUB_LABELS_KO: dict[str, str] = {
    "mobility_risk_cochange": "야간 외곽 경로",
    "mobility_change_safe": "신규 목적지",
    "wide_area_safe": "원거리 정기 방문지",
    "multi_zone": "두 번째 생활권",
    "stable_reward": "신규 외출지",
    "in_zone_risky": "야간 신규 목적지",
}
DEFAULT_SECONDARY_ZONE_LABEL_KO = "두 번째 생활권"
APPROVED_HUB_LABELS_KO: frozenset[str] = frozenset(
    {HOME_ZONE_LABEL_KO, DEFAULT_SECONDARY_ZONE_LABEL_KO}
    | set(SECONDARY_ZONE_LABELS_KO.values())
    | set(NEW_HUB_LABELS_KO.values())
)


def _secondary_zone_label_ko(driver: Mapping[str, Any]) -> str:
    return SECONDARY_ZONE_LABELS_KO.get(
        str(driver["designed_type"]), DEFAULT_SECONDARY_ZONE_LABEL_KO
    )


def _new_hub_label_ko(driver: Mapping[str, Any]) -> str:
    return NEW_HUB_LABELS_KO.get(str(driver["designed_type"]), "신규 목적지")

# Environment = a local density profile. Regular in-zone destinations sit inside
# ``zone_reach_m`` of home (close enough that DBSCAN with ``dbscan_eps_m`` groups
# them into ONE living zone); the far/secondary destination sits at
# ``outer_distance_m`` so it reads as outside the home zone (or a second zone for
# multi-hub personas). Visit points scatter only ``visit_jitter_m`` around each
# destination, so a cluster's radial P90 reflects the spread of real destinations
# (hundreds of metres), not GPS noise.
ENVIRONMENTS: dict[str, dict[str, Any]] = {
    "dense_urban": {
        "display_name_ko": "고밀도 도심형",
        "base_latitude": 37.55,
        "base_longitude": 126.96,
        "zone_reach_m": 900.0,
        "outer_distance_m": 5_200.0,
        "visit_jitter_m": 40.0,
        "dbscan_eps_m": 260.0,
        "base_trip_distance_km": 5.4,
    },
    "suburban_mid_density": {
        "display_name_ko": "교외·중밀도형",
        "base_latitude": 37.39,
        "base_longitude": 127.10,
        "zone_reach_m": 1_500.0,
        "outer_distance_m": 9_500.0,
        "visit_jitter_m": 70.0,
        "dbscan_eps_m": 520.0,
        "base_trip_distance_km": 11.0,
    },
    "wide_low_density": {
        "display_name_ko": "광역 저밀도형",
        "base_latitude": 36.55,
        "base_longitude": 127.74,
        "zone_reach_m": 3_000.0,
        "outer_distance_m": 22_000.0,
        "visit_jitter_m": 130.0,
        "dbscan_eps_m": 1_100.0,
        "base_trip_distance_km": 24.0,
    },
}

# Stable bearings so the synthetic living-zone layout is legible and
# deterministic. Hub A / Hub B sit inside ``zone_reach_m`` of home (the home
# living zone); the "New Hub" is either a distant second living zone (for
# multi-zone archetypes) or an out-of-zone / new destination.
_HUB_A_BEARING = 205.0
_HUB_B_BEARING = 58.0
_NEW_HUB_BEARING = 128.0
# A genuine second living zone sits at this fraction of ``outer_distance_m`` —
# far enough to fall outside the home buffer but close enough to read as a real
# secondary zone (e.g. a child's home) rather than an incidental far trip.
_SECONDARY_ZONE_OUTER_FRAC = 0.5
# Baseline visits within this multiple of ``zone_reach_m`` of the home centre
# count toward the home living zone's radial-P90 (the displayed buffer).
_HOME_ZONE_REACH_FACTOR = 1.25

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
    "reward_bonus_discount_rate_pct": 7.0,
    "reward_bonus_floor_pct": 1.0,
    "care_discount_reduction_pct": 13.0,
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
            "archetype_id",
            "designed_type",
            "data_quality",
            "visit_label",
            "scenario_truth",
            "expected_reward_state",
            "expected_care_state",
        ],
    },
}

# The raw visit-event CSV keeps a stable 17-column schema. Only generic visit
# labels and generation-only truth labels (designed_type / data_quality) appear;
# no person name, place name, or archetype id (which may carry a place token).
_ALLOWED_VISIT_LABELS = ("Routine Hub A", "Routine Hub B", "New Hub")
_VISIT_EVENT_FIELDS = (
    "trip_id",
    "visit_event_id",
    "driver_id",
    "designed_type",
    "environment_id",
    "dataset_partition",
    "data_quality",
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


# Deterministic dev:validation:holdout split, applied per archetype instance so
# every archetype (and, in aggregate, every environment) is represented in all
# three partitions. Instance i within an archetype: i%5 in {0,1,2}=development,
# 3=validation, 4=holdout — a clean, documented ~3:1:1 rule.
_PARTITION_BY_INSTANCE = ("development", "development", "development", "validation", "holdout")


def _partition_for_instance(instance_index: int) -> str:
    return _PARTITION_BY_INSTANCE[instance_index % len(_PARTITION_BY_INSTANCE)]


def _environment_for_instance(instance_index: int) -> str:
    environment_ids = list(ENVIRONMENTS)
    return environment_ids[instance_index % len(environment_ids)]


def _driver_name_ko(seed: int, driver_id: str, sex_bias: str) -> str:
    """Deterministic synthetic name (family + given by sex). Collisions are fine.

    Uses a dedicated ``_stable_seed("naming", ...)`` stream so name assignment
    never consumes draws from the visit-generation RNG streams.
    """

    rng = random.Random(_stable_seed("naming", seed, driver_id))
    family = rng.choice(personas.FAMILY_NAMES)
    given_pool = (
        personas.GIVEN_NAMES_FEMALE if sex_bias == "female" else personas.GIVEN_NAMES_MALE
    )
    return f"{family}{rng.choice(given_pool)}"


def _driver_age(driver_id: str, age_range: Sequence[int]) -> int:
    """Deterministic synthetic age inside the archetype's age_range."""

    low, high = int(age_range[0]), int(age_range[1])
    rng = random.Random(_stable_seed("naming", driver_id, "age"))
    return low + rng.randrange(high - low + 1)


def _build_driver_contracts(seed: int) -> list[dict[str, Any]]:
    """Build 180 driver-cases = the 60-person roster run in each of 3 environments.

    ``personas.build_person_roster`` returns 60 distinct people (fixed identity +
    driving disposition). Each person is then simulated in all three mobility
    environments (도심·도농·광역) — a "what if this person lived in a denser /
    sparser area" transferability experiment — so the same person appears three
    times with the same name/age/disposition but a different environment, home,
    and simulation seed. The archetype's ``designed_type`` is a validation label
    only; it never enters scoring.
    """

    roster = personas.build_person_roster(seed)
    environment_ids = list(ENVIRONMENTS)
    drivers: list[dict[str, Any]] = []
    for person_index, person in enumerate(roster):
        for env_index, environment_id in enumerate(environment_ids):
            global_index = len(drivers)
            driver_id = f"gaip-{global_index + 1:03d}"
            disposition = dict(person["disposition"])
            driver: dict[str, Any] = {
                "driver_id": driver_id,
                "person_id": str(person["person_id"]),
                "archetype_id": str(person["archetype_id"]),
                "designed_type": str(person["designed_type"]),
                "persona_display_name_ko": str(_ARCHETYPES_BY_ID[str(person["archetype_id"])]["name_ko"]),
                "persona_summary_ko": str(person["life_context_ko"]),
                "persona_narrative_ko": str(person["persona_narrative_ko"]),
                "mobility_goal_ko": str(person["mobility_goal_ko"]),
                "driving_habit_ko": str(person["driving_habit_ko"]),
                "environment_id": environment_id,
                "environment_display_name_ko": ENVIRONMENTS[environment_id]["display_name_ko"],
                # Each person appears in all three environments, so the split is by
                # person (not by case) to keep a person's 3 cases in one partition.
                "dataset_partition": _partition_for_instance(person_index),
                "driver_name_ko": str(person["name_ko"]),
                "age": int(person["age"]),
                "sex": str(person["sex"]),
                "household": str(person["household_ko"]),
                "retired": bool(person["retired"]),
                "primary_purpose_ko": str(person["primary_purpose_ko"]),
                "life_context_ko": str(person["life_context_ko"]),
                "data_quality": str(disposition.get("data_quality", "good")),
                "disposition": disposition,
                # Keep each person's home layout stable across environments via a
                # person-scoped sequence; the environment scales the zone.
                "persona_sequence": person_index + 1,
                "simulation_seed": _stable_seed(seed, person["person_id"], environment_id),
                "vehicle_class": VEHICLE_CLASS_ROTATION[person_index % len(VEHICLE_CLASS_ROTATION)],
                "base_premium_krw": 780_000 + (person_index % 16) * 12_000,
            }
            drivers.append(driver)
    return drivers


def _hub_centers(driver: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    """Place HOME and the driver's destinations from its disposition.

    Hub A / Hub B are in-zone destinations that sit inside ``zone_reach_m`` of
    home (they form the home living zone). The "New Hub" is either a genuine
    second living zone (multi-zone archetypes, at half the outer distance) or an
    out-of-zone / new destination (at the full outer distance).
    """

    environment = ENVIRONMENTS[str(driver["environment_id"])]
    disposition = driver["disposition"]
    sequence = int(driver["persona_sequence"])
    reach = float(environment["zone_reach_m"])
    outer = float(environment["outer_distance_m"])
    reach_fracs = list(disposition["in_zone_reach_frac"])
    has_secondary = bool(disposition["has_secondary_zone"])

    # Home anchor: golden-angle spread so drivers never overlap on the schematic.
    home_lat, home_lon = _offset_coordinate(
        float(environment["base_latitude"]),
        float(environment["base_longitude"]),
        50_000.0 + 1_700.0 * sequence,
        (137.508 * sequence) % 360.0,
    )
    hub_a = _offset_coordinate(home_lat, home_lon, reach * float(reach_fracs[0]), _HUB_A_BEARING)
    hub_b = _offset_coordinate(home_lat, home_lon, reach * float(reach_fracs[-1]), _HUB_B_BEARING)
    if has_secondary:
        # A genuine second living zone (child's home / farm): far enough to fall
        # outside the home buffer, revisited enough to form its own cluster.
        new_hub = _offset_coordinate(
            home_lat, home_lon, outer * _SECONDARY_ZONE_OUTER_FRAC, 300.0
        )
    else:
        new_hub = _offset_coordinate(home_lat, home_lon, outer, _NEW_HUB_BEARING)
    return {
        "Routine Hub A": hub_a,
        "Routine Hub B": hub_b,
        "New Hub": new_hub,
        "__home__": (home_lat, home_lon),
    }


def _month_visit_weights(
    disposition: Mapping[str, Any], evaluation_month: int | None
) -> dict[str, float]:
    """Where the driver goes this month, derived from the disposition.

    - secondary-zone archetypes keep steady visits to their second living zone
      (mapped to the "New Hub" label, but recognised as in-zone once clustered);
    - in-zone-risky drivers keep a small, constant out-of-zone share;
    - change archetypes shift toward the New Hub from evaluation month 8;
    - everyone else stays in their home zone (Hub A / Hub B).
    """

    change = disposition.get("change")
    locus = disposition["risk_locus"]
    shifted = evaluation_month is not None and evaluation_month >= 8

    if disposition["has_secondary_zone"]:
        if change in {"mobility", "cochange"} and shifted:
            return {"Routine Hub A": 0.32, "Routine Hub B": 0.26, "New Hub": 0.42}
        return {"Routine Hub A": 0.42, "Routine Hub B": 0.30, "New Hub": 0.28}
    if locus == "in_zone":
        # Risky wherever they drive, with a steady modest out-of-zone share so the
        # out-zone safety score also reflects the behaviour (→ neutral, not reward).
        return {"Routine Hub A": 0.52, "Routine Hub B": 0.26, "New Hub": 0.22}
    if change in {"mobility", "cochange"}:
        if shifted:
            return {"Routine Hub A": 0.30, "Routine Hub B": 0.16, "New Hub": 0.54}
        return {"Routine Hub A": 0.68, "Routine Hub B": 0.32}
    return {"Routine Hub A": 0.62, "Routine Hub B": 0.38}


def _risk_event_count(
    disposition: Mapping[str, Any],
    evaluation_month: int | None,
    visit_label: str,
    rng: random.Random,
) -> int:
    """Per-visit risky-event count. Risk emerges from the disposition only."""

    change = disposition.get("change")
    locus = disposition["risk_locus"]
    rate = float(disposition["risk_rate"])
    # Safe mobility change = negative control: the driving context moves but the
    # behaviour never worsens, so risk stays at zero and Care can never fire.
    if change == "mobility":
        return 0
    # Persistent in-zone risky behaviour (급감속·과속 반복): high AND stable over
    # time, so safety scores stay low (→ neutral) but the risk-CHANGE gate never
    # fires. Applies wherever the driver goes.
    if locus == "in_zone":
        # Probabilistic (see _profile_risk_event_count): keeps risk high AND stable
        # but lets per-person risk_rate produce varied, realistic event counts.
        return int(rng.random() < rate) + int(rng.random() < rate * 0.35)
    # Co-change: from evaluation month 8 the risk concentrates on the new/outer
    # night route, so out-zone safety drops while in-zone stays clean.
    if locus == "outer" and change == "cochange" and evaluation_month is not None and evaluation_month >= 8:
        if visit_label == "New Hub":
            return 1 + int(rng.random() < 0.55)
        return int(rng.random() < 0.03)
    # Low, stable baseline risk everywhere else.
    return int(rng.random() < rate)


def _trip_distance_km(
    disposition: Mapping[str, Any],
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
    # Wider-ranging dispositions rack up more odometer km per trip.
    if max(float(frac) for frac in disposition["in_zone_reach_frac"]) >= 0.8:
        multiplier *= 1.2
    # Per-person odometer scale so same-archetype drivers differ in mileage.
    multiplier *= float(disposition.get("trip_distance_scale", 1.0))
    return round(float(environment["base_trip_distance_km"]) * multiplier * rng.uniform(0.84, 1.18), 2)


def _visit_date(month: str, visit_index: int, driver_sequence: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    day = 2 + ((visit_index * 3 + driver_sequence * 2) % 25)
    return date(year, month_number, day).isoformat()


def _generate_visits_for_driver(driver: Mapping[str, Any], seed: int) -> list[dict[str, Any]]:
    # Option C: when an agent mobility profile exists for this person, expand it
    # (named zones, per-person change month) into visit events; otherwise fall
    # back to the parametric generator so the engine still runs without a cache.
    profile = _profile_for_driver(driver)
    if profile is not None and profile.get("zones"):
        return _generate_visits_from_profile(driver, profile, seed)
    environment_id = str(driver["environment_id"])
    designed_type = str(driver["designed_type"])
    disposition = driver["disposition"]
    data_quality = str(disposition.get("data_quality", "good"))
    sparse = data_quality == "sparse"
    environment = ENVIRONMENTS[environment_id]
    centers = _hub_centers(driver)
    # Sparse-evidence drivers run seldom, so the record is thin: fewer visits and
    # a naturally low data-coverage band that lands 보류 via the coverage<80 hold.
    base_visits = int(disposition["monthly_visits"]) - (3 if sparse else 0)
    minimum_visits = 3 if sparse else 5
    events: list[dict[str, Any]] = []

    for month in ALL_MONTHS:
        evaluation_month = _evaluation_month_number(month)
        period_role = _period_role(month)
        rng = random.Random(_stable_seed(seed, driver["driver_id"], month))
        visit_count = max(minimum_visits, base_visits + rng.choice((-1, 0, 0, 1)))
        weights = _month_visit_weights(disposition, evaluation_month)
        for visit_index in range(visit_count):
            visit_label = _choose_weighted(rng, weights)
            center_lat, center_lon = centers[visit_label]
            radius = rng.uniform(0.15, 1.0) * float(environment["visit_jitter_m"])
            latitude, longitude = _offset_coordinate(center_lat, center_lon, radius, rng.uniform(0, 360))
            trip_id = f"{driver['driver_id']}-{month.replace('-', '')}-{visit_index + 1:02d}"
            risk_event_count = _risk_event_count(disposition, evaluation_month, visit_label, rng)
            visit_date = _visit_date(month, visit_index, int(driver["persona_sequence"]))
            data_coverage_pct = (
                round(60.0 + rng.random() * 12.0, 1)
                if sparse
                else round(95.0 + rng.random() * 5.0, 1)
            )
            events.append(
                {
                    "trip_id": trip_id,
                    "visit_event_id": f"visit-{trip_id}",
                    "driver_id": driver["driver_id"],
                    "designed_type": designed_type,
                    "environment_id": environment_id,
                    "dataset_partition": driver["dataset_partition"],
                    "data_quality": data_quality,
                    "month": month,
                    "period_role": period_role,
                    "visit_date": visit_date,
                    "visit_label": visit_label,
                    "latitude": round(latitude, 6),
                    "longitude": round(longitude, 6),
                    "trip_distance_km": _trip_distance_km(disposition, environment_id, visit_label, rng),
                    "risk_event_count": risk_event_count,
                    "data_coverage_pct": data_coverage_pct,
                    "source_status": "simulated",
                }
            )
    return events


# ---------------------------------------------------------------------------
# Option C — agent mobility profiles (offline, cached). An LLM agent reasons out
# each senior's named living zones + per-person change month; this engine expands
# that profile into seeded visit events and then scores them BLIND, exactly like
# the parametric path. Risk *magnitude* stays keyed to the archetype disposition
# (the experimental control); the profile owns the spatial/temporal/naming layer.
# ---------------------------------------------------------------------------
_MOBILITY_PROFILES_CACHE: dict[str, dict[str, Any]] | None = None
# Post-change weight for a change destination — strong enough that the out-of-zone
# share reliably crosses the mobility-change threshold (mirrors the parametric
# generator's shift), so the archetype's change contract holds regardless of the
# agent's per-zone share. Kept in one place for auditability.
_PROFILE_CHANGE_DEST_WEIGHT = 0.52
_PROFILE_SECONDARY_MIN_WEIGHT = 0.30  # ensure a genuine 2nd living zone clusters


def _mobility_profiles() -> dict[str, dict[str, Any]]:
    """Load (once) the committed agent mobility-profile cache, keyed by person_id."""

    global _MOBILITY_PROFILES_CACHE
    if _MOBILITY_PROFILES_CACHE is not None:
        return _MOBILITY_PROFILES_CACHE
    if os.environ.get("MOBILITY_PROFILES_DISABLED"):
        _MOBILITY_PROFILES_CACHE = {}
        return _MOBILITY_PROFILES_CACHE
    override = os.environ.get("MOBILITY_PROFILES_PATH")
    path = Path(override) if override else Path(__file__).resolve().parents[2] / "data" / "fixtures" / "mobility_profiles.json"
    profiles: dict[str, dict[str, Any]] = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("profiles", []):
            profiles[str(row["person_id"])] = row
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        profiles = {}
    _MOBILITY_PROFILES_CACHE = profiles
    return profiles


def _profile_for_driver(driver: Mapping[str, Any]) -> dict[str, Any] | None:
    return _mobility_profiles().get(str(driver.get("person_id", "")))


def _profile_home_anchor(driver: Mapping[str, Any]) -> tuple[float, float]:
    """Same golden-angle residence anchor as ``_hub_centers`` (kept consistent so
    the summary's home_center matches the profile-placed visits)."""

    environment = ENVIRONMENTS[str(driver["environment_id"])]
    sequence = int(driver["persona_sequence"])
    return _offset_coordinate(
        float(environment["base_latitude"]),
        float(environment["base_longitude"]),
        50_000.0 + 1_700.0 * sequence,
        (137.508 * sequence) % 360.0,
    )


def _band_straight_line_m(
    environment: Mapping[str, Any], band: str, disposition: Mapping[str, Any] | None = None
) -> float:
    """Straight-line distance from home to a destination band (metres).

    ONE source of truth for a band's distance: the map coordinate AND the logged
    trip distance both derive from this, so a nearby destination can never be
    placed 300 m away yet logged as a 6 km drive. In-zone destinations sit close
    to home (tight, legible living zone); a secondary zone is a genuinely separate
    cluster; an outer destination is out of zone. Wide-ranging drivers get a wider
    in-zone reach (their living zone genuinely spans more ground).
    """

    reach = float(environment["zone_reach_m"])
    outer = float(environment["outer_distance_m"])
    # ONLY genuinely wide-area drivers widen their living zone; others stay tight
    # so their in-zone stops never drift past the home buffer (which would inflate
    # the baseline out-of-zone share and suppress the mobility-change signal).
    reach_scale = 1.0
    if disposition is not None:
        max_frac = max(float(f) for f in disposition["in_zone_reach_frac"])
        reach_scale = 1.0 + max(0.0, max_frac - 0.82) * 3.5  # <=0.82 -> 1.0; 0.95 -> ~1.46
    return {
        "near": reach * 0.24 * reach_scale,
        "mid_in": reach * 0.52 * reach_scale,
        "secondary": outer * 0.5,   # beyond the home buffer → its own cluster
        "outer": outer,             # genuinely out of zone
    }.get(band, reach * 0.4)


def _profile_band_center(
    home_lat: float,
    home_lon: float,
    environment: Mapping[str, Any],
    band: str,
    bearing_deg: float,
    disposition: Mapping[str, Any] | None = None,
) -> tuple[float, float]:
    return _offset_coordinate(
        home_lat, home_lon, _band_straight_line_m(environment, band, disposition), bearing_deg
    )


def _profile_destinations(driver: Mapping[str, Any], profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    environment = ENVIRONMENTS[str(driver["environment_id"])]
    home_lat, home_lon = _profile_home_anchor(driver)
    dests: list[dict[str, Any]] = []
    in_zone_seen = 0
    for index, zone in enumerate(profile["zones"]):
        role = str(zone["role"])
        # Distance band is contract-critical geometry, so it is derived from the
        # role (not left to the agent): a change destination must sit out of zone
        # so mobility-change fires, a secondary must sit far enough to form its own
        # cluster, and an in-zone destination stays inside the home living zone.
        agent_band = str(zone["distance_band"])
        if role == "change_destination":
            band = "outer"
        elif role == "secondary":
            band = "secondary"
        else:
            band = agent_band if agent_band in ("near", "mid_in") else "near"
        center = _profile_band_center(
            home_lat, home_lon, environment, band, float(zone["bearing_deg"]), driver["disposition"]
        )
        # Keep the raw event's visit_label in the generic vocabulary so the event
        # schema is unchanged; role drives risk/distance, the agent label is shown
        # from the profile at display time.
        if role == "change_destination" or role == "secondary":
            visit_label = "New Hub"
        else:
            visit_label = "Routine Hub A" if in_zone_seen == 0 else "Routine Hub B"
            in_zone_seen += 1
        dests.append(
            {
                "key": f"z{index}",
                "center": center,
                "role": role,
                "band": band,
                "visit_label": visit_label,
                "visit_share": float(zone["visit_share"]),
                "active_from": int(zone["active_from_month"]),
                "active_to": int(zone["active_to_month"]),
            }
        )
    return dests


def _profile_month_weights(active: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Weights over the month's active destinations.

    A change destination that is active (i.e. we are at/after change_month) takes
    a strong fixed share so mobility-change fires reliably; secondary zones are
    floored so they cluster into a real second living zone; the rest of the mass
    follows the agent's per-zone shares.
    """

    def _fixed_share_split(anchors: Sequence[Mapping[str, Any]], anchor_total: float) -> dict[str, float]:
        # Give the contract-critical anchors (change destination / secondary zone)
        # a GUARANTEED combined share so they reliably form their own cluster, then
        # distribute the remaining mass over the other destinations by agent share.
        weights: dict[str, float] = {}
        per = anchor_total / len(anchors)
        for dest in anchors:
            weights[dest["key"]] = per
        others = [d for d in active if d["key"] not in weights]
        remaining = max(0.0, 1.0 - anchor_total)
        share_sum = sum(max(0.05, float(d["visit_share"])) for d in others) or 1.0
        for dest in others:
            weights[dest["key"]] = remaining * max(0.05, float(dest["visit_share"])) / share_sum
        return weights

    change_dests = [d for d in active if d["role"] == "change_destination"]
    if change_dests:
        return _fixed_share_split(change_dests, _PROFILE_CHANGE_DEST_WEIGHT)
    secondaries = [d for d in active if d["role"] == "secondary"]
    if secondaries:
        # 0.32 per secondary (capped) — enough baseline visits to cross the
        # 3-distinct-day cluster support, matching the parametric secondary share.
        return _fixed_share_split(secondaries, min(0.58, _PROFILE_SECONDARY_MIN_WEIGHT * len(secondaries)))
    weights: dict[str, float] = {dest["key"]: max(0.05, float(dest["visit_share"])) for dest in active}
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _profile_risk_event_count(
    disposition: Mapping[str, Any],
    dest: Mapping[str, Any],
    all_month_num: int,
    change_month: int | None,
    rng: random.Random,
) -> int:
    """Per-visit risky-event count — same archetype logic as the parametric path,
    but keyed to the destination role and the person's own change month."""

    change = disposition.get("change")
    locus = disposition["risk_locus"]
    rate = float(disposition["risk_rate"])
    if change == "mobility":
        return 0  # safe mobility change = negative control (risk never rises)
    if locus == "in_zone":
        # Persistent in-zone risky behaviour, but PROBABILISTIC per visit so the
        # per-person risk_rate variation produces varied monthly event counts and
        # safety scores (instead of a guaranteed >=1 that pins every case to the
        # 18-point floor). Rate stays high enough to keep these drivers neutral.
        return int(rng.random() < rate) + int(rng.random() < rate * 0.35)
    if (
        locus == "outer"
        and change == "cochange"
        and change_month is not None
        and all_month_num >= change_month
    ):
        if dest["role"] == "change_destination":
            return 1 + int(rng.random() < 0.55)  # risk concentrates on the new route
        return int(rng.random() < 0.03)
    return int(rng.random() < rate)  # low, stable baseline everywhere else


def _profile_trip_distance_km(
    disposition: Mapping[str, Any], environment_id: str, dest: Mapping[str, Any], rng: random.Random
) -> float:
    """Odometer km for one visit, DERIVED FROM the destination's actual distance.

    A trip is home -> destination -> home (round trip) over real roads (not a
    straight line), plus a little local wandering (parking, an errand nearby). So
    a nearby stop is a short drive and a far stop is a long drive — the logged
    distance is now coherent with where the person actually goes on the map.
    """

    environment = ENVIRONMENTS[environment_id]
    straight_km = _band_straight_line_m(environment, str(dest["band"]), disposition) / 1000.0
    road_factor = rng.uniform(1.3, 1.6)            # roads are not straight lines
    local_wander_km = rng.uniform(0.6, 2.2)        # parking / a nearby errand / getting to a main road
    km = 2.0 * straight_km * road_factor + local_wander_km
    # wider-ranging drivers cover a bit more ground per trip
    if max(float(frac) for frac in disposition["in_zone_reach_frac"]) >= 0.8:
        km *= 1.2
    km *= float(disposition.get("trip_distance_scale", 1.0))
    return round(max(0.3, km), 2)


def _generate_visits_from_profile(
    driver: Mapping[str, Any], profile: Mapping[str, Any], seed: int
) -> list[dict[str, Any]]:
    environment_id = str(driver["environment_id"])
    designed_type = str(driver["designed_type"])
    disposition = driver["disposition"]
    data_quality = str(disposition.get("data_quality", "good"))
    sparse = data_quality == "sparse"
    environment = ENVIRONMENTS[environment_id]
    dests = _profile_destinations(driver, profile)
    change_month = profile.get("change_month")
    change_month = int(change_month) if isinstance(change_month, (int, float)) else None
    base_visits = int(disposition["monthly_visits"]) - (3 if sparse else 0)
    minimum_visits = 3 if sparse else 5
    events: list[dict[str, Any]] = []

    for month_index, month in enumerate(ALL_MONTHS):
        all_month_num = month_index + 1  # 1-2 baseline, 3-14 evaluation
        period_role = _period_role(month)
        rng = random.Random(_stable_seed(seed, driver["driver_id"], month))
        visit_count = max(minimum_visits, base_visits + rng.choice((-1, 0, 0, 1)))
        active = [d for d in dests if d["active_from"] <= all_month_num <= d["active_to"]]
        if not active:
            active = [d for d in dests if d["role"] != "change_destination"] or list(dests)
        weights = _profile_month_weights(active)
        by_key = {d["key"]: d for d in active}
        for visit_index in range(visit_count):
            dest = by_key[_choose_weighted(rng, weights)]
            center_lat, center_lon = dest["center"]
            radius = rng.uniform(0.15, 1.0) * float(environment["visit_jitter_m"])
            latitude, longitude = _offset_coordinate(center_lat, center_lon, radius, rng.uniform(0, 360))
            trip_id = f"{driver['driver_id']}-{month.replace('-', '')}-{visit_index + 1:02d}"
            risk_event_count = _profile_risk_event_count(disposition, dest, all_month_num, change_month, rng)
            visit_date = _visit_date(month, visit_index, int(driver["persona_sequence"]))
            data_coverage_pct = (
                round(60.0 + rng.random() * 12.0, 1)
                if sparse
                else round(95.0 + rng.random() * 5.0, 1)
            )
            events.append(
                {
                    "trip_id": trip_id,
                    "visit_event_id": f"visit-{trip_id}",
                    "driver_id": driver["driver_id"],
                    "designed_type": designed_type,
                    "environment_id": environment_id,
                    "dataset_partition": driver["dataset_partition"],
                    "data_quality": data_quality,
                    "month": month,
                    "period_role": period_role,
                    "visit_date": visit_date,
                    "visit_label": dest["visit_label"],
                    "latitude": round(latitude, 6),
                    "longitude": round(longitude, 6),
                    "trip_distance_km": _profile_trip_distance_km(disposition, environment_id, dest, rng),
                    "risk_event_count": risk_event_count,
                    "data_coverage_pct": data_coverage_pct,
                    "source_status": "simulated",
                }
            )
    return events


def _public_mobility_profile(profile: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """UI-safe view of the agent mobility profile: reasoning + named zones (no
    coordinates — only bearing/role/band descriptors — so no residence location
    can be reconstructed)."""

    if not profile:
        return None
    zones = [
        {
            "label_ko": zone.get("label_ko"),
            "label_en": zone.get("label_en", zone.get("label_ko")),
            "kind": zone.get("kind"),
            "role": zone.get("role"),
            "bearing_deg": zone.get("bearing_deg"),
            "distance_band": zone.get("distance_band"),
            "visit_share": zone.get("visit_share"),
            "active_from_month": zone.get("active_from_month"),
            "active_to_month": zone.get("active_to_month"),
        }
        for zone in profile.get("zones", [])
    ]
    reasoning_ko = str(profile.get("reasoning_ko", ""))
    return {
        "reasoning_ko": reasoning_ko,
        "reasoning_en": str(profile.get("reasoning_en", "") or reasoning_ko),
        "home_label_ko": profile.get("home_label_ko"),
        "home_label_en": profile.get("home_label_en"),
        "change_month": profile.get("change_month"),
        "change_trigger_ko": profile.get("change_trigger_ko"),
        "change_trigger_en": profile.get("change_trigger_en"),
        "zones": zones,
        "generator": "openai_agent_offline_cached",
    }


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
    # Bounded penalty: a clean month sits near 100, a persistently risky month
    # lands ~18-30 (clearly below the reward line without collapsing to a bare 0
    # that reads as "broken" on screen). The 18-point floor keeps a risky score
    # legible while still letting an in-zone-risky driver fall out of the reward
    # tier on the integrated score.
    return round(max(18.0, 100.0 - min(82.0, rate_per_100_km * 3.4)), 2)


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
    annual_care_state: str = "none",
    candidate_score: float | None = None,
    product_rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a Korea mileage reference with a non-binding Masil candidate.

    The proposed rate keeps the Korea mileage discount as its base and only moves
    it for a documented reason: a reward bonus that *scales with the integrated
    safety score* (so a 95-point driver earns visibly more than a borderline
    75-point one), or a preventive-care reduction when the same-month mobility+risk
    co-change gate fires (discount-leakage prevention, not an age surcharge).
    Neutral cases are left unchanged, so the two formulas agree unless there is
    evidence to differ.
    """

    rules = product_rules or DEFAULT_PRODUCT_RULES
    lookup = lookup_existing_mileage_discount(annual_distance_km, vehicle_class)
    korea_rate = float(lookup.discount_rate_pct)
    care_review = annual_care_state == "care_review"
    bonus = 0.0
    if annual_reward_state == "reward" and not care_review:
        bonus_max = float(rules["reward_bonus_discount_rate_pct"])
        bonus_floor = float(rules.get("reward_bonus_floor_pct", 1.0))
        threshold = float(rules["reward_threshold"])
        span = max(1.0, 100.0 - threshold)
        # Score-proportional bonus: floor at the reward threshold, max at 100.
        score_frac = 1.0 if candidate_score is None else max(0.0, min(1.0, (float(candidate_score) - threshold) / span))
        bonus = round(bonus_floor + score_frac * (bonus_max - bonus_floor), 2)
    reduction = float(rules.get("care_discount_reduction_pct", 0.0)) if care_review else 0.0
    masil_rate = korea_rate + bonus - reduction
    masil_rate = max(0.0, min(float(rules["candidate_discount_cap_pct"]), masil_rate))
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
        "candidate_care_reduction_rate_pct": round(reduction, 2),
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
        # Per-destination (visit_label) aggregates from the REAL events, so the UI can
        # show where the km and risky events actually occurred instead of splitting the
        # monthly totals evenly across destinations. This keeps risk on the destination
        # that produced it (e.g. a co-change person's night outer route), not smeared
        # onto in-zone hubs.
        breakdown: dict[str, dict[str, Any]] = {}
        for row in rows:
            label = str(row["visit_label"])
            zone = located[str(row["visit_event_id"])]["zone"]
            entry = breakdown.setdefault(
                label,
                {"visit_label": label, "trip_count": 0, "distance_km": 0.0,
                 "risk_event_count": 0, "in_zone_count": 0, "out_zone_count": 0},
            )
            entry["trip_count"] += 1
            entry["distance_km"] += float(row["trip_distance_km"])
            entry["risk_event_count"] += int(row["risk_event_count"])
            if zone in {"core", "buffer"}:
                entry["in_zone_count"] += 1
            else:
                entry["out_zone_count"] += 1
        destination_breakdown = []
        for entry in sorted(breakdown.values(), key=lambda item: (-item["trip_count"], item["visit_label"])):
            entry["distance_km"] = round(entry["distance_km"], 2)
            entry["is_outer"] = entry["out_zone_count"] > entry["in_zone_count"]
            destination_breakdown.append(entry)
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
            "destination_breakdown": destination_breakdown,
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
    home_center = _hub_centers(driver)["__home__"]
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
        home_zone_reach_m=float(environment["zone_reach_m"]) * _HOME_ZONE_REACH_FACTOR,
        home_center=home_center,
    )
    home_label_ko = HOME_ZONE_LABEL_KO
    secondary_label_ko = _secondary_zone_label_ko(driver)
    new_hub_label_ko = _new_hub_label_ko(driver)
    public_hubs = [
        {
            **{
                key: value
                for key, value in hub.items()
                if key not in {"centroid", "source_cluster_id"}
            },
            "display_label_ko": home_label_ko if str(hub["display_label"]) == "Routine Hub A" else secondary_label_ko,
        }
        for hub in hubs
    ]
    monthly = _monthly_results(driver, events, hubs, product_rules)
    evaluation = [result for result in monthly if result["period_role"] == "evaluation"]
    annual_reward, annual_care = _annual_state(monthly, product_rules)
    annual_distance = sum(float(result["total_distance_km"]) for result in evaluation)
    scored_months = [
        float(result["integrated_score"])
        for result in evaluation
        if result.get("integrated_score") is not None
    ]
    annual_candidate_score = round(sum(scored_months) / len(scored_months), 2) if scored_months else None
    tariff = pricing_sandbox(
        base_premium_krw=int(driver["base_premium_krw"]),
        annual_distance_km=annual_distance,
        vehicle_class=str(driver["vehicle_class"]),
        annual_reward_state=annual_reward,
        annual_care_state=annual_care,
        candidate_score=annual_candidate_score,
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
        "mobility_profile": _public_mobility_profile(_profile_for_driver(driver)),
        "mobility": {
            "zone_status": "available" if hubs else "insufficient",
            "algorithm": "DBSCAN",
            "distance_metric": "haversine_m",
            "eps_m": float(environment["dbscan_eps_m"]),
            "min_distinct_days": 3,
            "repeated_hub_count": len(hubs),
            "routine_hubs": public_hubs,
            "new_hub_label_ko": new_hub_label_ko,
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
        designed_type = str(driver["designed_type"])
        if designed_type in seen:
            continue
        seen.add(designed_type)
        for month in ("2026-07", "2026-10"):
            result = next(row for row in driver["monthly_results"] if row["month"] == month)
            selected.append(
                {
                    "driver_id": driver["driver_id"],
                    "designed_type": designed_type,
                    "archetype_id": driver["archetype_id"],
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
            "archetype_counts": dict(sorted(Counter(driver["archetype_id"] for driver in subset).items())),
            "designed_type_counts": dict(sorted(Counter(driver["designed_type"] for driver in subset).items())),
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


def _share(subset: Sequence[Mapping[str, Any]], predicate) -> float:
    """Fraction of a driver subset satisfying ``predicate`` (0.0 if empty)."""
    if not subset:
        return 0.0
    return sum(1 for driver in subset if predicate(driver)) / len(subset)


def _validation_results(
    drivers: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    product_rules: Mapping[str, Any],
) -> dict[str, Any]:
    archetype_counts = Counter(str(driver["archetype_id"]) for driver in drivers)
    designed_type_counts = Counter(str(driver["designed_type"]) for driver in drivers)
    environment_counts = Counter(str(driver["environment_id"]) for driver in drivers)
    partition_counts = Counter(str(driver["dataset_partition"]) for driver in drivers)
    by_designed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for driver in drivers:
        by_designed[str(driver["designed_type"])].append(driver)
    sparse_drivers = [driver for driver in drivers if str(driver["data_quality"]) == "sparse"]
    partitions = ("development", "validation", "holdout")
    environment_ids = list(ENVIRONMENTS)

    # Each of the 60 people is run in every environment, so each environment holds
    # exactly ROSTER_SIZE cases; partitions are assigned per person (all 3 of a
    # person's cases share a partition).
    def _expected_environment_counts() -> Counter:
        return Counter({env: personas.ROSTER_SIZE for env in ENVIRONMENTS})

    def _expected_partition_counts() -> Counter:
        counts: Counter = Counter()
        for person_index in range(personas.ROSTER_SIZE):
            counts[_partition_for_instance(person_index)] += personas.ENVIRONMENTS_PER_PERSON
        return counts

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
            "result_status": "passed"
            if len(drivers) == personas.COHORT_SIZE
            and len({str(driver["person_id"]) for driver in drivers}) == personas.ROSTER_SIZE
            and len(archetype_counts) == len(personas.ARCHETYPES)
            and all(
                archetype_counts.get(str(archetype["id"]), 0)
                == int(personas.PERSONS_PER_ARCHETYPE.get(str(archetype["id"]), 0))
                * personas.ENVIRONMENTS_PER_PERSON
                for archetype in personas.ARCHETYPES
            )
            else "failed",
            "evidence": {
                "case_count": len(drivers),
                "person_count": len({str(driver["person_id"]) for driver in drivers}),
                "archetype_count": len(archetype_counts),
                "designed_type_counts": dict(sorted(designed_type_counts.items())),
            },
        },
        {
            "check_id": "environment_balance",
            "result_status": "passed"
            if environment_counts == _expected_environment_counts()
            and len(environment_counts) == len(ENVIRONMENTS)
            else "failed",
            "evidence": dict(sorted(environment_counts.items())),
        },
        {
            "check_id": "deterministic_partition_shape",
            "result_status": "passed"
            if partition_counts == _expected_partition_counts()
            and sum(partition_counts.values()) == personas.COHORT_SIZE
            else "failed",
            "evidence": dict(sorted(partition_counts.items())),
        },
        {
            "check_id": "partition_stratification",
            "result_status": "passed"
            if all(partition_counts.get(partition, 0) > 0 for partition in partitions)
            and all(
                set(
                    driver["environment_id"]
                    for driver in drivers
                    if driver["dataset_partition"] == partition
                )
                == set(environment_ids)
                for partition in partitions
            )
            and set(
                driver["designed_type"]
                for driver in drivers
                if driver["dataset_partition"] == "development"
            )
            == set(designed_type_counts)
            else "failed",
            "evidence": {
                partition: {
                    "driver_count": partition_counts.get(partition, 0),
                    "designed_type_counts": dict(
                        sorted(
                            Counter(
                                driver["designed_type"]
                                for driver in drivers
                                if driver["dataset_partition"] == partition
                            ).items()
                        )
                    ),
                    "environment_counts": dict(
                        sorted(
                            Counter(
                                driver["environment_id"]
                                for driver in drivers
                                if driver["dataset_partition"] == partition
                            ).items()
                        )
                    ),
                }
                for partition in partitions
            },
        },
        {
            "check_id": "fourteen_months_per_driver",
            "result_status": "passed" if all(months == set(ALL_MONTHS) for months in months_by_driver.values()) else "failed",
            "evidence": {"expected_month_count": 14, "drivers_checked": len(months_by_driver)},
        },
        {
            "check_id": "sparse_evidence_reaches_hold",
            "result_status": "passed"
            if sparse_drivers
            and all(
                float(driver["data_coverage_pct"]) < float(product_rules["min_data_coverage_pct"])
                and driver["annual_reward_state"] == "hold"
                and driver["annual_care_state"] == "hold"
                for driver in sparse_drivers
            )
            else "failed",
            "evidence": {
                "sparse_driver_ids": [driver["driver_id"] for driver in sparse_drivers],
                "policy": "low_data_coverage_holds_without_customer_disadvantage",
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
            "check_id": "mobility_change_safe_is_care_negative_control",
            "result_status": "passed"
            if by_designed["mobility_change_safe"]
            and all(
                float(row["risky_behavior_change_index"]) == 0.0
                and float(row["pattern_stability_score"]) == 100.0
                for driver in by_designed["mobility_change_safe"]
                for row in driver["monthly_results"]
                if row["period_role"] == "evaluation"
            )
            and all(
                driver["annual_care_state"] == "none"
                for driver in by_designed["mobility_change_safe"]
            )
            else "failed",
            "evidence": {
                "designed_type": "mobility_change_safe",
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
            "check_id": "designed_type_behavior_contract",
            # This is a synthetic SIMULATION, so outcomes emerge with variance —
            # we verify the DESIGN PREDICTS the tier (a strong dominant tendency),
            # not that every instance lands identically. A designed_type passes on
            # its majority tendency plus the hard safety invariants that must never
            # break (safe archetypes never systematically flagged for care; the
            # negative-control mobility_change_safe never triggers care; the
            # cochange archetype reliably reaches care review).
            "result_status": "passed"
            if _share(by_designed["stable_reward"], lambda d: d["annual_reward_state"] == "reward") >= 0.8
            and _share(by_designed["stable_reward"], lambda d: d["annual_care_state"] == "care_review") <= 0.1
            and _share(by_designed["in_zone_risky"], lambda d: d["annual_reward_state"] == "neutral") >= 0.5
            and _share(by_designed["in_zone_risky"], lambda d: d["annual_care_state"] == "care_review") <= 0.1
            and _share(by_designed["mobility_change_safe"], lambda d: d["annual_care_state"] == "none") >= 0.9
            and _share(by_designed["mobility_risk_cochange"], lambda d: d["annual_care_state"] == "care_review") >= 0.8
            and _share(by_designed["multi_zone"], lambda d: int(d["mobility"]["repeated_hub_count"]) >= 2) >= 0.6
            and _share(by_designed["multi_zone"], lambda d: d["annual_care_state"] == "care_review") <= 0.1
            and _share(by_designed["wide_area_safe"], lambda d: d["annual_reward_state"] == "reward") >= 0.8
            and _share(by_designed["wide_area_safe"], lambda d: d["annual_care_state"] == "care_review") <= 0.1
            # Sparse telematics is an individual-level trait (not a behaviour type):
            # those drivers should mostly abstain (hold), not be penalised.
            and _share(sparse_drivers, lambda d: d["annual_reward_state"] == "hold") >= 0.5
            else "failed",
            "evidence": {
                designed_type: {
                    "reward_states": dict(
                        Counter(driver["annual_reward_state"] for driver in subset)
                    ),
                    "care_states": dict(
                        Counter(driver["annual_care_state"] for driver in subset)
                    ),
                    "zone_counts": dict(
                        sorted(
                            Counter(
                                str(int(driver["mobility"]["repeated_hub_count"])) for driver in subset
                            ).items()
                        )
                    ),
                }
                for designed_type, subset in sorted(by_designed.items())
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

    archetype_counts = Counter(driver["archetype_id"] for driver in driver_summaries)
    designed_type_counts = Counter(driver["designed_type"] for driver in driver_summaries)
    environment_counts = Counter(driver["environment_id"] for driver in driver_summaries)
    partition_counts = Counter(driver["dataset_partition"] for driver in driver_summaries)
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
            "persona_count": len(personas.ARCHETYPES),
            "archetype_count": len(personas.ARCHETYPES),
            "designed_type_count": len(personas.DESIGNED_TYPES),
            "persona_counts": dict(sorted(archetype_counts.items())),
            "designed_type_counts": dict(sorted(designed_type_counts.items())),
            "environment_counts": dict(environment_counts),
            "partition_counts": dict(partition_counts),
            "partition_contract": {
                **{partition: partition_counts.get(partition, 0) for partition in ("development", "validation", "holdout")},
                "split_rule": "per_archetype_instance_index_mod_5_dev_dev_dev_val_holdout",
                "purpose": "Report robustness by untouched synthetic partitions; no partition is claimed as real-world evidence.",
            },
            "allocation_rule": (
                "The 60-person roster is run in each of 3 environments (60 x 3 = 180 cases); "
                "round-robin across the three environments; instances split ~3:1:1 dev:val:holdout."
            ),
            "personas": [
                {
                    "persona_type": str(archetype["id"]),
                    "archetype_id": str(archetype["id"]),
                    "designed_type": str(archetype["designed_type"]),
                    "display_name_ko": str(archetype["name_ko"]),
                    "summary_ko": str(archetype["life_context_ko"]),
                    "driver_count": archetype_counts.get(str(archetype["id"]), 0),
                }
                for archetype in personas.ARCHETYPES
            ],
            "designed_types": [
                {"designed_type": key, "label_ko": value}
                for key, value in personas.DESIGNED_TYPES.items()
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

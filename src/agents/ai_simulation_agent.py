"""Deterministic AI Simulation Agent for senior-driver trip fixtures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from src.agents.contracts import (
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentStatus,
    ArtifactType,
    utc_now_iso,
)
from src.agents.persona_agent import CustomerDrivingPattern, CustomerIdentity, PersonaAgent


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRIP_OUTPUT = ROOT / "data" / "fixtures" / "senior_trip_logs.csv"
DEFAULT_MANIFEST_OUTPUT = ROOT / "data" / "fixtures" / "simulation_manifest.json"
DEFAULT_START_DATE = date(2026, 1, 1)
SCHEMA_VERSION = "senior-trip-log-fixture/v1"

TRIP_FIELDS = [
    "customer_id",
    "driver_id",
    "persona_type",
    "scenario_id",
    "simulation_seed",
    "observation_period",
    "observation_day_index",
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
    "reduced_activity_signal",
    "fatigue_indicator",
    "risk_signal_codes",
    "persona_risk_annotation",
    "synthetic_risk_tag",
]

TIME_WINDOWS = {
    "morning": (8, 11),
    "afternoon": (12, 16),
    "evening": (17, 20),
    "night": (22, 23),
}

RISK_EVENT_COLUMNS = {
    "speeding": "speeding_count",
    "harsh_accel": "harsh_accel_count",
    "harsh_brake": "harsh_brake_count",
    "sharp_turn": "sharp_turn_count",
}

RISK_SIGNAL_FIELDS = (
    "night_driving_signal",
    "sudden_braking_signal",
    "route_deviation_signal",
    "reduced_activity_signal",
    "fatigue_indicator",
)

EVENT_COUNT_FIELDS = tuple(RISK_EVENT_COLUMNS.values())


@dataclass(frozen=True)
class GeneratedFixture:
    rows: list[dict[str, Any]]
    manifest: dict[str, Any]


def stable_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    threshold = rng.random()
    cumulative = 0.0
    last_key = next(iter(weights))
    for key, weight in weights.items():
        cumulative += float(weight)
        last_key = key
        if threshold <= cumulative:
            return key
    return last_key


def allocate_counts(total: int, weights: dict[str, float]) -> list[str]:
    raw = {key: total * float(weight) for key, weight in weights.items()}
    counts = {key: int(value) for key, value in raw.items()}
    remainder = total - sum(counts.values())
    ranked = sorted(raw, key=lambda key: (raw[key] - counts[key], key), reverse=True)
    for key in ranked[:remainder]:
        counts[key] += 1
    labels: list[str] = []
    for key in weights:
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


def in_synthetic_coordinate_range(point: tuple[float, float]) -> bool:
    return 126.70 <= point[0] <= 127.30 and 37.35 <= point[1] <= 37.75


def bounded_offset_coordinate(
    center_x: float,
    center_y: float,
    meters: float,
    angle_degrees: float,
    rng: random.Random,
) -> tuple[float, float]:
    point = offset_coordinate(center_x, center_y, meters, angle_degrees)
    if in_synthetic_coordinate_range(point):
        return point
    for _ in range(24):
        point = offset_coordinate(center_x, center_y, meters, rng.uniform(0, 360))
        if in_synthetic_coordinate_range(point):
            return point
    return (
        min(127.30, max(126.70, point[0])),
        min(37.75, max(37.35, point[1])),
    )


def zone_radius_m(zone_label: str, rng: random.Random, jitter_m: float, route_variability: str) -> float:
    variability_multiplier = {"low": 0.85, "medium": 1.0, "high": 1.2}[route_variability]
    if zone_label == "core":
        return rng.uniform(80, min(450, max(120, jitter_m))) * variability_multiplier
    if zone_label == "buffer":
        return rng.uniform(650, 1_650) * variability_multiplier
    return rng.uniform(5_500, 18_000) * variability_multiplier


def choose_day_indices(period: str, trip_count: int, rng: random.Random) -> list[int]:
    start_day, day_count = (1, 60) if period == "baseline" else (61, 30)
    end_day = start_day + day_count - 1
    if trip_count < 2:
        return [start_day]

    spacing = day_count / trip_count
    indices: list[int] = []
    for index in range(trip_count):
        base = start_day + int(index * spacing)
        jitter = rng.choice([-1, 0, 0, 1])
        day_index = max(start_day, min(end_day, base + jitter))
        indices.append(day_index)

    indices[0] = start_day
    indices[-1] = end_day

    used: set[int] = set()
    normalized: list[int] = []
    for index, day_index in enumerate(indices):
        if index == len(indices) - 1:
            normalized.append(end_day)
            used.add(end_day)
            continue
        day_index = min(day_index, end_day - 1)
        while day_index in used and day_index < end_day - 1:
            day_index += 1
        used.add(day_index)
        normalized.append(day_index)
    return sorted(normalized)


def build_event_plan(
    total_distance: float,
    target_rate_per_100km: float,
    event_mix: dict[str, float],
    trip_count: int,
    rng: random.Random,
) -> list[dict[str, int]]:
    target_events = int(round(total_distance * target_rate_per_100km / 100))
    rows = [{column: 0 for column in RISK_EVENT_COLUMNS.values()} for _ in range(trip_count)]
    if target_events <= 0:
        return rows

    risk_trip_count = max(1, min(trip_count, int(round(trip_count * 0.35))))
    trip_indices = [rng.randrange(trip_count) for _ in range(max(target_events, risk_trip_count))]
    for event_index in range(target_events):
        event_type = weighted_choice(rng, event_mix)
        column = RISK_EVENT_COLUMNS[event_type]
        rows[trip_indices[event_index % len(trip_indices)]][column] += 1
    return rows


class AISimulationAgent:
    """Generates reproducible 60-day baseline and 30-day recent synthetic trips."""

    metadata = AgentMetadata(
        agent_id="ai_simulation_agent",
        role=AgentRole.SIMULATION,
        display_name="AI Simulation Agent",
        description="Generates reproducible synthetic 90-day trip logs.",
        consumes=("scenario_config.json",),
        produces=("senior_trip_logs.csv", "simulation_manifest.json"),
    )

    def __init__(
        self,
        persona_agent: PersonaAgent | None = None,
        simulation_seed: int | None = None,
        start_date: date = DEFAULT_START_DATE,
    ) -> None:
        self.persona_agent = persona_agent or PersonaAgent()
        self.simulation_seed = simulation_seed
        self.start_date = start_date

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        """Generate trip fixtures and return the standard agent contract result."""
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            trip_output = Path(str(payload.parameters.get("trip_output", DEFAULT_TRIP_OUTPUT)))
            manifest_output = Path(str(payload.parameters.get("manifest_output", DEFAULT_MANIFEST_OUTPUT)))
            fixture = self.write_fixture(trip_output, manifest_output)
            manifest = fixture.manifest
            risk_change_count = len(manifest["recent_risk_increase_trip_count_by_customer"])
            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="senior_trip_logs.csv",
                        artifact_type=ArtifactType.CSV,
                        path=_relative_fixture_path(trip_output),
                        rows=len(fixture.rows),
                        summary={
                            "customer_count": manifest["customer_count"],
                            "trip_count": manifest["trip_count"],
                            "persona_customer_counts": manifest["persona_customer_counts"],
                            "observation_period": manifest["observation_period"],
                        },
                    ),
                    AgentArtifact(
                        artifact_id="simulation_manifest.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_fixture_path(manifest_output),
                        rows=manifest["customer_count"],
                        summary={
                            "schema_version": manifest["schema_version"],
                            "simulation_seed": manifest["simulation_seed"],
                            "recent_risk_change_customer_count": risk_change_count,
                            "risk_signal_counts": manifest["risk_signal_counts"],
                        },
                    ),
                ),
                metrics={
                    "customer_count": manifest["customer_count"],
                    "trip_count": manifest["trip_count"],
                    "persona_count": len(manifest["persona_customer_counts"]),
                    "risk_change_target_customer_count": risk_change_count,
                    "baseline_days": 60,
                    "recent_days": 30,
                },
                validation={
                    "passed": True,
                    "customer_90_day_coverage_validation": manifest["customer_90_day_coverage_validation"]["passed"],
                    "baseline_coverage_validation": manifest["baseline_coverage_validation"]["passed"],
                    "recent_coverage_validation": manifest["recent_coverage_validation"]["passed"],
                    "downstream_signal_validation_passed": all(
                        row["passed"] for row in manifest["downstream_signal_validation"].values()
                    ),
                },
                reason_codes=(
                    "SYNTHETIC_90_DAY_TRIP_LOG_GENERATED",
                    "BASELINE_60_RECENT_30_COVERAGE_VALIDATED",
                    "PERSONA_DOWNSTREAM_SIGNALS_VALIDATED",
                ),
                messages=("synthetic trip fixture and simulation manifest generated",),
            )
            return AgentExecutionResult(
                run_id=payload.run_id,
                metadata=self.metadata,
                status=AgentStatus.SUCCEEDED,
                input_payload=payload,
                output_payload=output,
                started_at=started_at,
                completed_at=utc_now_iso(),
                duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
            )
        except Exception as exc:
            return AgentExecutionResult(
                run_id=payload.run_id,
                metadata=self.metadata,
                status=AgentStatus.FAILED,
                input_payload=payload,
                started_at=started_at,
                completed_at=utc_now_iso(),
                duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
                errors=(f"{exc.__class__.__name__}: {exc}",),
            )

    def generate_fixture(self) -> GeneratedFixture:
        identities = self.persona_agent.load_customer_identities()
        patterns = self.persona_agent.load_customer_driving_patterns()
        fixture_seed = self._fixture_seed()
        rows: list[dict[str, Any]] = []
        patterns_by_customer = {pattern.customer_id: pattern for pattern in patterns}

        for identity in identities:
            pattern = patterns_by_customer[identity.customer_id]
            rows.extend(self.generate_customer_trips(identity, pattern, fixture_seed))

        self.validate_rows(rows)
        manifest = self.build_manifest(rows, fixture_seed)
        return GeneratedFixture(rows=rows, manifest=manifest)

    def generate_customer_trips(
        self,
        identity: CustomerIdentity,
        pattern: CustomerDrivingPattern,
        fixture_seed: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        trip_sequence = 1
        for period in ("baseline", "recent"):
            period_rows = self.generate_period_trips(identity, pattern, fixture_seed, period, trip_sequence)
            rows.extend(period_rows)
            trip_sequence += len(period_rows)
        return rows

    def generate_period_trips(
        self,
        identity: CustomerIdentity,
        pattern: CustomerDrivingPattern,
        fixture_seed: int,
        period: str,
        starting_sequence: int,
    ) -> list[dict[str, Any]]:
        trip_count = pattern.trip_count[period]
        rng = random.Random(stable_seed(fixture_seed, identity.customer_id, period))
        zone_labels = allocate_counts(trip_count, pattern.zone_mix[period])
        time_windows = allocate_counts(trip_count, pattern.time_window_weights[period])
        rng.shuffle(zone_labels)
        rng.shuffle(time_windows)
        day_indices = choose_day_indices(period, trip_count, rng)
        distances = [
            rng.uniform(*pattern.distance_km_per_trip_range[period])
            for _ in range(trip_count)
        ]
        event_plan = build_event_plan(
            total_distance=sum(distances),
            target_rate_per_100km=pattern.risk_event_rate_per_100km[period],
            event_mix=pattern.risk_event_mix,
            trip_count=trip_count,
            rng=rng,
        )
        recent_daily_frequency = pattern.trip_count["recent"] / 30
        baseline_daily_frequency = pattern.trip_count["baseline"] / 60
        has_reduced_recent_activity = period == "recent" and recent_daily_frequency <= baseline_daily_frequency * 1.10

        rows: list[dict[str, Any]] = []
        for index in range(trip_count):
            sequence = starting_sequence + index
            zone_label = zone_labels[index]
            destination_type = self.destination_for_trip(identity, pattern, period, zone_label, rng)
            start_dt = self.trip_start_datetime(day_indices[index], time_windows[index], rng)
            distance_km = round(distances[index], 2)
            avg_speed = self.average_speed(zone_label, period, identity.persona_type, rng)
            duration_min = round(max(3.0, distance_km / avg_speed * 60), 1)
            end_dt = start_dt + timedelta(minutes=duration_min)
            event_counts = event_plan[index]
            max_speed = self.max_speed(avg_speed, event_counts, identity.persona_type, period, rng)
            start_point, end_point = self.trip_coordinates(identity, pattern, zone_label, destination_type, rng, sequence)
            night_flag = int(start_dt.hour >= 22 or start_dt.hour < 6)
            previous_day_index = day_indices[index - 1] if index > 0 else None
            risk_signals = self.risk_signal_annotations(
                persona_type=identity.persona_type,
                period=period,
                zone_label=zone_label,
                destination_type=destination_type,
                night_flag=night_flag,
                event_counts=event_counts,
                duration_min=duration_min,
                day_index=day_indices[index],
                previous_day_index=previous_day_index,
                has_reduced_recent_activity=has_reduced_recent_activity,
            )
            rows.append(
                {
                    "customer_id": identity.customer_id,
                    "driver_id": identity.driver_id,
                    "persona_type": identity.persona_type,
                    "scenario_id": identity.scenario_id,
                    "simulation_seed": fixture_seed,
                    "observation_period": period,
                    "observation_day_index": day_indices[index],
                    "service_date": (self.start_date + timedelta(days=day_indices[index] - 1)).isoformat(),
                    "trip_id": f"trip_{identity.customer_id}_{sequence:04d}",
                    "trip_sequence": sequence,
                    "trip_start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "trip_end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "start_gps_x": round(start_point[0], 6),
                    "start_gps_y": round(start_point[1], 6),
                    "end_gps_x": round(end_point[0], 6),
                    "end_gps_y": round(end_point[1], 6),
                    "zone_label": zone_label,
                    "destination_type": destination_type,
                    "trip_distance_km": distance_km,
                    "trip_duration_min": duration_min,
                    "avg_speed": round(distance_km / duration_min * 60, 1),
                    "max_speed": max_speed,
                    "night_drive_flag": night_flag,
                    "speeding_count": event_counts["speeding_count"],
                    "harsh_accel_count": event_counts["harsh_accel_count"],
                    "harsh_brake_count": event_counts["harsh_brake_count"],
                    "sharp_turn_count": event_counts["sharp_turn_count"],
                    "stop_count": self.stop_count(zone_label, distance_km, rng),
                    "night_driving_signal": risk_signals["night_driving_signal"],
                    "sudden_braking_signal": risk_signals["sudden_braking_signal"],
                    "route_deviation_signal": risk_signals["route_deviation_signal"],
                    "reduced_activity_signal": risk_signals["reduced_activity_signal"],
                    "fatigue_indicator": risk_signals["fatigue_indicator"],
                    "risk_signal_codes": risk_signals["risk_signal_codes"],
                    "persona_risk_annotation": risk_signals["persona_risk_annotation"],
                    "synthetic_risk_tag": self.risk_tag(identity.persona_type, period, zone_label, night_flag, event_counts),
                }
            )
        return rows

    def destination_for_trip(
        self,
        identity: CustomerIdentity,
        pattern: CustomerDrivingPattern,
        period: str,
        zone_label: str,
        rng: random.Random,
    ) -> str:
        if zone_label == "outer":
            if identity.persona_type == "recent_outer_risk_change" and period == "recent":
                return "unknown_outer"
            if identity.persona_type == "medical_visit_pattern":
                return "clinic"
            if "family" in pattern.destination_weights and rng.random() < 0.55:
                return "family"
        return weighted_choice(rng, pattern.destination_weights)

    def trip_start_datetime(self, day_index: int, time_window: str, rng: random.Random) -> datetime:
        hour_start, hour_end = TIME_WINDOWS[time_window]
        hour = rng.randint(hour_start, hour_end)
        minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
        return datetime.combine(self.start_date + timedelta(days=day_index - 1), datetime.min.time()).replace(
            hour=hour,
            minute=minute,
        )

    def average_speed(self, zone_label: str, period: str, persona_type: str, rng: random.Random) -> float:
        if zone_label == "outer":
            base = rng.uniform(34, 48)
        elif zone_label == "buffer":
            base = rng.uniform(20, 34)
        else:
            base = rng.uniform(14, 28)
        if persona_type == "recent_outer_risk_change" and period == "recent" and zone_label == "outer":
            base += rng.uniform(6, 10)
        return base

    def max_speed(
        self,
        avg_speed: float,
        event_counts: dict[str, int],
        persona_type: str,
        period: str,
        rng: random.Random,
    ) -> float:
        event_total = sum(event_counts.values())
        uplift = rng.uniform(12, 24) + event_total * rng.uniform(3, 7)
        if persona_type == "recent_outer_risk_change" and period == "recent":
            uplift += 8
        return round(min(120.0, max(avg_speed, avg_speed + uplift)), 1)

    def trip_coordinates(
        self,
        identity: CustomerIdentity,
        pattern: CustomerDrivingPattern,
        zone_label: str,
        destination_type: str,
        rng: random.Random,
        sequence: int,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        seed = identity.living_zone_seed
        center_x = float(seed["center_gps_x"])
        center_y = float(seed["center_gps_y"])
        jitter_m = float(seed["jitter_m"])
        start_radius = rng.uniform(20, min(180, jitter_m))
        start_angle = rng.uniform(0, 360)
        start = bounded_offset_coordinate(center_x, center_y, start_radius, start_angle, rng)
        if destination_type == "home" and sequence % 2 == 0:
            end = bounded_offset_coordinate(center_x, center_y, rng.uniform(10, 90), rng.uniform(0, 360), rng)
        else:
            end_radius = zone_radius_m(zone_label, rng, jitter_m, pattern.route_variability)
            end_angle = rng.uniform(0, 360)
            end = bounded_offset_coordinate(center_x, center_y, end_radius, end_angle, rng)
        return start, end

    def stop_count(self, zone_label: str, distance_km: float, rng: random.Random) -> int:
        base = {"core": 3, "buffer": 2, "outer": 1}[zone_label]
        return max(0, int(round(base + distance_km / 8 + rng.choice([-1, 0, 0, 1]))))

    def risk_signal_annotations(
        self,
        persona_type: str,
        period: str,
        zone_label: str,
        destination_type: str,
        night_flag: int,
        event_counts: dict[str, int],
        duration_min: float,
        day_index: int,
        previous_day_index: int | None,
        has_reduced_recent_activity: bool,
    ) -> dict[str, int | str]:
        trip_gap_days = 0 if previous_day_index is None else max(0, day_index - previous_day_index)
        sudden_braking = int(event_counts["harsh_brake_count"] > 0)
        night_driving = int(night_flag == 1)
        route_deviation = int(
            zone_label == "outer"
            and (
                destination_type == "unknown_outer"
                or (persona_type == "recent_outer_risk_change" and period == "recent")
                or (persona_type == "irregular_family_support" and trip_gap_days >= 3)
            )
        )
        reduced_activity = int(has_reduced_recent_activity and trip_gap_days >= 4)
        fatigue = int(night_driving and (duration_min >= 50 or sum(event_counts.values()) > 0))

        codes: list[str] = []
        if night_driving:
            codes.append("NIGHT_DRIVING")
        if sudden_braking:
            codes.append("SUDDEN_BRAKING")
        if route_deviation:
            codes.append("ROUTE_DEVIATION")
        if reduced_activity:
            codes.append("REDUCED_ACTIVITY")
        if fatigue:
            codes.append("FATIGUE_INDICATOR")

        annotation = self.persona_risk_annotation(
            persona_type=persona_type,
            period=period,
            zone_label=zone_label,
            night_driving=night_driving,
            sudden_braking=sudden_braking,
            route_deviation=route_deviation,
            reduced_activity=reduced_activity,
            fatigue=fatigue,
        )
        return {
            "night_driving_signal": night_driving,
            "sudden_braking_signal": sudden_braking,
            "route_deviation_signal": route_deviation,
            "reduced_activity_signal": reduced_activity,
            "fatigue_indicator": fatigue,
            "risk_signal_codes": "|".join(codes) if codes else "none",
            "persona_risk_annotation": annotation,
        }

    def persona_risk_annotation(
        self,
        persona_type: str,
        period: str,
        zone_label: str,
        night_driving: int,
        sudden_braking: int,
        route_deviation: int,
        reduced_activity: int,
        fatigue: int,
    ) -> str:
        if persona_type == "recent_outer_risk_change" and period == "recent" and (route_deviation or night_driving or fatigue):
            return "recent_out_zone_risk_signal"
        if persona_type == "in_zone_risky_low_mileage" and zone_label in {"core", "buffer"} and sudden_braking:
            return "in_zone_braking_risk_signal"
        if persona_type == "medical_visit_pattern" and zone_label == "outer" and not (night_driving or sudden_braking or fatigue):
            return "repeated_medical_outer_context"
        if persona_type == "irregular_family_support" and route_deviation and not fatigue:
            return "family_support_route_variation"
        if reduced_activity:
            return "recent_activity_drop_watch"
        if night_driving or sudden_braking or route_deviation or fatigue:
            return "general_trip_risk_signal"
        return "no_trip_risk_signal"

    def risk_tag(
        self,
        persona_type: str,
        period: str,
        zone_label: str,
        night_flag: int,
        event_counts: dict[str, int],
    ) -> str:
        event_total = sum(event_counts.values())
        if persona_type == "recent_outer_risk_change" and period == "recent" and (
            zone_label == "outer" or night_flag or event_total
        ):
            return "recent_risk_increase"
        if persona_type == "in_zone_risky_low_mileage" and zone_label in {"core", "buffer"} and event_total:
            return "in_zone_risk"
        if zone_label == "outer" and event_total == 0:
            return "safe_outer"
        if persona_type in {"medical_visit_pattern", "irregular_family_support"} and zone_label == "outer":
            return "edge_case"
        return "normal"

    def validate_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            raise ValueError("simulation produced no rows")
        by_customer: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_customer.setdefault(str(row["customer_id"]), []).append(row)
            self._validate_row(row)
        if len(by_customer) != 30:
            raise ValueError(f"simulation must contain exactly 30 customers, got {len(by_customer)}")
        persona_counts: dict[str, set[str]] = {}
        for customer_id, customer_rows in by_customer.items():
            baseline = [row for row in customer_rows if row["observation_period"] == "baseline"]
            recent = [row for row in customer_rows if row["observation_period"] == "recent"]
            if len(baseline) < 20 or len(recent) < 8:
                raise ValueError(f"{customer_id} must have at least 20 baseline and 8 recent trips")
            self._validate_customer_90_day_coverage(customer_id, customer_rows)
            self._validate_baseline_coverage(customer_id, baseline)
            self._validate_recent_coverage(customer_id, recent)
            self._validate_recent_behavior_signal(customer_id, customer_rows[0]["persona_type"], recent)
            self._validate_persona_specific_downstream_signal(
                customer_id,
                customer_rows[0]["persona_type"],
                customer_rows,
            )
            persona_counts.setdefault(str(customer_rows[0]["persona_type"]), set()).add(customer_id)
        invalid = {persona: len(customers) for persona, customers in persona_counts.items() if len(customers) != 5}
        if invalid:
            raise ValueError(f"each persona must have exactly five customers; invalid={invalid}")

    def _validate_customer_90_day_coverage(self, customer_id: str, customer_rows: list[dict[str, Any]]) -> None:
        period_days: dict[str, set[int]] = {"baseline": set(), "recent": set()}
        period_dates: dict[str, set[date]] = {"baseline": set(), "recent": set()}
        service_dates_by_day: dict[int, set[str]] = {}
        for row in customer_rows:
            period = str(row["observation_period"])
            if period not in period_days:
                raise ValueError(f"{customer_id} has invalid observation_period: {period}")
            day_index = int(row["observation_day_index"])
            try:
                service_date = date.fromisoformat(str(row["service_date"]))
            except ValueError as exc:
                raise ValueError(f"{customer_id} has invalid service_date: {row['service_date']}") from exc
            period_days[period].add(day_index)
            period_dates[period].add(service_date)
            service_dates_by_day.setdefault(day_index, set()).add(str(row["service_date"]))

        required_period_boundaries = {
            "baseline": {1, 60},
            "recent": {61, 90},
        }
        missing_boundaries = {
            period: sorted(required_days - period_days[period])
            for period, required_days in required_period_boundaries.items()
            if required_days - period_days[period]
        }
        if missing_boundaries:
            raise ValueError(
                f"{customer_id} must span the complete 90-day observation window; "
                f"missing_boundary_days_by_period={missing_boundaries}"
            )

        overlapping_day_indices = sorted(period_days["baseline"] & period_days["recent"])
        if overlapping_day_indices:
            raise ValueError(
                f"{customer_id} baseline and recent observation periods must be non-overlapping; "
                f"overlapping_day_indices={overlapping_day_indices}"
            )

        overlapping_service_dates = sorted(
            service_date.isoformat() for service_date in period_dates["baseline"] & period_dates["recent"]
        )
        if overlapping_service_dates:
            raise ValueError(
                f"{customer_id} baseline and recent observation periods must be non-overlapping; "
                f"overlapping_service_dates={overlapping_service_dates}"
            )

        expected_boundary_dates = {
            1: self.start_date.isoformat(),
            60: (self.start_date + timedelta(days=59)).isoformat(),
            61: (self.start_date + timedelta(days=60)).isoformat(),
            90: (self.start_date + timedelta(days=89)).isoformat(),
        }
        mismatched_dates = {
            day_index: {
                "expected": expected_date,
                "actual": sorted(service_dates_by_day.get(day_index, set())),
            }
            for day_index, expected_date in expected_boundary_dates.items()
            if service_dates_by_day.get(day_index) != {expected_date}
        }
        if mismatched_dates:
            raise ValueError(
                f"{customer_id} has 90-day coverage service_date mismatch; "
                f"mismatched_boundary_dates={mismatched_dates}"
            )

        expected_ranges = {
            "baseline": (self.start_date, self.start_date + timedelta(days=59)),
            "recent": (self.start_date + timedelta(days=60), self.start_date + timedelta(days=89)),
        }
        mismatched_period_dates = {
            period: {
                "expected_start": expected_start.isoformat(),
                "expected_end": expected_end.isoformat(),
                "actual_start": min(dates).isoformat() if dates else None,
                "actual_end": max(dates).isoformat() if dates else None,
            }
            for period, (expected_start, expected_end) in expected_ranges.items()
            for dates in [period_dates[period]]
            if not dates or min(dates) != expected_start or max(dates) != expected_end
        }
        if mismatched_period_dates:
            raise ValueError(
                f"{customer_id} has incorrectly defined baseline/recent service_date boundaries; "
                f"mismatched_period_dates={mismatched_period_dates}"
            )

        if max(period_dates["baseline"]) >= min(period_dates["recent"]):
            raise ValueError(
                f"{customer_id} baseline period must end before recent period starts; "
                f"baseline_end={max(period_dates['baseline']).isoformat()}, "
                f"recent_start={min(period_dates['recent']).isoformat()}"
            )

    def _validate_baseline_coverage(self, customer_id: str, baseline_rows: list[dict[str, Any]]) -> None:
        baseline_days = sorted({int(row["observation_day_index"]) for row in baseline_rows})
        missing_boundaries = sorted({1, 60} - set(baseline_days))
        if missing_boundaries:
            raise ValueError(
                f"{customer_id} baseline must span the complete 60-day observation window; "
                f"missing_boundary_days={missing_boundaries}"
            )

        start_dates = {str(row["service_date"]) for row in baseline_rows if int(row["observation_day_index"]) == 1}
        end_dates = {str(row["service_date"]) for row in baseline_rows if int(row["observation_day_index"]) == 60}
        expected_start = self.start_date.isoformat()
        expected_end = (self.start_date + timedelta(days=59)).isoformat()
        if start_dates != {expected_start} or end_dates != {expected_end}:
            raise ValueError(
                f"{customer_id} baseline service_date coverage mismatch; "
                f"expected_start={expected_start}, actual_start={sorted(start_dates)}, "
                f"expected_end={expected_end}, actual_end={sorted(end_dates)}"
            )

    def _validate_recent_coverage(self, customer_id: str, recent_rows: list[dict[str, Any]]) -> None:
        recent_days = sorted({int(row["observation_day_index"]) for row in recent_rows})
        missing_boundaries = sorted({61, 90} - set(recent_days))
        if missing_boundaries:
            raise ValueError(
                f"{customer_id} recent must span the complete 30-day observation window; "
                f"missing_boundary_days={missing_boundaries}"
            )

        start_dates = {str(row["service_date"]) for row in recent_rows if int(row["observation_day_index"]) == 61}
        end_dates = {str(row["service_date"]) for row in recent_rows if int(row["observation_day_index"]) == 90}
        expected_start = (self.start_date + timedelta(days=60)).isoformat()
        expected_end = (self.start_date + timedelta(days=89)).isoformat()
        if start_dates != {expected_start} or end_dates != {expected_end}:
            raise ValueError(
                f"{customer_id} recent service_date coverage mismatch; "
                f"expected_start={expected_start}, actual_start={sorted(start_dates)}, "
                f"expected_end={expected_end}, actual_end={sorted(end_dates)}"
            )

    def _validate_recent_behavior_signal(
        self,
        customer_id: str,
        persona_type: object,
        recent_rows: list[dict[str, Any]],
    ) -> None:
        if str(persona_type) != "recent_outer_risk_change":
            return
        signal_rows = [
            row
            for row in recent_rows
            if row["synthetic_risk_tag"] == "recent_risk_increase"
            and (row["zone_label"] == "outer" or int(row["night_drive_flag"]) == 1)
        ]
        if len(signal_rows) < 3:
            raise ValueError(
                f"{customer_id} recent risk-change persona must include at least three "
                f"realistic recent 30-day risk-increase trips"
            )

    def _validate_persona_specific_downstream_signal(
        self,
        customer_id: str,
        persona_type: object,
        customer_rows: list[dict[str, Any]],
    ) -> None:
        summary = self.customer_signal_summary(customer_rows)
        evidence = self.persona_evidence_codes(str(persona_type), summary)
        if not evidence:
            raise ValueError(
                f"{customer_id} {persona_type} lacks detectable persona-specific "
                "change or risk/context signal for downstream scoring, XAI, A/B comparison, and reporting"
            )

    def customer_signal_summary(self, customer_rows: list[dict[str, Any]]) -> dict[str, Any]:
        baseline = [row for row in customer_rows if row["observation_period"] == "baseline"]
        recent = [row for row in customer_rows if row["observation_period"] == "recent"]
        if not baseline or not recent:
            raise ValueError("customer rows must include both baseline and recent trips")

        baseline_metrics = self._period_signal_metrics(baseline)
        recent_metrics = self._period_signal_metrics(recent)
        return {
            "customer_id": str(customer_rows[0]["customer_id"]),
            "persona_type": str(customer_rows[0]["persona_type"]),
            "baseline": baseline_metrics,
            "recent": recent_metrics,
            "outer_ratio_delta": recent_metrics["outer_ratio"] - baseline_metrics["outer_ratio"],
            "night_ratio_delta": recent_metrics["night_ratio"] - baseline_metrics["night_ratio"],
            "risk_rate_delta_per_100km": (
                recent_metrics["risk_event_rate_per_100km"] - baseline_metrics["risk_event_rate_per_100km"]
            ),
            "recent_risk_increase_trip_count": sum(
                1 for row in recent if row["synthetic_risk_tag"] == "recent_risk_increase"
            ),
            "recent_in_zone_risk_trip_count": sum(
                1
                for row in recent
                if row["synthetic_risk_tag"] == "in_zone_risk" and row["zone_label"] in {"core", "buffer"}
            ),
            "recent_route_deviation_count": sum(int(row["route_deviation_signal"]) for row in recent),
            "recent_persona_annotation_counts": self._annotation_counts(recent),
            "all_persona_annotation_counts": self._annotation_counts(customer_rows),
            "recent_outer_clinic_trip_count": sum(
                1 for row in recent if row["zone_label"] == "outer" and row["destination_type"] == "clinic"
            ),
            "recent_outer_family_trip_count": sum(
                1 for row in recent if row["zone_label"] == "outer" and row["destination_type"] == "family"
            ),
        }

    def _period_signal_metrics(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        trip_count = len(rows)
        total_distance = sum(float(row["trip_distance_km"]) for row in rows)
        risk_event_count = sum(int(row[field]) for row in rows for field in EVENT_COUNT_FIELDS)
        return {
            "trip_count": trip_count,
            "total_distance_km": round(total_distance, 2),
            "outer_ratio": self._ratio(rows, lambda row: row["zone_label"] == "outer"),
            "in_zone_ratio": self._ratio(rows, lambda row: row["zone_label"] in {"core", "buffer"}),
            "night_ratio": self._ratio(rows, lambda row: int(row["night_drive_flag"]) == 1),
            "risk_event_count": risk_event_count,
            "risk_event_rate_per_100km": risk_event_count / total_distance * 100 if total_distance else 0.0,
            "risk_signal_count": sum(int(row[field]) for row in rows for field in RISK_SIGNAL_FIELDS),
        }

    def _annotation_counts(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            annotation = str(row["persona_risk_annotation"])
            counts[annotation] = counts.get(annotation, 0) + 1
        return counts

    def _ratio(self, rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if predicate(row)) / len(rows)

    def persona_evidence_codes(self, persona_type: str, summary: dict[str, Any]) -> list[str]:
        baseline = summary["baseline"]
        recent = summary["recent"]
        recent_annotations = summary["recent_persona_annotation_counts"]
        all_annotations = summary["all_persona_annotation_counts"]
        evidence: list[str] = []

        if persona_type == "stable_local_low_mileage":
            if recent["in_zone_ratio"] >= 0.85 and recent["risk_event_rate_per_100km"] <= 2.0:
                evidence.append("STABLE_IN_ZONE_LOW_RISK_PATTERN")
            if abs(summary["outer_ratio_delta"]) <= 0.08 and recent["night_ratio"] <= 0.08:
                evidence.append("NO_RECENT_OUT_ZONE_OR_NIGHT_SPIKE")

        elif persona_type == "stable_outer_safe":
            if baseline["outer_ratio"] >= 0.15 and recent["outer_ratio"] >= 0.15:
                evidence.append("REPEATED_OUT_ZONE_EXPOSURE")
            if recent["risk_event_rate_per_100km"] <= 2.0 and recent["night_ratio"] <= 0.10:
                evidence.append("OUT_ZONE_LOW_RISK_CONTEXT")

        elif persona_type == "recent_outer_risk_change":
            if summary["outer_ratio_delta"] >= 0.20:
                evidence.append("OUT_ZONE_RATIO_INCREASE")
            if summary["night_ratio_delta"] >= 0.15:
                evidence.append("NIGHT_DRIVING_INCREASE")
            if summary["risk_rate_delta_per_100km"] >= 3.0:
                evidence.append("RISK_EVENT_RATE_INCREASE")
            if summary["recent_risk_increase_trip_count"] >= 3 and summary["recent_route_deviation_count"] >= 3:
                evidence.append("RECENT_ROUTE_DEVIATION_RISK_TRIPS")

        elif persona_type == "in_zone_risky_low_mileage":
            if summary["recent_in_zone_risk_trip_count"] >= 2:
                evidence.append("RECENT_IN_ZONE_RISK_EVENTS")
            if recent_annotations.get("in_zone_braking_risk_signal", 0) >= 1:
                evidence.append("IN_ZONE_BRAKING_ANNOTATION")
            if summary["risk_rate_delta_per_100km"] >= 1.5:
                evidence.append("RECENT_RISK_RATE_INCREASE")

        elif persona_type == "medical_visit_pattern":
            if summary["recent_outer_clinic_trip_count"] >= 2:
                evidence.append("REPEATED_MEDICAL_OUTER_DESTINATION")
            if all_annotations.get("repeated_medical_outer_context", 0) >= 2:
                evidence.append("MEDICAL_CONTEXT_ANNOTATION")
            if recent["night_ratio"] <= 0.10:
                evidence.append("LOW_NIGHT_MEDICAL_CONTEXT")

        elif persona_type == "irregular_family_support":
            if summary["outer_ratio_delta"] >= 0.08:
                evidence.append("FAMILY_SUPPORT_OUT_ZONE_INCREASE")
            if all_annotations.get("family_support_route_variation", 0) >= 2:
                evidence.append("FAMILY_ROUTE_VARIATION_CONTEXT")
            if summary["recent_route_deviation_count"] >= 2:
                evidence.append("RECENT_ROUTE_DEVIATION_CONTEXT")

        return evidence

    def _validate_row(self, row: dict[str, Any]) -> None:
        start_dt = datetime.strptime(str(row["trip_start_time"]), "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(str(row["trip_end_time"]), "%Y-%m-%d %H:%M:%S")
        if start_dt >= end_dt:
            raise ValueError(f"{row['trip_id']} has invalid time order")
        expected_service_date = (self.start_date + timedelta(days=int(row["observation_day_index"]) - 1)).isoformat()
        if str(row["service_date"]) != expected_service_date:
            raise ValueError(
                f"{row['trip_id']} service_date must match observation_day_index; "
                f"expected={expected_service_date}, actual={row['service_date']}"
            )
        if start_dt.date().isoformat() != expected_service_date:
            raise ValueError(f"{row['trip_id']} trip_start_time date must match service_date")
        if row["observation_period"] == "baseline" and not 1 <= int(row["observation_day_index"]) <= 60:
            raise ValueError(f"{row['trip_id']} has invalid baseline day index")
        if row["observation_period"] == "recent" and not 61 <= int(row["observation_day_index"]) <= 90:
            raise ValueError(f"{row['trip_id']} has invalid recent day index")
        for key in ("start_gps_x", "end_gps_x"):
            if not 126.70 <= float(row[key]) <= 127.30:
                raise ValueError(f"{row['trip_id']} {key} outside synthetic range")
        for key in ("start_gps_y", "end_gps_y"):
            if not 37.35 <= float(row[key]) <= 37.75:
                raise ValueError(f"{row['trip_id']} {key} outside synthetic range")
        avg_speed = float(row["trip_distance_km"]) / float(row["trip_duration_min"]) * 60
        if abs(avg_speed - float(row["avg_speed"])) > 1.0:
            raise ValueError(f"{row['trip_id']} average speed mismatch")
        if float(row["max_speed"]) < float(row["avg_speed"]):
            raise ValueError(f"{row['trip_id']} max_speed lower than avg_speed")
        for key in ("speeding_count", "harsh_accel_count", "harsh_brake_count", "sharp_turn_count", "stop_count"):
            if int(row[key]) < 0:
                raise ValueError(f"{row['trip_id']} {key} must be non-negative")
        for key in (
            "night_driving_signal",
            "sudden_braking_signal",
            "route_deviation_signal",
            "reduced_activity_signal",
            "fatigue_indicator",
        ):
            if int(row[key]) not in {0, 1}:
                raise ValueError(f"{row['trip_id']} {key} must be 0 or 1")
        if int(row["night_driving_signal"]) != int(row["night_drive_flag"]):
            raise ValueError(f"{row['trip_id']} night_driving_signal must mirror night_drive_flag")
        if int(row["sudden_braking_signal"]) != int(int(row["harsh_brake_count"]) > 0):
            raise ValueError(f"{row['trip_id']} sudden_braking_signal must follow harsh_brake_count")
        if not row["risk_signal_codes"] or not row["persona_risk_annotation"]:
            raise ValueError(f"{row['trip_id']} missing risk signal annotation")

    def build_manifest(self, rows: list[dict[str, Any]], fixture_seed: int) -> dict[str, Any]:
        by_persona: dict[str, set[str]] = {}
        baseline_days_by_customer: dict[str, set[int]] = {}
        recent_days_by_customer: dict[str, set[int]] = {}
        all_days_by_customer: dict[str, set[int]] = {}
        recent_risk_signal_by_customer: dict[str, int] = {}
        rows_by_customer: dict[str, list[dict[str, Any]]] = {}
        risk_signal_counts = {
            "night_driving_signal": 0,
            "sudden_braking_signal": 0,
            "route_deviation_signal": 0,
            "reduced_activity_signal": 0,
            "fatigue_indicator": 0,
        }
        recent_risk_rows = 0
        for row in rows:
            customer_id = str(row["customer_id"])
            day_index = int(row["observation_day_index"])
            rows_by_customer.setdefault(customer_id, []).append(row)
            by_persona.setdefault(str(row["persona_type"]), set()).add(customer_id)
            all_days_by_customer.setdefault(customer_id, set()).add(day_index)
            for signal_field in risk_signal_counts:
                risk_signal_counts[signal_field] += int(row[signal_field])
            if row["observation_period"] == "baseline":
                baseline_days_by_customer.setdefault(customer_id, set()).add(day_index)
            if row["observation_period"] == "recent":
                recent_days_by_customer.setdefault(customer_id, set()).add(day_index)
                if row["synthetic_risk_tag"] == "recent_risk_increase":
                    recent_risk_signal_by_customer[customer_id] = recent_risk_signal_by_customer.get(customer_id, 0) + 1
            if row["synthetic_risk_tag"] == "recent_risk_increase":
                recent_risk_rows += 1
        downstream_signal_validation: dict[str, Any] = {}
        for customer_id, customer_rows in sorted(rows_by_customer.items()):
            summary = self.customer_signal_summary(customer_rows)
            downstream_signal_validation[customer_id] = {
                "persona_type": summary["persona_type"],
                "passed": bool(self.persona_evidence_codes(summary["persona_type"], summary)),
                "evidence_codes": self.persona_evidence_codes(summary["persona_type"], summary),
                "outer_ratio_delta": round(float(summary["outer_ratio_delta"]), 4),
                "night_ratio_delta": round(float(summary["night_ratio_delta"]), 4),
                "risk_rate_delta_per_100km": round(float(summary["risk_rate_delta_per_100km"]), 4),
                "recent_risk_signal_count": int(summary["recent"]["risk_signal_count"]),
            }
        baseline_complete_customers = [
            customer_id
            for customer_id, days in sorted(baseline_days_by_customer.items())
            if 1 in days and 60 in days
        ]
        recent_complete_customers = [
            customer_id
            for customer_id, days in sorted(recent_days_by_customer.items())
            if 61 in days and 90 in days
        ]
        complete_90_day_customers = [
            customer_id
            for customer_id, days in sorted(all_days_by_customer.items())
            if {1, 60, 61, 90}.issubset(days)
        ]
        customer_90_day_coverage = {
            customer_id: {
                "passed": {1, 60, 61, 90}.issubset(days),
                "observed_day_index_min": min(days),
                "observed_day_index_max": max(days),
                "required_boundary_day_indices": [1, 60, 61, 90],
                "missing_boundary_day_indices": sorted({1, 60, 61, 90} - days),
                "baseline_start_date": self.start_date.isoformat(),
                "baseline_end_date": (self.start_date + timedelta(days=59)).isoformat(),
                "recent_start_date": (self.start_date + timedelta(days=60)).isoformat(),
                "recent_end_date": (self.start_date + timedelta(days=89)).isoformat(),
                "periods_non_overlapping": not (
                    baseline_days_by_customer.get(customer_id, set())
                    & recent_days_by_customer.get(customer_id, set())
                ),
                "baseline_trip_count": len(
                    [row for row in rows_by_customer[customer_id] if row["observation_period"] == "baseline"]
                ),
                "recent_trip_count": len(
                    [row for row in rows_by_customer[customer_id] if row["observation_period"] == "recent"]
                ),
            }
            for customer_id, days in sorted(all_days_by_customer.items())
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "simulation_seed": fixture_seed,
            "start_date": self.start_date.isoformat(),
            "observation_period": {
                "baseline_days": 60,
                "recent_days": 30,
                "baseline_start_date": self.start_date.isoformat(),
                "baseline_end_date": (self.start_date + timedelta(days=59)).isoformat(),
                "recent_start_date": (self.start_date + timedelta(days=60)).isoformat(),
                "recent_end_date": (self.start_date + timedelta(days=89)).isoformat(),
                "periods_non_overlapping": True,
            },
            "customer_90_day_coverage_validation": {
                "required_day_index_start": 1,
                "required_baseline_day_index_end": 60,
                "required_recent_day_index_start": 61,
                "required_day_index_end": 90,
                "complete_customer_count": len(complete_90_day_customers),
                "customer_count": len(all_days_by_customer),
                "passed": len(complete_90_day_customers) == len(all_days_by_customer),
                "customers": customer_90_day_coverage,
            },
            "baseline_coverage_validation": {
                "required_day_index_start": 1,
                "required_day_index_end": 60,
                "complete_customer_count": len(baseline_complete_customers),
                "customer_count": len(baseline_days_by_customer),
                "passed": len(baseline_complete_customers) == len(baseline_days_by_customer),
            },
            "recent_coverage_validation": {
                "required_day_index_start": 61,
                "required_day_index_end": 90,
                "complete_customer_count": len(recent_complete_customers),
                "customer_count": len(recent_days_by_customer),
                "passed": len(recent_complete_customers) == len(recent_days_by_customer),
            },
            "customer_count": len({row["customer_id"] for row in rows}),
            "trip_count": len(rows),
            "persona_customer_counts": {persona: len(customers) for persona, customers in sorted(by_persona.items())},
            "recent_risk_increase_trip_count": recent_risk_rows,
            "recent_risk_increase_trip_count_by_customer": dict(sorted(recent_risk_signal_by_customer.items())),
            "downstream_signal_validation": downstream_signal_validation,
            "risk_signal_counts": risk_signal_counts,
            "output_fields": TRIP_FIELDS,
        }

    def write_fixture(
        self,
        trip_output: str | Path = DEFAULT_TRIP_OUTPUT,
        manifest_output: str | Path = DEFAULT_MANIFEST_OUTPUT,
    ) -> GeneratedFixture:
        fixture = self.generate_fixture()
        trip_path = Path(trip_output)
        manifest_path = Path(manifest_output)
        trip_path.parent.mkdir(parents=True, exist_ok=True)
        with trip_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=TRIP_FIELDS)
            writer.writeheader()
            writer.writerows(fixture.rows)
        with manifest_path.open("w", encoding="utf-8") as file:
            json.dump(fixture.manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return fixture

    def _fixture_seed(self) -> int:
        if self.simulation_seed is not None:
            return self.simulation_seed
        template = self.persona_agent.load_template()
        return int(template["simulation_seed"])


def _relative_fixture_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic senior synthetic trip fixtures.")
    parser.add_argument("--output", default=str(DEFAULT_TRIP_OUTPUT), help="CSV output path")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_OUTPUT), help="Manifest JSON output path")
    parser.add_argument("--seed", type=int, default=None, help="Override simulation seed")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat(), help="Observation day 1 date")
    args = parser.parse_args(argv)

    agent = AISimulationAgent(simulation_seed=args.seed, start_date=date.fromisoformat(args.start_date))
    fixture = agent.write_fixture(args.output, args.manifest)
    print(f"wrote {len(fixture.rows)} rows to {args.output}")
    print(f"wrote manifest to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

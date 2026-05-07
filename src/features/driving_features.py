"""Driving behavior feature aggregation."""

from __future__ import annotations

from typing import Any

from src.data.load_trips import group_by_driver

OUTSIDE_SEGMENT_SAFETY_METRIC_FIELDS = (
    "speeding",
    "harsh_accel",
    "harsh_brake",
    "sharp_turn",
)


def per_100km(count: int | float, total_km: float) -> float:
    if total_km <= 0:
        return 0.0
    return count / total_km * 100


def coerce_flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return bool(value)


def is_in_zone_trip(trip: dict[str, Any]) -> bool:
    if "in_zone_flag" in trip:
        return coerce_flag(trip["in_zone_flag"])
    return str(trip.get("zone_label", "")) in {"core", "buffer"}


def is_outside_living_zone_segment(trip: dict[str, Any]) -> bool:
    if "living_zone_outside_segment_flag" in trip:
        return coerce_flag(trip["living_zone_outside_segment_flag"])
    return coerce_flag(trip.get("out_zone_flag"))


def trip_period(trip: dict[str, Any]) -> str:
    return str(trip.get("period") or trip.get("observation_period") or "")


def is_night(trip: dict[str, Any]) -> bool:
    return coerce_flag(trip.get("night_flag", False))


def summarize_living_zone_outside_segment_safety(trips: list[dict[str, Any]]) -> dict[str, float | int]:
    """Aggregate safety behavior only for trips outside the DBSCAN/P90 living-zone segment."""
    outside_trips = [trip for trip in trips if is_outside_living_zone_segment(trip)]
    outside_km = sum(float(trip.get("trip_distance_km", 0.0)) for trip in outside_trips)
    outside_night_km = sum(float(trip.get("trip_distance_km", 0.0)) for trip in outside_trips if is_night(trip))
    counts = {
        metric: sum(int(trip.get(f"{metric}_count", 0)) for trip in outside_trips)
        for metric in OUTSIDE_SEGMENT_SAFETY_METRIC_FIELDS
    }
    risk_event_count = sum(counts.values())

    return {
        "living_zone_outside_segment_km": round(outside_km, 2),
        "living_zone_outside_segment_speeding_count": counts["speeding"],
        "living_zone_outside_segment_harsh_accel_count": counts["harsh_accel"],
        "living_zone_outside_segment_harsh_brake_count": counts["harsh_brake"],
        "living_zone_outside_segment_sharp_turn_count": counts["sharp_turn"],
        "living_zone_outside_segment_risk_event_count": risk_event_count,
        "living_zone_outside_segment_speeding_per_100km": round(per_100km(counts["speeding"], outside_km), 4),
        "living_zone_outside_segment_harsh_accel_per_100km": round(per_100km(counts["harsh_accel"], outside_km), 4),
        "living_zone_outside_segment_harsh_brake_per_100km": round(per_100km(counts["harsh_brake"], outside_km), 4),
        "living_zone_outside_segment_sharp_turn_per_100km": round(per_100km(counts["sharp_turn"], outside_km), 4),
        "living_zone_outside_segment_risk_events_per_100km": round(per_100km(risk_event_count, outside_km), 4),
        "living_zone_outside_segment_night_ratio": round(outside_night_km / outside_km, 4) if outside_km else 0.0,
    }


def summarize_living_zone_outside_segment_change(
    baseline: list[dict[str, Any]],
    recent: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Compare recent outside-living-zone exposure and risk with baseline behavior."""
    baseline_total_km = sum(float(trip.get("trip_distance_km", 0.0)) for trip in baseline)
    recent_total_km = sum(float(trip.get("trip_distance_km", 0.0)) for trip in recent)
    baseline_safety = summarize_living_zone_outside_segment_safety(baseline)
    recent_safety = summarize_living_zone_outside_segment_safety(recent)

    baseline_count = sum(1 for trip in baseline if is_outside_living_zone_segment(trip))
    recent_count = sum(1 for trip in recent if is_outside_living_zone_segment(trip))
    baseline_ratio = baseline_count / len(baseline) if baseline else 0.0
    recent_ratio = recent_count / len(recent) if recent else 0.0
    baseline_distance_ratio = (
        float(baseline_safety["living_zone_outside_segment_km"]) / baseline_total_km
        if baseline_total_km
        else 0.0
    )
    recent_distance_ratio = (
        float(recent_safety["living_zone_outside_segment_km"]) / recent_total_km
        if recent_total_km
        else 0.0
    )
    risk_delta = (
        float(recent_safety["living_zone_outside_segment_risk_events_per_100km"])
        - float(baseline_safety["living_zone_outside_segment_risk_events_per_100km"])
    )
    night_delta = (
        float(recent_safety["living_zone_outside_segment_night_ratio"])
        - float(baseline_safety["living_zone_outside_segment_night_ratio"])
    )
    change_score = (
        min(max(0.0, recent_distance_ratio - baseline_distance_ratio) / 0.30, 1.0) * 30.0
        + min(max(0.0, risk_delta) / 8.0, 1.0) * 45.0
        + min(max(0.0, night_delta) / 0.30, 1.0) * 25.0
    )

    return {
        "baseline_living_zone_outside_segment_count": baseline_count,
        "baseline_living_zone_outside_segment_ratio": round(baseline_ratio, 4),
        "baseline_living_zone_outside_segment_km": round(
            float(baseline_safety["living_zone_outside_segment_km"]),
            2,
        ),
        "baseline_living_zone_outside_segment_distance_ratio": round(baseline_distance_ratio, 4),
        "baseline_living_zone_outside_segment_risk_events_per_100km": baseline_safety[
            "living_zone_outside_segment_risk_events_per_100km"
        ],
        "baseline_living_zone_outside_segment_night_ratio": baseline_safety[
            "living_zone_outside_segment_night_ratio"
        ],
        "living_zone_outside_segment_ratio_delta": round(recent_ratio - baseline_ratio, 4),
        "living_zone_outside_segment_distance_ratio_delta": round(
            recent_distance_ratio - baseline_distance_ratio,
            4,
        ),
        "living_zone_outside_segment_risk_events_delta_per_100km": round(risk_delta, 4),
        "living_zone_outside_segment_night_ratio_delta": round(night_delta, 4),
        "living_zone_outside_segment_risk_change_score": round(min(100.0, change_score), 2),
    }


def aggregate_recent_behavior(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for driver_id, driver_trips in group_by_driver(trips).items():
        recent = [trip for trip in driver_trips if trip_period(trip) == "recent"]
        if not recent:
            continue

        total_km = sum(trip["trip_distance_km"] for trip in recent)
        trip_count = len(recent)
        night_km = sum(trip["trip_distance_km"] for trip in recent if is_night(trip))
        speeding_count = sum(trip["speeding_count"] for trip in recent)
        harsh_accel_count = sum(trip["harsh_accel_count"] for trip in recent)
        harsh_brake_count = sum(trip["harsh_brake_count"] for trip in recent)
        sharp_turn_count = sum(trip["sharp_turn_count"] for trip in recent)
        in_zone = [trip for trip in recent if is_in_zone_trip(trip)]
        outside_living_zone_segments = [trip for trip in recent if is_outside_living_zone_segment(trip)]
        in_zone_total_km = sum(trip["trip_distance_km"] for trip in in_zone)
        outside_segment_total_km = sum(trip["trip_distance_km"] for trip in outside_living_zone_segments)
        in_zone_night_km = sum(trip["trip_distance_km"] for trip in in_zone if is_night(trip))
        in_zone_speeding_count = sum(trip["speeding_count"] for trip in in_zone)
        in_zone_harsh_accel_count = sum(trip["harsh_accel_count"] for trip in in_zone)
        in_zone_harsh_brake_count = sum(trip["harsh_brake_count"] for trip in in_zone)
        in_zone_sharp_turn_count = sum(trip["sharp_turn_count"] for trip in in_zone)
        in_zone_risk_event_count = (
            in_zone_speeding_count
            + in_zone_harsh_accel_count
            + in_zone_harsh_brake_count
            + in_zone_sharp_turn_count
        )
        outside_segment_safety = summarize_living_zone_outside_segment_safety(recent)

        rows.append(
            {
                "driver_id": driver_id,
                "total_km": round(total_km, 2),
                "trip_count": trip_count,
                "avg_trip_km": round(total_km / trip_count, 2) if trip_count else 0.0,
                "night_ratio": round(night_km / total_km, 4) if total_km else 0.0,
                "speeding_per_100km": round(per_100km(speeding_count, total_km), 4),
                "harsh_accel_per_100km": round(per_100km(harsh_accel_count, total_km), 4),
                "harsh_brake_per_100km": round(per_100km(harsh_brake_count, total_km), 4),
                "sharp_turn_per_100km": round(per_100km(sharp_turn_count, total_km), 4),
                "in_zone_total_km": round(in_zone_total_km, 2),
                "in_zone_trip_count": len(in_zone),
                "in_zone_distance_ratio": round(in_zone_total_km / total_km, 4) if total_km else 0.0,
                "in_zone_night_ratio": round(in_zone_night_km / in_zone_total_km, 4) if in_zone_total_km else 0.0,
                "in_zone_speeding_per_100km": round(per_100km(in_zone_speeding_count, in_zone_total_km), 4),
                "in_zone_harsh_accel_per_100km": round(per_100km(in_zone_harsh_accel_count, in_zone_total_km), 4),
                "in_zone_harsh_brake_per_100km": round(per_100km(in_zone_harsh_brake_count, in_zone_total_km), 4),
                "in_zone_sharp_turn_per_100km": round(per_100km(in_zone_sharp_turn_count, in_zone_total_km), 4),
                "in_zone_risk_events_per_100km": round(per_100km(in_zone_risk_event_count, in_zone_total_km), 4),
                "living_zone_outside_segment_count": len(outside_living_zone_segments),
                "living_zone_outside_segment_km": round(outside_segment_total_km, 2),
                "living_zone_outside_segment_night_ratio": outside_segment_safety[
                    "living_zone_outside_segment_night_ratio"
                ],
                "living_zone_outside_segment_ratio": round(len(outside_living_zone_segments) / trip_count, 4)
                if trip_count
                else 0.0,
                "living_zone_outside_segment_distance_ratio": round(outside_segment_total_km / total_km, 4)
                if total_km
                else 0.0,
                **outside_segment_safety,
            }
        )
    return rows


def aggregate_baseline_behavior(trips: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    baselines: dict[str, dict[str, float]] = {}
    for driver_id, driver_trips in group_by_driver(trips).items():
        baseline = [trip for trip in driver_trips if trip_period(trip) == "baseline"]
        recent = [trip for trip in driver_trips if trip_period(trip) == "recent"]
        if not baseline:
            continue
        total_km = sum(trip["trip_distance_km"] for trip in baseline)
        outside_segment_change = summarize_living_zone_outside_segment_change(baseline, recent)
        baselines[driver_id] = {
            "baseline_out_zone_ratio": round(
                sum(trip["trip_distance_km"] for trip in baseline if trip.get("out_zone_flag")) / total_km,
                4,
            )
            if total_km
            else 0.0,
            "baseline_speeding_per_100km": round(
                per_100km(sum(trip["speeding_count"] for trip in baseline), total_km),
                4,
            ),
            "baseline_harsh_brake_per_100km": round(
                per_100km(sum(trip["harsh_brake_count"] for trip in baseline), total_km),
                4,
            ),
            "baseline_night_ratio": round(
                sum(trip["trip_distance_km"] for trip in baseline if is_night(trip)) / total_km,
                4,
            )
            if total_km
            else 0.0,
            **outside_segment_change,
        }
    return baselines

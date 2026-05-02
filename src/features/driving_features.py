"""Driving behavior feature aggregation."""

from __future__ import annotations

from typing import Any

from src.data.load_trips import group_by_driver


def per_100km(count: int | float, total_km: float) -> float:
    if total_km <= 0:
        return 0.0
    return count / total_km * 100


def aggregate_recent_behavior(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for driver_id, driver_trips in group_by_driver(trips).items():
        recent = [trip for trip in driver_trips if trip["period"] == "recent"]
        if not recent:
            continue

        total_km = sum(trip["trip_distance_km"] for trip in recent)
        trip_count = len(recent)
        night_km = sum(trip["trip_distance_km"] for trip in recent if trip["night_flag"])
        speeding_count = sum(trip["speeding_count"] for trip in recent)
        harsh_accel_count = sum(trip["harsh_accel_count"] for trip in recent)
        harsh_brake_count = sum(trip["harsh_brake_count"] for trip in recent)
        sharp_turn_count = sum(trip["sharp_turn_count"] for trip in recent)

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
            }
        )
    return rows


def aggregate_baseline_behavior(trips: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    baselines: dict[str, dict[str, float]] = {}
    for driver_id, driver_trips in group_by_driver(trips).items():
        baseline = [trip for trip in driver_trips if trip["period"] == "baseline"]
        if not baseline:
            continue
        total_km = sum(trip["trip_distance_km"] for trip in baseline)
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
                sum(trip["trip_distance_km"] for trip in baseline if trip["night_flag"]) / total_km,
                4,
            )
            if total_km
            else 0.0,
        }
    return baselines

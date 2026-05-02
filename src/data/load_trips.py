"""Trip data loading and validation utilities."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from src.data.column_mapping import STANDARD_COLUMNS

REQUIRED_COLUMNS = STANDARD_COLUMNS

FLOAT_COLUMNS = {
    "start_gps_x",
    "start_gps_y",
    "end_gps_x",
    "end_gps_y",
    "trip_distance_km",
    "avg_speed",
    "max_speed",
}

INT_COLUMNS = {
    "trip_duration_min",
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
    "stop_count",
}


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def is_night_trip(start_time: datetime) -> bool:
    return start_time.hour >= 22 or start_time.hour < 6


def validate_columns(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise ValueError("CSV header is missing")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")


def coerce_row(row: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = dict(row)
    for column in FLOAT_COLUMNS:
        result[column] = float(row[column])
    for column in INT_COLUMNS:
        result[column] = int(row[column])

    result["trip_start_dt"] = parse_time(row["trip_start_time"])
    result["trip_end_dt"] = parse_time(row["trip_end_time"])
    result["night_flag"] = is_night_trip(result["trip_start_dt"])

    if result["trip_distance_km"] <= 0:
        raise ValueError(f"trip_distance_km must be positive: {row['trip_id']}")
    if result["trip_duration_min"] <= 0:
        raise ValueError(f"trip_duration_min must be positive: {row['trip_id']}")

    for column in ["speeding_count", "harsh_accel_count", "harsh_brake_count", "sharp_turn_count", "stop_count"]:
        if result[column] < 0:
            raise ValueError(f"{column} must be non-negative: {row['trip_id']}")
    return result


def assign_periods(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows

    months = sorted({row["trip_start_dt"].strftime("%Y-%m") for row in rows})
    recent_month = months[-1]
    for row in rows:
        row["period"] = "recent" if row["trip_start_dt"].strftime("%Y-%m") == recent_month else "baseline"
    return rows


def load_trips(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        validate_columns(reader.fieldnames)
        rows = [coerce_row(row) for row in reader]
    return assign_periods(rows)


def group_by_driver(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["driver_id"]), []).append(row)
    return grouped

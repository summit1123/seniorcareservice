#!/usr/bin/env python3
"""Create deterministic sample trip data for the model pipeline."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "trip_sample.csv"

FIELDS = [
    "driver_id",
    "trip_id",
    "trip_start_time",
    "trip_end_time",
    "start_gps_x",
    "start_gps_y",
    "end_gps_x",
    "end_gps_y",
    "trip_distance_km",
    "trip_duration_min",
    "avg_speed",
    "max_speed",
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
    "stop_count",
]


def make_trip(
    driver_id: str,
    index: int,
    start_time: datetime,
    start: tuple[float, float],
    end: tuple[float, float],
    distance: float,
    duration: int,
    max_speed: float,
    speeding: int,
    harsh_accel: int,
    harsh_brake: int,
    sharp_turn: int,
    stop_count: int,
) -> dict[str, str]:
    avg_speed = distance / (duration / 60)
    return {
        "driver_id": driver_id,
        "trip_id": f"{driver_id}_trip_{index:03d}",
        "trip_start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "trip_end_time": (start_time + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S"),
        "start_gps_x": f"{start[0]:.6f}",
        "start_gps_y": f"{start[1]:.6f}",
        "end_gps_x": f"{end[0]:.6f}",
        "end_gps_y": f"{end[1]:.6f}",
        "trip_distance_km": f"{distance:.2f}",
        "trip_duration_min": str(duration),
        "avg_speed": f"{avg_speed:.1f}",
        "max_speed": f"{max_speed:.1f}",
        "speeding_count": str(speeding),
        "harsh_accel_count": str(harsh_accel),
        "harsh_brake_count": str(harsh_brake),
        "sharp_turn_count": str(sharp_turn),
        "stop_count": str(stop_count),
    }


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    configs = {
        "driver_001": {
            "home": (126.978000, 37.566500),
            "near": [(126.982200, 37.570100), (126.990100, 37.565200), (126.975400, 37.560900)],
            "far": [(126.995000, 37.575000)],
            "risk_recent": False,
        },
        "driver_002": {
            "home": (127.025000, 37.500000),
            "near": [(127.030000, 37.504000), (127.018000, 37.497500), (127.033000, 37.493000)],
            "far": [(127.080000, 37.520000), (127.090000, 37.530000)],
            "risk_recent": False,
        },
        "driver_003": {
            "home": (126.900000, 37.480000),
            "near": [(126.906000, 37.484000), (126.895000, 37.476000), (126.910000, 37.488000)],
            "far": [(127.100000, 37.600000), (127.120000, 37.620000), (127.070000, 37.590000)],
            "risk_recent": True,
        },
    }

    for driver_id, cfg in configs.items():
        trip_index = 1
        home = cfg["home"]
        near = cfg["near"]
        far = cfg["far"]

        for i in range(8):
            start_time = datetime(2024, 1, 3 + i * 3, 9 + (i % 3), 10)
            destination = near[i % len(near)]
            rows.append(
                make_trip(
                    driver_id,
                    trip_index,
                    start_time,
                    home if i % 2 == 0 else destination,
                    destination if i % 2 == 0 else home,
                    distance=5.8 + (i % 3) * 1.1,
                    duration=18 + (i % 4) * 3,
                    max_speed=48 + (i % 3) * 4,
                    speeding=0,
                    harsh_accel=0 if i % 4 else 1,
                    harsh_brake=0 if i % 5 else 1,
                    sharp_turn=0 if i % 3 else 1,
                    stop_count=2 + (i % 4),
                )
            )
            trip_index += 1

        for i in range(5):
            if driver_id == "driver_001":
                destination = near[i % len(near)]
                distance = 6.2 + (i % 2)
                duration = 20 + (i % 3) * 2
                max_speed = 52 + (i % 2) * 3
                speeding = 0
                harsh_accel = 0
                harsh_brake = 0 if i != 3 else 1
                sharp_turn = 0
                hour = 10 + i
            elif driver_id == "driver_002":
                destination = far[i % len(far)] if i in (1, 3) else near[i % len(near)]
                distance = 9.5 if i in (1, 3) else 6.5
                duration = 28 if i in (1, 3) else 21
                max_speed = 58
                speeding = 0
                harsh_accel = 0
                harsh_brake = 1 if i == 3 else 0
                sharp_turn = 0
                hour = 11 + i
            else:
                destination = far[i % len(far)] if i >= 1 else near[i % len(near)]
                distance = 15.0 + i * 2.5
                duration = 32 + i * 4
                max_speed = 72 + i * 4
                speeding = 1 + (i // 2)
                harsh_accel = 1 if i >= 2 else 0
                harsh_brake = 2 if i >= 2 else 1
                sharp_turn = 1 + (i % 2)
                hour = 22 if i in (2, 4) else 14 + i

            start_time = datetime(2024, 2, 2 + i * 5, hour, 20)
            rows.append(
                make_trip(
                    driver_id,
                    trip_index,
                    start_time,
                    home if i % 2 == 0 else destination,
                    destination if i % 2 == 0 else home,
                    distance=distance,
                    duration=duration,
                    max_speed=max_speed,
                    speeding=speeding,
                    harsh_accel=harsh_accel,
                    harsh_brake=harsh_brake,
                    sharp_turn=sharp_turn,
                    stop_count=2 + i,
                )
            )
            trip_index += 1

    return rows


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with OUTPUT.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

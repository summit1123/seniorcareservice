"""Lifestyle-zone feature generation."""

from __future__ import annotations

from math import sqrt
from typing import Any

from src.data.load_trips import group_by_driver


Point = tuple[float, float]
ZoneMap = dict[str, list[Point]]


def grid_id(x: float, y: float, precision: int = 3) -> str:
    return f"{round(x, precision):.{precision}f}:{round(y, precision):.{precision}f}"


def distance(a: Point, b: Point) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def close_to_any(point: Point, centers: list[Point], eps: float) -> bool:
    return any(distance(point, center) <= eps for center in centers)


def region_query(points: list[Point], point_index: int, eps: float) -> list[int]:
    point = points[point_index]
    return [idx for idx, candidate in enumerate(points) if distance(point, candidate) <= eps]


def dbscan_clusters(points: list[Point], eps: float = 0.012, min_samples: int = 3) -> list[list[Point]]:
    labels: list[int | None] = [None for _ in points]
    cluster_id = 0

    for point_index in range(len(points)):
        if labels[point_index] is not None:
            continue

        neighbors = region_query(points, point_index, eps)
        if len(neighbors) < min_samples:
            labels[point_index] = -1
            continue

        labels[point_index] = cluster_id
        seeds = list(neighbors)
        seed_lookup = set(seeds)
        cursor = 0

        while cursor < len(seeds):
            neighbor_index = seeds[cursor]
            if labels[neighbor_index] == -1:
                labels[neighbor_index] = cluster_id
            elif labels[neighbor_index] is None:
                labels[neighbor_index] = cluster_id
                expanded = region_query(points, neighbor_index, eps)
                if len(expanded) >= min_samples:
                    for expanded_index in expanded:
                        if expanded_index not in seed_lookup:
                            seeds.append(expanded_index)
                            seed_lookup.add(expanded_index)
            cursor += 1

        cluster_id += 1

    clusters: list[list[Point]] = [[] for _ in range(cluster_id)]
    for point, label in zip(points, labels):
        if label is not None and label >= 0:
            clusters[label].append(point)
    return clusters


def cluster_points(points: list[Point], eps: float = 0.012, min_samples: int = 3) -> list[Point]:
    return [cluster_center(cluster) for cluster in dbscan_clusters(points, eps=eps, min_samples=min_samples)]


def cluster_center(points: list[Point]) -> Point:
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def fit_zone_centers(trips: list[dict[str, Any]], eps: float = 0.012, min_samples: int = 3) -> ZoneMap:
    zones: ZoneMap = {}
    for driver_id, driver_trips in group_by_driver(trips).items():
        baseline_points: list[Point] = []
        for trip in driver_trips:
            if trip["period"] != "baseline":
                continue
            baseline_points.append((trip["start_gps_x"], trip["start_gps_y"]))
            baseline_points.append((trip["end_gps_x"], trip["end_gps_y"]))
        zones[driver_id] = cluster_points(baseline_points, eps=eps, min_samples=min_samples)
    return zones


def label_trips_with_zones(trips: list[dict[str, Any]], zones: ZoneMap, eps: float = 0.012) -> list[dict[str, Any]]:
    baseline_destinations: dict[str, set[str]] = {}
    baseline_routes: dict[str, set[str]] = {}

    for trip in trips:
        driver_id = trip["driver_id"]
        start_grid = grid_id(trip["start_gps_x"], trip["start_gps_y"])
        end_grid = grid_id(trip["end_gps_x"], trip["end_gps_y"])
        route_key = f"{start_grid}->{end_grid}"
        trip["start_grid"] = start_grid
        trip["end_grid"] = end_grid
        trip["route_key"] = route_key
        if trip["period"] == "baseline":
            baseline_destinations.setdefault(driver_id, set()).add(end_grid)
            baseline_routes.setdefault(driver_id, set()).add(route_key)

    for trip in trips:
        driver_id = trip["driver_id"]
        centers = zones.get(driver_id, [])
        start = (trip["start_gps_x"], trip["start_gps_y"])
        end = (trip["end_gps_x"], trip["end_gps_y"])
        start_in_zone = close_to_any(start, centers, eps)
        end_in_zone = close_to_any(end, centers, eps)
        trip["in_zone_flag"] = int(start_in_zone and end_in_zone)
        trip["out_zone_flag"] = int(not trip["in_zone_flag"])
        trip["route_repeat_flag"] = int(trip["route_key"] in baseline_routes.get(driver_id, set()))
        trip["new_destination_flag"] = int(trip["end_grid"] not in baseline_destinations.get(driver_id, set()))
    return trips


def build_zone_feature_table(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for driver_id, driver_trips in group_by_driver(trips).items():
        recent = [trip for trip in driver_trips if trip["period"] == "recent"]
        if not recent:
            continue
        total_km = sum(trip["trip_distance_km"] for trip in recent)
        in_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["in_zone_flag"])
        route_repeat_count = sum(trip["route_repeat_flag"] for trip in recent)
        new_destinations = {trip["end_grid"] for trip in recent if trip["new_destination_flag"]}
        in_zone_ratio = in_zone_km / total_km if total_km else 0.0
        route_repeat_ratio = route_repeat_count / len(recent) if recent else 0.0
        new_destination_count = len(new_destinations)
        zone_stability_score = max(0.0, min(100.0, 70 * in_zone_ratio + 30 * route_repeat_ratio - 5 * new_destination_count))
        rows.append(
            {
                "driver_id": driver_id,
                "zone_model_backend": "dbscan_density_cluster",
                "in_zone_ratio": round(in_zone_ratio, 4),
                "out_zone_ratio": round(1 - in_zone_ratio, 4),
                "route_repeat_ratio": round(route_repeat_ratio, 4),
                "new_destination_count": new_destination_count,
                "zone_stability_score": round(zone_stability_score, 2),
            }
        )
    return rows


def add_zone_features(trips: list[dict[str, Any]], eps: float = 0.012) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    zones = fit_zone_centers(trips, eps=eps)
    labeled = label_trips_with_zones(trips, zones, eps=eps)
    return labeled, build_zone_feature_table(labeled)

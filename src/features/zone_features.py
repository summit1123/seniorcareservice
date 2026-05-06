"""Lifestyle-zone feature generation."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from src.data.load_trips import group_by_driver


Point = tuple[float, float]
ZoneMap = dict[str, list[Point]]
BufferMap = dict[str, float]

EARTH_RADIUS_M = 6_371_000
MIN_ZONE_BUFFER_M = 500.0
MAX_ZONE_BUFFER_M = 2_000.0
BUFFER_PERCENTILE = 0.90


def grid_id(x: float, y: float, precision: int = 3) -> str:
    return f"{round(x, precision):.{precision}f}:{round(y, precision):.{precision}f}"


def distance(a: Point, b: Point) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def is_valid_point(point: Point) -> bool:
    return point[0] != 0 and point[1] != 0


def haversine_meters(a: Point, b: Point) -> float:
    lon1, lat1 = radians(a[0]), radians(a[1])
    lon2, lat2 = radians(b[0]), radians(b[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(value))


def close_to_any(point: Point, centers: list[Point], eps: float) -> bool:
    return any(distance(point, center) <= eps for center in centers)


def close_to_any_buffer(point: Point, centers: list[Point], buffer_m: float) -> bool:
    return any(haversine_meters(point, center) <= buffer_m for center in centers)


def nearest_center_distance_m(point: Point, centers: list[Point]) -> float:
    return min(haversine_meters(point, center) for center in centers)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def region_query(points: list[Point], point_index: int, eps: float) -> list[int]:
    point = points[point_index]
    return [idx for idx, candidate in enumerate(points) if distance(point, candidate) <= eps]


def dbscan_clusters(points: list[Point], eps: float = 0.012, min_samples: int = 3) -> list[list[Point]]:
    points = [point for point in points if is_valid_point(point)]
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
            for point in [(trip["start_gps_x"], trip["start_gps_y"]), (trip["end_gps_x"], trip["end_gps_y"])]:
                if is_valid_point(point):
                    baseline_points.append(point)
        zones[driver_id] = cluster_points(baseline_points, eps=eps, min_samples=min_samples)
    return zones


def fit_zone_buffers(trips: list[dict[str, Any]], zones: ZoneMap) -> BufferMap:
    buffers: BufferMap = {}
    for driver_id, driver_trips in group_by_driver(trips).items():
        centers = zones.get(driver_id, [])
        if not centers:
            buffers[driver_id] = 0.0
            continue
        distances: list[float] = []
        for trip in driver_trips:
            if trip["period"] != "baseline":
                continue
            for point in [(trip["start_gps_x"], trip["start_gps_y"]), (trip["end_gps_x"], trip["end_gps_y"])]:
                if is_valid_point(point):
                    distances.append(nearest_center_distance_m(point, centers))
        p90 = percentile(distances, BUFFER_PERCENTILE)
        buffers[driver_id] = max(MIN_ZONE_BUFFER_M, min(p90, MAX_ZONE_BUFFER_M))
    return buffers


def label_trips_with_zones(
    trips: list[dict[str, Any]],
    zones: ZoneMap,
    buffers: BufferMap,
    eps: float = 0.012,
) -> list[dict[str, Any]]:
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
        buffer_m = buffers.get(driver_id, 0.0)
        trip["zone_buffer_m"] = round(buffer_m, 2)
        if not centers:
            trip["core_zone_flag"] = 0
            trip["buffer_zone_flag"] = 0
            trip["outer_zone_flag"] = 0
            trip["in_zone_flag"] = 0
            trip["out_zone_flag"] = 0
            trip["route_repeat_flag"] = int(trip["route_key"] in baseline_routes.get(driver_id, set()))
            trip["new_destination_flag"] = 0
            continue
        start = (trip["start_gps_x"], trip["start_gps_y"])
        end = (trip["end_gps_x"], trip["end_gps_y"])
        start_in_zone = close_to_any_buffer(start, centers, MIN_ZONE_BUFFER_M)
        end_in_zone = close_to_any_buffer(end, centers, MIN_ZONE_BUFFER_M)
        start_in_buffer = close_to_any_buffer(start, centers, buffer_m)
        end_in_buffer = close_to_any_buffer(end, centers, buffer_m)
        core_zone = int(start_in_zone and end_in_zone)
        buffer_zone = int(not core_zone and start_in_buffer and end_in_buffer)
        outer_zone = int(not core_zone and not buffer_zone)
        trip["core_zone_flag"] = core_zone
        trip["buffer_zone_flag"] = buffer_zone
        trip["outer_zone_flag"] = outer_zone
        trip["in_zone_flag"] = int(core_zone or buffer_zone)
        trip["out_zone_flag"] = outer_zone
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
        core_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["core_zone_flag"])
        buffer_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["buffer_zone_flag"])
        in_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["in_zone_flag"])
        out_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["out_zone_flag"])
        route_repeat_count = sum(trip["route_repeat_flag"] for trip in recent)
        new_destinations = {trip["end_grid"] for trip in recent if trip["new_destination_flag"]}
        core_zone_ratio = core_zone_km / total_km if total_km else 0.0
        buffer_zone_ratio = buffer_zone_km / total_km if total_km else 0.0
        in_zone_ratio = in_zone_km / total_km if total_km else 0.0
        out_zone_ratio = out_zone_km / total_km if total_km else 0.0
        route_repeat_ratio = route_repeat_count / len(recent) if recent else 0.0
        new_destination_count = len(new_destinations)
        buffer_m = max((trip.get("zone_buffer_m", 0.0) for trip in recent), default=0.0)
        zone_stability_score = max(
            0.0,
            min(
                100.0,
                70 * core_zone_ratio + 20 * buffer_zone_ratio + 10 * route_repeat_ratio - 5 * new_destination_count,
            ),
        )
        rows.append(
            {
                "driver_id": driver_id,
                "zone_model_backend": "dbscan_density_cluster",
                "zone_buffer_m": round(buffer_m, 2),
                "core_zone_ratio": round(core_zone_ratio, 4),
                "buffer_zone_ratio": round(buffer_zone_ratio, 4),
                "in_zone_ratio": round(in_zone_ratio, 4),
                "out_zone_ratio": round(out_zone_ratio, 4),
                "route_repeat_ratio": round(route_repeat_ratio, 4),
                "new_destination_count": new_destination_count,
                "zone_stability_score": round(zone_stability_score, 2),
            }
        )
    return rows


def add_zone_features(trips: list[dict[str, Any]], eps: float = 0.012) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    zones = fit_zone_centers(trips, eps=eps)
    buffers = fit_zone_buffers(trips, zones)
    labeled = label_trips_with_zones(trips, zones, buffers, eps=eps)
    return labeled, build_zone_feature_table(labeled)

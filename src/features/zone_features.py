"""Lifestyle-zone feature generation."""

from __future__ import annotations

import json
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

from src.data.load_trips import group_by_driver
from src.features.driving_features import summarize_living_zone_outside_segment_safety


Point = tuple[float, float]
ZoneMap = dict[str, list[Point]]
BufferMap = dict[str, float]
DepartureThresholdMap = dict[str, dict[str, float | int]]
DistanceThresholdMap = dict[str, dict[str, float | int]]
FrequencyThresholdMap = dict[str, dict[str, float | int]]
DBSCANPointRecord = dict[str, Any]
DBSCANInputMap = dict[str, list[DBSCANPointRecord]]
DBSCANClusterResult = dict[str, Any]
CustomerDBSCANResultMap = dict[str, DBSCANClusterResult]
LivingZoneCriteria = dict[str, Any]

EARTH_RADIUS_M = 6_371_000
MIN_ZONE_BUFFER_M = 500.0
MAX_ZONE_BUFFER_M = 2_000.0
BUFFER_PERCENTILE = 0.90
DEFAULT_DBSCAN_PERIODS = ("baseline",)
POINT_ROLES = ("start", "end")
OBSERVATION_DAYS = {"baseline": 60, "recent": 30}
OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA = "start_or_end_distance_gt_living_zone_departure_p90_threshold_m"
LIVING_ZONE_RESULT_SCHEMA_VERSION = "customer-living-zone-result/v1"
LIVING_ZONE_RESULT_FIELDS = (
    "schema_version",
    "customer_id",
    "driver_id",
    "persona_type",
    "observation_period",
    "analysis_method",
    "living_zone",
    "privacy_filtered_features",
)
CUSTOMER_LIVING_ZONE_RECORDS_BY_ID_SCHEMA_VERSION = "customer-living-zone-result-by-id/v1"
CUSTOMER_LIVING_ZONE_CRITERIA_SCHEMA_VERSION = "customer-living-zone-criteria/v1"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CUSTOMER_LIVING_ZONE_RECORD_STORE_PATH = (
    ROOT / "data" / "processed" / "customer_living_zone_records_by_id.json"
)


def grid_id(x: float, y: float, precision: int = 3) -> str:
    return f"{round(x, precision):.{precision}f}:{round(y, precision):.{precision}f}"


def distance(a: Point, b: Point) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def is_valid_point(point: Point) -> bool:
    return point[0] != 0 and point[1] != 0


def trip_customer_id(trip: dict[str, Any]) -> str:
    return str(trip.get("customer_id") or trip["driver_id"])


def trip_period(trip: dict[str, Any]) -> str:
    return str(trip.get("period") or trip.get("observation_period") or "")


def trip_service_date(trip: dict[str, Any]) -> str:
    if trip.get("service_date"):
        return str(trip["service_date"])
    if trip.get("trip_start_dt"):
        return trip["trip_start_dt"].date().isoformat()
    return datetime.strptime(str(trip["trip_start_time"]), "%Y-%m-%d %H:%M:%S").date().isoformat()


def group_by_customer(trips: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trip in trips:
        grouped.setdefault(trip_customer_id(trip), []).append(trip)
    return grouped


def coerce_coordinate_pair(trip: dict[str, Any], role: str) -> Point:
    return (float(trip[f"{role}_gps_x"]), float(trip[f"{role}_gps_y"]))


def dbscan_point_record(trip: dict[str, Any], role: str) -> DBSCANPointRecord:
    point = coerce_coordinate_pair(trip, role)
    return {
        "customer_id": trip_customer_id(trip),
        "driver_id": str(trip["driver_id"]),
        "trip_id": str(trip.get("trip_id", "")),
        "period": trip_period(trip),
        "point_role": role,
        "longitude": point[0],
        "latitude": point[1],
        "dbscan_point": point,
    }


def build_customer_dbscan_input(
    trips: list[dict[str, Any]],
    periods: tuple[str, ...] | set[str] | None = DEFAULT_DBSCAN_PERIODS,
) -> DBSCANInputMap:
    """Convert trip start/end coordinates into customer-keyed DBSCAN input records."""
    allowed_periods = set(periods) if periods is not None else None
    inputs: DBSCANInputMap = {}
    for trip in trips:
        period = trip_period(trip)
        if allowed_periods is not None and period not in allowed_periods:
            continue
        customer_id = trip_customer_id(trip)
        for role in POINT_ROLES:
            record = dbscan_point_record(trip, role)
            if is_valid_point(record["dbscan_point"]):
                inputs.setdefault(customer_id, []).append(record)
    return inputs


def dbscan_points(records: list[DBSCANPointRecord]) -> list[Point]:
    return [record["dbscan_point"] for record in records]


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


def living_zone_segment_distances(
    start: Point,
    end: Point,
    centers: list[Point],
) -> dict[str, float]:
    """Return start/end distance from the nearest living-zone center."""
    if not centers:
        return {
            "start_living_zone_distance_m": 0.0,
            "end_living_zone_distance_m": 0.0,
            "living_zone_segment_max_distance_m": 0.0,
        }

    start_distance_m = nearest_center_distance_m(start, centers) if is_valid_point(start) else 0.0
    end_distance_m = nearest_center_distance_m(end, centers) if is_valid_point(end) else 0.0
    return {
        "start_living_zone_distance_m": round(start_distance_m, 2),
        "end_living_zone_distance_m": round(end_distance_m, 2),
        "living_zone_segment_max_distance_m": round(max(start_distance_m, end_distance_m), 2),
    }


def build_customer_living_zone_criteria(
    customer_id: str,
    centers: list[Point],
    *,
    departure_threshold: dict[str, float | int] | None = None,
    cluster_summaries: list[dict[str, Any]] | None = None,
) -> LivingZoneCriteria:
    """Define the customer-specific living-zone area used to judge trip segments.

    The criteria object is deliberately local-data only: it can include derived
    center coordinates for UI and deterministic trip labeling, but should not be
    sent to external LLM requests.
    """
    threshold = departure_threshold or {}
    departure_threshold_m = float(threshold.get("living_zone_departure_p90_threshold_m", 0.0))
    return {
        "schema_version": CUSTOMER_LIVING_ZONE_CRITERIA_SCHEMA_VERSION,
        "customer_id": customer_id,
        "criteria": OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA,
        "core_radius_m": MIN_ZONE_BUFFER_M,
        "buffer_radius_m": round(departure_threshold_m, 2),
        "departure_p90_raw_m": float(threshold.get("living_zone_departure_p90_raw_m", 0.0)),
        "departure_p90_threshold_m": round(departure_threshold_m, 2),
        "departure_threshold_sample_count": int(
            threshold.get("living_zone_departure_threshold_sample_count", 0)
        ),
        "departure_threshold_percentile": float(
            threshold.get("living_zone_departure_threshold_percentile", BUFFER_PERCENTILE)
        ),
        "centers": [
            {
                "center_longitude": round(center[0], 6),
                "center_latitude": round(center[1], 6),
            }
            for center in centers
        ],
        "clusters": cluster_summaries or [],
    }


def build_customer_living_zone_criteria_map(
    zones: ZoneMap,
    departure_thresholds: DepartureThresholdMap,
    *,
    dbscan_results: CustomerDBSCANResultMap | None = None,
) -> dict[str, LivingZoneCriteria]:
    """Build customer-keyed living-zone criteria from DBSCAN centers and P90 buffers."""
    criteria_by_customer: dict[str, LivingZoneCriteria] = {}
    for customer_id in sorted(set(zones) | set(departure_thresholds)):
        clusters = []
        if dbscan_results and customer_id in dbscan_results:
            clusters = [
                {key: value for key, value in cluster.items() if key != "points"}
                for cluster in dbscan_results[customer_id].get("clusters", [])
            ]
        criteria_by_customer[customer_id] = build_customer_living_zone_criteria(
            customer_id,
            zones.get(customer_id, []),
            departure_threshold=departure_thresholds.get(customer_id, {}),
            cluster_summaries=clusters,
        )
    return criteria_by_customer


def classify_trip_against_living_zone(
    trip: dict[str, Any],
    criteria: LivingZoneCriteria,
) -> dict[str, Any]:
    """Classify one trip segment as core, buffer, or outside the customer's living zone."""
    centers = [
        (float(center["center_longitude"]), float(center["center_latitude"]))
        for center in criteria.get("centers", [])
    ]
    buffer_m = float(criteria.get("buffer_radius_m", 0.0))
    start = coerce_coordinate_pair(trip, "start")
    end = coerce_coordinate_pair(trip, "end")

    if not centers:
        return {
            "core_zone_flag": 0,
            "buffer_zone_flag": 0,
            "outer_zone_flag": 0,
            "in_zone_flag": 0,
            "out_zone_flag": 0,
            "start_living_zone_distance_m": 0.0,
            "end_living_zone_distance_m": 0.0,
            "living_zone_segment_max_distance_m": 0.0,
            "living_zone_outside_segment_flag": 0,
            "living_zone_outside_segment_criteria": str(
                criteria.get("criteria", OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)
            ),
            "living_zone_outside_threshold_m": round(buffer_m, 2),
        }

    segment_distances = living_zone_segment_distances(start, end, centers)
    start_in_core = close_to_any_buffer(start, centers, MIN_ZONE_BUFFER_M)
    end_in_core = close_to_any_buffer(end, centers, MIN_ZONE_BUFFER_M)
    start_in_buffer = close_to_any_buffer(start, centers, buffer_m)
    end_in_buffer = close_to_any_buffer(end, centers, buffer_m)
    core_zone = int(start_in_core and end_in_core)
    buffer_zone = int(not core_zone and start_in_buffer and end_in_buffer)
    outer_zone = int(not core_zone and not buffer_zone)
    outside_segment = int(segment_distances["living_zone_segment_max_distance_m"] > buffer_m)

    return {
        "core_zone_flag": core_zone,
        "buffer_zone_flag": buffer_zone,
        "outer_zone_flag": outer_zone,
        "in_zone_flag": int(core_zone or buffer_zone),
        "out_zone_flag": outer_zone,
        **segment_distances,
        "living_zone_outside_segment_flag": outside_segment,
        "living_zone_outside_segment_criteria": str(
            criteria.get("criteria", OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)
        ),
        "living_zone_outside_threshold_m": round(buffer_m, 2),
    }


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


def cluster_radius_metrics(points: list[Point], center: Point | None = None) -> dict[str, float]:
    """Measure living-zone radius from center-to-cluster-point distances."""
    if not points:
        return {
            "avg_radius_m": 0.0,
            "median_radius_m": 0.0,
            "p90_radius_m": 0.0,
            "max_radius_m": 0.0,
            "radius_metric_m": 0.0,
        }

    zone_center = center or cluster_center(points)
    distances_m = [haversine_meters(point, zone_center) for point in points]
    p90_radius_m = round(percentile(distances_m, BUFFER_PERCENTILE), 2)
    return {
        "avg_radius_m": round(sum(distances_m) / len(distances_m), 2),
        "median_radius_m": round(percentile(distances_m, 0.50), 2),
        "p90_radius_m": p90_radius_m,
        "max_radius_m": round(max(distances_m), 2),
        "radius_metric_m": p90_radius_m,
    }


def cluster_boundary_metrics(points: list[Point], center: Point | None = None) -> dict[str, float]:
    """Measure living-zone boundary and outer extent from clustered GPS distribution."""
    if not points:
        return {
            "boundary_min_longitude": 0.0,
            "boundary_max_longitude": 0.0,
            "boundary_min_latitude": 0.0,
            "boundary_max_latitude": 0.0,
            "boundary_width_m": 0.0,
            "boundary_height_m": 0.0,
            "boundary_area_km2": 0.0,
            "outer_extent_radius_m": 0.0,
        }

    zone_center = center or cluster_center(points)
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    min_longitude = min(longitudes)
    max_longitude = max(longitudes)
    min_latitude = min(latitudes)
    max_latitude = max(latitudes)
    midpoint_latitude = (min_latitude + max_latitude) / 2
    midpoint_longitude = (min_longitude + max_longitude) / 2
    width_m = haversine_meters((min_longitude, midpoint_latitude), (max_longitude, midpoint_latitude))
    height_m = haversine_meters((midpoint_longitude, min_latitude), (midpoint_longitude, max_latitude))
    outer_extent_radius_m = max(haversine_meters(point, zone_center) for point in points)

    return {
        "boundary_min_longitude": round(min_longitude, 6),
        "boundary_max_longitude": round(max_longitude, 6),
        "boundary_min_latitude": round(min_latitude, 6),
        "boundary_max_latitude": round(max_latitude, 6),
        "boundary_width_m": round(width_m, 2),
        "boundary_height_m": round(height_m, 2),
        "boundary_area_km2": round((width_m * height_m) / 1_000_000, 4),
        "outer_extent_radius_m": round(outer_extent_radius_m, 2),
    }


def region_query(points: list[Point], point_index: int, eps: float) -> list[int]:
    point = points[point_index]
    return [idx for idx, candidate in enumerate(points) if distance(point, candidate) <= eps]


def dbscan_labels(points: list[Point], eps: float = 0.012, min_samples: int = 3) -> list[int]:
    """Return DBSCAN labels for each point, using -1 for noise."""
    labels: list[int | None] = [None for _ in points]
    cluster_id = 0

    for point_index in range(len(points)):
        if labels[point_index] is not None:
            continue
        if not is_valid_point(points[point_index]):
            labels[point_index] = -1
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

    return [label if label is not None else -1 for label in labels]


def dbscan_clusters(points: list[Point], eps: float = 0.012, min_samples: int = 3) -> list[list[Point]]:
    labels = dbscan_labels(points, eps=eps, min_samples=min_samples)
    cluster_count = max((label for label in labels if label >= 0), default=-1) + 1
    clusters: list[list[Point]] = [[] for _ in range(cluster_count)]
    for point, label in zip(points, labels):
        if label >= 0:
            clusters[label].append(point)
    return clusters


def cluster_points(points: list[Point], eps: float = 0.012, min_samples: int = 3) -> list[Point]:
    return [cluster_center(cluster) for cluster in dbscan_clusters(points, eps=eps, min_samples=min_samples)]


def cluster_center(points: list[Point]) -> Point:
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def summarize_cluster_records(
    cluster_id: int,
    cluster_records: list[DBSCANPointRecord],
    total_point_count: int,
    total_visit_count: int,
) -> dict[str, Any]:
    """Build UI/decision-ready summary metrics for one DBSCAN living-zone cluster."""
    points = dbscan_points(cluster_records)
    center = cluster_center(points)
    radius_metrics = cluster_radius_metrics(points, center=center)
    boundary_metrics = cluster_boundary_metrics(points, center=center)
    visit_count = len({record["trip_id"] for record in cluster_records if record.get("trip_id")})
    role_counts = {role: sum(1 for record in cluster_records if record["point_role"] == role) for role in POINT_ROLES}
    point_frequency = len(cluster_records) / total_point_count if total_point_count else 0.0
    visit_frequency = visit_count / total_visit_count if total_visit_count else 0.0

    return {
        "cluster_id": cluster_id,
        "center_longitude": round(center[0], 6),
        "center_latitude": round(center[1], 6),
        "point_count": len(cluster_records),
        "visit_count": visit_count,
        "point_frequency": round(point_frequency, 4),
        "visit_frequency": round(visit_frequency, 4),
        "start_point_count": role_counts["start"],
        "end_point_count": role_counts["end"],
        **radius_metrics,
        **boundary_metrics,
    }


def run_customer_dbscan(
    records: list[DBSCANPointRecord],
    eps: float = 0.012,
    min_samples: int = 3,
) -> DBSCANClusterResult:
    """Run DBSCAN for one customer's point records and keep both clusters and noise."""
    labels = dbscan_labels(dbscan_points(records), eps=eps, min_samples=min_samples)
    annotated_records: list[DBSCANPointRecord] = []
    clusters_by_id: dict[int, list[DBSCANPointRecord]] = {}
    noise_points: list[DBSCANPointRecord] = []

    for record, label in zip(records, labels):
        annotated = dict(record)
        annotated["dbscan_cluster_id"] = label
        annotated["dbscan_is_noise"] = label == -1
        annotated_records.append(annotated)
        if label == -1:
            noise_points.append(annotated)
        else:
            clusters_by_id.setdefault(label, []).append(annotated)

    total_visit_count = len({record["trip_id"] for record in annotated_records if record.get("trip_id")})
    clusters = []
    for cluster_id in sorted(clusters_by_id):
        cluster_records = clusters_by_id[cluster_id]
        summary = summarize_cluster_records(
            cluster_id=cluster_id,
            cluster_records=cluster_records,
            total_point_count=len(annotated_records),
            total_visit_count=total_visit_count,
        )
        clusters.append(
            {
                **summary,
                "points": cluster_records,
            }
        )

    return {
        "point_count": len(annotated_records),
        "cluster_count": len(clusters),
        "noise_count": len(noise_points),
        "clusters": clusters,
        "noise_points": noise_points,
        "points": annotated_records,
    }


def fit_customer_dbscan_results(
    trips: list[dict[str, Any]],
    eps: float = 0.012,
    min_samples: int = 3,
    periods: tuple[str, ...] | set[str] | None = DEFAULT_DBSCAN_PERIODS,
) -> CustomerDBSCANResultMap:
    """Run DBSCAN separately for each customer."""
    return {
        customer_id: run_customer_dbscan(records, eps=eps, min_samples=min_samples)
        for customer_id, records in build_customer_dbscan_input(trips, periods=periods).items()
    }


def fit_zone_centers(trips: list[dict[str, Any]], eps: float = 0.012, min_samples: int = 3) -> ZoneMap:
    return zone_centers_from_dbscan_results(fit_customer_dbscan_results(trips, eps=eps, min_samples=min_samples))


def zone_centers_from_dbscan_results(dbscan_results: CustomerDBSCANResultMap) -> ZoneMap:
    zones: ZoneMap = {}
    for customer_id, result in dbscan_results.items():
        zones[customer_id] = [
            (cluster["center_longitude"], cluster["center_latitude"])
            for cluster in result["clusters"]
        ]
    return zones


def fit_zone_departure_thresholds(trips: list[dict[str, Any]], zones: ZoneMap) -> DepartureThresholdMap:
    """Calculate customer-level P90 thresholds for baseline destination departure distance."""
    thresholds: DepartureThresholdMap = {}
    for customer_id, customer_trips in group_by_customer(trips).items():
        centers = zones.get(customer_id, [])
        if not centers:
            thresholds[customer_id] = {
                "living_zone_departure_p90_raw_m": 0.0,
                "living_zone_departure_p90_threshold_m": 0.0,
                "living_zone_departure_threshold_sample_count": 0,
                "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
            }
            continue
        distances: list[float] = []
        for trip in customer_trips:
            if trip_period(trip) != "baseline":
                continue
            destination = coerce_coordinate_pair(trip, "end")
            if is_valid_point(destination):
                distances.append(nearest_center_distance_m(destination, centers))
        p90 = percentile(distances, BUFFER_PERCENTILE)
        thresholds[customer_id] = {
            "living_zone_departure_p90_raw_m": round(p90, 2),
            "living_zone_departure_p90_threshold_m": round(max(MIN_ZONE_BUFFER_M, min(p90, MAX_ZONE_BUFFER_M)), 2)
            if distances
            else 0.0,
            "living_zone_departure_threshold_sample_count": len(distances),
            "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
        }
    return thresholds


def fit_customer_trip_distance_thresholds(trips: list[dict[str, Any]]) -> DistanceThresholdMap:
    """Calculate customer-level P90 thresholds from baseline trip distances."""
    thresholds: DistanceThresholdMap = {}
    for customer_id, customer_trips in group_by_customer(trips).items():
        distances = [
            float(trip["trip_distance_km"])
            for trip in customer_trips
            if trip_period(trip) == "baseline" and float(trip.get("trip_distance_km", 0.0)) > 0.0
        ]
        p90 = percentile(distances, BUFFER_PERCENTILE)
        thresholds[customer_id] = {
            "baseline_trip_distance_p90_km": round(p90, 2) if distances else 0.0,
            "baseline_trip_distance_threshold_sample_count": len(distances),
            "baseline_trip_distance_threshold_percentile": BUFFER_PERCENTILE,
        }
    return thresholds


def fit_customer_movement_frequency_thresholds(trips: list[dict[str, Any]]) -> FrequencyThresholdMap:
    """Calculate customer-level P90 thresholds from baseline daily trip frequency."""
    thresholds: FrequencyThresholdMap = {}
    for customer_id, customer_trips in group_by_customer(trips).items():
        daily_trip_counts: dict[str, int] = {}
        for trip in customer_trips:
            if trip_period(trip) != "baseline":
                continue
            service_date = trip_service_date(trip)
            daily_trip_counts[service_date] = daily_trip_counts.get(service_date, 0) + 1

        frequency_values = [float(count) for count in daily_trip_counts.values()]
        p90 = percentile(frequency_values, BUFFER_PERCENTILE)
        thresholds[customer_id] = {
            "baseline_movement_frequency_p90_per_day": round(p90, 4) if frequency_values else 0.0,
            "baseline_movement_frequency_threshold_sample_count": len(frequency_values),
            "baseline_movement_frequency_threshold_percentile": BUFFER_PERCENTILE,
        }
    return thresholds


def fit_zone_buffers(trips: list[dict[str, Any]], zones: ZoneMap) -> BufferMap:
    thresholds = fit_zone_departure_thresholds(trips, zones)
    return {
        customer_id: float(threshold["living_zone_departure_p90_threshold_m"])
        for customer_id, threshold in thresholds.items()
    }


def zone_buffers_from_departure_thresholds(thresholds: DepartureThresholdMap) -> BufferMap:
    return {
        customer_id: float(threshold["living_zone_departure_p90_threshold_m"])
        for customer_id, threshold in thresholds.items()
    }


def label_trips_with_zones(
    trips: list[dict[str, Any]],
    zones: ZoneMap,
    buffers: BufferMap,
    departure_thresholds: DepartureThresholdMap | None = None,
    distance_thresholds: DistanceThresholdMap | None = None,
    eps: float = 0.012,
) -> list[dict[str, Any]]:
    baseline_destinations: dict[str, set[str]] = {}
    baseline_routes: dict[str, set[str]] = {}
    living_zone_criteria_by_customer = build_customer_living_zone_criteria_map(
        zones,
        departure_thresholds or {
            customer_id: {
                "living_zone_departure_p90_threshold_m": buffer_m,
                "living_zone_departure_p90_raw_m": buffer_m,
                "living_zone_departure_threshold_sample_count": 0,
                "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
            }
            for customer_id, buffer_m in buffers.items()
        },
    )

    for trip in trips:
        customer_id = trip_customer_id(trip)
        start = coerce_coordinate_pair(trip, "start")
        end = coerce_coordinate_pair(trip, "end")
        start_grid = grid_id(start[0], start[1])
        end_grid = grid_id(end[0], end[1])
        route_key = f"{start_grid}->{end_grid}"
        trip["start_grid"] = start_grid
        trip["end_grid"] = end_grid
        trip["route_key"] = route_key
        if trip_period(trip) == "baseline":
            baseline_destinations.setdefault(customer_id, set()).add(end_grid)
            baseline_routes.setdefault(customer_id, set()).add(route_key)

    for trip in trips:
        customer_id = trip_customer_id(trip)
        centers = zones.get(customer_id, [])
        buffer_m = buffers.get(customer_id, 0.0)
        threshold = (departure_thresholds or {}).get(customer_id, {})
        distance_threshold = (distance_thresholds or {}).get(customer_id, {})
        trip["zone_buffer_m"] = round(buffer_m, 2)
        trip["living_zone_departure_p90_raw_m"] = threshold.get("living_zone_departure_p90_raw_m", round(buffer_m, 2))
        trip["living_zone_departure_p90_threshold_m"] = threshold.get(
            "living_zone_departure_p90_threshold_m",
            round(buffer_m, 2),
        )
        trip["living_zone_departure_threshold_sample_count"] = threshold.get(
            "living_zone_departure_threshold_sample_count",
            0,
        )
        trip["living_zone_departure_threshold_percentile"] = threshold.get(
            "living_zone_departure_threshold_percentile",
            BUFFER_PERCENTILE,
        )
        trip["baseline_trip_distance_p90_km"] = distance_threshold.get("baseline_trip_distance_p90_km", 0.0)
        trip["baseline_trip_distance_threshold_sample_count"] = distance_threshold.get(
            "baseline_trip_distance_threshold_sample_count",
            0,
        )
        trip["baseline_trip_distance_threshold_percentile"] = distance_threshold.get(
            "baseline_trip_distance_threshold_percentile",
            BUFFER_PERCENTILE,
        )
        living_zone_criteria = living_zone_criteria_by_customer.get(
            customer_id,
            build_customer_living_zone_criteria(
                customer_id,
                centers,
                departure_threshold=threshold,
            ),
        )
        trip["living_zone_outside_segment_criteria"] = living_zone_criteria["criteria"]
        trip["living_zone_outside_threshold_m"] = round(
            float(living_zone_criteria["departure_p90_threshold_m"]),
            2,
        )
        if not centers:
            trip.update(classify_trip_against_living_zone(trip, living_zone_criteria))
            trip["route_repeat_flag"] = int(trip["route_key"] in baseline_routes.get(customer_id, set()))
            trip["new_destination_flag"] = 0
            continue
        trip.update(classify_trip_against_living_zone(trip, living_zone_criteria))
        trip["route_repeat_flag"] = int(trip["route_key"] in baseline_routes.get(customer_id, set()))
        trip["new_destination_flag"] = int(trip["end_grid"] not in baseline_destinations.get(customer_id, set()))
    return trips


def build_zone_feature_table(
    trips: list[dict[str, Any]],
    dbscan_results: CustomerDBSCANResultMap | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dbscan_results = dbscan_results or fit_customer_dbscan_results(trips)
    for driver_id, driver_trips in group_by_driver(trips).items():
        customer_id = trip_customer_id(driver_trips[0])
        clusters = dbscan_results.get(customer_id, {}).get("clusters", [])
        cluster_summaries = [
            {key: value for key, value in cluster.items() if key != "points"}
            for cluster in sorted(clusters, key=lambda cluster: (-cluster["visit_frequency"], cluster["cluster_id"]))
        ]
        primary_cluster = cluster_summaries[0] if cluster_summaries else {}
        recent = [trip for trip in driver_trips if trip_period(trip) == "recent"]
        if not recent:
            continue
        total_km = sum(trip["trip_distance_km"] for trip in recent)
        core_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["core_zone_flag"])
        buffer_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["buffer_zone_flag"])
        in_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["in_zone_flag"])
        out_zone_km = sum(trip["trip_distance_km"] for trip in recent if trip["out_zone_flag"])
        outside_segment_trips = [trip for trip in recent if int(trip.get("living_zone_outside_segment_flag", 0))]
        outside_segment_km = sum(trip["trip_distance_km"] for trip in outside_segment_trips)
        outside_segment_safety = summarize_living_zone_outside_segment_safety(recent)
        route_repeat_count = sum(trip["route_repeat_flag"] for trip in recent)
        new_destinations = {trip["end_grid"] for trip in recent if trip["new_destination_flag"]}
        core_zone_ratio = core_zone_km / total_km if total_km else 0.0
        buffer_zone_ratio = buffer_zone_km / total_km if total_km else 0.0
        in_zone_ratio = in_zone_km / total_km if total_km else 0.0
        out_zone_ratio = out_zone_km / total_km if total_km else 0.0
        outside_segment_ratio = len(outside_segment_trips) / len(recent) if recent else 0.0
        outside_segment_distance_ratio = outside_segment_km / total_km if total_km else 0.0
        route_repeat_ratio = route_repeat_count / len(recent) if recent else 0.0
        new_destination_count = len(new_destinations)
        buffer_m = max((trip.get("zone_buffer_m", 0.0) for trip in recent), default=0.0)
        departure_threshold_m = max(
            (float(trip.get("living_zone_departure_p90_threshold_m", 0.0)) for trip in recent),
            default=0.0,
        )
        departure_raw_p90_m = max(
            (float(trip.get("living_zone_departure_p90_raw_m", 0.0)) for trip in recent),
            default=0.0,
        )
        departure_threshold_sample_count = max(
            (int(trip.get("living_zone_departure_threshold_sample_count", 0)) for trip in recent),
            default=0,
        )
        distance_p90_km = max(
            (float(trip.get("baseline_trip_distance_p90_km", 0.0)) for trip in recent),
            default=0.0,
        )
        distance_threshold_sample_count = max(
            (int(trip.get("baseline_trip_distance_threshold_sample_count", 0)) for trip in recent),
            default=0,
        )
        zone_stability_score = max(
            0.0,
            min(
                100.0,
                70 * core_zone_ratio + 20 * buffer_zone_ratio + 10 * route_repeat_ratio - 5 * new_destination_count,
            ),
        )
        rows.append(
            {
                "customer_id": customer_id,
                "driver_id": driver_id,
                "persona_type": str(driver_trips[0].get("persona_type", "")),
                "zone_model_backend": "dbscan_density_cluster",
                "zone_buffer_m": round(buffer_m, 2),
                "living_zone_departure_p90_raw_m": round(departure_raw_p90_m, 2),
                "living_zone_departure_p90_threshold_m": round(departure_threshold_m, 2),
                "living_zone_departure_threshold_sample_count": departure_threshold_sample_count,
                "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
                "baseline_trip_distance_p90_km": round(distance_p90_km, 2),
                "baseline_trip_distance_threshold_sample_count": distance_threshold_sample_count,
                "baseline_trip_distance_threshold_percentile": BUFFER_PERCENTILE,
                "living_zone_cluster_count": len(cluster_summaries),
                "primary_zone_center_longitude": primary_cluster.get("center_longitude", ""),
                "primary_zone_center_latitude": primary_cluster.get("center_latitude", ""),
                "primary_zone_visit_frequency": primary_cluster.get("visit_frequency", 0.0),
                "primary_zone_radius_m": primary_cluster.get("radius_metric_m", 0.0),
                "primary_zone_p90_radius_m": primary_cluster.get("p90_radius_m", 0.0),
                "primary_zone_outer_extent_radius_m": primary_cluster.get("outer_extent_radius_m", 0.0),
                "primary_zone_boundary_area_km2": primary_cluster.get("boundary_area_km2", 0.0),
                "primary_zone_boundary_width_m": primary_cluster.get("boundary_width_m", 0.0),
                "primary_zone_boundary_height_m": primary_cluster.get("boundary_height_m", 0.0),
                "living_zone_clusters_json": json.dumps(cluster_summaries, ensure_ascii=True, separators=(",", ":")),
                "core_zone_ratio": round(core_zone_ratio, 4),
                "buffer_zone_ratio": round(buffer_zone_ratio, 4),
                "in_zone_ratio": round(in_zone_ratio, 4),
                "out_zone_ratio": round(out_zone_ratio, 4),
                "living_zone_outside_segment_criteria": OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA,
                "living_zone_outside_segment_count": len(outside_segment_trips),
                "living_zone_outside_segment_ratio": round(outside_segment_ratio, 4),
                "living_zone_outside_segment_km": round(outside_segment_km, 2),
                "living_zone_outside_segment_distance_ratio": round(outside_segment_distance_ratio, 4),
                **outside_segment_safety,
                "route_repeat_ratio": round(route_repeat_ratio, 4),
                "new_destination_count": new_destination_count,
                "zone_stability_score": round(zone_stability_score, 2),
            }
        )
    return rows


def build_movement_history_table(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate customer-period movement inputs for zone departure, distance, and frequency checks."""
    rows: list[dict[str, Any]] = []
    frequency_thresholds = fit_customer_movement_frequency_thresholds(trips)
    for customer_id, customer_trips in sorted(group_by_customer(trips).items()):
        frequency_threshold = frequency_thresholds.get(customer_id, {})
        periods = sorted({trip_period(trip) for trip in customer_trips if trip_period(trip)})
        for period in periods:
            period_trips = [trip for trip in customer_trips if trip_period(trip) == period]
            if not period_trips:
                continue

            driver_id = str(period_trips[0]["driver_id"])
            persona_type = str(period_trips[0].get("persona_type", ""))
            observation_days = OBSERVATION_DAYS.get(period, len({trip_service_date(trip) for trip in period_trips}))
            active_days = len({trip_service_date(trip) for trip in period_trips})
            trip_count = len(period_trips)
            total_distance_km = sum(float(trip["trip_distance_km"]) for trip in period_trips)
            out_zone_trips = [trip for trip in period_trips if int(trip.get("out_zone_flag", 0))]
            outside_segment_trips = [
                trip for trip in period_trips if int(trip.get("living_zone_outside_segment_flag", 0))
            ]
            out_zone_trip_count = len(out_zone_trips)
            out_zone_distance_km = sum(float(trip["trip_distance_km"]) for trip in out_zone_trips)
            outside_segment_distance_km = sum(float(trip["trip_distance_km"]) for trip in outside_segment_trips)
            outside_segment_safety = summarize_living_zone_outside_segment_safety(period_trips)
            route_repeat_count = sum(int(trip.get("route_repeat_flag", 0)) for trip in period_trips)
            new_destinations = {trip["end_grid"] for trip in period_trips if int(trip.get("new_destination_flag", 0))}
            departure_threshold_m = max(
                (float(trip.get("living_zone_departure_p90_threshold_m", 0.0)) for trip in period_trips),
                default=0.0,
            )
            departure_raw_p90_m = max(
                (float(trip.get("living_zone_departure_p90_raw_m", 0.0)) for trip in period_trips),
                default=0.0,
            )
            departure_threshold_sample_count = max(
                (int(trip.get("living_zone_departure_threshold_sample_count", 0)) for trip in period_trips),
                default=0,
            )
            distance_p90_km = max(
                (float(trip.get("baseline_trip_distance_p90_km", 0.0)) for trip in period_trips),
                default=0.0,
            )
            distance_threshold_sample_count = max(
                (int(trip.get("baseline_trip_distance_threshold_sample_count", 0)) for trip in period_trips),
                default=0,
            )

            rows.append(
                {
                    "customer_id": customer_id,
                    "driver_id": driver_id,
                    "persona_type": persona_type,
                    "period": period,
                    "observation_days": observation_days,
                    "active_day_count": active_days,
                    "trip_count": trip_count,
                    "trip_frequency_per_day": round(trip_count / observation_days, 4) if observation_days else 0.0,
                    "trip_frequency_per_active_day": round(trip_count / active_days, 4) if active_days else 0.0,
                    "baseline_movement_frequency_p90_per_day": frequency_threshold.get(
                        "baseline_movement_frequency_p90_per_day",
                        0.0,
                    ),
                    "baseline_movement_frequency_threshold_sample_count": frequency_threshold.get(
                        "baseline_movement_frequency_threshold_sample_count",
                        0,
                    ),
                    "baseline_movement_frequency_threshold_percentile": frequency_threshold.get(
                        "baseline_movement_frequency_threshold_percentile",
                        BUFFER_PERCENTILE,
                    ),
                    "total_distance_km": round(total_distance_km, 2),
                    "avg_trip_distance_km": round(total_distance_km / trip_count, 2) if trip_count else 0.0,
                    "avg_daily_distance_km": round(total_distance_km / observation_days, 4) if observation_days else 0.0,
                    "core_zone_trip_count": sum(int(trip.get("core_zone_flag", 0)) for trip in period_trips),
                    "buffer_zone_trip_count": sum(int(trip.get("buffer_zone_flag", 0)) for trip in period_trips),
                    "in_zone_trip_count": sum(int(trip.get("in_zone_flag", 0)) for trip in period_trips),
                    "out_zone_trip_count": out_zone_trip_count,
                    "out_zone_trip_ratio": round(out_zone_trip_count / trip_count, 4) if trip_count else 0.0,
                    "out_zone_distance_km": round(out_zone_distance_km, 2),
                    "out_zone_distance_ratio": round(out_zone_distance_km / total_distance_km, 4) if total_distance_km else 0.0,
                    "living_zone_outside_segment_criteria": OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA,
                    "living_zone_outside_segment_count": len(outside_segment_trips),
                    "living_zone_outside_segment_ratio": round(len(outside_segment_trips) / trip_count, 4)
                    if trip_count
                    else 0.0,
                    "living_zone_outside_segment_km": round(outside_segment_distance_km, 2),
                    "living_zone_outside_segment_distance_ratio": round(
                        outside_segment_distance_km / total_distance_km,
                        4,
                    )
                    if total_distance_km
                    else 0.0,
                    **outside_segment_safety,
                    "living_zone_departure_p90_raw_m": round(departure_raw_p90_m, 2),
                    "living_zone_departure_p90_threshold_m": round(departure_threshold_m, 2),
                    "living_zone_departure_threshold_sample_count": departure_threshold_sample_count,
                    "living_zone_departure_threshold_percentile": BUFFER_PERCENTILE,
                    "baseline_trip_distance_p90_km": round(distance_p90_km, 2),
                    "baseline_trip_distance_threshold_sample_count": distance_threshold_sample_count,
                    "baseline_trip_distance_threshold_percentile": BUFFER_PERCENTILE,
                    "living_zone_departure_count": out_zone_trip_count,
                    "living_zone_departure_distance_km": round(out_zone_distance_km, 2),
                    "living_zone_departure_frequency_per_day": round(out_zone_trip_count / observation_days, 4)
                    if observation_days
                    else 0.0,
                    "route_repeat_count": route_repeat_count,
                    "route_repeat_ratio": round(route_repeat_count / trip_count, 4) if trip_count else 0.0,
                    "new_destination_count": len(new_destinations),
                }
            )
    return rows


def build_customer_living_zone_records(
    zone_rows: list[dict[str, Any]],
    *,
    dbscan_eps: float = 0.012,
    dbscan_min_samples: int = 3,
) -> list[dict[str, Any]]:
    """Convert flat zone feature rows into customer-level saved living-zone records.

    The record is the local UI/agent contract.  It may keep local join ids and
    derived center coordinates for product screens, while
    ``privacy_filtered_features`` is the only envelope eligible for LLM report
    prompts.
    """
    records: list[dict[str, Any]] = []
    for row in zone_rows:
        clusters = json.loads(str(row.get("living_zone_clusters_json") or "[]"))
        criteria = build_customer_living_zone_criteria(
            str(row.get("customer_id", "")),
            [
                (float(cluster["center_longitude"]), float(cluster["center_latitude"]))
                for cluster in clusters
                if cluster.get("center_longitude") not in ("", None)
                and cluster.get("center_latitude") not in ("", None)
            ],
            departure_threshold={
                "living_zone_departure_p90_raw_m": float(row.get("living_zone_departure_p90_raw_m", 0.0)),
                "living_zone_departure_p90_threshold_m": float(
                    row.get("living_zone_departure_p90_threshold_m", 0.0)
                ),
                "living_zone_departure_threshold_sample_count": int(
                    row.get("living_zone_departure_threshold_sample_count", 0)
                ),
                "living_zone_departure_threshold_percentile": float(
                    row.get("living_zone_departure_threshold_percentile", BUFFER_PERCENTILE)
                ),
            },
            cluster_summaries=clusters,
        )
        living_zone = {
            "cluster_count": int(row.get("living_zone_cluster_count", 0)),
            "customer_living_zone_criteria": criteria,
            "primary_zone": {
                "center_longitude": row.get("primary_zone_center_longitude", ""),
                "center_latitude": row.get("primary_zone_center_latitude", ""),
                "visit_frequency": float(row.get("primary_zone_visit_frequency", 0.0)),
                "radius_metric_m": float(row.get("primary_zone_radius_m", 0.0)),
                "p90_radius_m": float(row.get("primary_zone_p90_radius_m", 0.0)),
                "outer_extent_radius_m": float(row.get("primary_zone_outer_extent_radius_m", 0.0)),
                "boundary_area_km2": float(row.get("primary_zone_boundary_area_km2", 0.0)),
                "boundary_width_m": float(row.get("primary_zone_boundary_width_m", 0.0)),
                "boundary_height_m": float(row.get("primary_zone_boundary_height_m", 0.0)),
            },
            "buffer": {
                "zone_buffer_m": float(row.get("zone_buffer_m", 0.0)),
                "departure_p90_raw_m": float(row.get("living_zone_departure_p90_raw_m", 0.0)),
                "departure_p90_threshold_m": float(row.get("living_zone_departure_p90_threshold_m", 0.0)),
                "departure_threshold_sample_count": int(
                    row.get("living_zone_departure_threshold_sample_count", 0)
                ),
                "departure_threshold_percentile": float(
                    row.get("living_zone_departure_threshold_percentile", BUFFER_PERCENTILE)
                ),
            },
            "baseline_thresholds": {
                "trip_distance_p90_km": float(row.get("baseline_trip_distance_p90_km", 0.0)),
                "trip_distance_threshold_sample_count": int(
                    row.get("baseline_trip_distance_threshold_sample_count", 0)
                ),
                "trip_distance_threshold_percentile": float(
                    row.get("baseline_trip_distance_threshold_percentile", BUFFER_PERCENTILE)
                ),
            },
            "recent_zone_mix": {
                "core_zone_ratio": float(row.get("core_zone_ratio", 0.0)),
                "buffer_zone_ratio": float(row.get("buffer_zone_ratio", 0.0)),
                "in_zone_ratio": float(row.get("in_zone_ratio", 0.0)),
                "out_zone_ratio": float(row.get("out_zone_ratio", 0.0)),
            },
            "outside_living_zone_segments": {
                "criteria": str(
                    row.get("living_zone_outside_segment_criteria", OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)
                ),
                "threshold_m": float(row.get("living_zone_departure_p90_threshold_m", 0.0)),
                "segment_count": int(row.get("living_zone_outside_segment_count", 0)),
                "segment_ratio": float(row.get("living_zone_outside_segment_ratio", 0.0)),
                "distance_km": float(row.get("living_zone_outside_segment_km", 0.0)),
                "distance_ratio": float(row.get("living_zone_outside_segment_distance_ratio", 0.0)),
                "safety_metrics": {
                    "speeding_count": int(row.get("living_zone_outside_segment_speeding_count", 0)),
                    "harsh_accel_count": int(row.get("living_zone_outside_segment_harsh_accel_count", 0)),
                    "harsh_brake_count": int(row.get("living_zone_outside_segment_harsh_brake_count", 0)),
                    "sharp_turn_count": int(row.get("living_zone_outside_segment_sharp_turn_count", 0)),
                    "risk_event_count": int(row.get("living_zone_outside_segment_risk_event_count", 0)),
                    "night_ratio": float(row.get("living_zone_outside_segment_night_ratio", 0.0)),
                    "speeding_per_100km": float(row.get("living_zone_outside_segment_speeding_per_100km", 0.0)),
                    "harsh_accel_per_100km": float(
                        row.get("living_zone_outside_segment_harsh_accel_per_100km", 0.0)
                    ),
                    "harsh_brake_per_100km": float(
                        row.get("living_zone_outside_segment_harsh_brake_per_100km", 0.0)
                    ),
                    "sharp_turn_per_100km": float(row.get("living_zone_outside_segment_sharp_turn_per_100km", 0.0)),
                    "risk_events_per_100km": float(row.get("living_zone_outside_segment_risk_events_per_100km", 0.0)),
                },
            },
            "route_repeat_ratio": float(row.get("route_repeat_ratio", 0.0)),
            "new_destination_count": int(row.get("new_destination_count", 0)),
            "zone_stability_score": float(row.get("zone_stability_score", 0.0)),
            "clusters": clusters,
        }
        privacy_filtered_features = {
            "persona_type": str(row.get("persona_type", "")),
            "living_zone_cluster_count": living_zone["cluster_count"],
            "zone_buffer_m": living_zone["buffer"]["zone_buffer_m"],
            "departure_p90_threshold_m": living_zone["buffer"]["departure_p90_threshold_m"],
            "primary_zone_visit_frequency": living_zone["primary_zone"]["visit_frequency"],
            "primary_zone_radius_metric_m": living_zone["primary_zone"]["radius_metric_m"],
            "recent_in_zone_ratio": living_zone["recent_zone_mix"]["in_zone_ratio"],
            "recent_out_zone_ratio": living_zone["recent_zone_mix"]["out_zone_ratio"],
            "outside_living_zone_segment_ratio": living_zone["outside_living_zone_segments"]["segment_ratio"],
            "outside_living_zone_segment_count": living_zone["outside_living_zone_segments"]["segment_count"],
            "outside_living_zone_safety_metrics": living_zone["outside_living_zone_segments"]["safety_metrics"],
            "route_repeat_ratio": living_zone["route_repeat_ratio"],
            "new_destination_count": living_zone["new_destination_count"],
            "zone_stability_score": living_zone["zone_stability_score"],
        }
        records.append(
            {
                "schema_version": LIVING_ZONE_RESULT_SCHEMA_VERSION,
                "customer_id": str(row.get("customer_id", "")),
                "driver_id": str(row.get("driver_id", "")),
                "persona_type": str(row.get("persona_type", "")),
                "observation_period": {
                    "baseline_days": OBSERVATION_DAYS["baseline"],
                    "recent_days": OBSERVATION_DAYS["recent"],
                    "source_period_for_zone": "baseline",
                    "scored_period": "recent",
                },
                "analysis_method": {
                    "zone_model_backend": str(row.get("zone_model_backend", "dbscan_density_cluster")),
                    "dbscan_eps": dbscan_eps,
                    "dbscan_min_samples": dbscan_min_samples,
                    "buffer_percentile": BUFFER_PERCENTILE,
                    "buffer_min_m": MIN_ZONE_BUFFER_M,
                    "buffer_max_m": MAX_ZONE_BUFFER_M,
                },
                "living_zone": living_zone,
                "privacy_filtered_features": privacy_filtered_features,
            }
        )
    return records


def build_customer_living_zone_records_by_id(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index saved living-zone records by customer_id for direct product lookup."""
    indexed: dict[str, dict[str, Any]] = {}
    for record in sorted(records, key=lambda item: str(item.get("customer_id", ""))):
        customer_id = str(record.get("customer_id", ""))
        if not customer_id:
            raise ValueError("living-zone record missing customer_id")
        if customer_id in indexed:
            raise ValueError(f"duplicate living-zone record for customer_id={customer_id}")
        indexed[customer_id] = record
    return indexed


def build_customer_living_zone_record_store(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the reproducible customer-keyed JSON payload saved after zone analysis."""
    indexed = build_customer_living_zone_records_by_id(records)
    return {
        "schema_version": CUSTOMER_LIVING_ZONE_RECORDS_BY_ID_SCHEMA_VERSION,
        "customer_count": len(indexed),
        "customer_ids": list(indexed),
        "records_by_customer_id": indexed,
    }


def validate_customer_living_zone_record(record: dict[str, Any]) -> None:
    """Validate one saved living-zone record before decision-time use."""
    missing = [field for field in LIVING_ZONE_RESULT_FIELDS if field not in record]
    if missing:
        raise ValueError(f"living-zone record missing fields: {missing}")
    if record["schema_version"] != LIVING_ZONE_RESULT_SCHEMA_VERSION:
        raise ValueError(f"invalid living-zone record schema_version: {record['schema_version']}")
    if not str(record.get("customer_id", "")):
        raise ValueError("living-zone record missing customer_id")
    living_zone = record.get("living_zone")
    if not isinstance(living_zone, dict) or not living_zone:
        raise ValueError("living-zone record must include living_zone")
    if "cluster_count" not in living_zone or "recent_zone_mix" not in living_zone:
        raise ValueError("living-zone record lacks decision-time living_zone summary fields")
    privacy_features = record.get("privacy_filtered_features")
    if not isinstance(privacy_features, dict):
        raise ValueError("living-zone record must include privacy_filtered_features")


def validate_customer_living_zone_record_store(store: dict[str, Any]) -> None:
    """Validate the customer-keyed living-zone result store."""
    if store.get("schema_version") != CUSTOMER_LIVING_ZONE_RECORDS_BY_ID_SCHEMA_VERSION:
        raise ValueError(f"invalid living-zone store schema_version: {store.get('schema_version')}")
    records_by_id = store.get("records_by_customer_id")
    if not isinstance(records_by_id, dict):
        raise ValueError("living-zone store missing records_by_customer_id")
    if int(store.get("customer_count", -1)) != len(records_by_id):
        raise ValueError("living-zone store customer_count does not match records_by_customer_id")
    customer_ids = list(store.get("customer_ids", []))
    if customer_ids and customer_ids != list(records_by_id):
        raise ValueError("living-zone store customer_ids must match records_by_customer_id order")
    for customer_id, record in records_by_id.items():
        validate_customer_living_zone_record(record)
        if str(record["customer_id"]) != str(customer_id):
            raise ValueError(f"living-zone store key mismatch for customer_id={customer_id}")


def living_zone_criteria_from_record(record: dict[str, Any]) -> LivingZoneCriteria:
    """Return stored living-zone criteria, rebuilding it for older fixture records."""
    validate_customer_living_zone_record(record)
    living_zone = record["living_zone"]
    existing = living_zone.get("customer_living_zone_criteria")
    if isinstance(existing, dict) and existing.get("schema_version") == CUSTOMER_LIVING_ZONE_CRITERIA_SCHEMA_VERSION:
        return existing

    centers = [
        (float(cluster["center_longitude"]), float(cluster["center_latitude"]))
        for cluster in living_zone.get("clusters", [])
        if cluster.get("center_longitude") not in ("", None)
        and cluster.get("center_latitude") not in ("", None)
    ]
    buffer = living_zone.get("buffer", {})
    return build_customer_living_zone_criteria(
        str(record["customer_id"]),
        centers,
        departure_threshold={
            "living_zone_departure_p90_raw_m": float(buffer.get("departure_p90_raw_m", 0.0)),
            "living_zone_departure_p90_threshold_m": float(buffer.get("departure_p90_threshold_m", 0.0)),
            "living_zone_departure_threshold_sample_count": int(
                buffer.get("departure_threshold_sample_count", 0)
            ),
            "living_zone_departure_threshold_percentile": float(
                buffer.get("departure_threshold_percentile", BUFFER_PERCENTILE)
            ),
        },
        cluster_summaries=living_zone.get("clusters", []),
    )


def load_customer_living_zone_record_store(
    path: str | Path = DEFAULT_CUSTOMER_LIVING_ZONE_RECORD_STORE_PATH,
) -> dict[str, Any]:
    """Load the saved customer-keyed living-zone result store for product decisions."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_customer_living_zone_record_store(payload)
    return payload


def get_customer_living_zone_record(
    customer_id: str,
    *,
    store: dict[str, Any] | None = None,
    path: str | Path = DEFAULT_CUSTOMER_LIVING_ZONE_RECORD_STORE_PATH,
) -> dict[str, Any]:
    """Return one saved living-zone analysis record by customer_id."""
    record_store = store if store is not None else load_customer_living_zone_record_store(path)
    validate_customer_living_zone_record_store(record_store)
    records_by_id = record_store["records_by_customer_id"]
    try:
        record = records_by_id[customer_id]
    except KeyError as exc:
        raise KeyError(f"saved living-zone record not found for customer_id={customer_id}") from exc
    validate_customer_living_zone_record(record)
    return record


def living_zone_decision_summary(
    customer_id: str,
    *,
    store: dict[str, Any] | None = None,
    record: dict[str, Any] | None = None,
    path: str | Path = DEFAULT_CUSTOMER_LIVING_ZONE_RECORD_STORE_PATH,
) -> dict[str, Any]:
    """Return the saved living-zone result in a customer-decision-friendly shape."""
    saved_record = record or get_customer_living_zone_record(customer_id, store=store, path=path)
    validate_customer_living_zone_record(saved_record)
    living_zone = saved_record["living_zone"]
    zone_mix = living_zone["recent_zone_mix"]
    criteria = living_zone_criteria_from_record(saved_record)
    return {
        "source": "saved_customer_living_zone_record",
        "schema_version": saved_record["schema_version"],
        "customer_id": saved_record["customer_id"],
        "method": saved_record["analysis_method"]["zone_model_backend"],
        "analysis_method": saved_record["analysis_method"],
        "observation_period": saved_record["observation_period"],
        "cluster_count": living_zone["cluster_count"],
        "customer_living_zone_criteria": criteria,
        "primary_zone": living_zone["primary_zone"],
        "buffer": living_zone["buffer"],
        "baseline_thresholds": living_zone["baseline_thresholds"],
        "recent_zone_mix": zone_mix,
        "baseline_out_zone_ratio": None,
        "recent_out_zone_ratio": zone_mix["out_zone_ratio"],
        "recent_in_zone_ratio": zone_mix["in_zone_ratio"],
        "out_zone_ratio_delta": None,
        "outside_living_zone_segments": living_zone["outside_living_zone_segments"],
        "route_repeat_ratio": living_zone["route_repeat_ratio"],
        "new_destination_count": living_zone["new_destination_count"],
        "zone_stability_score": living_zone["zone_stability_score"],
        "clusters": living_zone["clusters"],
    }


def add_zone_features(
    trips: list[dict[str, Any]],
    eps: float = 0.012,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dbscan_results = fit_customer_dbscan_results(trips, eps=eps)
    zones = zone_centers_from_dbscan_results(dbscan_results)
    departure_thresholds = fit_zone_departure_thresholds(trips, zones)
    distance_thresholds = fit_customer_trip_distance_thresholds(trips)
    buffers = zone_buffers_from_departure_thresholds(departure_thresholds)
    labeled = label_trips_with_zones(
        trips,
        zones,
        buffers,
        departure_thresholds=departure_thresholds,
        distance_thresholds=distance_thresholds,
        eps=eps,
    )
    return labeled, build_zone_feature_table(labeled, dbscan_results=dbscan_results)

"""Meter-based clustering helpers for synthetic mobility visit events.

The reference implementation deliberately uses haversine meters.  Product
zones are calculated after clustering and never reused as DBSCAN parameters.
"""

from __future__ import annotations

from collections import deque
from math import asin, cos, radians, sin, sqrt
from typing import Any, Iterable, Mapping, Sequence


EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Return great-circle distance in meters."""

    lat1 = radians(float(lat_a))
    lat2 = radians(float(lat_b))
    delta_lat = lat2 - lat1
    delta_lon = radians(float(lon_b) - float(lon_a))
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(value)))


def _event_date(event: Mapping[str, Any]) -> str:
    value = event.get("visit_date")
    if not value:
        raise ValueError("visit event requires visit_date")
    return str(value)


def _neighbors(events: Sequence[Mapping[str, Any]], index: int, eps_m: float) -> list[int]:
    point = events[index]
    return [
        candidate_index
        for candidate_index, candidate in enumerate(events)
        if haversine_m(
            float(point["latitude"]),
            float(point["longitude"]),
            float(candidate["latitude"]),
            float(candidate["longitude"]),
        )
        <= eps_m
    ]


def dbscan_distinct_days(
    events: Sequence[Mapping[str, Any]],
    *,
    eps_m: float,
    min_distinct_days: int,
) -> dict[str, Any]:
    """Cluster visit events using DBSCAN connectivity and distinct-day support.

    Multiple visits on one day remain in the event log, but they count as one
    day of recurrence when deciding whether a point is a core point.  This
    prevents a single day with duplicate pings or repeated short trips from
    manufacturing a routine hub.
    """

    if eps_m <= 0:
        raise ValueError("eps_m must be positive")
    if min_distinct_days < 2:
        raise ValueError("min_distinct_days must be at least 2")
    if not events:
        return {
            "labels": [],
            "cluster_count": 0,
            "noise_count": 0,
            "core_point_count": 0,
        }

    neighbor_cache = [_neighbors(events, index, float(eps_m)) for index in range(len(events))]

    def is_core(index: int) -> bool:
        distinct_days = {_event_date(events[neighbor]) for neighbor in neighbor_cache[index]}
        return len(distinct_days) >= min_distinct_days

    labels: list[int | None] = [None] * len(events)
    visited = [False] * len(events)
    cluster_id = 0

    for index in range(len(events)):
        if visited[index]:
            continue
        visited[index] = True
        if not is_core(index):
            labels[index] = -1
            continue

        labels[index] = cluster_id
        queue: deque[int] = deque(neighbor_cache[index])
        queued = set(neighbor_cache[index])
        while queue:
            neighbor = queue.popleft()
            if not visited[neighbor]:
                visited[neighbor] = True
                if is_core(neighbor):
                    for expanded in neighbor_cache[neighbor]:
                        if expanded not in queued:
                            queue.append(expanded)
                            queued.add(expanded)
            if labels[neighbor] is None or labels[neighbor] == -1:
                labels[neighbor] = cluster_id
        cluster_id += 1

    normalized_labels = [int(label if label is not None else -1) for label in labels]
    return {
        "labels": normalized_labels,
        "cluster_count": cluster_id,
        "noise_count": sum(label == -1 for label in normalized_labels),
        "core_point_count": sum(is_core(index) for index in range(len(events))),
    }


def percentile_nearest_rank(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percentile <= 1:
        raise ValueError("percentile must be between 0 and 1")
    rank = max(1, int((len(ordered) * percentile) + 0.999999999))
    return ordered[min(len(ordered), rank) - 1]


def summarize_clusters(
    events: Sequence[Mapping[str, Any]],
    labels: Sequence[int],
    *,
    core_radius_m: float,
    buffer_cap_m: float,
) -> list[dict[str, Any]]:
    """Build per-hub radial-P90 product zones from DBSCAN output."""

    if len(events) != len(labels):
        raise ValueError("events and labels must have equal length")
    cluster_ids = sorted({label for label in labels if label >= 0})
    raw: list[dict[str, Any]] = []
    for cluster_id in cluster_ids:
        members = [event for event, label in zip(events, labels) if label == cluster_id]
        latitude = sum(float(event["latitude"]) for event in members) / len(members)
        longitude = sum(float(event["longitude"]) for event in members) / len(members)
        radii = [
            haversine_m(latitude, longitude, float(event["latitude"]), float(event["longitude"]))
            for event in members
        ]
        radial_p90_m = percentile_nearest_rank(radii, 0.90)
        raw.append(
            {
                "source_cluster_id": cluster_id,
                "visit_count": len(members),
                "distinct_day_count": len({_event_date(event) for event in members}),
                "centroid": {
                    "latitude": round(latitude, 6),
                    "longitude": round(longitude, 6),
                },
                "radial_p90_m": round(radial_p90_m, 1),
                "core_radius_m": round(float(core_radius_m), 1),
                "buffer_radius_m": round(
                    max(float(core_radius_m), min(radial_p90_m, float(buffer_cap_m))),
                    1,
                ),
            }
        )

    raw.sort(
        key=lambda cluster: (
            -int(cluster["distinct_day_count"]),
            -int(cluster["visit_count"]),
            float(cluster["centroid"]["latitude"]),
            float(cluster["centroid"]["longitude"]),
        )
    )
    for index, cluster in enumerate(raw):
        cluster["hub_id"] = f"hub-{index + 1}"
        cluster["display_label"] = "Routine Hub A" if index == 0 else "Routine Hub B"
        cluster["zone_source_status"] = "simulated_from_baseline_visits"
    return raw[:2]


def locate_product_zone(event: Mapping[str, Any], hubs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Locate an event relative to product zones; outer is context, not risk."""

    if not hubs:
        return {"zone": "insufficient", "nearest_hub_id": None, "distance_m": None}

    distances = [
        (
            haversine_m(
                float(event["latitude"]),
                float(event["longitude"]),
                float(hub["centroid"]["latitude"]),
                float(hub["centroid"]["longitude"]),
            ),
            hub,
        )
        for hub in hubs
    ]
    distance_m, hub = min(distances, key=lambda pair: pair[0])
    if distance_m <= float(hub["core_radius_m"]):
        zone = "core"
    elif distance_m <= float(hub["buffer_radius_m"]):
        zone = "buffer"
    else:
        zone = "outer"
    return {
        "zone": zone,
        "nearest_hub_id": hub["hub_id"],
        "distance_m": round(distance_m, 1),
    }

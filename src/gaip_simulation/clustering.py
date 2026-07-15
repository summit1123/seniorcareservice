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


def _cluster_records(
    events: Sequence[Mapping[str, Any]], labels: Sequence[int]
) -> list[dict[str, Any]]:
    """Group labelled events into clusters with centroid and intra-cluster P90."""

    records: list[dict[str, Any]] = []
    for cluster_id in sorted({label for label in labels if label >= 0}):
        members = [event for event, label in zip(events, labels) if label == cluster_id]
        latitude = sum(float(event["latitude"]) for event in members) / len(members)
        longitude = sum(float(event["longitude"]) for event in members) / len(members)
        radii = [
            haversine_m(latitude, longitude, float(event["latitude"]), float(event["longitude"]))
            for event in members
        ]
        records.append(
            {
                "source_cluster_id": cluster_id,
                "members": members,
                "visit_count": len(members),
                "distinct_day_count": len({_event_date(event) for event in members}),
                "latitude": latitude,
                "longitude": longitude,
                "intra_radial_p90_m": percentile_nearest_rank(radii, 0.90),
            }
        )
    records.sort(
        key=lambda cluster: (
            -int(cluster["distinct_day_count"]),
            -int(cluster["visit_count"]),
            float(cluster["latitude"]),
            float(cluster["longitude"]),
        )
    )
    return records


def summarize_clusters(
    events: Sequence[Mapping[str, Any]],
    labels: Sequence[int],
    *,
    core_radius_m: float,
    buffer_cap_m: float,
    home_zone_reach_m: float,
    home_center: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Build the HOME-centred living zone (and any genuine secondary zone).

    The displayed radial P90 is the 90th-percentile distance from the HOME
    centre to every baseline visit that belongs to the home zone — i.e. visits
    within ``home_zone_reach_m`` of home. The home centre is the driver's
    residence anchor when provided (``home_center``); otherwise it falls back to
    the most-recurrent cluster's centroid. Anchoring on the residence — rather
    than the single busiest cluster — makes the radial P90 span the real living
    zone (the residence and the destinations around it, hundreds of metres to a
    kilometre or two) instead of the GPS jitter inside one tight cluster.

    Core radius and radial P90 are product-zone values kept strictly separate
    from the DBSCAN ``eps_m`` used to find the clusters in the first place.
    """

    if len(events) != len(labels):
        raise ValueError("events and labels must have equal length")
    clusters = _cluster_records(events, labels)
    if not clusters:
        return []

    core = float(core_radius_m)
    cap = float(buffer_cap_m)
    primary = clusters[0]
    if home_center is not None:
        home_lat = float(home_center[0])
        home_lon = float(home_center[1])
    else:
        home_lat = float(primary["latitude"])
        home_lon = float(primary["longitude"])
    home_visits = [
        event
        for event in events
        if haversine_m(home_lat, home_lon, float(event["latitude"]), float(event["longitude"]))
        <= float(home_zone_reach_m)
    ]
    home_radii = [
        haversine_m(home_lat, home_lon, float(event["latitude"]), float(event["longitude"]))
        for event in home_visits
    ]
    radial_p90_m = percentile_nearest_rank(home_radii, 0.90)
    buffer_radius_m = max(core, min(radial_p90_m, cap))

    hubs: list[dict[str, Any]] = [
        {
            "source_cluster_id": primary["source_cluster_id"],
            "hub_id": "hub-1",
            "display_label": "Routine Hub A",
            "visit_count": len(home_visits),
            "distinct_day_count": len({_event_date(event) for event in home_visits}),
            "centroid": {"latitude": round(home_lat, 6), "longitude": round(home_lon, 6)},
            "radial_p90_m": round(radial_p90_m, 1),
            "core_radius_m": round(core, 1),
            "buffer_radius_m": round(buffer_radius_m, 1),
            "zone_source_status": "simulated_from_baseline_visits",
        }
    ]

    # A genuine second living zone: a distinct cluster beyond the home buffer with
    # its own recurrent support (>= 3 distinct days).
    secondaries = [
        cluster
        for cluster in clusters[1:]
        if int(cluster["distinct_day_count"]) >= 3
        and haversine_m(home_lat, home_lon, float(cluster["latitude"]), float(cluster["longitude"]))
        > buffer_radius_m
    ]
    if secondaries:
        secondary = secondaries[0]
        secondary_p90 = float(secondary["intra_radial_p90_m"])
        hubs.append(
            {
                "source_cluster_id": secondary["source_cluster_id"],
                "hub_id": "hub-2",
                "display_label": "Routine Hub B",
                "visit_count": int(secondary["visit_count"]),
                "distinct_day_count": int(secondary["distinct_day_count"]),
                "centroid": {
                    "latitude": round(float(secondary["latitude"]), 6),
                    "longitude": round(float(secondary["longitude"]), 6),
                },
                "radial_p90_m": round(secondary_p90, 1),
                "core_radius_m": round(core, 1),
                "buffer_radius_m": round(max(core, min(secondary_p90, cap)), 1),
                "zone_source_status": "simulated_from_baseline_visits",
            }
        )
    return hubs


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

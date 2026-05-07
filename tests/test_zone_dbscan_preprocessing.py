from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.agents.ai_simulation_agent import AISimulationAgent
from src.agents.contracts import validate_privacy_filtered_features
from src.features.build_model_features import merge_feature_tables, write_customer_living_zone_record_files
from src.features.driving_features import aggregate_baseline_behavior, aggregate_recent_behavior
from src.features.zone_features import (
    add_zone_features,
    build_customer_living_zone_criteria,
    build_customer_living_zone_criteria_map,
    build_customer_living_zone_record_store,
    build_customer_living_zone_records,
    build_customer_living_zone_records_by_id,
    build_movement_history_table,
    build_customer_dbscan_input,
    classify_trip_against_living_zone,
    cluster_boundary_metrics,
    cluster_radius_metrics,
    CUSTOMER_LIVING_ZONE_CRITERIA_SCHEMA_VERSION,
    CUSTOMER_LIVING_ZONE_RECORDS_BY_ID_SCHEMA_VERSION,
    fit_customer_movement_frequency_thresholds,
    fit_customer_trip_distance_thresholds,
    fit_zone_departure_thresholds,
    fit_customer_dbscan_results,
    get_customer_living_zone_record,
    haversine_meters,
    LIVING_ZONE_RESULT_FIELDS,
    LIVING_ZONE_RESULT_SCHEMA_VERSION,
    living_zone_decision_summary,
    load_customer_living_zone_record_store,
    OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA,
    percentile,
    zone_centers_from_dbscan_results,
)


class TestZoneDBSCANPreprocessing(unittest.TestCase):
    def test_synthetic_trips_are_grouped_by_customer_for_baseline_dbscan_input(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        dbscan_input = build_customer_dbscan_input(fixture.rows)

        self.assertEqual(len(dbscan_input), 30)
        self.assertEqual(set(dbscan_input), {f"cust_{index:03d}" for index in range(1, 31)})

        for customer_id, records in dbscan_input.items():
            baseline_trips = [
                row
                for row in fixture.rows
                if row["customer_id"] == customer_id and row["observation_period"] == "baseline"
            ]

            self.assertEqual(len(records), len(baseline_trips) * 2)
            self.assertEqual({record["period"] for record in records}, {"baseline"})
            self.assertEqual({record["point_role"] for record in records}, {"start", "end"})
            self.assertTrue(all(record["customer_id"] == customer_id for record in records))
            self.assertTrue(all(isinstance(record["longitude"], float) for record in records))
            self.assertTrue(all(isinstance(record["latitude"], float) for record in records))
            self.assertTrue(
                all(record["dbscan_point"] == (record["longitude"], record["latitude"]) for record in records)
            )

    def test_preprocessing_can_include_recent_period_when_requested(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        dbscan_input = build_customer_dbscan_input(fixture.rows, periods={"baseline", "recent"})

        for customer_id, records in dbscan_input.items():
            customer_trips = [row for row in fixture.rows if row["customer_id"] == customer_id]

            self.assertEqual(len(records), len(customer_trips) * 2)
            self.assertEqual({record["period"] for record in records}, {"baseline", "recent"})

    def test_preprocessing_drops_zero_coordinate_points(self) -> None:
        rows = [
            {
                "customer_id": "cust_999",
                "driver_id": "driver_999",
                "trip_id": "trip_valid",
                "observation_period": "baseline",
                "start_gps_x": "126.978",
                "start_gps_y": "37.566",
                "end_gps_x": "0",
                "end_gps_y": "0",
            }
        ]

        dbscan_input = build_customer_dbscan_input(rows)

        self.assertEqual(len(dbscan_input["cust_999"]), 1)
        self.assertEqual(dbscan_input["cust_999"][0]["point_role"], "start")
        self.assertEqual(dbscan_input["cust_999"][0]["dbscan_point"], (126.978, 37.566))

    def test_dbscan_runs_per_customer_and_identifies_clusters_and_noise_points(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0001",
                "observation_period": "baseline",
                "start_gps_x": 126.9780,
                "start_gps_y": 37.5660,
                "end_gps_x": 126.9781,
                "end_gps_y": 37.5661,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0002",
                "observation_period": "baseline",
                "start_gps_x": 126.9782,
                "start_gps_y": 37.5662,
                "end_gps_x": 127.2000,
                "end_gps_y": 37.7000,
            },
            {
                "customer_id": "cust_002",
                "driver_id": "driver_002",
                "trip_id": "trip_cust_002_0001",
                "observation_period": "baseline",
                "start_gps_x": 126.9000,
                "start_gps_y": 37.5000,
                "end_gps_x": 126.9001,
                "end_gps_y": 37.5001,
            },
            {
                "customer_id": "cust_002",
                "driver_id": "driver_002",
                "trip_id": "trip_cust_002_0002",
                "observation_period": "baseline",
                "start_gps_x": 126.9002,
                "start_gps_y": 37.5002,
                "end_gps_x": 127.2500,
                "end_gps_y": 37.7200,
            },
        ]

        results = fit_customer_dbscan_results(rows, eps=0.001, min_samples=3)

        self.assertEqual(set(results), {"cust_001", "cust_002"})
        for customer_id, result in results.items():
            self.assertEqual(result["point_count"], 4, customer_id)
            self.assertEqual(result["cluster_count"], 1, customer_id)
            self.assertEqual(result["noise_count"], 1, customer_id)
            self.assertEqual(result["clusters"][0]["point_count"], 3, customer_id)
            self.assertEqual(result["clusters"][0]["visit_count"], 2, customer_id)
            self.assertEqual(result["clusters"][0]["start_point_count"], 2, customer_id)
            self.assertEqual(result["clusters"][0]["end_point_count"], 1, customer_id)
            self.assertGreater(result["clusters"][0]["point_frequency"], 0.0, customer_id)
            self.assertGreater(result["clusters"][0]["visit_frequency"], 0.0, customer_id)
            self.assertGreaterEqual(result["clusters"][0]["p90_radius_m"], 0.0, customer_id)
            self.assertGreaterEqual(result["clusters"][0]["max_radius_m"], result["clusters"][0]["p90_radius_m"], customer_id)
            self.assertEqual({point["customer_id"] for point in result["clusters"][0]["points"]}, {customer_id})
            self.assertEqual({point["customer_id"] for point in result["noise_points"]}, {customer_id})
            self.assertTrue(all(point["dbscan_cluster_id"] == 0 for point in result["clusters"][0]["points"]))
            self.assertTrue(all(point["dbscan_is_noise"] for point in result["noise_points"]))

    def test_cluster_summary_aggregates_gps_points_and_visit_counts_for_center_coordinates(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0001",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5000,
                "end_gps_x": 127.0002,
                "end_gps_y": 37.5002,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0002",
                "observation_period": "baseline",
                "start_gps_x": 127.0004,
                "start_gps_y": 37.5004,
                "end_gps_x": 127.0006,
                "end_gps_y": 37.5006,
            },
        ]

        result = fit_customer_dbscan_results(rows, eps=0.001, min_samples=3)["cust_001"]
        cluster = result["clusters"][0]

        self.assertEqual(cluster["point_count"], 4)
        self.assertEqual(cluster["visit_count"], 2)
        self.assertEqual(cluster["start_point_count"], 2)
        self.assertEqual(cluster["end_point_count"], 2)
        self.assertAlmostEqual(cluster["center_longitude"], 127.0003, places=6)
        self.assertAlmostEqual(cluster["center_latitude"], 37.5003, places=6)
        self.assertEqual({point["trip_id"] for point in cluster["points"]}, {"trip_cust_001_0001", "trip_cust_001_0002"})

    def test_cluster_radius_metric_uses_center_to_cluster_point_distances(self) -> None:
        points = [
            (127.0000, 37.5000),
            (127.0010, 37.5000),
            (127.0000, 37.5010),
            (127.0010, 37.5010),
        ]

        metrics = cluster_radius_metrics(points, center=(127.0005, 37.5005))

        self.assertGreater(metrics["avg_radius_m"], 60.0)
        self.assertLess(metrics["avg_radius_m"], 80.0)
        self.assertGreaterEqual(metrics["median_radius_m"], 0.0)
        self.assertGreaterEqual(metrics["p90_radius_m"], metrics["median_radius_m"])
        self.assertGreaterEqual(metrics["max_radius_m"], metrics["p90_radius_m"])
        self.assertEqual(metrics["radius_metric_m"], metrics["p90_radius_m"])

    def test_cluster_boundary_metric_uses_cluster_distribution_outer_extent(self) -> None:
        points = [
            (127.0000, 37.5000),
            (127.0020, 37.5000),
            (127.0000, 37.5030),
            (127.0020, 37.5030),
        ]

        metrics = cluster_boundary_metrics(points, center=(127.0010, 37.5015))

        self.assertEqual(metrics["boundary_min_longitude"], 127.0000)
        self.assertEqual(metrics["boundary_max_longitude"], 127.0020)
        self.assertEqual(metrics["boundary_min_latitude"], 37.5000)
        self.assertEqual(metrics["boundary_max_latitude"], 37.5030)
        self.assertGreater(metrics["boundary_width_m"], 150.0)
        self.assertGreater(metrics["boundary_height_m"], 300.0)
        self.assertGreater(metrics["boundary_area_km2"], 0.05)
        self.assertGreater(metrics["outer_extent_radius_m"], 180.0)

    def test_dbscan_cluster_summary_exposes_radius_indicator_fields(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0001",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5000,
                "end_gps_x": 127.0010,
                "end_gps_y": 37.5000,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0002",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5010,
                "end_gps_x": 127.0010,
                "end_gps_y": 37.5010,
            },
        ]

        cluster = fit_customer_dbscan_results(rows, eps=0.002, min_samples=3)["cust_001"]["clusters"][0]

        self.assertGreater(cluster["avg_radius_m"], 0.0)
        self.assertGreater(cluster["median_radius_m"], 0.0)
        self.assertGreater(cluster["radius_metric_m"], 0.0)
        self.assertEqual(cluster["radius_metric_m"], cluster["p90_radius_m"])

    def test_dbscan_cluster_summary_exposes_boundary_and_outer_extent_fields(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0001",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5000,
                "end_gps_x": 127.0020,
                "end_gps_y": 37.5000,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0002",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5030,
                "end_gps_x": 127.0020,
                "end_gps_y": 37.5030,
            },
        ]

        cluster = fit_customer_dbscan_results(rows, eps=0.004, min_samples=3)["cust_001"]["clusters"][0]

        self.assertEqual(cluster["boundary_min_longitude"], 127.0000)
        self.assertEqual(cluster["boundary_max_longitude"], 127.0020)
        self.assertEqual(cluster["boundary_min_latitude"], 37.5000)
        self.assertEqual(cluster["boundary_max_latitude"], 37.5030)
        self.assertGreater(cluster["boundary_width_m"], 0.0)
        self.assertGreater(cluster["boundary_height_m"], 0.0)
        self.assertGreater(cluster["boundary_area_km2"], 0.0)
        self.assertGreaterEqual(cluster["outer_extent_radius_m"], cluster["p90_radius_m"])

    def test_living_zone_outside_segment_criteria_and_flag_are_scoring_features(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0001",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5000,
                "end_gps_x": 127.0002,
                "end_gps_y": 37.5002,
                "trip_distance_km": 4.0,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0002",
                "observation_period": "baseline",
                "start_gps_x": 127.0001,
                "start_gps_y": 37.5001,
                "end_gps_x": 127.0003,
                "end_gps_y": 37.5003,
                "trip_distance_km": 4.0,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0003",
                "observation_period": "recent",
                "start_gps_x": 127.0001,
                "start_gps_y": 37.5001,
                "end_gps_x": 127.0600,
                "end_gps_y": 37.5600,
                "trip_distance_km": 9.0,
            },
        ]

        labeled, zone_rows = add_zone_features(rows, eps=0.001)
        recent_trip = next(row for row in labeled if row["trip_id"] == "trip_cust_001_0003")

        self.assertEqual(recent_trip["living_zone_outside_segment_criteria"], OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)
        self.assertEqual(recent_trip["living_zone_outside_threshold_m"], 500.0)
        self.assertGreater(recent_trip["living_zone_segment_max_distance_m"], recent_trip["living_zone_outside_threshold_m"])
        self.assertEqual(recent_trip["living_zone_outside_segment_flag"], 1)
        self.assertEqual(recent_trip["out_zone_flag"], 1)
        self.assertEqual(zone_rows[0]["living_zone_outside_segment_count"], 1)
        self.assertEqual(zone_rows[0]["living_zone_outside_segment_ratio"], 1.0)
        self.assertEqual(zone_rows[0]["living_zone_outside_segment_km"], 9.0)

    def test_customer_living_zone_criteria_defines_customer_specific_area(self) -> None:
        zones = {"cust_001": [(127.0000, 37.5000)], "cust_002": [(127.1000, 37.6000)]}
        thresholds = {
            "cust_001": {
                "living_zone_departure_p90_raw_m": 420.0,
                "living_zone_departure_p90_threshold_m": 500.0,
                "living_zone_departure_threshold_sample_count": 15,
                "living_zone_departure_threshold_percentile": 0.9,
            },
            "cust_002": {
                "living_zone_departure_p90_raw_m": 2400.0,
                "living_zone_departure_p90_threshold_m": 2000.0,
                "living_zone_departure_threshold_sample_count": 20,
                "living_zone_departure_threshold_percentile": 0.9,
            },
        }

        criteria_by_customer = build_customer_living_zone_criteria_map(zones, thresholds)

        self.assertEqual(set(criteria_by_customer), {"cust_001", "cust_002"})
        self.assertEqual(criteria_by_customer["cust_001"]["schema_version"], CUSTOMER_LIVING_ZONE_CRITERIA_SCHEMA_VERSION)
        self.assertEqual(criteria_by_customer["cust_001"]["criteria"], OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)
        self.assertEqual(criteria_by_customer["cust_001"]["core_radius_m"], 500.0)
        self.assertEqual(criteria_by_customer["cust_001"]["buffer_radius_m"], 500.0)
        self.assertEqual(criteria_by_customer["cust_001"]["departure_threshold_sample_count"], 15)
        self.assertEqual(criteria_by_customer["cust_002"]["buffer_radius_m"], 2000.0)
        self.assertEqual(
            criteria_by_customer["cust_001"]["centers"],
            [{"center_longitude": 127.0, "center_latitude": 37.5}],
        )

    def test_trip_is_classified_outside_customer_living_zone_from_start_or_end_distance(self) -> None:
        criteria = build_customer_living_zone_criteria(
            "cust_001",
            [(127.0000, 37.5000)],
            departure_threshold={
                "living_zone_departure_p90_raw_m": 430.0,
                "living_zone_departure_p90_threshold_m": 500.0,
                "living_zone_departure_threshold_sample_count": 12,
                "living_zone_departure_threshold_percentile": 0.9,
            },
        )
        in_zone_trip = {
            "customer_id": "cust_001",
            "driver_id": "driver_001",
            "start_gps_x": 127.0001,
            "start_gps_y": 37.5001,
            "end_gps_x": 127.0002,
            "end_gps_y": 37.5002,
        }
        outside_trip = {
            "customer_id": "cust_001",
            "driver_id": "driver_001",
            "start_gps_x": 127.0001,
            "start_gps_y": 37.5001,
            "end_gps_x": 127.0200,
            "end_gps_y": 37.5200,
        }

        in_zone_result = classify_trip_against_living_zone(in_zone_trip, criteria)
        outside_result = classify_trip_against_living_zone(outside_trip, criteria)

        self.assertEqual(in_zone_result["core_zone_flag"], 1)
        self.assertEqual(in_zone_result["in_zone_flag"], 1)
        self.assertEqual(in_zone_result["out_zone_flag"], 0)
        self.assertEqual(in_zone_result["living_zone_outside_segment_flag"], 0)
        self.assertEqual(outside_result["outer_zone_flag"], 1)
        self.assertEqual(outside_result["in_zone_flag"], 0)
        self.assertEqual(outside_result["out_zone_flag"], 1)
        self.assertGreater(
            outside_result["living_zone_segment_max_distance_m"],
            outside_result["living_zone_outside_threshold_m"],
        )
        self.assertEqual(outside_result["living_zone_outside_segment_flag"], 1)
        self.assertEqual(outside_result["living_zone_outside_segment_criteria"], OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)

    def test_living_zone_outside_segment_safety_metrics_are_aggregated_separately(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0001",
                "observation_period": "baseline",
                "start_gps_x": 127.0000,
                "start_gps_y": 37.5000,
                "end_gps_x": 127.0002,
                "end_gps_y": 37.5002,
                "trip_distance_km": 4.0,
                "speeding_count": 0,
                "harsh_accel_count": 0,
                "harsh_brake_count": 0,
                "sharp_turn_count": 0,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_0002",
                "observation_period": "baseline",
                "start_gps_x": 127.0001,
                "start_gps_y": 37.5001,
                "end_gps_x": 127.0003,
                "end_gps_y": 37.5003,
                "trip_distance_km": 4.0,
                "speeding_count": 0,
                "harsh_accel_count": 0,
                "harsh_brake_count": 0,
                "sharp_turn_count": 0,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_recent_in_zone",
                "observation_period": "recent",
                "start_gps_x": 127.0001,
                "start_gps_y": 37.5001,
                "end_gps_x": 127.0002,
                "end_gps_y": 37.5002,
                "trip_distance_km": 10.0,
                "speeding_count": 9,
                "harsh_accel_count": 9,
                "harsh_brake_count": 9,
                "sharp_turn_count": 9,
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_recent_outside",
                "observation_period": "recent",
                "start_gps_x": 127.0001,
                "start_gps_y": 37.5001,
                "end_gps_x": 127.0600,
                "end_gps_y": 37.5600,
                "trip_distance_km": 20.0,
                "speeding_count": 2,
                "harsh_accel_count": 1,
                "harsh_brake_count": 3,
                "sharp_turn_count": 4,
            },
        ]

        labeled, zone_rows = add_zone_features(rows, eps=0.001)
        driving_row = aggregate_recent_behavior(labeled)[0]
        zone_row = zone_rows[0]
        living_zone_record = build_customer_living_zone_records(zone_rows)[0]
        safety_metrics = living_zone_record["living_zone"]["outside_living_zone_segments"]["safety_metrics"]

        self.assertEqual(zone_row["living_zone_outside_segment_count"], 1)
        self.assertEqual(zone_row["living_zone_outside_segment_km"], 20.0)
        self.assertEqual(zone_row["living_zone_outside_segment_speeding_count"], 2)
        self.assertEqual(zone_row["living_zone_outside_segment_harsh_accel_count"], 1)
        self.assertEqual(zone_row["living_zone_outside_segment_harsh_brake_count"], 3)
        self.assertEqual(zone_row["living_zone_outside_segment_sharp_turn_count"], 4)
        self.assertEqual(zone_row["living_zone_outside_segment_risk_event_count"], 10)
        self.assertEqual(zone_row["living_zone_outside_segment_speeding_per_100km"], 10.0)
        self.assertEqual(zone_row["living_zone_outside_segment_harsh_accel_per_100km"], 5.0)
        self.assertEqual(zone_row["living_zone_outside_segment_harsh_brake_per_100km"], 15.0)
        self.assertEqual(zone_row["living_zone_outside_segment_sharp_turn_per_100km"], 20.0)
        self.assertEqual(zone_row["living_zone_outside_segment_risk_events_per_100km"], 50.0)
        self.assertEqual(driving_row["living_zone_outside_segment_risk_event_count"], 10)
        self.assertEqual(safety_metrics["speeding_count"], 2)
        self.assertEqual(safety_metrics["harsh_accel_count"], 1)
        self.assertEqual(safety_metrics["harsh_brake_count"], 3)
        self.assertEqual(safety_metrics["risk_events_per_100km"], 50.0)

    def test_living_zone_outside_segment_risk_change_metrics_compare_baseline_and_recent(self) -> None:
        trips = [
            {
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "trip_distance_km": 40.0,
                "night_flag": False,
                "out_zone_flag": 1,
                "living_zone_outside_segment_flag": 1,
                "speeding_count": 1,
                "harsh_accel_count": 0,
                "harsh_brake_count": 0,
                "sharp_turn_count": 0,
            },
            {
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "trip_distance_km": 60.0,
                "night_flag": False,
                "out_zone_flag": 0,
                "living_zone_outside_segment_flag": 0,
                "speeding_count": 0,
                "harsh_accel_count": 0,
                "harsh_brake_count": 0,
                "sharp_turn_count": 0,
            },
            {
                "driver_id": "driver_001",
                "observation_period": "recent",
                "trip_distance_km": 40.0,
                "night_flag": True,
                "out_zone_flag": 1,
                "living_zone_outside_segment_flag": 1,
                "speeding_count": 2,
                "harsh_accel_count": 1,
                "harsh_brake_count": 2,
                "sharp_turn_count": 0,
            },
            {
                "driver_id": "driver_001",
                "observation_period": "recent",
                "trip_distance_km": 40.0,
                "night_flag": False,
                "out_zone_flag": 1,
                "living_zone_outside_segment_flag": 1,
                "speeding_count": 0,
                "harsh_accel_count": 0,
                "harsh_brake_count": 1,
                "sharp_turn_count": 0,
            },
            {
                "driver_id": "driver_001",
                "observation_period": "recent",
                "trip_distance_km": 20.0,
                "night_flag": False,
                "out_zone_flag": 0,
                "living_zone_outside_segment_flag": 0,
                "speeding_count": 0,
                "harsh_accel_count": 0,
                "harsh_brake_count": 0,
                "sharp_turn_count": 0,
            },
        ]

        recent_row = aggregate_recent_behavior(trips)[0]
        baseline_by_driver = aggregate_baseline_behavior(trips)
        model_row = merge_feature_tables(
            zone_rows=[
                {
                    "driver_id": "driver_001",
                    "customer_id": "cust_001",
                    "zone_stability_score": 50.0,
                    "out_zone_ratio": 0.8,
                }
            ],
            driving_rows=[recent_row],
            baseline_rows=baseline_by_driver,
        )[0]

        self.assertEqual(recent_row["living_zone_outside_segment_night_ratio"], 0.5)
        self.assertEqual(model_row["baseline_living_zone_outside_segment_ratio"], 0.5)
        self.assertEqual(model_row["baseline_living_zone_outside_segment_distance_ratio"], 0.4)
        self.assertEqual(model_row["baseline_living_zone_outside_segment_risk_events_per_100km"], 2.5)
        self.assertEqual(model_row["living_zone_outside_segment_ratio_delta"], 0.1667)
        self.assertEqual(model_row["living_zone_outside_segment_distance_ratio_delta"], 0.4)
        self.assertEqual(model_row["living_zone_outside_segment_risk_events_delta_per_100km"], 5.0)
        self.assertEqual(model_row["living_zone_outside_segment_night_ratio_delta"], 0.5)
        self.assertGreater(model_row["living_zone_outside_segment_risk_change_score"], 0.0)

    def test_generated_fixture_dbscan_result_covers_all_customers(self) -> None:
        fixture = AISimulationAgent().generate_fixture()

        results = fit_customer_dbscan_results(fixture.rows)

        self.assertEqual(len(results), 30)
        for customer_id, result in results.items():
            self.assertGreaterEqual(result["cluster_count"], 1, customer_id)
            self.assertEqual(
                result["point_count"],
                sum(1 for point in result["points"] if point["customer_id"] == customer_id),
                customer_id,
            )
            self.assertEqual(
                result["point_count"],
                sum(cluster["point_count"] for cluster in result["clusters"]) + result["noise_count"],
                customer_id,
            )

    def test_zone_feature_table_exposes_cluster_summaries_for_product_flow(self) -> None:
        fixture = AISimulationAgent().generate_fixture()

        _, zone_rows = add_zone_features(fixture.rows)

        self.assertEqual(len(zone_rows), 30)
        for row in zone_rows:
            self.assertGreaterEqual(row["living_zone_cluster_count"], 1)
            self.assertNotEqual(row["primary_zone_center_longitude"], "")
            self.assertNotEqual(row["primary_zone_center_latitude"], "")
            self.assertGreater(row["primary_zone_visit_frequency"], 0.0)
            self.assertGreaterEqual(row["primary_zone_radius_m"], 0.0)
            self.assertGreaterEqual(row["primary_zone_p90_radius_m"], 0.0)
            self.assertGreaterEqual(row["primary_zone_outer_extent_radius_m"], row["primary_zone_p90_radius_m"])
            self.assertGreaterEqual(row["primary_zone_boundary_area_km2"], 0.0)
            self.assertGreaterEqual(row["primary_zone_boundary_width_m"], 0.0)
            self.assertGreaterEqual(row["primary_zone_boundary_height_m"], 0.0)
            self.assertGreaterEqual(row["living_zone_departure_p90_raw_m"], 0.0)
            self.assertGreaterEqual(row["living_zone_departure_p90_threshold_m"], 500.0)
            self.assertLessEqual(row["living_zone_departure_p90_threshold_m"], 2000.0)
            self.assertEqual(row["living_zone_outside_segment_criteria"], OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA)
            self.assertGreaterEqual(row["living_zone_outside_segment_count"], 0)
            self.assertGreaterEqual(row["living_zone_outside_segment_ratio"], 0.0)
            self.assertLessEqual(row["living_zone_outside_segment_ratio"], 1.0)
            self.assertGreaterEqual(row["living_zone_outside_segment_speeding_count"], 0)
            self.assertGreaterEqual(row["living_zone_outside_segment_harsh_accel_count"], 0)
            self.assertGreaterEqual(row["living_zone_outside_segment_harsh_brake_count"], 0)
            self.assertGreaterEqual(row["living_zone_outside_segment_risk_event_count"], 0)
            self.assertGreaterEqual(row["living_zone_outside_segment_risk_events_per_100km"], 0.0)
            self.assertGreater(row["living_zone_departure_threshold_sample_count"], 0)
            self.assertEqual(row["living_zone_departure_threshold_percentile"], 0.9)
            self.assertGreater(row["baseline_trip_distance_p90_km"], 0.0)
            self.assertGreater(row["baseline_trip_distance_threshold_sample_count"], 0)
            self.assertEqual(row["baseline_trip_distance_threshold_percentile"], 0.9)
            self.assertIn('"center_longitude"', row["living_zone_clusters_json"])
            self.assertIn('"visit_frequency"', row["living_zone_clusters_json"])
            self.assertIn('"radius_metric_m"', row["living_zone_clusters_json"])
            self.assertIn('"p90_radius_m"', row["living_zone_clusters_json"])
            self.assertIn('"outer_extent_radius_m"', row["living_zone_clusters_json"])
            self.assertIn('"boundary_area_km2"', row["living_zone_clusters_json"])

    def test_customer_living_zone_records_define_customer_saved_schema(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        _, zone_rows = add_zone_features(fixture.rows)

        records = build_customer_living_zone_records(zone_rows)

        self.assertEqual(len(records), 30)
        for record in records:
            self.assertEqual(tuple(record.keys()), LIVING_ZONE_RESULT_FIELDS)
            self.assertEqual(record["schema_version"], LIVING_ZONE_RESULT_SCHEMA_VERSION)
            self.assertIn(record["customer_id"], {f"cust_{index:03d}" for index in range(1, 31)})
            self.assertTrue(record["driver_id"].startswith("driver_"))
            self.assertEqual(
                record["observation_period"],
                {
                    "baseline_days": 60,
                    "recent_days": 30,
                    "source_period_for_zone": "baseline",
                    "scored_period": "recent",
                },
            )
            self.assertEqual(record["analysis_method"]["zone_model_backend"], "dbscan_density_cluster")
            self.assertEqual(record["analysis_method"]["buffer_percentile"], 0.9)

            living_zone = record["living_zone"]
            self.assertGreaterEqual(living_zone["cluster_count"], 1)
            self.assertEqual(
                living_zone["customer_living_zone_criteria"]["schema_version"],
                CUSTOMER_LIVING_ZONE_CRITERIA_SCHEMA_VERSION,
            )
            self.assertEqual(
                living_zone["customer_living_zone_criteria"]["criteria"],
                OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA,
            )
            self.assertEqual(
                living_zone["customer_living_zone_criteria"]["buffer_radius_m"],
                living_zone["buffer"]["departure_p90_threshold_m"],
            )
            self.assertEqual(
                len(living_zone["customer_living_zone_criteria"]["centers"]),
                living_zone["cluster_count"],
            )
            self.assertGreaterEqual(living_zone["primary_zone"]["p90_radius_m"], 0.0)
            self.assertGreaterEqual(
                living_zone["primary_zone"]["outer_extent_radius_m"],
                living_zone["primary_zone"]["p90_radius_m"],
            )
            self.assertGreaterEqual(living_zone["buffer"]["departure_p90_threshold_m"], 500.0)
            self.assertLessEqual(living_zone["buffer"]["departure_p90_threshold_m"], 2000.0)
            self.assertGreater(living_zone["buffer"]["departure_threshold_sample_count"], 0)
            self.assertGreater(living_zone["baseline_thresholds"]["trip_distance_p90_km"], 0.0)
            self.assertGreater(living_zone["baseline_thresholds"]["trip_distance_threshold_sample_count"], 0)
            self.assertEqual(
                living_zone["outside_living_zone_segments"]["criteria"],
                OUTSIDE_LIVING_ZONE_SEGMENT_CRITERIA,
            )
            self.assertGreaterEqual(living_zone["outside_living_zone_segments"]["segment_count"], 0)
            self.assertGreaterEqual(living_zone["outside_living_zone_segments"]["segment_ratio"], 0.0)
            self.assertLessEqual(living_zone["outside_living_zone_segments"]["segment_ratio"], 1.0)
            self.assertIn("safety_metrics", living_zone["outside_living_zone_segments"])
            self.assertGreaterEqual(
                living_zone["outside_living_zone_segments"]["safety_metrics"]["risk_event_count"],
                0,
            )
            self.assertAlmostEqual(
                living_zone["recent_zone_mix"]["in_zone_ratio"] + living_zone["recent_zone_mix"]["out_zone_ratio"],
                1.0,
                places=4,
            )
            self.assertEqual(len(living_zone["clusters"]), living_zone["cluster_count"])

    def test_living_zone_privacy_filtered_features_exclude_ids_gps_and_trip_keys(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        _, zone_rows = add_zone_features(fixture.rows)

        records = build_customer_living_zone_records(zone_rows)

        for record in records:
            validate_privacy_filtered_features(record["privacy_filtered_features"])
            flattened = str(record["privacy_filtered_features"])
            self.assertNotIn("customer_id", flattened)
            self.assertNotIn("driver_id", flattened)
            self.assertNotIn("trip_id", flattened)
            self.assertNotIn("longitude", flattened)
            self.assertNotIn("latitude", flattened)
            self.assertNotIn("gps", flattened)

    def test_customer_living_zone_results_are_saved_by_customer_id(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        _, zone_rows = add_zone_features(fixture.rows)
        records = build_customer_living_zone_records(zone_rows)

        records_by_id = build_customer_living_zone_records_by_id(records)
        store = build_customer_living_zone_record_store(records)

        self.assertEqual(set(records_by_id), {f"cust_{index:03d}" for index in range(1, 31)})
        self.assertEqual(store["schema_version"], CUSTOMER_LIVING_ZONE_RECORDS_BY_ID_SCHEMA_VERSION)
        self.assertEqual(store["customer_count"], 30)
        self.assertEqual(store["customer_ids"], [f"cust_{index:03d}" for index in range(1, 31)])
        self.assertEqual(set(store["records_by_customer_id"]), set(records_by_id))
        self.assertEqual(store["records_by_customer_id"]["cust_001"]["customer_id"], "cust_001")

    def test_customer_living_zone_record_files_are_written_per_customer(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        _, zone_rows = add_zone_features(fixture.rows)
        records = build_customer_living_zone_records(zone_rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_customer_living_zone_record_files(Path(tmpdir), records)
            first_record = json.loads((Path(tmpdir) / "cust_001.json").read_text(encoding="utf-8"))

        self.assertEqual(len(paths), 30)
        self.assertEqual(first_record["customer_id"], "cust_001")
        self.assertIn("living_zone", first_record)
        self.assertIn("privacy_filtered_features", first_record)

    def test_customer_decision_can_lookup_saved_living_zone_result_by_customer_id(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        _, zone_rows = add_zone_features(fixture.rows)
        records = build_customer_living_zone_records(zone_rows)
        store = build_customer_living_zone_record_store(records)

        record = get_customer_living_zone_record("cust_011", store=store)
        summary = living_zone_decision_summary("cust_011", store=store)

        self.assertEqual(record["customer_id"], "cust_011")
        self.assertEqual(summary["source"], "saved_customer_living_zone_record")
        self.assertEqual(summary["schema_version"], LIVING_ZONE_RESULT_SCHEMA_VERSION)
        self.assertEqual(summary["cluster_count"], record["living_zone"]["cluster_count"])
        self.assertEqual(
            summary["customer_living_zone_criteria"],
            record["living_zone"]["customer_living_zone_criteria"],
        )
        self.assertEqual(summary["primary_zone"], record["living_zone"]["primary_zone"])
        self.assertEqual(summary["recent_zone_mix"], record["living_zone"]["recent_zone_mix"])
        self.assertIn("clusters", summary)

    def test_customer_living_zone_record_store_loader_returns_valid_lookup_interface(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        _, zone_rows = add_zone_features(fixture.rows)
        records = build_customer_living_zone_records(zone_rows)
        store = build_customer_living_zone_record_store(records)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "customer_living_zone_records_by_id.json"
            path.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")

            loaded_store = load_customer_living_zone_record_store(path)
            loaded_record = get_customer_living_zone_record("cust_001", store=loaded_store)

        self.assertEqual(loaded_store["customer_count"], 30)
        self.assertEqual(loaded_record["customer_id"], "cust_001")

    def test_customer_departure_threshold_uses_baseline_destination_p90(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": f"trip_cust_001_{index:04d}",
                "observation_period": "baseline",
                "start_gps_x": 127.2000,
                "start_gps_y": 37.7000,
                "end_gps_x": 127.0000 + index * 0.0010,
                "end_gps_y": 37.5000,
            }
            for index in range(5)
        ]
        rows.append(
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_recent",
                "observation_period": "recent",
                "start_gps_x": 127.2500,
                "start_gps_y": 37.7200,
                "end_gps_x": 127.2500,
                "end_gps_y": 37.7200,
            }
        )
        zones = {"cust_001": [(127.0, 37.5)]}

        thresholds = fit_zone_departure_thresholds(rows, zones)
        expected_distances = [
            haversine_meters((float(row["end_gps_x"]), float(row["end_gps_y"])), zones["cust_001"][0])
            for row in rows
            if row["observation_period"] == "baseline"
        ]
        expected_p90 = round(percentile(expected_distances, 0.9), 2)

        self.assertEqual(thresholds["cust_001"]["living_zone_departure_threshold_sample_count"], 5)
        self.assertEqual(thresholds["cust_001"]["living_zone_departure_p90_raw_m"], expected_p90)
        self.assertEqual(thresholds["cust_001"]["living_zone_departure_p90_threshold_m"], 500.0)
        self.assertLess(expected_p90, 500.0)

    def test_generated_fixture_departure_thresholds_exist_for_all_customers(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        dbscan_results = fit_customer_dbscan_results(fixture.rows)
        zones = zone_centers_from_dbscan_results(dbscan_results)

        thresholds = fit_zone_departure_thresholds(fixture.rows, zones)

        self.assertEqual(set(thresholds), {f"cust_{index:03d}" for index in range(1, 31)})
        for customer_id, threshold in thresholds.items():
            baseline_destination_count = sum(
                1
                for row in fixture.rows
                if row["customer_id"] == customer_id and row["observation_period"] == "baseline"
            )
            self.assertEqual(threshold["living_zone_departure_threshold_sample_count"], baseline_destination_count)
            self.assertGreaterEqual(threshold["living_zone_departure_p90_raw_m"], 0.0)
            self.assertGreaterEqual(threshold["living_zone_departure_p90_threshold_m"], 500.0)
            self.assertLessEqual(threshold["living_zone_departure_p90_threshold_m"], 2000.0)
            self.assertEqual(threshold["living_zone_departure_threshold_percentile"], 0.9)

    def test_customer_trip_distance_threshold_uses_baseline_distance_p90(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": f"trip_cust_001_{index:04d}",
                "observation_period": "baseline",
                "trip_distance_km": distance,
            }
            for index, distance in enumerate([5.0, 8.0, 12.0, 20.0, 40.0], start=1)
        ]
        rows.append(
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "trip_id": "trip_cust_001_recent",
                "observation_period": "recent",
                "trip_distance_km": 120.0,
            }
        )

        thresholds = fit_customer_trip_distance_thresholds(rows)
        expected_p90 = round(percentile([5.0, 8.0, 12.0, 20.0, 40.0], 0.9), 2)

        self.assertEqual(thresholds["cust_001"]["baseline_trip_distance_p90_km"], expected_p90)
        self.assertEqual(thresholds["cust_001"]["baseline_trip_distance_threshold_sample_count"], 5)
        self.assertEqual(thresholds["cust_001"]["baseline_trip_distance_threshold_percentile"], 0.9)

    def test_movement_history_table_aggregates_customer_period_inputs(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        labeled_trips, _ = add_zone_features(fixture.rows)

        movement_rows = build_movement_history_table(labeled_trips)

        self.assertEqual(len(movement_rows), 60)
        self.assertEqual(
            {(row["customer_id"], row["period"]) for row in movement_rows},
            {(f"cust_{index:03d}", period) for index in range(1, 31) for period in ("baseline", "recent")},
        )
        for row in movement_rows:
            customer_period_trips = [
                trip
                for trip in labeled_trips
                if trip["customer_id"] == row["customer_id"] and trip["observation_period"] == row["period"]
            ]
            expected_out_zone_count = sum(trip["out_zone_flag"] for trip in customer_period_trips)
            expected_out_zone_distance = round(
                sum(trip["trip_distance_km"] for trip in customer_period_trips if trip["out_zone_flag"]),
                2,
            )
            outside_segment_trips = [
                trip for trip in customer_period_trips if trip["living_zone_outside_segment_flag"]
            ]
            expected_outside_segment_risk_events = sum(
                trip["speeding_count"]
                + trip["harsh_accel_count"]
                + trip["harsh_brake_count"]
                + trip["sharp_turn_count"]
                for trip in outside_segment_trips
            )

            self.assertIn(row["period"], {"baseline", "recent"})
            self.assertEqual(row["observation_days"], 60 if row["period"] == "baseline" else 30)
            self.assertEqual(row["trip_count"], len(customer_period_trips))
            self.assertGreater(row["active_day_count"], 0)
            self.assertEqual(row["living_zone_departure_count"], expected_out_zone_count)
            self.assertEqual(row["living_zone_departure_distance_km"], expected_out_zone_distance)
            self.assertEqual(row["out_zone_trip_count"], expected_out_zone_count)
            self.assertEqual(row["out_zone_distance_km"], expected_out_zone_distance)
            self.assertEqual(
                row["living_zone_outside_segment_risk_event_count"],
                expected_outside_segment_risk_events,
            )
            self.assertGreaterEqual(row["living_zone_outside_segment_speeding_per_100km"], 0.0)
            self.assertGreaterEqual(row["living_zone_outside_segment_harsh_accel_per_100km"], 0.0)
            self.assertGreaterEqual(row["living_zone_outside_segment_harsh_brake_per_100km"], 0.0)
            self.assertGreaterEqual(row["living_zone_departure_p90_raw_m"], 0.0)
            self.assertGreaterEqual(row["living_zone_departure_p90_threshold_m"], 500.0)
            self.assertGreater(row["living_zone_departure_threshold_sample_count"], 0)
            self.assertEqual(row["living_zone_departure_threshold_percentile"], 0.9)
            baseline_distances = [
                trip["trip_distance_km"]
                for trip in labeled_trips
                if trip["customer_id"] == row["customer_id"] and trip["observation_period"] == "baseline"
            ]
            self.assertEqual(row["baseline_trip_distance_p90_km"], round(percentile(baseline_distances, 0.9), 2))
            self.assertEqual(row["baseline_trip_distance_threshold_sample_count"], len(baseline_distances))
            self.assertEqual(row["baseline_trip_distance_threshold_percentile"], 0.9)
            baseline_daily_counts: dict[str, int] = {}
            for trip in labeled_trips:
                if trip["customer_id"] == row["customer_id"] and trip["observation_period"] == "baseline":
                    baseline_daily_counts[trip["service_date"]] = baseline_daily_counts.get(trip["service_date"], 0) + 1
            self.assertEqual(
                row["baseline_movement_frequency_p90_per_day"],
                round(percentile([float(count) for count in baseline_daily_counts.values()], 0.9), 4),
            )
            self.assertEqual(row["baseline_movement_frequency_threshold_sample_count"], len(baseline_daily_counts))
            self.assertEqual(row["baseline_movement_frequency_threshold_percentile"], 0.9)
            self.assertGreaterEqual(row["trip_frequency_per_day"], 0.0)
            self.assertGreaterEqual(row["avg_daily_distance_km"], 0.0)

    def test_customer_movement_frequency_threshold_uses_baseline_daily_trip_count_p90(self) -> None:
        rows = [
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "service_date": "2026-01-01",
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "service_date": "2026-01-02",
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "service_date": "2026-01-02",
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "service_date": "2026-01-03",
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "service_date": "2026-01-03",
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "baseline",
                "service_date": "2026-01-03",
            },
            {
                "customer_id": "cust_001",
                "driver_id": "driver_001",
                "observation_period": "recent",
                "service_date": "2026-03-01",
            },
        ]

        thresholds = fit_customer_movement_frequency_thresholds(rows)

        expected_p90 = round(percentile([1.0, 2.0, 3.0], 0.9), 4)
        self.assertEqual(thresholds["cust_001"]["baseline_movement_frequency_p90_per_day"], expected_p90)
        self.assertEqual(thresholds["cust_001"]["baseline_movement_frequency_threshold_sample_count"], 3)
        self.assertEqual(thresholds["cust_001"]["baseline_movement_frequency_threshold_percentile"], 0.9)

    def test_movement_history_table_supports_manual_labeled_trip_inputs(self) -> None:
        rows = [
            {
                "customer_id": "cust_999",
                "driver_id": "driver_999",
                "persona_type": "manual_case",
                "observation_period": "recent",
                "service_date": "2026-03-01",
                "trip_distance_km": 10.0,
                "core_zone_flag": 1,
                "buffer_zone_flag": 0,
                "in_zone_flag": 1,
                "out_zone_flag": 0,
                "route_repeat_flag": 1,
                "new_destination_flag": 0,
                "end_grid": "127.000:37.500",
                "speeding_count": 5,
                "harsh_accel_count": 5,
                "harsh_brake_count": 5,
                "sharp_turn_count": 5,
                "living_zone_departure_p90_raw_m": 420.0,
                "living_zone_departure_p90_threshold_m": 500.0,
                "living_zone_departure_threshold_sample_count": 12,
                "baseline_trip_distance_p90_km": 22.0,
                "baseline_trip_distance_threshold_sample_count": 9,
            },
            {
                "customer_id": "cust_999",
                "driver_id": "driver_999",
                "persona_type": "manual_case",
                "observation_period": "recent",
                "service_date": "2026-03-02",
                "trip_distance_km": 30.0,
                "core_zone_flag": 0,
                "buffer_zone_flag": 0,
                "in_zone_flag": 0,
                "out_zone_flag": 1,
                "route_repeat_flag": 0,
                "new_destination_flag": 1,
                "end_grid": "127.300:37.800",
                "speeding_count": 2,
                "harsh_accel_count": 1,
                "harsh_brake_count": 3,
                "sharp_turn_count": 0,
                "living_zone_departure_p90_raw_m": 420.0,
                "living_zone_departure_p90_threshold_m": 500.0,
                "living_zone_departure_threshold_sample_count": 12,
                "baseline_trip_distance_p90_km": 22.0,
                "baseline_trip_distance_threshold_sample_count": 9,
            },
        ]

        movement_row = build_movement_history_table(rows)[0]

        self.assertEqual(movement_row["customer_id"], "cust_999")
        self.assertEqual(movement_row["period"], "recent")
        self.assertEqual(movement_row["observation_days"], 30)
        self.assertEqual(movement_row["active_day_count"], 2)
        self.assertEqual(movement_row["trip_count"], 2)
        self.assertEqual(movement_row["total_distance_km"], 40.0)
        self.assertEqual(movement_row["avg_trip_distance_km"], 20.0)
        self.assertEqual(movement_row["out_zone_trip_ratio"], 0.5)
        self.assertEqual(movement_row["out_zone_distance_ratio"], 0.75)
        self.assertEqual(movement_row["living_zone_departure_count"], 1)
        self.assertEqual(movement_row["living_zone_departure_distance_km"], 30.0)
        self.assertEqual(movement_row["living_zone_departure_frequency_per_day"], 0.0333)
        self.assertEqual(movement_row["living_zone_outside_segment_speeding_count"], 2)
        self.assertEqual(movement_row["living_zone_outside_segment_harsh_accel_count"], 1)
        self.assertEqual(movement_row["living_zone_outside_segment_harsh_brake_count"], 3)
        self.assertEqual(movement_row["living_zone_outside_segment_risk_event_count"], 6)
        self.assertEqual(movement_row["living_zone_outside_segment_speeding_per_100km"], 6.6667)
        self.assertEqual(movement_row["living_zone_outside_segment_harsh_accel_per_100km"], 3.3333)
        self.assertEqual(movement_row["living_zone_outside_segment_harsh_brake_per_100km"], 10.0)
        self.assertEqual(movement_row["living_zone_departure_p90_raw_m"], 420.0)
        self.assertEqual(movement_row["living_zone_departure_p90_threshold_m"], 500.0)
        self.assertEqual(movement_row["living_zone_departure_threshold_sample_count"], 12)
        self.assertEqual(movement_row["living_zone_departure_threshold_percentile"], 0.9)
        self.assertEqual(movement_row["baseline_trip_distance_p90_km"], 22.0)
        self.assertEqual(movement_row["baseline_trip_distance_threshold_sample_count"], 9)
        self.assertEqual(movement_row["baseline_trip_distance_threshold_percentile"], 0.9)
        self.assertEqual(movement_row["baseline_movement_frequency_p90_per_day"], 0.0)
        self.assertEqual(movement_row["baseline_movement_frequency_threshold_sample_count"], 0)
        self.assertEqual(movement_row["baseline_movement_frequency_threshold_percentile"], 0.9)
        self.assertEqual(movement_row["route_repeat_ratio"], 0.5)
        self.assertEqual(movement_row["new_destination_count"], 1)


if __name__ == "__main__":
    unittest.main()

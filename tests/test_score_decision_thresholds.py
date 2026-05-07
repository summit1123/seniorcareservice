from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.models.score_rules import build_score_table, calculate_out_zone_risk, calculate_senior_safe_mileage_score
from src.product.decision_rules import CARE_DECISIONS, build_decision_table, decide


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class TestScoreDecisionThresholds(unittest.TestCase):
    def test_decision_rules_provide_seed_care_decision_labels(self) -> None:
        base_row = {
            "customer_id": "cust_001",
            "driver_id": "driver_001",
            "persona_type": "stable_local_low_mileage",
            "safe_driving_score": "95.0",
            "mileage_baseline_score": "80.0",
            "senior_safe_mileage_score": "88.0",
            "risk_change_score": "20.0",
            "familiar_zone_score": "70.0",
            "pattern_change_score": "18.0",
            "out_zone_behavior_risk": "20.0",
            "care_trigger_score": "18.0",
        }

        favorable = decide(base_row)
        standard = decide(
            {
                **base_row,
                "customer_id": "cust_002",
                "driver_id": "driver_002",
                "senior_safe_mileage_score": "72.0",
                "risk_change_score": "32.0",
                "care_trigger_score": "34.0",
            }
        )
        preventive = decide(
            {
                **base_row,
                "customer_id": "cust_003",
                "driver_id": "driver_003",
                "senior_safe_mileage_score": "58.0",
                "risk_change_score": "74.0",
                "pattern_change_score": "68.0",
                "out_zone_behavior_risk": "76.0",
                "care_trigger_score": "72.0",
            }
        )

        self.assertEqual(favorable["care_decision"], "우대")
        self.assertEqual(standard["care_decision"], "기본")
        self.assertEqual(preventive["care_decision"], "예방 케어")
        self.assertEqual(favorable["decision"], favorable["care_decision"])
        self.assertEqual({favorable["care_decision"], standard["care_decision"], preventive["care_decision"]}, CARE_DECISIONS)

    def test_out_zone_risk_uses_living_zone_outside_segment_change_indicators(self) -> None:
        base_row = {
            "out_zone_ratio": "0.20",
            "out_zone_ratio_delta": "0.05",
            "night_ratio": "0.10",
            "night_ratio_delta": "0.00",
            "living_zone_outside_segment_risk_events_per_100km": "2.0",
            "living_zone_outside_segment_harsh_brake_per_100km": "1.0",
        }
        changed_row = {
            **base_row,
            "living_zone_outside_segment_distance_ratio_delta": "0.30",
            "living_zone_outside_segment_risk_events_delta_per_100km": "6.0",
            "living_zone_outside_segment_night_ratio_delta": "0.25",
            "living_zone_outside_segment_risk_change_score": "75.0",
        }

        self.assertGreater(calculate_out_zone_risk(changed_row), calculate_out_zone_risk(base_row))
        self.assertEqual(calculate_out_zone_risk(changed_row), 52.35)

    def test_senior_safe_mileage_score_reflects_outside_living_zone_risk_change(self) -> None:
        base_row = {
            "total_km": "300.0",
            "speeding_per_100km": "0.0",
            "harsh_accel_per_100km": "0.0",
            "harsh_brake_per_100km": "0.0",
            "sharp_turn_per_100km": "0.0",
            "night_ratio": "0.00",
            "in_zone_total_km": "250.0",
            "in_zone_speeding_per_100km": "0.0",
            "in_zone_harsh_accel_per_100km": "0.0",
            "in_zone_harsh_brake_per_100km": "0.0",
            "in_zone_sharp_turn_per_100km": "0.0",
            "in_zone_night_ratio": "0.0",
            "out_zone_ratio": "0.10",
            "out_zone_ratio_delta": "0.00",
            "night_ratio_delta": "0.00",
            "living_zone_outside_segment_count": "1",
            "living_zone_outside_segment_km": "50.0",
            "living_zone_outside_segment_speeding_per_100km": "0.0",
            "living_zone_outside_segment_harsh_accel_per_100km": "0.0",
            "living_zone_outside_segment_harsh_brake_per_100km": "0.0",
            "living_zone_outside_segment_sharp_turn_per_100km": "0.0",
            "living_zone_outside_segment_risk_events_per_100km": "0.0",
            "living_zone_outside_segment_risk_change_score": "0.0",
        }
        changed_row = {
            **base_row,
            "living_zone_outside_segment_distance_ratio_delta": "0.40",
            "living_zone_outside_segment_risk_events_delta_per_100km": "8.0",
            "living_zone_outside_segment_night_ratio_delta": "0.30",
            "living_zone_outside_segment_risk_change_score": "90.0",
        }

        self.assertLess(
            calculate_senior_safe_mileage_score(changed_row),
            calculate_senior_safe_mileage_score(base_row),
        )
        self.assertEqual(calculate_senior_safe_mileage_score(base_row), 88.97)
        self.assertEqual(calculate_senior_safe_mileage_score(changed_row), 82.36)

    def test_p90_thresholds_flow_from_scores_to_customer_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            model_feature_path = tmp_path / "model_feature_table.csv"
            pattern_score_path = tmp_path / "pattern_change_score.csv"
            score_table_path = tmp_path / "score_table.csv"
            decision_table_path = tmp_path / "decision_table.csv"

            write_rows(
                model_feature_path,
                [
                    {
                        "customer_id": "cust_001",
                        "driver_id": "driver_001",
                        "persona_type": "recent_outer_risk_change",
                        "speeding_per_100km": 1.0,
                        "harsh_accel_per_100km": 0.5,
                        "harsh_brake_per_100km": 0.25,
                        "sharp_turn_per_100km": 0.0,
                        "night_ratio": 0.1,
                        "in_zone_total_km": 80.0,
                        "in_zone_trip_count": 8,
                        "in_zone_distance_ratio": 0.8,
                        "in_zone_night_ratio": 0.0,
                        "in_zone_speeding_per_100km": 0.0,
                        "in_zone_harsh_accel_per_100km": 0.0,
                        "in_zone_harsh_brake_per_100km": 1.0,
                        "in_zone_sharp_turn_per_100km": 0.0,
                        "in_zone_risk_events_per_100km": 1.0,
                        "zone_stability_score": 72.0,
                        "out_zone_ratio": 0.2,
                        "out_zone_ratio_delta": 0.15,
                        "night_ratio_delta": 0.05,
                        "zone_buffer_m": 640.12,
                        "living_zone_departure_p90_raw_m": 640.12,
                        "living_zone_departure_p90_threshold_m": 640.12,
                        "living_zone_departure_threshold_sample_count": 60,
                        "living_zone_departure_threshold_percentile": 0.9,
                        "baseline_trip_distance_p90_km": 18.34,
                        "baseline_trip_distance_threshold_sample_count": 58,
                        "baseline_trip_distance_threshold_percentile": 0.9,
                        "baseline_movement_frequency_p90_per_day": 3.2,
                        "baseline_movement_frequency_threshold_sample_count": 42,
                        "baseline_movement_frequency_threshold_percentile": 0.9,
                        "primary_zone_p90_radius_m": 180.55,
                        "living_zone_outside_segment_criteria": "start_or_end_distance_gt_living_zone_departure_p90_threshold_m",
                        "living_zone_outside_segment_count": 2,
                        "living_zone_outside_segment_ratio": 0.2,
                        "living_zone_outside_segment_km": 20.0,
                        "living_zone_outside_segment_distance_ratio": 0.2,
                        "living_zone_outside_segment_speeding_count": 1,
                        "living_zone_outside_segment_harsh_accel_count": 0,
                        "living_zone_outside_segment_harsh_brake_count": 1,
                        "living_zone_outside_segment_sharp_turn_count": 0,
                        "living_zone_outside_segment_risk_event_count": 2,
                        "living_zone_outside_segment_speeding_per_100km": 5.0,
                        "living_zone_outside_segment_harsh_accel_per_100km": 0.0,
                        "living_zone_outside_segment_harsh_brake_per_100km": 5.0,
                        "living_zone_outside_segment_sharp_turn_per_100km": 0.0,
                        "living_zone_outside_segment_risk_events_per_100km": 10.0,
                    }
                ],
            )
            write_rows(pattern_score_path, [{"driver_id": "driver_001", "pattern_change_score": 61.0}])

            score_rows = build_score_table(
                model_feature_path=model_feature_path,
                pattern_score_path=pattern_score_path,
                output_path=score_table_path,
            )
            decision_rows = build_decision_table(score_table_path=score_table_path, output_path=decision_table_path)

            self.assertEqual(score_rows[0]["customer_id"], "cust_001")
            self.assertEqual(score_rows[0]["in_zone_safe_score"], 97.0)
            self.assertEqual(score_rows[0]["out_zone_safe_score"], 65.0)
            self.assertEqual(score_rows[0]["overall_safe_driving_score"], 92.5)
            self.assertEqual(score_rows[0]["safe_driving_score"], 88.1)
            self.assertEqual(score_rows[0]["out_zone_behavior_risk"], 47.25)
            self.assertEqual(score_rows[0]["risk_change_score"], 47.25)
            self.assertEqual(score_rows[0]["senior_safe_mileage_score"], 86.61)
            self.assertEqual(score_rows[0]["in_zone_risk_events_per_100km"], 1.0)
            self.assertEqual(score_rows[0]["living_zone_departure_p90_threshold_m"], 640.12)
            self.assertEqual(score_rows[0]["baseline_trip_distance_p90_km"], 18.34)
            self.assertEqual(score_rows[0]["baseline_movement_frequency_p90_per_day"], 3.2)
            self.assertEqual(score_rows[0]["living_zone_outside_segment_count"], 2)
            self.assertEqual(score_rows[0]["living_zone_outside_segment_ratio"], 0.2)

            decision = decision_rows[0]
            thresholds = json.loads(decision["p90_thresholds_json"])
            outside_segments = json.loads(decision["outside_living_zone_segments_json"])
            self.assertEqual(decision["customer_id"], "cust_001")
            self.assertIn(decision["care_decision"], CARE_DECISIONS)
            self.assertEqual(decision["decision"], decision["care_decision"])
            self.assertEqual(decision["risk_change_score"], 47.25)
            self.assertEqual(decision["senior_safe_mileage_score"], 86.61)
            self.assertEqual(decision["living_zone_departure_p90_threshold_m"], 640.12)
            self.assertEqual(thresholds["living_zone_departure_p90_threshold_m"], 640.12)
            self.assertEqual(thresholds["living_zone_departure_threshold_sample_count"], 60)
            self.assertEqual(thresholds["baseline_trip_distance_p90_km"], 18.34)
            self.assertEqual(thresholds["baseline_movement_frequency_p90_per_day"], 3.2)
            self.assertEqual(thresholds["primary_zone_p90_radius_m"], 180.55)
            self.assertEqual(outside_segments["living_zone_outside_segment_count"], 2)
            self.assertEqual(outside_segments["living_zone_outside_segment_ratio"], 0.2)
            self.assertEqual(outside_segments["living_zone_outside_segment_risk_events_per_100km"], 10.0)
            self.assertEqual(
                outside_segments["living_zone_outside_segment_criteria"],
                "start_or_end_distance_gt_living_zone_departure_p90_threshold_m",
            )


if __name__ == "__main__":
    unittest.main()

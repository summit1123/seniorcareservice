from __future__ import annotations

import csv
import json
import unittest
from collections import defaultdict
from pathlib import Path

from src.product.annual_ab_comparison import (
    build_annual_ab_comparison_rows,
    build_existing_tier_segments,
    build_judge_demo_view_model,
    discount_amount,
)
from src.product.mileage_discount_table import lookup_existing_mileage_discount


ROOT = Path(__file__).resolve().parents[1]
PROFILE_FIXTURE = ROOT / "data" / "fixtures" / "annual_persona_profiles.json"
TRIP_FIXTURE = ROOT / "data" / "fixtures" / "annual_trip_logs.csv"
COMPARISON_OUTPUT = ROOT / "data" / "processed" / "annual_ab_comparison.csv"
VIEW_MODEL_OUTPUT = ROOT / "data" / "fixtures" / "judge_demo_view_model.json"


class TestAnnualABComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_annual_ab_comparison_rows()
        cls.view_model = build_judge_demo_view_model(cls.rows)
        with PROFILE_FIXTURE.open(encoding="utf-8") as file:
            cls.profiles = json.load(file)
        with TRIP_FIXTURE.open(newline="", encoding="utf-8") as csvfile:
            cls.trips = list(csv.DictReader(csvfile))

    def test_builds_30_row_same_input_annual_comparison(self) -> None:
        self.assertEqual(len(self.rows), 30)
        for row in self.rows:
            self.assertEqual(row["schema_version"], "senior-safe-mileage-annual-ab-comparison/v1")
            self.assertEqual(row["annual_distance_scope"], "evaluation_period_only")
            self.assertEqual(int(row["baseline_60_day_excluded_from_discount"]), 1)
            self.assertTrue(str(row["same_input_contract_id"]).startswith("same-annual-input:"))
            self.assertGreaterEqual(float(row["existing_discount_rate_pct"]), 0.0)
            self.assertGreaterEqual(float(row["proposed_discount_rate_pct"]), 0.0)
            self.assertNotIn("monthly_discount", json.dumps(row, ensure_ascii=False))
            self.assertNotIn("CAGR", json.dumps(row, ensure_ascii=False))
            self.assertNotIn("월복리", json.dumps(row, ensure_ascii=False))

    def test_existing_discount_uses_evaluation_period_distance_not_baseline(self) -> None:
        profiles_by_customer = {profile["customer_id"]: profile for profile in self.profiles["drivers"]}
        evaluation_distance_by_customer: dict[str, float] = defaultdict(float)
        baseline_distance_by_customer: dict[str, float] = defaultdict(float)
        for trip in self.trips:
            if trip["period_role"] == "evaluation":
                evaluation_distance_by_customer[trip["customer_id"]] += float(trip["trip_distance_km"])
            else:
                baseline_distance_by_customer[trip["customer_id"]] += float(trip["trip_distance_km"])

        for row in self.rows:
            customer_id = row["customer_id"]
            profile = profiles_by_customer[customer_id]
            self.assertGreater(baseline_distance_by_customer[customer_id], 0)
            self.assertEqual(
                float(row["annual_total_distance_km"]),
                round(evaluation_distance_by_customer[customer_id], 2),
            )
            lookup = lookup_existing_mileage_discount(
                evaluation_distance_by_customer[customer_id],
                profile["vehicle_class"],
            )
            self.assertEqual(float(row["existing_discount_rate_pct"]), lookup.discount_rate_pct)
            self.assertEqual(
                int(row["existing_discount_amount_krw"]),
                discount_amount(int(profile["base_premium_krw"]), lookup.discount_rate_pct),
            )

    def test_same_existing_mileage_tier_is_split_by_proposed_decisions(self) -> None:
        segments = build_existing_tier_segments(self.rows)
        self.assertGreaterEqual(len(segments), 6)
        self.assertTrue(
            any(
                segment["customer_count"] > 1
                and len(segment["proposed_decision_signal_counts"]) > 1
                for segment in segments
            )
        )
        self.assertGreater(sum(int(row["preventive_care_required"]) for row in self.rows), 0)

    def test_proposed_rate_adjusts_independently_by_integrated_score(self) -> None:
        deltas = [float(row["discount_rate_delta_pct"]) for row in self.rows]

        self.assertGreater(sum(delta > 0 for delta in deltas), 0)
        self.assertGreater(sum(delta < 0 for delta in deltas), 0)
        self.assertNotEqual(
            sum(int(row["existing_discount_amount_krw"]) for row in self.rows),
            sum(int(row["proposed_discount_amount_krw"]) for row in self.rows),
        )
        for row in self.rows:
            self.assertEqual(
                row["proposed_discount_rule_id"],
                "annual_integrated_score_adjusted_discount/v4",
            )
            self.assertNotIn("portfolio_existing_discount_budget_krw", row["same_input_contract_json"])

    def test_view_model_is_ready_for_react_driver_selection(self) -> None:
        payload = self.view_model

        self.assertEqual(payload["schema_version"], "senior-safe-mileage-judge-demo-view-model/v1")
        self.assertEqual(payload["summary"]["customer_count"], 30)
        self.assertTrue(payload["summary"]["same_input_contract_all_rows"])
        self.assertEqual(len(payload["persona_summaries"]), 6)
        self.assertEqual(len(payload["driver_options"]), 30)
        self.assertEqual(len(payload["drivers"]), 30)
        first = payload["drivers"][0]
        self.assertEqual(len(first["monthly_evidence"]), 12)
        self.assertIn("ab_comparison", first)
        self.assertIn("annual_score", first)
        self.assertIn(first["customer_id"], payload["by_customer_id"])

    def test_persisted_outputs_match_builder_contract(self) -> None:
        with COMPARISON_OUTPUT.open(newline="", encoding="utf-8") as csvfile:
            persisted_rows = list(csv.DictReader(csvfile))
        with VIEW_MODEL_OUTPUT.open(encoding="utf-8") as file:
            persisted_view_model = json.load(file)

        self.assertEqual(len(persisted_rows), len(self.rows))
        self.assertEqual(persisted_view_model["schema_version"], self.view_model["schema_version"])
        self.assertEqual(persisted_view_model["summary"], self.view_model["summary"])


if __name__ == "__main__":
    unittest.main()

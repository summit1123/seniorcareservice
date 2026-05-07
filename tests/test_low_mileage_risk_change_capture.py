from __future__ import annotations

import unittest

from src.agents.evaluation_agent import build_evaluation_input, evaluate_selected_policy


class TestLowMileageRiskChangeCapture(unittest.TestCase):
    def test_proposed_model_captures_at_least_four_of_five_low_mileage_risk_change_customers(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        rows = [
            row
            for row in result["customer_rows"]
            if row["persona_type"] == "recent_outer_risk_change"
        ]

        self.assertEqual(len(rows), 5)
        self.assertTrue(all(bool(row["risk_change_target"]) for row in rows))
        self.assertGreaterEqual(
            result["summary_metrics"]["proposed_capture_count"],
            4,
        )
        self.assertGreaterEqual(
            result["summary_metrics"]["proposed_low_mileage_high_risk_capture"],
            0.8,
        )
        self.assertGreaterEqual(
            sum(1 for row in rows if bool(row["proposed_detected"])),
            4,
        )
        missed = [row["customer_id"] for row in rows if not bool(row["proposed_detected"])]
        self.assertLessEqual(len(missed), 1)

    def test_captured_low_mileage_risk_change_customers_have_preventive_care_decisions(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        rows = [
            row
            for row in result["customer_rows"]
            if row["persona_type"] == "recent_outer_risk_change"
        ]

        captured_rows = [row for row in rows if bool(row["proposed_detected"])]

        self.assertGreaterEqual(len(captured_rows), 4)
        self.assertTrue(
            all(row["care_decision"] == "예방 케어" for row in captured_rows)
        )
        self.assertTrue(
            all(float(row["risk_change_score"]) >= 60.0 for row in captured_rows)
        )


if __name__ == "__main__":
    unittest.main()

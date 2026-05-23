from __future__ import annotations

import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from src.features.monthly_living_zone import (
    MAX_ZONE_BUFFER_M,
    MIN_ZONE_BUFFER_M,
    build_monthly_living_zone_outputs,
    write_csv,
)
from src.product.annual_scoring_engine import build_annual_score_table


class TestMonthlyLivingZone(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshots, cls.monthly_rows = build_monthly_living_zone_outputs()
        with tempfile.TemporaryDirectory() as tmpdir:
            cls.monthly_csv = Path(tmpdir) / "monthly_score_table.csv"
            write_csv(cls.monthly_csv, cls.monthly_rows)
            cls.annual_rows = build_annual_score_table(monthly_score_input=cls.monthly_csv)

    def test_builds_12_month_snapshots_without_current_month_leakage(self) -> None:
        self.assertEqual(self.snapshots["schema_version"], "senior-monthly-living-zone-snapshots/v1")
        self.assertEqual(self.snapshots["snapshot_count"], 360)
        self.assertEqual(len(self.monthly_rows), 360)
        self.assertTrue(self.snapshots["analysis_method"]["current_month_excluded_from_zone_fit"])
        self.assertTrue(self.snapshots["analysis_method"]["monthly_scores_are_evidence_not_discount_rates"])

        months_by_customer: dict[str, set[int]] = defaultdict(set)
        basis_statuses = Counter()
        for snapshot in self.snapshots["snapshots"]:
            months_by_customer[snapshot["customer_id"]].add(int(snapshot["month"]))
            basis_statuses[snapshot["basis_window"]["basis_status"]] += 1
            self.assertEqual(snapshot["leakage_guard"]["current_month_trip_count_in_basis"], 0)
            if int(snapshot["month"]) == 1:
                self.assertEqual(snapshot["basis_window"]["basis_status"], "pre_policy_60_day_dbscan")
                self.assertGreater(snapshot["basis_window"]["basis_trip_count"], 0)
            else:
                self.assertEqual(snapshot["basis_window"]["basis_status"], "rolling_60_day_dbscan")

        self.assertEqual(set(months_by_customer), {f"cust_{index:03d}" for index in range(1, 31)})
        self.assertTrue(all(months == set(range(1, 13)) for months in months_by_customer.values()))
        self.assertEqual(basis_statuses["pre_policy_60_day_dbscan"], 30)
        self.assertEqual(basis_statuses["rolling_60_day_dbscan"], 330)

    def test_monthly_score_table_has_four_evidence_scores_and_clamped_p90_buffers(self) -> None:
        for row in self.monthly_rows:
            threshold = float(row["living_zone_departure_p90_threshold_m"])
            self.assertGreaterEqual(threshold, MIN_ZONE_BUFFER_M)
            self.assertLessEqual(threshold, MAX_ZONE_BUFFER_M)
            self.assertEqual(row["score_role"], "annual_decision_evidence_not_monthly_discount")
            self.assertNotIn("monthly_discount_rate_pct", row)
            for field in (
                "mileage_score",
                "in_zone_safe_driving_score",
                "out_zone_safe_driving_score",
                "out_zone_pattern_change_risk",
            ):
                value = float(row[field])
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 100.0)

        interpretation_totals = Counter()
        for row in self.monthly_rows:
            interpretation_totals["existing_living_zone"] += int(row["existing_living_zone_trip_count"])
            interpretation_totals["candidate_living_zone"] += int(row["candidate_living_zone_trip_count"])
            interpretation_totals["out_zone_safe_driving"] += int(row["out_zone_safe_driving_trip_count"])
            interpretation_totals["out_zone_pattern_change_risk"] += int(
                row["out_zone_pattern_change_risk_trip_count"]
            )
        for interpretation in (
            "existing_living_zone",
            "candidate_living_zone",
            "out_zone_safe_driving",
            "out_zone_pattern_change_risk",
        ):
            self.assertGreater(interpretation_totals[interpretation], 0, interpretation)

    def test_annual_score_rolls_up_12_months_and_preserves_risk_change_signal(self) -> None:
        self.assertEqual(len(self.annual_rows), 30)
        by_persona: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in self.annual_rows:
            self.assertEqual(int(row["months_evaluated"]), 12)
            self.assertEqual(int(row["monthly_scores_are_evidence_not_discount_rates"]), 1)
            for field in (
                "annual_mileage_score",
                "annual_in_zone_safe_driving_score",
                "annual_out_zone_safe_driving_score",
                "annual_out_zone_pattern_change_risk",
                "annual_senior_safe_mileage_score",
            ):
                value = float(row[field])
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 100.0)
            by_persona[str(row["persona_type"])].append(row)

        recent_risk_avg = _avg(by_persona["recent_outer_risk_change"], "annual_out_zone_pattern_change_risk")
        stable_outer_avg = _avg(by_persona["stable_outer_safe"], "annual_out_zone_pattern_change_risk")
        stable_local_avg = _avg(by_persona["stable_local_low_mileage"], "annual_out_zone_pattern_change_risk")
        self.assertGreater(recent_risk_avg, stable_outer_avg)
        self.assertGreater(recent_risk_avg, stable_local_avg)
        self.assertGreater(
            sum(int(row["preventive_care_detected"]) for row in by_persona["recent_outer_risk_change"]),
            0,
        )


def _avg(rows: list[dict[str, object]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


if __name__ == "__main__":
    unittest.main()

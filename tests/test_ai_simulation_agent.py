from __future__ import annotations

import csv
from datetime import date, timedelta
import json
from pathlib import Path
import unittest

from src.agents.ai_simulation_agent import AISimulationAgent, TRIP_FIELDS, choose_day_indices
from src.agents.persona_agent import EXPECTED_PERSONA_TYPES, PersonaAgent


ROOT = Path(__file__).resolve().parents[1]
PERSISTED_TRIP_FIXTURE = ROOT / "data" / "fixtures" / "senior_trip_logs.csv"
PERSISTED_MANIFEST = ROOT / "data" / "fixtures" / "simulation_manifest.json"


class TestAISimulationAgentCoverage(unittest.TestCase):
    def test_input_fixtures_define_exactly_six_personas_with_five_customers_each(self) -> None:
        agent = PersonaAgent()
        profiles = agent.load_profiles()
        identities = agent.load_customer_identities()
        patterns = agent.load_customer_driving_patterns()

        profile_personas = {profile.persona_type for profile in profiles}
        identity_persona_counts = {
            persona_type: sum(1 for identity in identities if identity.persona_type == persona_type)
            for persona_type in EXPECTED_PERSONA_TYPES
        }
        pattern_persona_counts = {
            persona_type: sum(1 for pattern in patterns if pattern.persona_type == persona_type)
            for persona_type in EXPECTED_PERSONA_TYPES
        }

        self.assertEqual(len(profile_personas), 6)
        self.assertEqual(profile_personas, EXPECTED_PERSONA_TYPES)
        self.assertEqual(identity_persona_counts, {persona_type: 5 for persona_type in EXPECTED_PERSONA_TYPES})
        self.assertEqual(pattern_persona_counts, {persona_type: 5 for persona_type in EXPECTED_PERSONA_TYPES})
        self.assertEqual(len(identities), 30)
        self.assertEqual(len(patterns), 30)

    def test_choose_day_indices_spans_baseline_window(self) -> None:
        import random

        days = choose_day_indices("baseline", 24, random.Random(7))

        self.assertEqual(days[0], 1)
        self.assertEqual(days[-1], 60)

    def test_choose_day_indices_spans_recent_window(self) -> None:
        import random

        days = choose_day_indices("recent", 10, random.Random(7))

        self.assertEqual(days[0], 61)
        self.assertEqual(days[-1], 90)

    def test_baseline_coverage_validation_rejects_missing_boundary(self) -> None:
        agent = AISimulationAgent()
        baseline_rows = [
            {"observation_day_index": 1, "service_date": "2026-01-01"},
            {"observation_day_index": 59, "service_date": "2026-02-28"},
        ]

        with self.assertRaisesRegex(ValueError, "complete 60-day observation window"):
            agent._validate_baseline_coverage("cust_001", baseline_rows)

    def test_recent_coverage_validation_rejects_missing_boundary(self) -> None:
        agent = AISimulationAgent()
        recent_rows = [
            {"observation_day_index": 61, "service_date": "2026-03-02"},
            {"observation_day_index": 89, "service_date": "2026-03-30"},
        ]

        with self.assertRaisesRegex(ValueError, "complete 30-day observation window"):
            agent._validate_recent_coverage("cust_001", recent_rows)

    def test_customer_90_day_coverage_validation_rejects_missing_period_boundary(self) -> None:
        agent = AISimulationAgent()
        customer_rows = [
            {"observation_period": "baseline", "observation_day_index": 1, "service_date": "2026-01-01"},
            {"observation_period": "baseline", "observation_day_index": 60, "service_date": "2026-03-01"},
            {"observation_period": "recent", "observation_day_index": 61, "service_date": "2026-03-02"},
            {"observation_period": "recent", "observation_day_index": 89, "service_date": "2026-03-30"},
        ]

        with self.assertRaisesRegex(ValueError, "complete 90-day observation window"):
            agent._validate_customer_90_day_coverage("cust_001", customer_rows)

    def test_customer_90_day_coverage_validation_rejects_overlapping_service_date(self) -> None:
        agent = AISimulationAgent()
        customer_rows = [
            {"observation_period": "baseline", "observation_day_index": 1, "service_date": "2026-01-01"},
            {"observation_period": "baseline", "observation_day_index": 59, "service_date": "2026-03-02"},
            {"observation_period": "baseline", "observation_day_index": 60, "service_date": "2026-03-01"},
            {"observation_period": "recent", "observation_day_index": 61, "service_date": "2026-03-02"},
            {"observation_period": "recent", "observation_day_index": 90, "service_date": "2026-03-31"},
        ]

        with self.assertRaisesRegex(ValueError, "non-overlapping"):
            agent._validate_customer_90_day_coverage("cust_001", customer_rows)

    def test_generated_fixture_has_complete_90_day_coverage_for_each_customer(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        rows_by_customer: dict[str, list[dict[str, object]]] = {}
        for row in fixture.rows:
            rows_by_customer.setdefault(str(row["customer_id"]), []).append(row)

        self.assertEqual(len(rows_by_customer), 30)
        for customer_id, customer_rows in rows_by_customer.items():
            days = {int(row["observation_day_index"]) for row in customer_rows}
            periods = {str(row["observation_period"]) for row in customer_rows}
            boundary_dates = {
                int(row["observation_day_index"]): str(row["service_date"])
                for row in customer_rows
                if int(row["observation_day_index"]) in {1, 60, 61, 90}
            }

            self.assertEqual(periods, {"baseline", "recent"}, customer_id)
            self.assertTrue({1, 60, 61, 90}.issubset(days), customer_id)
            self.assertEqual(boundary_dates[1], "2026-01-01")
            self.assertEqual(boundary_dates[60], "2026-03-01")
            self.assertEqual(boundary_dates[61], "2026-03-02")
            self.assertEqual(boundary_dates[90], "2026-03-31")

    def test_generated_fixture_period_dates_are_correctly_defined_and_non_overlapping(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        rows_by_customer: dict[str, list[dict[str, object]]] = {}
        expected_baseline_start = date(2026, 1, 1)
        expected_baseline_end = expected_baseline_start + timedelta(days=59)
        expected_recent_start = expected_baseline_start + timedelta(days=60)
        expected_recent_end = expected_baseline_start + timedelta(days=89)

        for row in fixture.rows:
            rows_by_customer.setdefault(str(row["customer_id"]), []).append(row)

        for customer_id, customer_rows in rows_by_customer.items():
            baseline_dates = {
                date.fromisoformat(str(row["service_date"]))
                for row in customer_rows
                if row["observation_period"] == "baseline"
            }
            recent_dates = {
                date.fromisoformat(str(row["service_date"]))
                for row in customer_rows
                if row["observation_period"] == "recent"
            }

            self.assertEqual(min(baseline_dates), expected_baseline_start, customer_id)
            self.assertEqual(max(baseline_dates), expected_baseline_end, customer_id)
            self.assertEqual(min(recent_dates), expected_recent_start, customer_id)
            self.assertEqual(max(recent_dates), expected_recent_end, customer_id)
            self.assertLess(max(baseline_dates), min(recent_dates), customer_id)
            self.assertFalse(baseline_dates & recent_dates, customer_id)

    def test_generated_fixture_has_recent_30_day_records_for_each_customer(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        rows_by_customer: dict[str, list[dict[str, object]]] = {}
        for row in fixture.rows:
            rows_by_customer.setdefault(str(row["customer_id"]), []).append(row)

        self.assertEqual(len(rows_by_customer), 30)
        for customer_rows in rows_by_customer.values():
            recent_rows = [row for row in customer_rows if row["observation_period"] == "recent"]
            recent_days = {int(row["observation_day_index"]) for row in recent_rows}

            self.assertGreaterEqual(len(recent_rows), 8)
            self.assertIn(61, recent_days)
            self.assertIn(90, recent_days)
            self.assertTrue(all(61 <= int(row["observation_day_index"]) <= 90 for row in recent_rows))

    def test_persisted_fixture_matches_app_local_data_contract(self) -> None:
        with PERSISTED_TRIP_FIXTURE.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

        with PERSISTED_MANIFEST.open(encoding="utf-8") as file:
            manifest = json.load(file)

        self.assertEqual(reader.fieldnames, TRIP_FIELDS)
        self.assertEqual(manifest["schema_version"], "senior-trip-log-fixture/v1")
        self.assertEqual(manifest["trip_count"], len(rows))
        self.assertEqual(len({row["customer_id"] for row in rows}), 30)
        self.assertEqual(len(manifest["persona_customer_counts"]), 6)
        self.assertEqual(set(manifest["persona_customer_counts"]), EXPECTED_PERSONA_TYPES)
        self.assertEqual(manifest["persona_customer_counts"], {persona_type: 5 for persona_type in EXPECTED_PERSONA_TYPES})
        self.assertEqual(
            manifest["observation_period"],
            {
                "baseline_days": 60,
                "recent_days": 30,
                "baseline_start_date": "2026-01-01",
                "baseline_end_date": "2026-03-01",
                "recent_start_date": "2026-03-02",
                "recent_end_date": "2026-03-31",
                "periods_non_overlapping": True,
            },
        )
        self.assertTrue(manifest["customer_90_day_coverage_validation"]["passed"])
        self.assertEqual(manifest["customer_90_day_coverage_validation"]["complete_customer_count"], 30)
        self.assertEqual(len(manifest["customer_90_day_coverage_validation"]["customers"]), 30)
        self.assertTrue(
            all(
                row["passed"]
                for row in manifest["customer_90_day_coverage_validation"]["customers"].values()
            )
        )
        self.assertTrue(manifest["baseline_coverage_validation"]["passed"])
        self.assertTrue(manifest["recent_coverage_validation"]["passed"])

        fixture_persona_counts = {
            persona_type: len({row["customer_id"] for row in rows if row["persona_type"] == persona_type})
            for persona_type in EXPECTED_PERSONA_TYPES
        }
        self.assertEqual(fixture_persona_counts, {persona_type: 5 for persona_type in EXPECTED_PERSONA_TYPES})

        for customer_id in {row["customer_id"] for row in rows}:
            customer_rows = [row for row in rows if row["customer_id"] == customer_id]
            baseline_days = {int(row["observation_day_index"]) for row in customer_rows if row["observation_period"] == "baseline"}
            recent_days = {int(row["observation_day_index"]) for row in customer_rows if row["observation_period"] == "recent"}

            self.assertGreaterEqual(len([row for row in customer_rows if row["observation_period"] == "baseline"]), 20)
            self.assertGreaterEqual(len([row for row in customer_rows if row["observation_period"] == "recent"]), 8)
            self.assertIn(1, baseline_days)
            self.assertIn(60, baseline_days)
            self.assertIn(61, recent_days)
            self.assertIn(90, recent_days)
            self.assertTrue(
                manifest["customer_90_day_coverage_validation"]["customers"][customer_id]["periods_non_overlapping"]
            )

    def test_recent_risk_change_persona_has_multiple_recent_signals(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        signal_counts: dict[str, int] = {}
        for row in fixture.rows:
            if row["persona_type"] != "recent_outer_risk_change" or row["observation_period"] != "recent":
                continue
            customer_id = str(row["customer_id"])
            if row["synthetic_risk_tag"] == "recent_risk_increase":
                signal_counts[customer_id] = signal_counts.get(customer_id, 0) + 1

        self.assertEqual(len(signal_counts), 5)
        self.assertTrue(all(count >= 3 for count in signal_counts.values()))

    def test_generated_fixture_has_persona_specific_risk_signal_fields(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        required_fields = {
            "night_driving_signal",
            "sudden_braking_signal",
            "route_deviation_signal",
            "reduced_activity_signal",
            "fatigue_indicator",
            "risk_signal_codes",
            "persona_risk_annotation",
        }

        for row in fixture.rows:
            self.assertTrue(required_fields.issubset(row))
            self.assertIn(int(row["night_driving_signal"]), {0, 1})
            self.assertIn(int(row["sudden_braking_signal"]), {0, 1})
            self.assertIn(int(row["route_deviation_signal"]), {0, 1})
            self.assertIn(int(row["reduced_activity_signal"]), {0, 1})
            self.assertIn(int(row["fatigue_indicator"]), {0, 1})
            self.assertEqual(int(row["night_driving_signal"]), int(row["night_drive_flag"]))
            self.assertEqual(int(row["sudden_braking_signal"]), int(int(row["harsh_brake_count"]) > 0))
            self.assertTrue(str(row["risk_signal_codes"]))
            self.assertTrue(str(row["persona_risk_annotation"]))

    def test_recent_risk_change_persona_has_route_and_fatigue_annotations(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        by_customer: dict[str, dict[str, int]] = {}
        for row in fixture.rows:
            if row["persona_type"] != "recent_outer_risk_change" or row["observation_period"] != "recent":
                continue
            customer_signals = by_customer.setdefault(str(row["customer_id"]), {"route": 0, "fatigue_or_night": 0})
            customer_signals["route"] += int(row["route_deviation_signal"])
            customer_signals["fatigue_or_night"] += int(row["fatigue_indicator"]) or int(row["night_driving_signal"])
            if int(row["route_deviation_signal"]):
                self.assertIn("ROUTE_DEVIATION", str(row["risk_signal_codes"]))
                self.assertEqual(row["persona_risk_annotation"], "recent_out_zone_risk_signal")

        self.assertEqual(len(by_customer), 5)
        self.assertTrue(all(signals["route"] >= 3 for signals in by_customer.values()))
        self.assertTrue(all(signals["fatigue_or_night"] >= 1 for signals in by_customer.values()))

    def test_non_target_personas_include_contextual_risk_annotations(self) -> None:
        fixture = AISimulationAgent().generate_fixture()
        annotations = {str(row["persona_risk_annotation"]) for row in fixture.rows}
        reduced_activity_rows = [row for row in fixture.rows if int(row["reduced_activity_signal"]) == 1]

        self.assertIn("in_zone_braking_risk_signal", annotations)
        self.assertIn("repeated_medical_outer_context", annotations)
        self.assertIn("family_support_route_variation", annotations)
        self.assertGreater(len(reduced_activity_rows), 0)
        self.assertTrue(all("REDUCED_ACTIVITY" in str(row["risk_signal_codes"]) for row in reduced_activity_rows))

    def test_every_customer_has_persona_specific_downstream_evidence(self) -> None:
        agent = AISimulationAgent()
        fixture = agent.generate_fixture()
        rows_by_customer: dict[str, list[dict[str, object]]] = {}
        for row in fixture.rows:
            rows_by_customer.setdefault(str(row["customer_id"]), []).append(row)

        self.assertEqual(len(rows_by_customer), 30)
        for customer_id, customer_rows in rows_by_customer.items():
            summary = agent.customer_signal_summary(customer_rows)  # type: ignore[arg-type]
            evidence_codes = agent.persona_evidence_codes(str(summary["persona_type"]), summary)

            self.assertTrue(evidence_codes, customer_id)

    def test_downstream_signal_validation_rejects_blind_recent_risk_change_history(self) -> None:
        agent = AISimulationAgent()
        fixture = agent.generate_fixture()
        customer_rows = [
            dict(row)
            for row in fixture.rows
            if row["customer_id"] == "cust_011"
        ]

        for row in customer_rows:
            if row["observation_period"] != "recent":
                continue
            row["zone_label"] = "core"
            row["destination_type"] = "market"
            row["night_drive_flag"] = 0
            row["night_driving_signal"] = 0
            row["route_deviation_signal"] = 0
            row["fatigue_indicator"] = 0
            row["speeding_count"] = 0
            row["harsh_accel_count"] = 0
            row["harsh_brake_count"] = 0
            row["sharp_turn_count"] = 0
            row["sudden_braking_signal"] = 0
            row["risk_signal_codes"] = "none"
            row["persona_risk_annotation"] = "no_trip_risk_signal"
            row["synthetic_risk_tag"] = "normal"

        with self.assertRaisesRegex(ValueError, "lacks detectable persona-specific"):
            agent._validate_persona_specific_downstream_signal(
                "cust_011",
                "recent_outer_risk_change",
                customer_rows,
            )

    def test_manifest_records_downstream_signal_validation_for_all_customers(self) -> None:
        manifest = AISimulationAgent().generate_fixture().manifest
        validation = manifest["downstream_signal_validation"]

        self.assertEqual(len(validation), 30)
        self.assertTrue(all(row["passed"] for row in validation.values()))
        self.assertTrue(all(row["evidence_codes"] for row in validation.values()))


if __name__ == "__main__":
    unittest.main()

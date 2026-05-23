from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import unittest

from src.product.mileage_discount_table import lookup_existing_mileage_discount


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_annual_persona_simulation.py"
PROFILE_FIXTURE = ROOT / "data" / "fixtures" / "annual_persona_profiles.json"
TRIP_FIXTURE = ROOT / "data" / "fixtures" / "annual_trip_logs.csv"
EVENT_FIXTURE = ROOT / "data" / "fixtures" / "monthly_scenario_events.json"


def load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_annual_persona_simulation", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load annual simulation generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_generator_module()


class TestAnnualPersonaSimulation(unittest.TestCase):
    def test_generated_profiles_define_30_realistic_senior_personas(self) -> None:
        profiles, _trips, _events = GENERATOR.generate_annual_fixture()
        drivers = profiles["drivers"]

        self.assertEqual(profiles["schema_version"], "senior-annual-persona-profiles/v1")
        self.assertEqual(len(drivers), 30)
        self.assertEqual(Counter(driver["persona_type"] for driver in drivers), profiles["persona_counts"])
        self.assertEqual(set(profiles["persona_counts"].values()), {5})
        self.assertEqual(profiles["baseline_observation_window"]["days"], 60)
        self.assertTrue(profiles["baseline_observation_window"]["excluded_from_annual_mileage_and_discount_amounts"])

        for driver in drivers:
            destinations = driver["living_destinations"]
            self.assertTrue({"home", "clinic", "market", "family_home"}.issubset(destinations), driver["customer_id"])
            self.assertGreater(driver["base_premium_krw"], 0)
            self.assertGreater(driver["annual_mileage_target_km"], 0)
            self.assertIn(driver["expected_care_decision"], {"favorable", "standard", "preventive_care"})
            self.assertTrue(driver["expected_reason_codes"])
            self.assertTrue(driver["living_pattern"]["weekly_outing_frequency_ko"])
            self.assertTrue(driver["care_context"]["message_focus"])

    def test_generated_trip_logs_cover_all_12_months_with_required_driving_fields(self) -> None:
        _profiles, trips, _events = GENERATOR.generate_annual_fixture()
        rows_by_customer: dict[str, list[dict[str, object]]] = defaultdict(list)

        self.assertGreater(len(trips), 30 * 12)
        for row in trips:
            rows_by_customer[str(row["customer_id"])].append(row)
            self.assertEqual(set(GENERATOR.TRIP_FIELDS), set(row))
            self.assertIn(str(row["period_role"]), {"baseline", "evaluation"})
            if row["period_role"] == "evaluation":
                self.assertIn(int(row["month"]), set(range(1, 13)))
            self.assertIn(str(row["zone_label"]), {"core", "buffer", "outer"})
            self.assertIn(
                str(row["destination_type"]),
                {"home", "market", "clinic", "family_home", "pharmacy", "leisure", "unknown_outer"},
            )
            self.assertGreater(float(row["trip_distance_km"]), 0)
            self.assertGreater(float(row["trip_duration_min"]), 0)
            self.assertGreaterEqual(float(row["max_speed"]), float(row["avg_speed"]))
            for field in ("speeding_count", "harsh_accel_count", "harsh_brake_count", "sharp_turn_count"):
                self.assertGreaterEqual(int(row[field]), 0)

        self.assertEqual(len(rows_by_customer), 30)
        for customer_id, customer_rows in rows_by_customer.items():
            baseline_rows = [row for row in customer_rows if row["period_role"] == "baseline"]
            evaluation_rows = [row for row in customer_rows if row["period_role"] == "evaluation"]
            self.assertTrue(baseline_rows, customer_id)
            self.assertTrue(evaluation_rows, customer_id)
            self.assertEqual({int(row["month"]) for row in evaluation_rows}, set(range(1, 13)), customer_id)
            baseline_dates = [date.fromisoformat(str(row["service_date"])) for row in baseline_rows]
            self.assertGreaterEqual(min(baseline_dates), date(2025, 11, 2))
            self.assertLessEqual(max(baseline_dates), date(2025, 12, 31))

    def test_monthly_events_and_annual_mileage_cover_existing_discount_tiers(self) -> None:
        profiles, trips, events = GENERATOR.generate_annual_fixture()
        annual_distance_by_customer: dict[str, float] = defaultdict(float)
        vehicle_by_customer = {driver["customer_id"]: driver["vehicle_class"] for driver in profiles["drivers"]}

        for row in trips:
            if row["period_role"] != "evaluation":
                continue
            annual_distance_by_customer[str(row["customer_id"])] += float(row["trip_distance_km"])

        tier_labels = {
            lookup_existing_mileage_discount(distance, vehicle_by_customer[customer_id]).matched_tier_label
            for customer_id, distance in annual_distance_by_customer.items()
        }

        self.assertGreaterEqual(len(tier_labels), 6)
        self.assertEqual(events["schema_version"], "senior-monthly-scenario-events/v1")
        self.assertEqual(events["event_count"], 360)
        self.assertEqual(len(events["events"]), 360)

        months_by_customer: dict[str, set[int]] = defaultdict(set)
        risk_change_events = []
        for event in events["events"]:
            months_by_customer[str(event["customer_id"])].add(int(event["month"]))
            if event["persona_type"] == "recent_outer_risk_change" and int(event["month"]) >= 9:
                risk_change_events.append(event)

        self.assertEqual(len(months_by_customer), 30)
        self.assertTrue(all(months == set(range(1, 13)) for months in months_by_customer.values()))
        self.assertEqual(len(risk_change_events), 20)
        self.assertTrue(all(event["scenario_phase"] == "recent_risk_change" for event in risk_change_events))

    def test_persisted_fixtures_match_deterministic_generator(self) -> None:
        generated_profiles, generated_trips, generated_events = GENERATOR.generate_annual_fixture()

        with PROFILE_FIXTURE.open(encoding="utf-8") as file:
            persisted_profiles = json.load(file)
        with TRIP_FIXTURE.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            persisted_trips = list(reader)
        with EVENT_FIXTURE.open(encoding="utf-8") as file:
            persisted_events = json.load(file)

        self.assertEqual(reader.fieldnames, GENERATOR.TRIP_FIELDS)
        self.assertEqual(persisted_profiles, generated_profiles)
        self.assertEqual(persisted_trips, [{field: str(row[field]) for field in GENERATOR.TRIP_FIELDS} for row in generated_trips])
        self.assertEqual(persisted_events, generated_events)


if __name__ == "__main__":
    unittest.main()

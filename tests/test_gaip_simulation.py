from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import unittest

from src.gaip_simulation import (
    ENVIRONMENTS,
    build_gaip_simulation_bundle,
    classify_month,
    pricing_sandbox,
)
from src.gaip_simulation.clustering import dbscan_distinct_days, haversine_m
from src.gaip_simulation.engine import (
    APPROVED_HUB_LABELS_KO,
    HOME_ZONE_LABEL_KO,
    NEW_HUB_LABELS_KO,
    _annual_state,
    _new_hub_label_ko,
    _safety_score,
    _secondary_zone_label_ko,
)
from src.product.mileage_discount_table import PERSONAL_PASSENGER_GENERAL


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = ROOT / "data" / "fixtures" / "gaip_simulation_bundle.json"
RAW_VISIT_EVENTS_PATH = ROOT / "data" / "fixtures" / "gaip_visit_events.csv"


class TestGaipSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = build_gaip_simulation_bundle()
        with RAW_VISIT_EVENTS_PATH.open(newline="", encoding="utf-8") as file:
            cls.visit_events = list(csv.DictReader(file))

    def test_generation_is_deterministic_and_persisted_bundle_matches(self) -> None:
        regenerated = build_gaip_simulation_bundle()
        self.assertEqual(self.bundle, regenerated)
        persisted = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(persisted, regenerated)
        artifact = regenerated["metadata"]["source_artifacts"]["raw_visit_events"]
        self.assertEqual(artifact["path"], "data/fixtures/gaip_visit_events.csv")
        self.assertEqual(artifact["row_count"], len(self.visit_events))
        self.assertEqual(artifact["sha256"], hashlib.sha256(RAW_VISIT_EVENTS_PATH.read_bytes()).hexdigest())
        self.assertNotIn("visit_events", regenerated)

    def test_cohort_has_sixty_persons_six_designed_types_across_three_environments(self) -> None:
        drivers = self.bundle["drivers"]
        # 60 unique synthetic people, each simulated in 3 mobility environments.
        self.assertEqual(len(drivers), 180)
        self.assertEqual(len({driver["person_id"] for driver in drivers}), 60)
        self.assertEqual(self.bundle["cohort"]["driver_count"], 180)
        self.assertEqual(self.bundle["cohort"]["persona_count"], 6)
        # 6 region-neutral behaviour archetypes, 30 cases each (10 people x 3 env).
        self.assertEqual(set(Counter(driver["designed_type"] for driver in drivers).values()), {30})
        self.assertEqual(
            Counter(driver["environment_id"] for driver in drivers),
            Counter({
                "dense_urban": 60,
                "suburban_mid_density": 60,
                "wide_low_density": 60,
            }),
        )
        # Each behaviour archetype is balanced across the three environments.
        for designed_type in self.bundle["cohort"]["designed_type_counts"]:
            distribution = Counter(
                driver["environment_id"]
                for driver in drivers
                if driver["designed_type"] == designed_type
            )
            self.assertEqual(sorted(distribution.values()), [10, 10, 10], designed_type)
        # Every person appears in each environment exactly once.
        per_person = defaultdict(list)
        for driver in drivers:
            per_person[driver["person_id"]].append(driver["environment_id"])
        for person_id, environments in per_person.items():
            self.assertEqual(sorted(environments), sorted(ENVIRONMENTS), person_id)

    def test_each_driver_has_two_baseline_and_twelve_evaluation_months(self) -> None:
        for driver in self.bundle["drivers"]:
            monthly = driver["monthly_results"]
            self.assertEqual(len(monthly), 14, driver["driver_id"])
            self.assertEqual(sum(row["period_role"] == "baseline" for row in monthly), 2)
            self.assertEqual(sum(row["period_role"] == "evaluation" for row in monthly), 12)
            self.assertEqual({row["month"] for row in monthly}, set(self.bundle["periods"]["baseline_months"] + self.bundle["periods"]["evaluation_months"]))

    def test_deterministic_partitions_are_sized_and_stratified(self) -> None:
        drivers = self.bundle["drivers"]
        self.assertEqual(
            Counter(driver["dataset_partition"] for driver in drivers),
            Counter({"development": 108, "validation": 36, "holdout": 36}),
        )
        for partition, per_designed_type, per_environment in (
            ("development", 18, 36),
            ("validation", 6, 12),
            ("holdout", 6, 12),
        ):
            subset = [driver for driver in drivers if driver["dataset_partition"] == partition]
            self.assertEqual(set(Counter(driver["designed_type"] for driver in subset).values()), {per_designed_type})
            self.assertEqual(set(Counter(driver["environment_id"] for driver in subset).values()), {per_environment})
            self.assertEqual(self.bundle["portfolio_results"]["partition_summaries"][partition]["driver_count"], len(subset))
        # A person and all three of their environment cases share one partition.
        person_partitions = defaultdict(set)
        for driver in drivers:
            person_partitions[driver["person_id"]].add(driver["dataset_partition"])
        self.assertTrue(all(len(partitions) == 1 for partitions in person_partitions.values()))

    def test_one_visit_event_per_trip_and_repeated_visits_are_preserved_across_dates(self) -> None:
        events = self.visit_events
        self.assertEqual(len(events), len({event["trip_id"] for event in events}))
        self.assertEqual(len(events), len({event["visit_event_id"] for event in events}))
        grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
        for event in events:
            grouped[(event["driver_id"], event["visit_label"])].add(event["visit_date"])
        for driver in self.bundle["drivers"]:
            self.assertTrue(
                any(len(dates) >= 3 for (driver_id, _label), dates in grouped.items() if driver_id == driver["driver_id"]),
                driver["driver_id"],
            )

    def test_only_generic_visit_labels_are_exposed(self) -> None:
        # The raw CSV keeps generic visit labels and never carries place semantics.
        self.assertEqual(
            {event["visit_label"] for event in self.visit_events},
            {"Routine Hub A", "Routine Hub B", "New Hub"},
        )
        raw_csv = RAW_VISIT_EVENTS_PATH.read_text(encoding="utf-8").lower()
        for forbidden in (
            "hospital", "clinic", "pharmacy", "child_house", "family_home",
            "병원", "약국", "자녀", "자택", "마트", "경로당", "복지관", "시장",
        ):
            self.assertNotIn(forbidden, raw_csv)
        # Policy: the summary bundle may carry synthetic semantic hub labels, but
        # only values from the approved APPROVED_HUB_LABELS_KO union; English
        # place-code tokens stay forbidden.
        serialized = json.dumps(self.bundle, ensure_ascii=False).lower()
        for forbidden in ("hospital", "clinic", "pharmacy", "child_house", "family_home"):
            self.assertNotIn(forbidden, serialized)
        for driver in self.bundle["drivers"]:
            for hub in driver["mobility"]["routine_hubs"]:
                self.assertIn(hub["display_label_ko"], APPROVED_HUB_LABELS_KO, driver["driver_id"])
            self.assertIn(driver["mobility"]["new_hub_label_ko"], APPROVED_HUB_LABELS_KO, driver["driver_id"])

    def test_synthetic_naming_fields_are_deterministic_and_clearly_synthetic(self) -> None:
        self.assertEqual(
            self.bundle["metadata"]["persona_naming_note"],
            "이름·나이·장소 라벨은 전원 합성(실존 인물·장소 아님)",
        )
        drivers = self.bundle["drivers"]
        # A name belongs to a person; that person's three environment cases share
        # it, so names are unique across the 60 people, not the 180 cases.
        names_by_person = {driver["person_id"]: driver["driver_name_ko"] for driver in drivers}
        self.assertEqual(len(names_by_person), 60)
        self.assertEqual(len(set(names_by_person.values())), 60, "person names must be unique")
        for driver in drivers:
            self.assertEqual(driver["driver_name_ko"], names_by_person[driver["person_id"]])
            self.assertTrue(driver["driver_name_ko"].strip())
            self.assertIsInstance(driver["age"], int)
            self.assertGreaterEqual(driver["age"], 66)
            self.assertLessEqual(driver["age"], 84)
            for hub in driver["mobility"]["routine_hubs"]:
                expected = (
                    HOME_ZONE_LABEL_KO
                    if hub["display_label"] == "Routine Hub A"
                    else _secondary_zone_label_ko(driver)
                )
                self.assertEqual(hub["display_label_ko"], expected, driver["driver_id"])
            self.assertEqual(
                driver["mobility"]["new_hub_label_ko"],
                _new_hub_label_ko(driver),
                driver["driver_id"],
            )
            self.assertEqual(
                driver["mobility"]["new_hub_label_ko"],
                NEW_HUB_LABELS_KO[driver["designed_type"]],
                driver["driver_id"],
            )

    def test_ui_bundle_excludes_raw_coordinates(self) -> None:
        serialized = json.dumps(self.bundle, ensure_ascii=False).lower()
        for forbidden_key in ('"latitude"', '"longitude"', '"centroid"'):
            self.assertNotIn(forbidden_key, serialized)
        self.assertTrue(any("latitude" in event and "longitude" in event for event in self.visit_events))

    def test_dbscan_uses_haversine_meters_and_distinct_days(self) -> None:
        reference = self.bundle["algorithm"]["reference"]
        self.assertEqual(reference["distance_metric"], "haversine_m")
        self.assertEqual(reference["min_distinct_days"], 3)
        self.assertNotIn("eps_degrees", reference)
        self.assertEqual(reference["environment_eps_m"], {key: value["dbscan_eps_m"] for key, value in ENVIRONMENTS.items()})
        self.assertNotEqual(
            set(reference["environment_eps_m"].values()),
            {self.bundle["algorithm"]["product_zone"]["core_radius_m"]},
        )
        self.assertAlmostEqual(haversine_m(37.0, 127.0, 37.0, 127.001), 88.8, delta=1.0)

        same_day_only = [
            {"visit_date": "2026-01-01", "latitude": 37.0, "longitude": 127.0 + offset}
            for offset in (0.0, 0.00001, 0.00002, 0.00003)
        ]
        result = dbscan_distinct_days(same_day_only, eps_m=100.0, min_distinct_days=3)
        self.assertEqual(result["cluster_count"], 0)

    def test_outer_share_alone_is_neutral(self) -> None:
        metrics = {
            "zone_available": True,
            "data_coverage_pct": 100.0,
            "mileage_score": 90.0,
            "in_zone_safe_score": 94.0,
            "out_zone_safe_score": 96.0,
            "pattern_stability_score": 92.0,
            "mobility_change_index": 0.0,
            "risky_behavior_change_index": 0.0,
            "outer_visit_share": 0.0,
        }
        before = classify_month(metrics)
        after = classify_month({**metrics, "outer_visit_share": 0.95})
        self.assertEqual(before, after)
        self.assertEqual(after["location_penalty"], 0.0)

    def test_missing_zone_component_is_not_treated_as_perfect_safety(self) -> None:
        self.assertIsNone(_safety_score([]))
        metrics = {
            "zone_available": True,
            "data_coverage_pct": 100.0,
            "mileage_score": 80.0,
            "in_zone_safe_score": 90.0,
            "out_zone_safe_score": None,
            "pattern_stability_score": 70.0,
            "mobility_change_index": 0.0,
            "risky_behavior_change_index": 0.0,
        }
        result = classify_month(metrics)
        expected = ((80.0 * 30) + (90.0 * 30) + (70.0 * 20)) / 80
        self.assertEqual(result["integrated_score"], round(expected, 2))
        self.assertEqual(result["observed_score_weight_pct"], 80.0)
        self.assertFalse(result["component_availability"]["out_zone_safe_score"])
        self.assertIn("PARTIAL_SCORE_COMPONENTS_RENORMALIZED", result["reason_codes"])

        for driver in self.bundle["drivers"]:
            for row in driver["monthly_results"]:
                self.assertEqual(row["in_zone_trip_count"] > 0, row["in_zone_safe_score"] is not None)
                self.assertEqual(row["out_zone_trip_count"] > 0, row["out_zone_safe_score"] is not None)

    def test_partial_annual_reward_evidence_is_hold(self) -> None:
        required = self.bundle["product_rules"]["reward_required_months"]
        monthly = [
            *(
                {"period_role": "evaluation", "reward_state": "reward", "care_state": "none"}
                for _ in range(required - 1)
            ),
            *(
                {"period_role": "evaluation", "reward_state": "hold", "care_state": "hold"}
                for _ in range(12 - required + 1)
            ),
        ]
        reward, care = _annual_state(monthly, self.bundle["product_rules"])
        self.assertEqual(reward, "hold")
        self.assertEqual(care, "none")

    def test_pattern_stability_is_defined_by_risky_behavior_change_not_mobility_change(self) -> None:
        self.assertEqual(
            self.bundle["product_rules"]["pattern_stability_basis"],
            "risky_behavior_change_index",
        )
        for driver in self.bundle["drivers"]:
            for row in driver["monthly_results"]:
                self.assertEqual(
                    row["pattern_stability_score"],
                    round(max(0.0, 100.0 - row["risky_behavior_change_index"] * 100.0), 2),
                )
        risk_only = classify_month(
            {
                "zone_available": True,
                "data_coverage_pct": 100.0,
                "mileage_score": 90.0,
                "in_zone_safe_score": 60.0,
                "out_zone_safe_score": 60.0,
                "pattern_stability_score": 100.0,
                "mobility_change_index": 0.0,
                "risky_behavior_change_index": 0.8,
            }
        )
        self.assertIn("RISKY_BEHAVIOR_CHANGED", risk_only["reason_codes"])
        self.assertNotIn("MOBILITY_CONTEXT_CHANGED", risk_only["reason_codes"])

    def test_risky_behavior_rate_is_risky_trip_share_and_intensity_is_preserved(self) -> None:
        grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for event in self.visit_events:
            grouped[(event["driver_id"], event["month"])].append(event)

        for driver in self.bundle["drivers"]:
            for row in driver["monthly_results"]:
                events = grouped[(driver["driver_id"], row["month"])]
                risky_trip_share = sum(int(event["risk_event_count"]) > 0 for event in events) / len(events)
                total_risk_events = sum(int(event["risk_event_count"]) for event in events)
                total_distance = sum(float(event["trip_distance_km"]) for event in events)
                self.assertAlmostEqual(row["risky_behavior_rate"], round(risky_trip_share, 4), places=4)
                self.assertAlmostEqual(
                    row["risky_events_per_100_km"],
                    round((total_risk_events / max(total_distance, 1.0)) * 100.0, 4),
                    places=4,
                )
                self.assertGreaterEqual(row["risky_behavior_change_index"], 0.0)
                self.assertLessEqual(row["risky_behavior_change_index"], 1.0)

    def test_mobility_only_change_does_not_reduce_pattern_stability_or_reward_score(self) -> None:
        mobility_drivers = [
            driver
            for driver in self.bundle["drivers"]
            if driver["designed_type"] == "mobility_change_safe"
        ]
        self.assertTrue(mobility_drivers)
        for driver in mobility_drivers:
            changed = [
                row
                for row in driver["monthly_results"]
                if row["period_role"] == "evaluation" and row["mobility_change_index"] > 0
            ]
            self.assertTrue(changed, driver["driver_id"])
            self.assertTrue(all(row["risky_behavior_change_index"] == 0.0 for row in changed))
            self.assertTrue(all(row["pattern_stability_score"] == 100.0 for row in changed))
            self.assertTrue(all(row["reward_state"] == "reward" for row in changed))

    def test_mobility_only_change_does_not_trigger_care(self) -> None:
        mobility_drivers = [
            driver for driver in self.bundle["drivers"] if driver["designed_type"] == "mobility_change_safe"
        ]
        self.assertTrue(mobility_drivers)
        for driver in mobility_drivers:
            changed = [
                row
                for row in driver["monthly_results"]
                if row["period_role"] == "evaluation" and row["mobility_change_index"] >= 0.25
            ]
            self.assertTrue(changed, driver["driver_id"])
            self.assertTrue(all(row["care_state"] == "none" for row in changed), driver["driver_id"])

    def test_mobility_and_risky_behavior_cochange_can_trigger_care_review(self) -> None:
        cochange_drivers = [
            driver for driver in self.bundle["drivers"] if driver["designed_type"] == "mobility_risk_cochange"
        ]
        self.assertTrue(cochange_drivers)
        for driver in cochange_drivers:
            care_months = [row for row in driver["monthly_results"] if row["care_state"] == "care_review"]
            self.assertTrue(care_months, driver["driver_id"])
            self.assertTrue(
                all(row["mobility_change_index"] >= 0.25 and row["risky_behavior_change_index"] >= 0.20 for row in care_months)
            )

    def test_persona_behavior_contract_is_visible_in_annual_states(self) -> None:
        # Behaviour archetypes drive a *tendency* in the emergent annual states —
        # never a hand-set outcome. Reward/Care are computed from the simulated
        # evidence, so the contract is expressed as majority tendencies (and the
        # two hard structural gates: negative control and co-change care).
        by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
        for driver in self.bundle["drivers"]:
            by_type[driver["designed_type"]].append(driver)

        def reward_share(designed_type: str) -> float:
            group = by_type[designed_type]
            return sum(driver["annual_reward_state"] == "reward" for driver in group) / len(group)

        # Stable low-mileage safe drivers tend to earn the reward tier.
        self.assertGreater(reward_share("stable_reward"), 0.5)
        # In-zone risky behaviour tends to fall out of the reward tier.
        self.assertLess(reward_share("in_zone_risky"), 0.5)
        # Hard gate — mobility-only change is a Care negative control (never Care).
        self.assertTrue(
            all(driver["annual_care_state"] == "none" for driver in by_type["mobility_change_safe"])
        )
        # Hard gate — same-month mobility AND risky-behaviour co-change reaches Care.
        self.assertTrue(
            all(driver["annual_care_state"] == "care_review" for driver in by_type["mobility_risk_cochange"])
        )

    def test_sparse_evidence_individuals_reach_hold_end_to_end_without_penalty(self) -> None:
        # A few sparse-data people (too little coverage to judge) surface Hold
        # naturally — never manufactured, never penalised for driving location.
        sparse_drivers = [driver for driver in self.bundle["drivers"] if driver["data_quality"] == "sparse"]
        self.assertTrue(sparse_drivers)
        minimum_coverage = self.bundle["product_rules"]["min_data_coverage_pct"]
        for driver in sparse_drivers:
            self.assertEqual(driver["annual_reward_state"], "hold", driver["driver_id"])
            self.assertEqual(driver["annual_care_state"], "hold", driver["driver_id"])
            evaluation = [row for row in driver["monthly_results"] if row["period_role"] == "evaluation"]
            self.assertTrue(all(row["data_coverage_pct"] < minimum_coverage for row in evaluation))
            self.assertTrue(all(row["reward_state"] == "hold" for row in evaluation))
            self.assertTrue(all(row["care_state"] == "hold" for row in evaluation))
            self.assertTrue(all(row["location_penalty"] == 0.0 for row in evaluation))
        # Hold is confined to the sparse individuals; nothing else is held.
        held = [driver for driver in self.bundle["drivers"] if driver["annual_reward_state"] == "hold"]
        self.assertEqual(
            {driver["driver_id"] for driver in held},
            {driver["driver_id"] for driver in sparse_drivers},
        )

    def test_annual_reward_required_months_is_declared_and_applied(self) -> None:
        required_months = self.bundle["product_rules"]["reward_required_months"]
        self.assertEqual(required_months, 9)
        for driver in self.bundle["drivers"]:
            evaluation = [row for row in driver["monthly_results"] if row["period_role"] == "evaluation"]
            reward_months = sum(row["reward_state"] == "reward" for row in evaluation)
            self.assertEqual(driver["reward_month_count"], reward_months)
            if driver["annual_reward_state"] == "hold":
                self.assertTrue(all(row["reward_state"] == "hold" for row in evaluation))
            else:
                self.assertEqual(driver["annual_reward_state"] == "reward", reward_months >= required_months)

    def test_no_zone_means_hold_without_penalty_or_invented_hub(self) -> None:
        metrics = {
            "zone_available": False,
            "data_coverage_pct": 100.0,
            "mileage_score": 100.0,
            "in_zone_safe_score": 100.0,
            "out_zone_safe_score": 100.0,
            "pattern_stability_score": 100.0,
            "mobility_change_index": 0.0,
            "risky_behavior_change_index": 0.0,
        }
        result = classify_month(metrics)
        self.assertEqual(result["reward_state"], "hold")
        self.assertEqual(result["care_state"], "hold")
        self.assertEqual(result["location_penalty"], 0.0)
        self.assertIsNone(result["integrated_score"])
        self.assertEqual(self.bundle["algorithm"]["reference"]["no_cluster_policy"], "insufficient_evidence_hold_without_invented_hub")

    def test_reward_and_care_states_are_separate(self) -> None:
        thresholds = self.bundle["product_rules"]["care_thresholds"]
        self.assertEqual(thresholds["gate_logic"], "AND")
        self.assertEqual(thresholds["unit"], "normalized_ratio_0_to_1")
        for driver in self.bundle["drivers"]:
            self.assertIn("mobility_change_index", driver)
            self.assertIn("risky_behavior_change_index", driver)
            self.assertNotIn("pattern_change_risk", driver)
            for row in driver["monthly_results"]:
                self.assertNotIn("pattern_change_risk", row)
                self.assertIn(row["reward_state"], {"observation", "reward", "neutral", "hold"})
                self.assertIn(row["care_state"], {"observation", "none", "care_review", "hold"})
                if row["care_state"] == "care_review":
                    self.assertNotEqual(row["reward_state"], "hold")

    def test_pricing_sandbox_math_and_no_surcharge(self) -> None:
        result = pricing_sandbox(
            base_premium_krw=1_000_000,
            annual_distance_km=2_500.0,
            vehicle_class=PERSONAL_PASSENGER_GENERAL,
            annual_reward_state="reward",
        )
        self.assertEqual(
            result["korea_mileage_net_premium_krw"],
            round(1_000_000 * (1 - result["korea_mileage_discount_rate_pct"] / 100)),
        )
        self.assertEqual(
            result["masil_candidate_net_premium_krw"],
            round(1_000_000 * (1 - result["masil_candidate_discount_rate_pct"] / 100)),
        )
        self.assertEqual(result["candidate_surcharge_rate_pct"], 0.0)
        self.assertIn("not_final_tariff", result["source_status"])

    def test_offline_candidates_are_not_faked(self) -> None:
        candidates = self.bundle["algorithm"]["offline_comparison_candidates"]
        self.assertEqual({row["name"] for row in candidates}, {"HDBSCAN", "Grid Count"})
        self.assertTrue(all(row["result_status"] == "not_run" for row in candidates))

    def test_generation_truth_is_excluded_from_decision_features_and_reasons(self) -> None:
        contract = self.bundle["product_rules"]["decision_feature_contract"]
        allowed = set(contract["allowed_inputs"])
        excluded = set(contract["generation_only_fields_excluded"])
        self.assertTrue(allowed.isdisjoint(excluded))
        # The generation-truth labels (the archetype and its designed type) must
        # never be scoring inputs — they are validation-only tags.
        self.assertIn("designed_type", excluded)
        self.assertIn("archetype_id", excluded)
        self.assertIn("not_fit_to_any_partition", self.bundle["product_rules"]["rule_origin"])
        reason_codes = {
            reason
            for driver in self.bundle["drivers"]
            for month in driver["monthly_results"]
            for reason in month["reason_codes"]
        }
        self.assertFalse(
            any(token in reason for reason in reason_codes for token in ("PERSONA", "DESIGNED", "ARCHETYPE", "EXPECTED"))
        )
        leakage_check = next(
            check
            for check in self.bundle["validation_results"]["checks"]
            if check["check_id"] == "generation_label_leakage_guard"
        )
        self.assertEqual(leakage_check["result_status"], "passed")

    def test_bundle_validation_contract_passes(self) -> None:
        self.assertEqual(self.bundle["validation_results"]["result_status"], "passed")
        self.assertTrue(
            all(check["result_status"] == "passed" for check in self.bundle["validation_results"]["checks"])
        )

    def test_every_source_status_has_a_legend_entry(self) -> None:
        statuses: set[str] = set()

        def collect(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "source_status" and isinstance(child, str):
                        statuses.add(child)
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(self.bundle)
        self.assertTrue(statuses.issubset(self.bundle["source_status_legend"]))


if __name__ == "__main__":
    unittest.main()

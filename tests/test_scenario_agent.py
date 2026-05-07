from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.agents.contracts import AgentInputPayload, AgentStatus
from src.agents.persona_agent import PersonaAgent
from src.agents.scenario_agent import ScenarioAgent


class TestScenarioAgent(unittest.TestCase):
    def test_persona_agent_runs_with_shared_contract(self) -> None:
        agent = PersonaAgent()
        payload = AgentInputPayload(run_id="persona-contract-test", agent_id="persona_agent")

        result = agent.run(payload)

        result.validate()
        self.assertEqual(result.status, AgentStatus.SUCCEEDED)
        self.assertIsNotNone(result.output_payload)
        assert result.output_payload is not None
        self.assertEqual(result.output_payload.metrics["persona_count"], 6)
        self.assertEqual(result.output_payload.metrics["customer_count"], 30)
        self.assertEqual(result.output_payload.metrics["driving_pattern_count"], 30)
        self.assertEqual(
            [artifact.artifact_id for artifact in result.output_payload.output_artifacts],
            ["persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"],
        )
        self.assertTrue(result.output_payload.validation["passed"])

    def test_scenario_agent_runs_with_shared_contract_and_writes_reproducible_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "scenario_config.json"
            agent = ScenarioAgent()
            payload = AgentInputPayload(
                run_id="scenario-contract-test",
                agent_id="scenario_agent",
                parameters={"output_path": str(output_path)},
            )

            result = agent.run(payload)

            result.validate()
            self.assertTrue(output_path.exists())
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertIsNotNone(result.output_payload)
            assert result.output_payload is not None
            artifact = result.output_payload.output_artifacts[0]
            self.assertEqual(artifact.artifact_id, "scenario_config.json")
            self.assertEqual(artifact.rows, 30)
            self.assertEqual(result.output_payload.metrics["baseline_days"], 60)
            self.assertEqual(result.output_payload.metrics["recent_days"], 30)
            self.assertEqual(result.output_payload.metrics["risk_change_target_customer_count"], 5)
            self.assertTrue(result.output_payload.validation["passed"])

    def test_builds_rules_for_all_personas_and_customers(self) -> None:
        config = ScenarioAgent().build_config()

        rules = config["customer_scenario_rules"]
        persona_counts: dict[str, int] = {}
        for rule in rules:
            persona_counts[rule["persona_type"]] = persona_counts.get(rule["persona_type"], 0) + 1

        self.assertEqual(len(rules), 30)
        self.assertEqual(set(persona_counts.values()), {5})
        self.assertEqual(config["observation_period"], {"baseline_days": 60, "recent_days": 30})

    def test_customer_rules_define_baseline_recent_and_expected_change(self) -> None:
        config = ScenarioAgent().build_config()

        for rule in config["customer_scenario_rules"]:
            baseline = rule["baseline_driving_pattern"]
            recent = rule["recent_30_day_rule"]
            change = rule["expected_recent_behavior_change"]

            self.assertGreaterEqual(baseline["trip_count"], 20)
            self.assertGreaterEqual(recent["trip_count"], 8)
            self.assertAlmostEqual(change["outer_ratio_delta"], recent["zone_mix"]["outer"] - baseline["zone_mix"]["outer"])
            self.assertAlmostEqual(change["night_ratio_delta"], recent["night_drive_ratio"] - baseline["night_drive_ratio"])
            self.assertAlmostEqual(
                change["risk_rate_delta_per_100km"],
                recent["risk_event_rate_per_100km"] - baseline["risk_event_rate_per_100km"],
            )

    def test_risk_change_target_is_exactly_one_persona_group(self) -> None:
        config = ScenarioAgent().build_config()

        risk_change_rules = [
            rule for rule in config["customer_scenario_rules"]
            if rule["expected_recent_behavior_change"]["risk_change_target"]
        ]

        self.assertEqual(len(risk_change_rules), 5)
        self.assertEqual({rule["persona_type"] for rule in risk_change_rules}, {"recent_outer_risk_change"})

    def test_six_persona_edge_cases_define_input_data_and_ground_truth_decisions(self) -> None:
        agent = PersonaAgent()
        profiles = agent.load_profiles()
        identities = agent.load_customer_identities()
        patterns = agent.load_customer_driving_patterns()

        expected_decisions = {
            "stable_local_low_mileage": "favorable",
            "stable_outer_safe": "standard",
            "recent_outer_risk_change": "preventive_care",
            "in_zone_risky_low_mileage": "standard",
            "medical_visit_pattern": "standard",
            "irregular_family_support": "standard",
        }
        expected_risk_targets = {
            "stable_local_low_mileage": False,
            "stable_outer_safe": False,
            "recent_outer_risk_change": True,
            "in_zone_risky_low_mileage": False,
            "medical_visit_pattern": False,
            "irregular_family_support": False,
        }

        profiles_by_type = {profile.persona_type: profile for profile in profiles}
        self.assertEqual(set(profiles_by_type), set(expected_decisions))

        for persona_type, expected_decision in expected_decisions.items():
            profile = profiles_by_type[persona_type]
            persona_customers = [identity for identity in identities if identity.persona_type == persona_type]
            persona_patterns = [pattern for pattern in patterns if pattern.persona_type == persona_type]

            self.assertEqual(len(profile.scenario_variants), 5, persona_type)
            self.assertEqual(len(persona_customers), 5, persona_type)
            self.assertEqual(len(persona_patterns), 5, persona_type)
            self.assertEqual(profile.ground_truth["expected_care_decision"], expected_decision)
            self.assertEqual(profile.ground_truth["risk_change_target"], expected_risk_targets[persona_type])
            self.assertGreaterEqual(len(profile.ground_truth["expected_reason_codes"]), 3)

            for identity in persona_customers:
                self.assertEqual(identity.expected_care_decision, expected_decision)
                self.assertEqual(set(identity.expected_reason_codes), set(profile.ground_truth["expected_reason_codes"]))

            for pattern in persona_patterns:
                self.assertEqual(pattern.observation_period, {"baseline_days": 60, "recent_days": 30})
                self.assertGreaterEqual(pattern.trip_count["baseline"], 20)
                self.assertGreaterEqual(pattern.trip_count["recent"], 8)

    def test_scenario_ground_truth_carries_expected_customer_decision(self) -> None:
        config = ScenarioAgent().build_config()

        decision_counts: dict[str, int] = {}
        for rule in config["customer_scenario_rules"]:
            change = rule["expected_recent_behavior_change"]
            ground_truth = rule["ground_truth"]

            self.assertEqual(ground_truth["expected_care_decision"], change["expected_care_decision"])
            self.assertEqual(ground_truth["risk_change_target"], change["risk_change_target"])
            self.assertEqual(set(ground_truth["expected_reason_codes"]), set(change["expected_reason_codes"]))
            decision_counts[ground_truth["expected_care_decision"]] = (
                decision_counts.get(ground_truth["expected_care_decision"], 0) + 1
            )

        self.assertEqual(decision_counts, {"favorable": 5, "standard": 20, "preventive_care": 5})


if __name__ == "__main__":
    unittest.main()

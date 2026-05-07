from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from src.agents.contracts import AgentInputPayload, AgentStatus
from src.agents.policy_search_agent import (
    DEFAULT_OBJECTIVE_CONSTRAINTS,
    DEFAULT_WEIGHT_GRID,
    POLICY_CANDIDATE_SCHEMA_VERSION,
    PolicySearchAgent,
    build_customer_features,
    build_search_input,
    generate_threshold_candidates,
    iter_policy_candidate_score_rows,
    iter_weight_candidates,
)


class TestPolicySearchAgent(unittest.TestCase):
    def test_policy_search_agent_runs_with_shared_contract_and_writes_ranked_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "candidate_rules.json"
            candidate_scores_output_path = Path(tmpdir) / "policy_candidate_scores.csv"
            agent = PolicySearchAgent()
            payload = AgentInputPayload(
                run_id="policy-search-contract-test",
                agent_id="policy_search_agent",
                parameters={
                    "output_path": str(output_path),
                    "candidate_scores_output_path": str(candidate_scores_output_path),
                },
            )

            result = agent.run(payload)

            result.validate()
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertTrue(output_path.exists())
            self.assertIsNotNone(result.output_payload)
            assert result.output_payload is not None
            artifact = result.output_payload.output_artifacts[0]
            self.assertEqual(artifact.artifact_id, "candidate_rules.json")
            self.assertGreaterEqual(artifact.rows or 0, 1)
            self.assertTrue(result.output_payload.metrics["passes_approval_gate"])
            self.assertEqual(result.output_payload.metrics["selected_capture_count"], 5)
            self.assertLessEqual(result.output_payload.metrics["selected_false_positive_count"], 3)
            self.assertIn("selected_scores", result.output_payload.decisions)
            self.assertIn("selected_metadata", result.output_payload.decisions)
            self.assertEqual(len(result.output_payload.decisions["ranked_candidate_summaries"]), 114)
            first_summary = result.output_payload.decisions["ranked_candidate_summaries"][0]
            self.assertEqual(
                set(first_summary),
                {"candidate_id", "rank", "weights", "thresholds", "scores", "metadata"},
            )
            self.assertEqual(first_summary["metadata"]["schema_version"], POLICY_CANDIDATE_SCHEMA_VERSION)
            self.assertIn("APPROVAL_GATE_POLICY_CANDIDATE", result.output_payload.reason_codes)
            self.assertTrue(candidate_scores_output_path.exists())
            self.assertEqual(result.output_payload.output_artifacts[1].artifact_id, "policy_candidate_scores.csv")
            self.assertEqual(result.output_payload.output_artifacts[1].rows, 3420)

            candidate_rules = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate_rules["schema_version"], "senior-policy-candidate-rules/v1")
            self.assertEqual(candidate_rules["selected_candidate_id"], candidate_rules["ranked_candidates"][0]["candidate_id"])
            self.assertEqual(candidate_rules["ranked_candidates"][0]["rank"], 1)
            self.assertIn("search_input", candidate_rules)
            self.assertIn("weight_grid", candidate_rules["search_input"])
            self.assertEqual(candidate_rules["search_input"]["weight_candidate_summary"]["generated_candidate_count"], 19)
            self.assertIn("threshold_candidates", candidate_rules["search_input"])
            self.assertEqual(candidate_rules["search_input"]["threshold_candidate_summary"]["generated_candidate_count"], 6)
            self.assertIn("threshold_candidate_id", candidate_rules["ranked_candidates"][0]["thresholds"])
            self.assertIn("reason_metadata", candidate_rules["ranked_candidates"][0])
            self.assertIn("scores", candidate_rules["ranked_candidates"][0])
            self.assertIn("metadata", candidate_rules["ranked_candidates"][0])
            self.assertEqual(candidate_rules["candidate_score_summary"]["candidate_count"], 114)
            self.assertEqual(candidate_rules["candidate_score_summary"]["customers_per_candidate"], 30)
            self.assertEqual(candidate_rules["candidate_score_summary"]["score_row_count"], 3420)
            self.assertEqual(len(candidate_rules["ranked_candidates"][0]["customer_scores"]), 30)
            self.assertIn("score_summary", candidate_rules["ranked_candidates"][0])

            with candidate_scores_output_path.open(newline="", encoding="utf-8") as file:
                score_rows = list(csv.DictReader(file))
            self.assertEqual(len(score_rows), 3420)
            self.assertIn("candidate_id", score_rows[0])
            self.assertIn("senior_safe_mileage_score", score_rows[0])
            self.assertIn("care_decision", score_rows[0])

    def test_structured_search_input_uses_product_grid_and_objective_constraints(self) -> None:
        search_input = build_search_input()

        self.assertEqual(set(search_input["weight_grid"]), {"w_mileage", "w_in_zone", "w_out_zone_safe", "w_out_zone_change"})
        self.assertEqual(search_input["care_threshold_percentiles"], [0.2, 0.15, 0.1])
        self.assertEqual(search_input["objective_constraints"], DEFAULT_OBJECTIVE_CONSTRAINTS)
        self.assertGreater(len(iter_weight_candidates(search_input["weight_grid"])), 0)
        self.assertEqual(search_input["weight_candidate_summary"]["generated_candidate_count"], 19)

    def test_threshold_candidate_generation_uses_risk_score_percentiles_and_tier_bands(self) -> None:
        features = build_customer_features(
            Path("data/fixtures/senior_trip_logs.csv"),
            Path("data/fixtures/scenario_config.json"),
        )

        candidates = generate_threshold_candidates(
            features,
            [0.20, 0.15, 0.10],
            [{"S": 85, "A": 75, "B": 65, "C": 0}, {"S": 88, "A": 78, "B": 68, "C": 0}],
        )

        self.assertEqual(len(candidates), 6)
        self.assertEqual(len({candidate["threshold_candidate_id"] for candidate in candidates}), 6)
        self.assertEqual({candidate["care_threshold_percentile"] for candidate in candidates}, {0.20, 0.15, 0.10})
        self.assertEqual({candidate["care_threshold_expected_top_n"] for candidate in candidates}, {3, 4, 6})
        for candidate in candidates:
            self.assertGreaterEqual(candidate["care_threshold"], 0.0)
            self.assertLessEqual(candidate["care_threshold"], 100.0)
            self.assertEqual(candidate["care_threshold_source"], "risk_change_score_top_percentile")
            self.assertEqual(set(candidate["tier_threshold"]), {"S", "A", "B", "C"})

    def test_weight_candidate_generation_uses_final_product_direction_grid(self) -> None:
        candidates = iter_weight_candidates(DEFAULT_WEIGHT_GRID)

        self.assertEqual(len(candidates), 19)
        self.assertEqual(len({tuple(candidate.items()) for candidate in candidates}), 19)
        for candidate in candidates:
            self.assertEqual(set(candidate), set(DEFAULT_WEIGHT_GRID))
            self.assertAlmostEqual(sum(candidate.values()), 1.0, places=4)
            for key, value in candidate.items():
                self.assertIn(value, DEFAULT_WEIGHT_GRID[key])

        self.assertIn(
            {
                "w_mileage": 0.3,
                "w_in_zone": 0.3,
                "w_out_zone_safe": 0.2,
                "w_out_zone_change": 0.2,
            },
            candidates,
        )
        self.assertIn(
            {
                "w_mileage": 0.4,
                "w_in_zone": 0.4,
                "w_out_zone_safe": 0.1,
                "w_out_zone_change": 0.1,
            },
            candidates,
        )

    def test_customer_features_are_summary_only_and_preserve_30_customer_fixture(self) -> None:
        features = build_customer_features(
            Path("data/fixtures/senior_trip_logs.csv"),
            Path("data/fixtures/scenario_config.json"),
        )

        self.assertEqual(len(features), 30)
        self.assertEqual(sum(1 for feature in features if feature.risk_change_target), 5)
        summary = features[10].public_summary()
        self.assertNotIn("customer_id", summary)
        self.assertNotIn("trip_id", summary)
        self.assertNotIn("start_gps_x", summary)
        self.assertIn("risk_change_score", summary)
        self.assertIn("recent_in_zone_km", summary)
        self.assertIn("recent_in_zone_risk_rate_per_100km", summary)
        self.assertIn("recent_out_zone_km", summary)
        self.assertIn("recent_out_zone_risk_rate_per_100km", summary)
        self.assertGreaterEqual(summary["in_zone_safe_score"], 0.0)
        self.assertLessEqual(summary["in_zone_safe_score"], 100.0)
        self.assertGreaterEqual(summary["out_zone_safe_score"], 0.0)
        self.assertLessEqual(summary["out_zone_safe_score"], 100.0)

    def test_selected_candidate_contains_ranked_metrics_and_reason_metadata(self) -> None:
        result = PolicySearchAgent().search(build_search_input())
        selected = result["selected_candidate"]

        self.assertEqual(selected["rank"], 1)
        self.assertEqual(selected["metadata"]["schema_version"], POLICY_CANDIDATE_SCHEMA_VERSION)
        self.assertEqual(selected["metadata"]["rank"], selected["rank"])
        self.assertEqual(selected["metadata"]["candidate_id"], selected["candidate_id"])
        self.assertEqual(selected["metadata"]["threshold_candidate_id"], selected["thresholds"]["threshold_candidate_id"])
        self.assertAlmostEqual(selected["metadata"]["weight_sum"], 1.0, places=4)
        self.assertEqual(selected["metadata"]["customer_count"], 30)
        self.assertEqual(selected["scores"]["ranking_score"], selected["metrics"]["ranking_score"])
        self.assertEqual(selected["scores"]["insurer_efficiency_score"], selected["metrics"]["insurer_efficiency_score"])
        self.assertEqual(
            selected["scores"]["customer_score_summary"]["average_senior_safe_mileage_score"],
            selected["score_summary"]["average_senior_safe_mileage_score"],
        )
        self.assertEqual(selected["metrics"]["risk_change_target_capture_count"], 5)
        self.assertLessEqual(selected["metrics"]["non_target_false_positive_count"], 3)
        self.assertGreater(selected["metrics"]["low_mileage_high_risk_capture"], selected["metrics"]["baseline_low_mileage_high_risk_capture"])
        self.assertIn("persona_detection_counts", selected["reason_metadata"])
        self.assertIn("stable_outer_safe", selected["reason_metadata"]["persona_detection_counts"])
        self.assertTrue(selected["reason_metadata"]["strengths"])
        self.assertTrue(selected["reason_metadata"]["fairness_notes"])

    def test_each_candidate_returns_structured_weights_thresholds_scores_and_metadata(self) -> None:
        result = PolicySearchAgent().search(build_search_input())

        self.assertEqual(len(result["ranked_candidates"]), 114)
        for candidate in result["ranked_candidates"]:
            self.assertEqual(set(candidate["weights"]), set(DEFAULT_WEIGHT_GRID))
            self.assertIn("care_threshold", candidate["thresholds"])
            self.assertIn("tier_threshold", candidate["thresholds"])
            self.assertIn("ranking_score", candidate["scores"])
            self.assertIn("customer_score_summary", candidate["scores"])
            self.assertEqual(candidate["scores"]["customer_score_summary"], candidate["score_summary"])
            self.assertEqual(candidate["metadata"]["schema_version"], POLICY_CANDIDATE_SCHEMA_VERSION)
            self.assertEqual(candidate["metadata"]["rank"], candidate["rank"])
            self.assertEqual(candidate["metadata"]["candidate_id"], candidate["candidate_id"])
            self.assertEqual(candidate["metadata"]["threshold_candidate_id"], candidate["thresholds"]["threshold_candidate_id"])
            self.assertEqual(candidate["metadata"]["weight_keys"], list(DEFAULT_WEIGHT_GRID))
            self.assertAlmostEqual(candidate["metadata"]["weight_sum"], 1.0, places=4)
            self.assertEqual(candidate["metadata"]["customer_count"], 30)

    def test_each_policy_candidate_combination_has_30_customer_scores(self) -> None:
        result = PolicySearchAgent().search(build_search_input())
        score_rows = iter_policy_candidate_score_rows(result)

        self.assertEqual(len(result["ranked_candidates"]), 114)
        self.assertEqual(len(score_rows), 114 * 30)
        for candidate in result["ranked_candidates"]:
            self.assertEqual(len(candidate["customer_scores"]), 30)
            self.assertEqual(candidate["score_summary"]["customer_count"], 30)
            self.assertEqual(
                {row["customer_id"] for row in candidate["customer_scores"]},
                {f"cust_{index:03d}" for index in range(1, 31)},
            )
            for row in candidate["customer_scores"]:
                self.assertGreaterEqual(row["senior_safe_mileage_score"], 0.0)
                self.assertLessEqual(row["senior_safe_mileage_score"], 100.0)
                self.assertIn(row["care_decision"], {"우대", "기본", "예방 케어"})
                self.assertIn(row["tier"], {"S", "A", "B", "C"})

        selected = result["selected_candidate"]
        selected_rows = [row for row in score_rows if row["candidate_id"] == selected["candidate_id"]]
        self.assertEqual(len(selected_rows), 30)
        self.assertEqual(
            sum(1 for row in selected_rows if row["care_decision"] == "예방 케어"),
            selected["metrics"]["risk_change_target_capture_count"]
            + selected["metrics"]["non_target_false_positive_count"],
        )


if __name__ == "__main__":
    unittest.main()

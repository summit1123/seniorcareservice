from __future__ import annotations

import unittest

from src.agents.evaluation_agent import build_evaluation_input, evaluate_selected_policy
from src.product.ab_comparison import (
    BASELINE_ANNUAL_MILEAGE_LIMIT_KM,
    build_customer_ab_comparison_dataset,
    build_customer_comparison_input,
    compare_customer_models,
    run_mileage_baseline_model,
    run_senior_safe_mileage_model,
)


class TestABComparison(unittest.TestCase):
    def test_runs_baseline_and_proposed_models_on_same_customer_feature(self) -> None:
        evaluation_input = build_evaluation_input()
        feature = next(
            row
            for row in evaluation_input["customer_features"]
            if row.persona_type == "recent_outer_risk_change"
        )
        selected_policy = evaluation_input["selected_policy"]
        weights = {key: float(value) for key, value in selected_policy["weights"].items()}
        thresholds = selected_policy["thresholds"]

        comparison = compare_customer_models(
            feature,
            weights=weights,
            care_threshold=float(thresholds["care_threshold"]),
            tier_threshold=thresholds["tier_threshold"],
            target_label=feature.risk_change_target,
            proxy_target_label=True,
        )

        self.assertEqual(comparison.customer_id, feature.customer_id)
        self.assertEqual(comparison.baseline.input_summary["annualized_recent_km"], feature.annualized_recent_km)
        self.assertEqual(comparison.proposed.input_summary["annualized_recent_km"], feature.annualized_recent_km)
        self.assertEqual(comparison.baseline.threshold, BASELINE_ANNUAL_MILEAGE_LIMIT_KM)
        self.assertEqual(comparison.baseline.model_id, "existing_annual_mileage_baseline/v1")
        self.assertEqual(comparison.proposed.model_id, "senior_safe_mileage_integrated/v1")
        self.assertTrue(comparison.same_customer_input)
        self.assertEqual(comparison.baseline.input_data_ref, comparison.proposed.input_data_ref)
        self.assertEqual(comparison.baseline.input_data_ref, comparison.comparison_input.input_data_ref)
        self.assertFalse(comparison.baseline_detected)
        self.assertTrue(comparison.proposed_detected)
        self.assertEqual(comparison.care_decision, "예방 케어")
        self.assertTrue(comparison.metrics()["same_customer_input"])
        self.assertEqual(comparison.metrics()["input_data_ref"], comparison.comparison_input.input_data_ref)

    def test_comparison_input_envelope_is_stable_for_same_customer_feature(self) -> None:
        evaluation_input = build_evaluation_input()
        feature = evaluation_input["customer_features"][0]

        first = build_customer_comparison_input(feature)
        second = build_customer_comparison_input(feature)

        self.assertEqual(first.input_data_ref, second.input_data_ref)
        self.assertEqual(first.observation_period["baseline_days"], 60)
        self.assertEqual(first.observation_period["recent_days"], 30)
        self.assertEqual(first.observation_period["total_days"], 90)
        self.assertEqual(first.feature_summary["annualized_recent_km"], feature.annualized_recent_km)
        self.assertIn("risk_change_score", first.feature_summary)

    def test_builds_customer_lookup_dataset_for_baseline_and_proposed_results(self) -> None:
        evaluation_input = build_evaluation_input()
        selected_policy = evaluation_input["selected_policy"]
        weights = {key: float(value) for key, value in selected_policy["weights"].items()}
        thresholds = selected_policy["thresholds"]

        dataset = build_customer_ab_comparison_dataset(
            evaluation_input["customer_features"],
            selected_policy_id=selected_policy["candidate_id"],
            weights=weights,
            care_threshold=float(thresholds["care_threshold"]),
            tier_threshold=thresholds["tier_threshold"],
        )
        payload = dataset.to_dict()
        first_customer_id = evaluation_input["customer_features"][0].customer_id
        first_record = dataset.get(first_customer_id).to_record()

        self.assertEqual(payload["schema_version"], "senior-safe-mileage-ab-comparison-dataset/v1")
        self.assertEqual(payload["customer_count"], 30)
        self.assertTrue(payload["same_input_contract"]["baseline_and_proposed_share_input_data_ref"])
        self.assertEqual(
            payload["comparison_summary"]["schema_version"],
            "senior-safe-mileage-ab-comparison-summary/v1",
        )
        self.assertEqual(payload["comparison_summary"]["customer_count"], 30)
        self.assertIn("model_outputs", payload["comparison_summary"])
        self.assertIn("decision_differences", payload["comparison_summary"])
        self.assertEqual(len(payload["comparison_summary"]["persona_summaries"]), 6)
        self.assertGreater(
            payload["comparison_summary"]["decision_differences"]["decision_changed_count"],
            0,
        )
        self.assertIn(first_customer_id, payload["by_customer_id"])
        self.assertEqual(first_record["lookup_key"], f"customer_id:{first_customer_id}")
        self.assertTrue(first_record["same_customer_input"])
        self.assertEqual(
            first_record["baseline_model"]["input_data_ref"],
            first_record["proposed_model"]["input_data_ref"],
        )

    def test_core_metrics_return_scores_premium_grade_and_decision_difference(self) -> None:
        evaluation_input = build_evaluation_input()
        feature = next(
            row
            for row in evaluation_input["customer_features"]
            if row.persona_type == "recent_outer_risk_change"
        )
        selected_policy = evaluation_input["selected_policy"]
        weights = {key: float(value) for key, value in selected_policy["weights"].items()}
        thresholds = selected_policy["thresholds"]

        comparison = compare_customer_models(
            feature,
            weights=weights,
            care_threshold=float(thresholds["care_threshold"]),
            tier_threshold=thresholds["tier_threshold"],
            target_label=feature.risk_change_target,
            proxy_target_label=True,
        )
        core_metrics = comparison.core_metrics()

        self.assertEqual(core_metrics["schema_version"], "senior-safe-mileage-ab-core-metrics/v1")
        self.assertEqual(core_metrics["baseline"]["score"], comparison.baseline_score)
        self.assertEqual(core_metrics["proposed"]["score"], comparison.proposed_score)
        self.assertIn(core_metrics["baseline"]["grade"], {"S", "A", "B", "C", "D"})
        self.assertEqual(core_metrics["proposed"]["grade"], comparison.tier)
        self.assertIn("discount_rate_pct", core_metrics["baseline"])
        self.assertIn("surcharge_rate_pct", core_metrics["proposed"])
        self.assertEqual(core_metrics["proposed"]["decision"], "예방 케어")
        self.assertTrue(core_metrics["difference"]["decision_changed"])
        self.assertTrue(core_metrics["difference"]["proposed_captures_risk_change_not_baseline"])
        self.assertEqual(
            core_metrics["difference"]["score_delta"],
            round(comparison.proposed_score - comparison.baseline_score, 2),
        )

    def test_model_runners_match_evaluation_snapshot_scores_and_decisions(self) -> None:
        evaluation_input = build_evaluation_input()
        result = evaluate_selected_policy(evaluation_input)
        selected_policy = evaluation_input["selected_policy"]
        weights = {key: float(value) for key, value in selected_policy["weights"].items()}
        thresholds = selected_policy["thresholds"]

        for feature in evaluation_input["customer_features"]:
            baseline = run_mileage_baseline_model(feature)
            proposed = run_senior_safe_mileage_model(
                feature,
                weights=weights,
                care_threshold=float(thresholds["care_threshold"]),
                tier_threshold=thresholds["tier_threshold"],
            )
            snapshot = next(
                row
                for row in result["customer_snapshots"]
                if row["customer_id"] == feature.customer_id
            )

            self.assertEqual(snapshot["mileage_baseline_score"], baseline.score)
            self.assertEqual(snapshot["senior_safe_mileage_score"], proposed.score)
            self.assertEqual(snapshot["ab_comparison"]["baseline_detected"], baseline.detected)
            self.assertEqual(snapshot["ab_comparison"]["proposed_detected"], proposed.detected)
            self.assertEqual(
                snapshot["ab_comparison"]["metrics"]["baseline_model"]["input_summary"],
                baseline.input_summary,
            )
            self.assertEqual(
                snapshot["ab_comparison"]["metrics"]["proposed_model"]["input_summary"],
                proposed.input_summary,
            )


if __name__ == "__main__":
    unittest.main()

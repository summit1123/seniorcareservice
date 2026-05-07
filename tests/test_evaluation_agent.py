from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from src.agents.contracts import AgentInputPayload, AgentStatus, validate_customer_decision_snapshot
from src.agents.evaluation_agent import EvaluationAgent, build_evaluation_input, evaluate_selected_policy
from src.agents.policy_search_agent import CustomerPolicyFeature
from src.product.proxy_labels import PROXY_LABEL_RULE_ID


class TestEvaluationAgent(unittest.TestCase):
    def test_evaluation_agent_writes_ab_csv_and_ui_view_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_output = Path(tmpdir) / "ab_test_results.csv"
            json_output = Path(tmpdir) / "evaluation_view_model.json"
            payload = AgentInputPayload(
                run_id="evaluation-agent-test",
                agent_id="evaluation_agent",
                parameters={
                    "output_path": str(csv_output),
                    "view_model_output_path": str(json_output),
                },
            )

            result = EvaluationAgent().run(payload)

            result.validate()
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertTrue(csv_output.exists())
            self.assertTrue(json_output.exists())
            self.assertIsNotNone(result.output_payload)
            assert result.output_payload is not None
            self.assertEqual(result.output_payload.output_artifacts[0].artifact_id, "ab_test_results.csv")
            self.assertEqual(result.output_payload.output_artifacts[1].artifact_id, "evaluation_view_model.json")
            self.assertEqual(result.output_payload.metrics["customer_count"], 30)
            self.assertEqual(result.output_payload.metrics["proposed_capture_count"], 5)
            self.assertEqual(result.output_payload.metrics["baseline_capture_count"], 0)
            self.assertEqual(result.output_payload.metrics["non_target_count"], 25)
            self.assertLessEqual(
                result.output_payload.metrics["non_target_false_positive_count"],
                result.output_payload.metrics["non_target_false_positive_limit"],
            )
            self.assertTrue(result.output_payload.metrics["passes_non_target_false_positive_gate"])
            self.assertLessEqual(
                result.output_payload.metrics["total_misclassification_count"],
                result.output_payload.metrics["total_misclassification_limit"],
            )
            self.assertTrue(result.output_payload.metrics["passes_misclassification_check"])
            self.assertTrue(result.output_payload.metrics["passes_approval_gate"])

            with csv_output.open(newline="", encoding="utf-8") as file:
                csv_rows = list(csv.DictReader(file))
            self.assertEqual(len(csv_rows), 30)
            self.assertIn("reason_codes_json", csv_rows[0])
            self.assertIn("ab_comparison_json", csv_rows[0])
            self.assertIn("ab_core_metrics_json", csv_rows[0])
            self.assertIn("comparison_input_data_ref", csv_rows[0])
            self.assertIn("comparison_lookup_key", csv_rows[0])
            self.assertIn("same_customer_input", csv_rows[0])
            self.assertIn("comparison_input_json", csv_rows[0])
            self.assertIn("model_comparison_record_json", csv_rows[0])
            self.assertIn("baseline_discount_rate_pct", csv_rows[0])
            self.assertIn("proposed_surcharge_rate_pct", csv_rows[0])
            self.assertIn("baseline_grade", csv_rows[0])
            self.assertIn("proposed_grade", csv_rows[0])
            self.assertIn("ab_decision_changed", csv_rows[0])
            self.assertIn("proxy_label_json", csv_rows[0])
            self.assertIn("hybrid_evaluation_json", csv_rows[0])
            self.assertIn("proposed_hybrid_evaluation_score", csv_rows[0])
            self.assertIn("proposed_hybrid_evaluation_passed", csv_rows[0])
            self.assertIn("proposed_hybrid_evaluation_verdict", csv_rows[0])
            self.assertIn("proposed_hybrid_exception_rule", csv_rows[0])
            self.assertIn("non_target_false_positive", csv_rows[0])

            view_model = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertEqual(view_model["schema_version"], "senior-evaluation-results/v1")
            self.assertEqual(
                view_model["selected_policy"]["candidate_id"],
                "policy_30_30_20_20_p20_a75",
            )
            self.assertEqual(
                view_model["selected_scenario"]["schema_version"],
                "senior-safe-mileage-selected-scenario-state/v1",
            )
            self.assertEqual(
                view_model["selected_scenario"]["observation_period"],
                {"baseline_days": 60, "recent_days": 30},
            )
            self.assertEqual(len(view_model["customer_snapshots"]), 30)
            self.assertEqual(view_model["comparison_dataset"]["customer_count"], 30)
            self.assertEqual(
                view_model["comparison_summary"]["schema_version"],
                "senior-safe-mileage-ab-comparison-summary/v1",
            )
            self.assertEqual(
                view_model["comparison_summary"],
                view_model["comparison_dataset"]["comparison_summary"],
            )
            self.assertTrue(
                view_model["comparison_dataset"]["same_input_contract"][
                    "baseline_and_proposed_share_input_data_ref"
                ]
            )
            self.assertEqual(len(view_model["hybrid_case_results"]), 6)
            validate_customer_decision_snapshot(view_model["customer_snapshots"][0])
            self.assertEqual(
                {row["care_decision"] for row in view_model["customer_rows"]},
                {"우대", "기본", "예방 케어"},
            )
            self.assertEqual(
                {snapshot["care_decision"] for snapshot in view_model["customer_snapshots"]},
                {"우대", "기본", "예방 케어"},
            )

    def test_evaluation_outputs_ab_core_metrics_for_table_and_customer_snapshot(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        row = next(row for row in result["customer_rows"] if row["persona_type"] == "recent_outer_risk_change")
        snapshot = next(
            snapshot
            for snapshot in result["customer_snapshots"]
            if snapshot["customer_id"] == row["customer_id"]
        )
        row_core_metrics = json.loads(row["ab_core_metrics_json"])
        snapshot_core_metrics = snapshot["ab_comparison"]["metrics"]["core_metrics"]

        self.assertEqual(row_core_metrics, snapshot_core_metrics)
        self.assertEqual(row_core_metrics["schema_version"], "senior-safe-mileage-ab-core-metrics/v1")
        self.assertEqual(row_core_metrics["baseline"]["score"], row["mileage_baseline_score"])
        self.assertEqual(row_core_metrics["proposed"]["score"], row["senior_safe_mileage_score"])
        self.assertEqual(row_core_metrics["baseline"]["grade"], row["baseline_grade"])
        self.assertEqual(row_core_metrics["proposed"]["grade"], row["proposed_grade"])
        self.assertEqual(row_core_metrics["proposed"]["decision"], row["care_decision"])
        self.assertEqual(row_core_metrics["baseline"]["discount_rate_pct"], row["baseline_discount_rate_pct"])
        self.assertEqual(row_core_metrics["proposed"]["surcharge_rate_pct"], row["proposed_surcharge_rate_pct"])
        self.assertTrue(row_core_metrics["difference"]["decision_changed"])
        self.assertEqual(row_core_metrics["difference"]["baseline_decision"], "기존 저주행 할인")
        self.assertEqual(row_core_metrics["difference"]["proposed_decision"], "예방 케어")

    def test_evaluation_outputs_queryable_same_input_comparison_dataset(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        dataset = result["comparison_dataset"]
        snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "cust_011")
        record = snapshot["model_comparison_record"]
        lookup = dataset["by_customer_id"]["cust_011"]

        self.assertEqual(dataset["schema_version"], "senior-safe-mileage-ab-comparison-dataset/v1")
        self.assertEqual(dataset["record_lookup_key"], "customer_id")
        self.assertEqual(dataset["customer_count"], 30)
        self.assertEqual(len(dataset["records"]), 30)
        self.assertEqual(len(dataset["by_customer_id"]), 30)
        self.assertTrue(dataset["same_input_contract"]["baseline_and_proposed_share_input_data_ref"])
        self.assertEqual(record["lookup_key"], "customer_id:cust_011")
        self.assertTrue(record["same_customer_input"])
        self.assertEqual(record["comparison_input"]["input_data_ref"], lookup["input_data_ref"])
        self.assertEqual(record["baseline_model"]["input_data_ref"], record["proposed_model"]["input_data_ref"])
        self.assertEqual(record["baseline_score"], lookup["baseline_score"])
        self.assertEqual(record["proposed_score"], lookup["proposed_score"])
        self.assertEqual(record["core_metrics"], snapshot["ab_comparison"]["metrics"]["core_metrics"])
        self.assertIn("decision_changed", lookup)
        self.assertIn("score_delta", lookup)

    def test_evaluation_outputs_ab_comparison_summary_for_policy_overview(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        summary = result["comparison_summary"]
        differences = summary["decision_differences"]
        proposed_outputs = summary["model_outputs"]["proposed"]

        self.assertEqual(summary["schema_version"], "senior-safe-mileage-ab-comparison-summary/v1")
        self.assertEqual(summary["customer_count"], 30)
        self.assertEqual(len(summary["persona_summaries"]), 6)
        self.assertEqual(
            proposed_outputs["detected_count"],
            sum(1 for row in result["customer_rows"] if bool(row["proposed_detected"])),
        )
        self.assertGreater(differences["decision_changed_count"], 0)
        self.assertEqual(differences["proposed_only_risk_change_capture_count"], 5)
        self.assertEqual(
            set(differences["proposed_only_capture_customer_ids"]),
            {
                row["customer_id"]
                for row in result["customer_rows"]
                if bool(row["risk_change_target"]) and bool(row["proposed_detected"]) and not bool(row["baseline_detected"])
            },
        )
        self.assertTrue(summary["customer_decision_differences"])
        first_difference = summary["customer_decision_differences"][0]
        self.assertIn("baseline_decision", first_difference)
        self.assertIn("proposed_decision", first_difference)
        self.assertIn("score_delta", first_difference)

    def test_evaluation_view_model_contains_six_persona_hybrid_case_results(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        cases = result["hybrid_case_results"]

        self.assertEqual(len(cases), 6)
        self.assertEqual(
            {case["persona_type"] for case in cases},
            {snapshot["persona_type"] for snapshot in result["customer_snapshots"]},
        )
        for case in cases:
            self.assertEqual(case["customer_count"], 5)
            self.assertTrue(case["case_id"].startswith("hybrid_case_"))
            self.assertTrue(case["representative_customer_id"])
            self.assertIn(case["proposed"]["verdict"], {"pass", "review"})
            self.assertIn(case["baseline"]["verdict"], {"pass", "review"})
            self.assertIn("pass_count", case["proposed"])
            self.assertIn("average_score", case["proposed"])
            self.assertIn("ground_truth=", case["rationale"])
            self.assertIn("proxy_label=", case["rationale"])

    def test_evaluation_customer_cases_include_generated_proxy_labels(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())

        self.assertEqual(len(result["customer_rows"]), 30)
        self.assertEqual(len(result["customer_snapshots"]), 30)
        for row in result["customer_rows"]:
            self.assertEqual(row["proxy_label_rule_id"], PROXY_LABEL_RULE_ID)
            self.assertIn("PROXY_LABEL_RULE_BASED", json.loads(row["proxy_label_reason_codes_json"]))
            proxy_label = json.loads(row["proxy_label_json"])
            self.assertEqual(proxy_label["rule_id"], PROXY_LABEL_RULE_ID)
            self.assertEqual(bool(proxy_label["is_target"]), bool(row["risk_change_target"]))

        for snapshot in result["customer_snapshots"]:
            self.assertIn("proxy_label", snapshot)
            self.assertIn("hybrid_evaluation", snapshot)
            self.assertEqual(snapshot["proxy_label"]["rule_id"], PROXY_LABEL_RULE_ID)
            self.assertEqual(
                snapshot["hybrid_evaluation"]["proposed"]["hybrid_target"],
                snapshot["ab_comparison"]["metrics"]["risk_change_target"],
            )
            self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["weights"]["ground_truth_priority"], 0.8)
            self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["weights"]["proxy_label_correction"], 0.2)
            self.assertIn(snapshot["hybrid_evaluation"]["proposed"]["verdict"], {"pass", "fail"})
            self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["pass_threshold"], 80.0)

    def test_evaluation_output_preserves_privacy_filtered_llm_features(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        snapshot = next(
            row for row in result["customer_snapshots"] if row["persona_type"] == "recent_outer_risk_change"
        )

        request_features = snapshot["llm_report"]["request_features"]
        self.assertNotIn("customer_id", request_features)
        self.assertNotIn("trip_id", json.dumps(request_features))
        self.assertNotIn("start_gps_x", json.dumps(request_features))
        self.assertIn("risk_change_score", request_features)
        self.assertIn("recent_in_zone_km", request_features)
        self.assertIn("recent_in_zone_risk_rate_per_100km", request_features)
        self.assertIn("recent_out_zone_km", request_features)
        self.assertIn("recent_out_zone_risk_rate_per_100km", request_features)
        self.assertIn("out_zone_safe_score", request_features)
        self.assertEqual(snapshot["care_decision"], "예방 케어")
        self.assertTrue(snapshot["ab_comparison"]["proposed_detected"])
        self.assertFalse(snapshot["ab_comparison"]["baseline_detected"])

    def test_evaluation_snapshot_uses_saved_living_zone_lookup_result(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "cust_011")
        living_zone = snapshot["living_zone"]

        self.assertEqual(living_zone["source"], "saved_customer_living_zone_record")
        self.assertEqual(living_zone["schema_version"], "customer-living-zone-result/v1")
        self.assertEqual(living_zone["method"], "dbscan_density_cluster")
        self.assertIn("primary_zone", living_zone)
        self.assertIn("buffer", living_zone)
        self.assertIn("clusters", living_zone)
        self.assertEqual(living_zone["recent_out_zone_ratio"], living_zone["recent_zone_mix"]["out_zone_ratio"])
        self.assertEqual(living_zone["recent_in_zone_ratio"], living_zone["recent_zone_mix"]["in_zone_ratio"])

    def test_reason_codes_use_saved_living_zone_analysis_result(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "cust_011")
        reason_codes = snapshot["reason_codes"]

        self.assertEqual(snapshot["living_zone"]["source"], "saved_customer_living_zone_record")
        self.assertIn("LIVING_ZONE_DBSCAN_P90_INPUT_USED", reason_codes)
        if snapshot["living_zone"]["zone_stability_score"] >= 70.0:
            self.assertIn("LIVING_ZONE_HIGH_STABILITY", reason_codes)
        if snapshot["living_zone"]["route_repeat_ratio"] >= 0.6:
            self.assertIn("REPEATED_ROUTE_PATTERN", reason_codes)

    def test_evaluation_metrics_show_proposed_model_beats_distance_baseline(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        metrics = result["summary_metrics"]

        self.assertEqual(metrics["risk_change_target_count"], 5)
        self.assertEqual(metrics["non_target_count"], 25)
        self.assertGreater(metrics["proposed_low_mileage_high_risk_capture"], metrics["baseline_low_mileage_high_risk_capture"])
        self.assertEqual(metrics["proposed_capture_count"], 5)
        self.assertLessEqual(metrics["non_target_false_positive_count"], 3)
        self.assertEqual(metrics["non_target_false_positive_limit"], 3)
        self.assertTrue(metrics["passes_non_target_false_positive_gate"])
        self.assertLessEqual(metrics["total_misclassification_count"], 4)
        self.assertEqual(metrics["total_misclassification_limit"], 4)
        self.assertTrue(metrics["passes_misclassification_check"])
        self.assertGreaterEqual(metrics["agent_validation_pass_rate"], 0.95)
        self.assertEqual(metrics["hybrid_pass_fail_threshold"], 80.0)
        self.assertGreaterEqual(metrics["proposed_hybrid_pass_count"], 29)
        self.assertLessEqual(metrics["proposed_hybrid_fail_count"], 1)

    def test_misclassification_check_counts_all_30_customers_and_stays_within_limit(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        rows = result["customer_rows"]
        metrics = result["summary_metrics"]
        check = metrics["misclassification_check"]
        misclassified_rows = [
            row for row in rows
            if bool(row["risk_change_target"]) != bool(row["proposed_detected"])
        ]

        self.assertEqual(check["schema_version"], "senior-safe-mileage-misclassification-check/v1")
        self.assertEqual(check["customer_count"], 30)
        self.assertEqual(check["limit"], 4)
        self.assertEqual(check["count"], len(misclassified_rows))
        self.assertEqual(metrics["total_misclassification_count"], len(misclassified_rows))
        self.assertEqual(metrics["misclassified_customer_ids"], [row["customer_id"] for row in misclassified_rows])
        self.assertEqual(check["misclassified_customer_ids"], [row["customer_id"] for row in misclassified_rows])
        self.assertLessEqual(check["count"], check["limit"])
        self.assertTrue(check["passed"])
        self.assertTrue(metrics["passes_misclassification_check"])

    def test_non_target_false_positive_gate_counts_only_the_remaining_25_customers(self) -> None:
        result = evaluate_selected_policy(build_evaluation_input())
        rows = result["customer_rows"]
        non_targets = [row for row in rows if not bool(row["risk_change_target"])]
        false_positive_rows = [row for row in non_targets if bool(row["proposed_detected"])]
        metrics = result["summary_metrics"]

        self.assertEqual(len(non_targets), 25)
        self.assertEqual(metrics["non_target_count"], len(non_targets))
        self.assertEqual(metrics["non_target_false_positive_count"], len(false_positive_rows))
        self.assertEqual(
            metrics["non_target_false_positive_customer_ids"],
            [row["customer_id"] for row in false_positive_rows],
        )
        self.assertLessEqual(len(false_positive_rows), 3)
        self.assertTrue(metrics["passes_non_target_false_positive_gate"])
        self.assertTrue(all(row["non_target_false_positive"] for row in false_positive_rows))

    def test_hybrid_evaluation_uses_ground_truth_target_when_proxy_disagrees(self) -> None:
        selected_policy = {
            "candidate_id": "test-hybrid-ground-truth-priority",
            "rank": 1,
            "weights": {
                "w_mileage": 0.30,
                "w_in_zone": 0.30,
                "w_out_zone_safe": 0.20,
                "w_out_zone_change": 0.20,
            },
            "thresholds": {
                "care_threshold": 60.0,
                "tier_threshold": {"S": 85, "A": 75, "B": 65, "C": 0},
            },
        }
        ground_truth_target_proxy_non_target = CustomerPolicyFeature(
            customer_id="hybrid_disagreement",
            persona_type="recent_outer_risk_change",
            expected_care_decision="예방 케어",
            risk_change_target=True,
            baseline_total_km=900.0,
            recent_total_km=420.0,
            annualized_recent_km=5040.0,
            recent_trip_count=10,
            recent_in_zone_ratio=0.65,
            recent_out_zone_ratio=0.35,
            baseline_out_zone_ratio=0.12,
            out_zone_ratio_delta=0.23,
            baseline_night_ratio=0.05,
            recent_night_ratio=0.22,
            night_ratio_delta=0.17,
            baseline_risk_rate_per_100km=0.3,
            recent_risk_rate_per_100km=5.0,
            risk_rate_delta_per_100km=4.7,
            recent_risk_signal_count=6,
            recent_in_zone_km=273.0,
            recent_in_zone_trip_count=6,
            recent_in_zone_night_ratio=0.08,
            recent_in_zone_risk_rate_per_100km=0.4,
            recent_out_zone_km=147.0,
            recent_out_zone_trip_count=4,
            recent_out_zone_night_ratio=0.30,
            recent_out_zone_risk_rate_per_100km=6.0,
        )
        base_input = build_evaluation_input()
        fixture_targets = [feature for feature in base_input["customer_features"] if feature.risk_change_target]
        fixture_non_targets = [feature for feature in base_input["customer_features"] if not feature.risk_change_target]

        result = evaluate_selected_policy(
            {
                "source_artifacts": base_input["source_artifacts"],
                "selected_policy": selected_policy,
                "customer_features": (
                    [ground_truth_target_proxy_non_target]
                    + fixture_targets[:4]
                    + fixture_non_targets[:25]
                ),
                "living_zone_store": None,
            }
        )
        snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "hybrid_disagreement")

        self.assertTrue(snapshot["ab_comparison"]["metrics"]["risk_change_target"])
        self.assertFalse(snapshot["ab_comparison"]["metrics"]["proxy_label_target"])
        self.assertTrue(snapshot["ab_comparison"]["proposed_detected"])
        self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["score"], 80.0)
        self.assertTrue(snapshot["hybrid_evaluation"]["proposed"]["passed"])
        self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["verdict"], "pass")
        self.assertEqual(
            snapshot["hybrid_evaluation"]["proposed"]["exception_rule"],
            "HYBRID_EXCEPTION_PROXY_DISAGREEMENT_ALLOWED_WHEN_GROUND_TRUTH_MATCHES",
        )
        self.assertIn(
            "HYBRID_PROXY_CORRECTION_APPLIED",
            snapshot["hybrid_evaluation"]["proposed"]["reason_codes"],
        )

    def test_hybrid_evaluation_fails_proxy_only_match_exception(self) -> None:
        selected_policy = {
            "candidate_id": "test-hybrid-proxy-only-fails",
            "rank": 1,
            "weights": {
                "w_mileage": 0.30,
                "w_in_zone": 0.30,
                "w_out_zone_safe": 0.20,
                "w_out_zone_change": 0.20,
            },
            "thresholds": {
                "care_threshold": 80.0,
                "tier_threshold": {"S": 85, "A": 75, "B": 65, "C": 0},
            },
        }
        ground_truth_target_proxy_non_target = CustomerPolicyFeature(
            customer_id="hybrid_proxy_only",
            persona_type="recent_outer_risk_change",
            expected_care_decision="예방 케어",
            risk_change_target=True,
            baseline_total_km=900.0,
            recent_total_km=420.0,
            annualized_recent_km=5040.0,
            recent_trip_count=10,
            recent_in_zone_ratio=0.65,
            recent_out_zone_ratio=0.35,
            baseline_out_zone_ratio=0.12,
            out_zone_ratio_delta=0.23,
            baseline_night_ratio=0.05,
            recent_night_ratio=0.22,
            night_ratio_delta=0.17,
            baseline_risk_rate_per_100km=0.3,
            recent_risk_rate_per_100km=5.0,
            risk_rate_delta_per_100km=4.7,
            recent_risk_signal_count=6,
            recent_in_zone_km=273.0,
            recent_in_zone_trip_count=6,
            recent_in_zone_night_ratio=0.08,
            recent_in_zone_risk_rate_per_100km=0.4,
            recent_out_zone_km=147.0,
            recent_out_zone_trip_count=4,
            recent_out_zone_night_ratio=0.30,
            recent_out_zone_risk_rate_per_100km=6.0,
        )
        base_input = build_evaluation_input()
        fixture_targets = [feature for feature in base_input["customer_features"] if feature.risk_change_target]
        fixture_non_targets = [feature for feature in base_input["customer_features"] if not feature.risk_change_target]

        result = evaluate_selected_policy(
            {
                "source_artifacts": base_input["source_artifacts"],
                "selected_policy": selected_policy,
                "customer_features": (
                    [ground_truth_target_proxy_non_target]
                    + fixture_targets[:4]
                    + fixture_non_targets[:25]
                ),
                "living_zone_store": None,
            }
        )
        snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "hybrid_proxy_only")

        self.assertFalse(snapshot["ab_comparison"]["proposed_detected"])
        self.assertTrue(snapshot["ab_comparison"]["metrics"]["risk_change_target"])
        self.assertFalse(snapshot["ab_comparison"]["metrics"]["proxy_label_target"])
        self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["score"], 20.0)
        self.assertFalse(snapshot["hybrid_evaluation"]["proposed"]["passed"])
        self.assertEqual(snapshot["hybrid_evaluation"]["proposed"]["verdict"], "fail")
        self.assertEqual(
            snapshot["hybrid_evaluation"]["proposed"]["exception_rule"],
            "HYBRID_EXCEPTION_PROXY_ONLY_MATCH_DOES_NOT_OVERRIDE_GROUND_TRUTH",
        )

    def test_outside_living_zone_risk_change_affects_score_and_reason_code(self) -> None:
        selected_policy = {
            "candidate_id": "test-outside-zone-risk-change",
            "rank": 1,
            "weights": {
                "w_mileage": 0.30,
                "w_in_zone": 0.30,
                "w_out_zone_safe": 0.20,
                "w_out_zone_change": 0.20,
            },
            "thresholds": {
                "care_threshold": 60.0,
                "tier_threshold": {"S": 85, "A": 75, "B": 65, "C": 0},
            },
        }
        stable_feature = CustomerPolicyFeature(
            customer_id="stable_low_mileage",
            persona_type="stable_low_mileage",
            expected_care_decision="우대",
            risk_change_target=False,
            baseline_total_km=900.0,
            recent_total_km=420.0,
            annualized_recent_km=5040.0,
            recent_trip_count=10,
            recent_in_zone_ratio=0.85,
            recent_out_zone_ratio=0.15,
            baseline_out_zone_ratio=0.14,
            out_zone_ratio_delta=0.01,
            baseline_night_ratio=0.05,
            recent_night_ratio=0.06,
            night_ratio_delta=0.01,
            baseline_risk_rate_per_100km=0.3,
            recent_risk_rate_per_100km=0.5,
            risk_rate_delta_per_100km=0.2,
            recent_risk_signal_count=0,
            recent_in_zone_km=357.0,
            recent_in_zone_trip_count=8,
            recent_in_zone_night_ratio=0.04,
            recent_in_zone_risk_rate_per_100km=0.2,
            recent_out_zone_km=63.0,
            recent_out_zone_trip_count=2,
            recent_out_zone_night_ratio=0.02,
            recent_out_zone_risk_rate_per_100km=0.0,
        )
        outside_change_feature = CustomerPolicyFeature(
            customer_id="outside_zone_change",
            persona_type="recent_outer_risk_change",
            expected_care_decision="예방 케어",
            risk_change_target=True,
            baseline_total_km=900.0,
            recent_total_km=420.0,
            annualized_recent_km=5040.0,
            recent_trip_count=10,
            recent_in_zone_ratio=0.50,
            recent_out_zone_ratio=0.50,
            baseline_out_zone_ratio=0.10,
            out_zone_ratio_delta=0.40,
            baseline_night_ratio=0.05,
            recent_night_ratio=0.35,
            night_ratio_delta=0.30,
            baseline_risk_rate_per_100km=0.3,
            recent_risk_rate_per_100km=6.0,
            risk_rate_delta_per_100km=5.7,
            recent_risk_signal_count=6,
            recent_in_zone_km=210.0,
            recent_in_zone_trip_count=5,
            recent_in_zone_night_ratio=0.08,
            recent_in_zone_risk_rate_per_100km=0.4,
            recent_out_zone_km=210.0,
            recent_out_zone_trip_count=5,
            recent_out_zone_night_ratio=0.35,
            recent_out_zone_risk_rate_per_100km=6.0,
        )

        base_input = build_evaluation_input()
        fixture_targets = [feature for feature in base_input["customer_features"] if feature.risk_change_target]
        fixture_non_targets = [feature for feature in base_input["customer_features"] if not feature.risk_change_target]
        result = evaluate_selected_policy(
            {
                "source_artifacts": base_input["source_artifacts"],
                "selected_policy": selected_policy,
                "customer_features": (
                    [stable_feature, outside_change_feature]
                    + fixture_targets[:4]
                    + fixture_non_targets[:24]
                ),
                "living_zone_store": None,
            }
        )
        stable_snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "stable_low_mileage")
        changed_snapshot = next(row for row in result["customer_snapshots"] if row["customer_id"] == "outside_zone_change")

        self.assertGreater(changed_snapshot["risk_change_score"], stable_snapshot["risk_change_score"])
        self.assertLess(changed_snapshot["senior_safe_mileage_score"], stable_snapshot["senior_safe_mileage_score"])
        self.assertIn("OUT_ZONE_PATTERN_CHANGE_RISK", changed_snapshot["reason_codes"])
        self.assertIn("PROPOSED_MODEL_PREVENTIVE_CARE", changed_snapshot["reason_codes"])
        self.assertNotIn("OUT_ZONE_PATTERN_CHANGE_RISK", stable_snapshot["reason_codes"])
        self.assertEqual(changed_snapshot["care_decision"], "예방 케어")
        self.assertTrue(changed_snapshot["ab_comparison"]["proposed_detected"])
        self.assertFalse(changed_snapshot["ab_comparison"]["baseline_detected"])


if __name__ == "__main__":
    unittest.main()

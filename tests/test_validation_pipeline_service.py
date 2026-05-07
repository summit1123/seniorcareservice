from __future__ import annotations

import unittest

from src.agents.contracts import (
    AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION,
    REQUIRED_AGENT_IDS,
    validate_agent_validation_pipeline_result,
)
from src.webapp.validation_pipeline_service import (
    build_validation_execution_input,
    get_validation_pipeline_check,
    load_validation_pipeline_result,
    normalize_validation_pipeline_tab_model,
    validate_validation_pipeline_tab_model,
)


class TestValidationPipelineService(unittest.TestCase):
    def test_load_validation_pipeline_result_returns_queryable_agent_checks(self) -> None:
        result = load_validation_pipeline_result(run_id="validation-service-test")

        self.assertEqual(result["schema_version"], AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION)
        self.assertEqual(result["run_id"], "validation-service-test")
        self.assertEqual(tuple(result["required_agent_ids"]), REQUIRED_AGENT_IDS)
        self.assertEqual([check["agent_id"] for check in result["checks"]], list(REQUIRED_AGENT_IDS))
        self.assertEqual(result["summary"]["total_agent_count"], 8)
        self.assertEqual(result["summary"]["passed_agent_count"], 8)
        self.assertEqual(result["summary"]["failed_agent_count"], 0)
        self.assertEqual(result["summary"]["validation_pass_rate"], 1.0)
        self.assertTrue(result["summary"]["passed"])
        self.assertEqual(result["approval_gate_thresholds"]["agent_validation_pass_rate_minimum"], 0.95)
        validate_agent_validation_pipeline_result(result)

    def test_get_validation_pipeline_check_returns_one_agent_result_for_audit_tab(self) -> None:
        result = load_validation_pipeline_result()

        evaluation = get_validation_pipeline_check(result, "evaluation_agent")
        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["status"], "succeeded")
        self.assertEqual(evaluation["metrics"]["customer_count"], 30)
        self.assertEqual(evaluation["metrics"]["risk_change_capture_count"], 5)
        self.assertLessEqual(evaluation["metrics"]["non_target_false_positive_count"], 3)
        self.assertLessEqual(evaluation["metrics"]["total_misclassification_count"], 4)
        self.assertGreaterEqual(evaluation["metrics"]["agent_validation_pass_rate"], 0.95)
        self.assertTrue(evaluation["validation"]["approval_gate_passed"])
        self.assertTrue(any(artifact["artifact_id"] == "evaluation_view_model.json" for artifact in evaluation["artifacts"]))

    def test_normalizes_pipeline_result_for_evidence_and_audit_tabs(self) -> None:
        result = load_validation_pipeline_result(run_id="validation-tab-model-test")
        model = normalize_validation_pipeline_tab_model(result)

        self.assertEqual(
            model["schema_version"],
            "senior-safe-mileage-validation-pipeline-tab-model/v1",
        )
        self.assertEqual(model["run_id"], "validation-tab-model-test")
        self.assertEqual({tab["tab_id"] for tab in model["tabs"]}, {"evidence", "audit"})
        self.assertEqual(model["tabs"][0]["item_count"], len(model["evidence_items"]))
        self.assertEqual(model["tabs"][1]["item_count"], len(model["audit_log_entries"]))
        self.assertEqual(model["summary"]["total_agent_count"], 8)
        self.assertEqual(len(model["checks"]), 8)
        self.assertEqual(len(model["evidence_items"]), 8)
        self.assertGreaterEqual(len(model["audit_log_entries"]), 9)
        self.assertIn("execution_input", model["tabs"][0]["section_ids"])
        self.assertIn("audit_log", model["tabs"][1]["section_ids"])
        self.assertTrue(any(item["agent_id"] == "evaluation_agent" for item in model["evidence_items"]))
        self.assertTrue(any(item["agent_id"] == "report_agent" for item in model["evidence_items"]))
        self.assertIn("evaluation_view_model.json", {artifact["artifact_id"] for artifact in model["artifact_index"]})
        self.assertIn("simulation_summary.json", {artifact["artifact_id"] for artifact in model["artifact_index"]})
        self.assertEqual(
            model["privacy_contract"]["external_api_payload_scope"],
            "privacy_filtered_features_only",
        )
        self.assertIn("report_agent", model["privacy_contract"]["checks_with_privacy_filtered_features"])
        self.assertNotIn(
            "customer_id",
            get_validation_pipeline_check(result, "report_agent")["privacy_filtered_features"],
        )
        validate_validation_pipeline_tab_model(model)

    def test_selected_policy_and_scenario_state_feed_validation_pipeline_input(self) -> None:
        execution_input = build_validation_execution_input()
        result = load_validation_pipeline_result(
            run_id="selected-state-validation-test",
            selected_candidate_id=execution_input["selected_policy"]["candidate_id"],
            selected_scenario_id=execution_input["selected_scenario"]["scenario_id"],
        )
        policy_check = get_validation_pipeline_check(result, "policy_search_agent")
        scenario_check = get_validation_pipeline_check(result, "scenario_agent")
        evaluation_check = get_validation_pipeline_check(result, "evaluation_agent")

        self.assertEqual(
            result["execution_input"]["schema_version"],
            "senior-safe-mileage-validation-execution-input/v1",
        )
        self.assertEqual(
            result["execution_input"]["selected_policy"]["candidate_id"],
            execution_input["selected_policy"]["candidate_id"],
        )
        self.assertEqual(
            result["execution_input"]["selected_scenario"]["scenario_id"],
            execution_input["selected_scenario"]["scenario_id"],
        )
        self.assertTrue(policy_check["validation"]["selected_policy_connected_to_execution_input"])
        self.assertTrue(scenario_check["validation"]["selected_scenario_connected_to_execution_input"])
        self.assertTrue(evaluation_check["validation"]["selected_state_connected_to_execution_input"])
        self.assertEqual(
            evaluation_check["validation"]["selected_candidate_id"],
            execution_input["selected_policy"]["candidate_id"],
        )
        self.assertEqual(
            evaluation_check["validation"]["selected_scenario_id"],
            execution_input["selected_scenario"]["scenario_id"],
        )

    def test_report_agent_check_exposes_only_privacy_filtered_llm_features(self) -> None:
        result = load_validation_pipeline_result()

        report = get_validation_pipeline_check(result, "report_agent")
        features = report["privacy_filtered_features"]
        self.assertTrue(features)
        self.assertIn("customer_count", features)
        self.assertIn("agent_validation_pass_rate", features)
        self.assertNotIn("customer_id", features)
        self.assertNotIn("trip_id", features)
        self.assertNotIn("phone_number", features)
        self.assertTrue(report["validation"]["passed"])
        self.assertTrue(report["validation"]["approval"]["ready_for_insurer_review"])

    def test_get_validation_pipeline_check_rejects_unknown_agent_id(self) -> None:
        result = load_validation_pipeline_result()

        with self.assertRaisesRegex(KeyError, "validation pipeline check not found"):
            get_validation_pipeline_check(result, "unknown_agent")


if __name__ == "__main__":
    unittest.main()

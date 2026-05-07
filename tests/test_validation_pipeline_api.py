from __future__ import annotations

import unittest

from src.agents.contracts import validate_agent_validation_pipeline_result
from src.webapp.customer_decision_app import (
    VALIDATION_API_SCHEMA,
    build_validation_api_response,
)


class TestValidationPipelineApi(unittest.TestCase):
    def test_validation_api_endpoint_returns_pipeline_result_from_service(self) -> None:
        status, payload = build_validation_api_response("/api/validation?run_id=api-validation-test")

        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], VALIDATION_API_SCHEMA)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result_type"], "agent_validation_pipeline")
        self.assertEqual(payload["run_id"], "api-validation-test")
        self.assertEqual(payload["result"]["run_id"], "api-validation-test")
        self.assertEqual(payload["result"]["summary"]["validation_pass_rate"], 1.0)
        validate_agent_validation_pipeline_result(payload["result"])

    def test_validation_api_endpoint_returns_single_agent_check_for_audit_ui(self) -> None:
        status, payload = build_validation_api_response(
            "/api/validation/agent?agent_id=evaluation_agent&run_id=api-agent-test"
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result_type"], "agent_validation_check")
        self.assertEqual(payload["run_id"], "api-agent-test")
        self.assertEqual(payload["agent_id"], "evaluation_agent")
        self.assertEqual(payload["result"]["agent_id"], "evaluation_agent")
        self.assertTrue(payload["result"]["passed"])
        self.assertEqual(payload["result"]["metrics"]["customer_count"], 30)
        self.assertGreaterEqual(payload["result"]["metrics"]["agent_validation_pass_rate"], 0.95)
        self.assertTrue(payload["result"]["validation"]["approval_gate_passed"])

    def test_validation_api_forwards_selected_policy_and_scenario_state(self) -> None:
        selected_candidate_id = "policy_30_30_20_20_p20_a75"
        selected_scenario_id = "scenario_seed_20260507_baseline60_recent30"
        status, payload = build_validation_api_response(
            "/api/validation/agent"
            "?agent_id=evaluation_agent"
            "&run_id=api-selected-state-test"
            f"&selected_candidate_id={selected_candidate_id}"
            f"&selected_scenario_id={selected_scenario_id}"
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["execution_input"]["selected_policy"]["candidate_id"], selected_candidate_id)
        self.assertEqual(payload["execution_input"]["selected_scenario"]["scenario_id"], selected_scenario_id)
        self.assertEqual(payload["result"]["validation"]["selected_candidate_id"], selected_candidate_id)
        self.assertEqual(payload["result"]["validation"]["selected_scenario_id"], selected_scenario_id)

    def test_validation_api_endpoint_rejects_missing_agent_id_for_agent_route(self) -> None:
        status, payload = build_validation_api_response("/api/validation/agent")

        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("agent_id", payload["error"])

    def test_validation_api_endpoint_returns_not_found_for_unknown_agent(self) -> None:
        status, payload = build_validation_api_response("/api/validation/agent?agent_id=unknown_agent")

        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["agent_id"], "unknown_agent")
        self.assertIn("validation pipeline check not found", payload["error"])


if __name__ == "__main__":
    unittest.main()

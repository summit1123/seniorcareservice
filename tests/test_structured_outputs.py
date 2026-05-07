from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.agents.contracts import AgentInputPayload, AgentStatus
from src.agents.critic_agent import CriticAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.report_agent import ReportAgent
from src.agents.structured_outputs import (
    AGENT_VALIDATION_PASS_RATE_MINIMUM,
    StructuredOutputEnvelope,
    build_ui_dashboard_bundle,
    load_structured_json,
    validate_critic_review,
    validate_evaluation_view_model,
    validate_report_view_model,
    validate_ui_dashboard_bundle,
    write_structured_json,
)


class TestStructuredOutputs(unittest.TestCase):
    def test_evaluation_critic_report_outputs_share_ui_bundle_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ab_output = workspace / "ab_test_results.csv"
            view_model_output = workspace / "evaluation_view_model.json"
            review_output = workspace / "rule_review.md"
            structured_review_output = workspace / "rule_review.json"
            report_output = workspace / "simulation_summary.md"
            structured_report_output = workspace / "simulation_summary.json"
            llm_auxiliary_output = workspace / "llm_report_auxiliary_results.json"

            evaluation_result = EvaluationAgent().run(
                AgentInputPayload(
                    run_id="structured-evaluation-test",
                    agent_id="evaluation_agent",
                    parameters={
                        "output_path": str(ab_output),
                        "view_model_output_path": str(view_model_output),
                    },
                )
            )
            self.assertEqual(evaluation_result.status, AgentStatus.SUCCEEDED)
            critic_result = CriticAgent().run(
                AgentInputPayload(
                    run_id="structured-critic-test",
                    agent_id="critic_agent",
                    parameters={
                        "ab_results_input": str(ab_output),
                        "view_model_input": str(view_model_output),
                        "review_output": str(review_output),
                        "structured_output": str(structured_review_output),
                    },
                )
            )
            self.assertEqual(critic_result.status, AgentStatus.SUCCEEDED)
            report_result = ReportAgent().run(
                AgentInputPayload(
                    run_id="structured-report-test",
                    agent_id="report_agent",
                    parameters={
                        "evaluation_view_model_input": str(view_model_output),
                        "critic_review_input": str(structured_review_output),
                        "report_output": str(report_output),
                        "structured_output": str(structured_report_output),
                        "llm_auxiliary_output": str(llm_auxiliary_output),
                    },
                )
            )
            self.assertEqual(report_result.status, AgentStatus.SUCCEEDED)

            evaluation = load_structured_json(view_model_output, expected_schema_version="senior-evaluation-results/v1")
            critic = load_structured_json(structured_review_output, expected_schema_version="senior-critic-rule-review/v1")
            report = load_structured_json(structured_report_output, expected_schema_version="senior-report-agent/v1")

            validate_evaluation_view_model(evaluation)
            validate_critic_review(critic)
            validate_report_view_model(report)

            bundle = build_ui_dashboard_bundle(evaluation, critic_review=critic, report_view_model=report)
            validate_ui_dashboard_bundle(bundle)

            self.assertEqual(bundle["schema_version"], "senior-safe-mileage-ui-dashboard/v1")
            self.assertTrue(bundle["approval_gate"]["passed"])
            self.assertGreaterEqual(
                bundle["approval_gate"]["agent_validation_pass_rate"],
                AGENT_VALIDATION_PASS_RATE_MINIMUM,
            )
            self.assertEqual(bundle["ab_comparison"]["proposed_capture_count"], 5)
            self.assertEqual(len(bundle["customers"]), 30)
            self.assertEqual(bundle["critic_review"]["verdict"], "pass")
            self.assertTrue(bundle["report"]["available"])
            self.assertEqual(bundle["customers"][0]["llm_report"]["audience"], "insurer_staff")

    def test_evaluation_view_model_rejects_agent_validation_pass_rate_below_gate(self) -> None:
        evaluation = load_structured_json(
            "data/fixtures/evaluation_view_model.json",
            expected_schema_version="senior-evaluation-results/v1",
        )
        evaluation["summary_metrics"] = {
            **evaluation["summary_metrics"],
            "agent_validation_pass_rate": AGENT_VALIDATION_PASS_RATE_MINIMUM - 0.0001,
        }

        with self.assertRaisesRegex(ValueError, "agent_validation_pass_rate"):
            validate_evaluation_view_model(evaluation)

    def test_structured_output_envelope_and_json_helpers_validate_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "sample.json"
            payload = {"schema_version": "local-test/v1", "value": 1}

            write_structured_json(payload, output)
            loaded = load_structured_json(output, expected_schema_version="local-test/v1")
            envelope = StructuredOutputEnvelope(
                artifact_id="sample.json",
                schema_version="local-test/v1",
                payload=loaded,
            )

            self.assertEqual(envelope.to_dict()["payload"]["value"], 1)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["schema_version"], "local-test/v1")
            with self.assertRaisesRegex(ValueError, "invalid structured output schema_version"):
                load_structured_json(output, expected_schema_version="other/v1")


if __name__ == "__main__":
    unittest.main()

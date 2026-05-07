from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from src.agents.contracts import AgentInputPayload, AgentStatus
from src.agents.critic_agent import CriticAgent, load_evaluation_outputs, review_evaluation_outputs
from src.agents.evaluation_agent import EvaluationAgent


class TestCriticAgent(unittest.TestCase):
    def test_critic_agent_writes_structured_findings_risks_and_followups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ab_output = workspace / "ab_test_results.csv"
            view_model_output = workspace / "evaluation_view_model.json"
            review_output = workspace / "rule_review.md"
            structured_output = workspace / "rule_review.json"

            evaluation_result = EvaluationAgent().run(
                AgentInputPayload(
                    run_id="critic-evaluation-test",
                    agent_id="evaluation_agent",
                    parameters={
                        "output_path": str(ab_output),
                        "view_model_output_path": str(view_model_output),
                    },
                )
            )
            self.assertEqual(evaluation_result.status, AgentStatus.SUCCEEDED)

            result = CriticAgent().run(
                AgentInputPayload(
                    run_id="critic-agent-test",
                    agent_id="critic_agent",
                    parameters={
                        "ab_results_input": str(ab_output),
                        "view_model_input": str(view_model_output),
                        "review_output": str(review_output),
                        "structured_output": str(structured_output),
                    },
                )
            )

            result.validate()
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertTrue(review_output.exists())
            self.assertTrue(structured_output.exists())
            self.assertIsNotNone(result.output_payload)
            assert result.output_payload is not None
            self.assertEqual(
                tuple(artifact.artifact_id for artifact in result.output_payload.output_artifacts),
                ("rule_review.md", "rule_review.json"),
            )
            self.assertTrue(result.output_payload.validation["passed"])
            self.assertEqual(result.output_payload.metrics["risk_change_capture_count"], 5)
            self.assertEqual(result.output_payload.metrics["non_target_false_positive_count"], 1)
            self.assertIn("CRITIC_APPROVAL_GATE_PASSED", result.output_payload.reason_codes)

            review = json.loads(structured_output.read_text(encoding="utf-8"))
            self.assertEqual(review["schema_version"], "senior-critic-rule-review/v1")
            self.assertTrue(review["risks"])
            self.assertTrue(review["required_follow_ups"])
            self.assertIn("SYNTHETIC_ONLY_GENERALIZATION_RISK", {risk["code"] for risk in review["risks"]})
            self.assertIn("Critic Agent Rule Review", review_output.read_text(encoding="utf-8"))

    def test_critic_blocks_when_evaluation_gate_metrics_fail(self) -> None:
        evaluation = load_evaluation_outputs()
        rows = [dict(row) for row in evaluation["customer_rows"]]
        for row in rows:
            if row["risk_change_target"]:
                row["proposed_detected"] = False
                row["ab_comparison"] = dict(row["ab_comparison"], proposed_detected=False)
        evaluation["customer_rows"] = rows
        evaluation["summary_metrics"] = {
            **evaluation["summary_metrics"],
            "proposed_capture_count": 0,
            "proposed_low_mileage_high_risk_capture": 0.0,
            "false_negative_count": 5,
            "total_misclassification_count": 5,
            "agent_validation_pass_rate": 0.9,
            "passes_approval_gate": False,
        }

        review = review_evaluation_outputs(evaluation)

        self.assertFalse(review["validation"]["passed"])
        self.assertGreater(review["validation"]["blocking_finding_count"], 0)
        finding_codes = {finding["code"] for finding in review["findings"]}
        self.assertIn("RISK_CHANGE_CAPTURE_BELOW_GATE", finding_codes)
        self.assertIn("MISCLASSIFICATION_ABOVE_GATE", finding_codes)
        self.assertIn("AGENT_VALIDATION_RATE_BELOW_GATE", finding_codes)

    def test_critic_detects_forbidden_privacy_feature_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ab_input = workspace / "ab_test_results.csv"
            view_model_input = workspace / "evaluation_view_model.json"
            rows = _read_fixture_rows()
            privacy_features = json.loads(rows[0]["privacy_filtered_features_json"])
            privacy_features["trip_id"] = "raw-trip-001"
            rows[0]["privacy_filtered_features_json"] = json.dumps(privacy_features, ensure_ascii=True)
            _write_rows(ab_input, rows)
            view_model_input.write_text("{}", encoding="utf-8")

            result = CriticAgent().run(
                AgentInputPayload(
                    run_id="critic-privacy-test",
                    agent_id="critic_agent",
                    parameters={
                        "ab_results_input": str(ab_input),
                        "view_model_input": str(view_model_input),
                        "review_output": str(workspace / "rule_review.md"),
                        "structured_output": str(workspace / "rule_review.json"),
                    },
                )
            )

            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            assert result.output_payload is not None
            self.assertFalse(result.output_payload.validation["passed"])
            finding_codes = {finding["code"] for finding in result.output_payload.validation.get("findings", ())}
            self.assertIn("PRIVACY_FILTER_FAILURE", finding_codes)
            self.assertGreater(result.output_payload.metrics["blocking_finding_count"], 0)


def _read_fixture_rows() -> list[dict[str, str]]:
    with Path("data/fixtures/ab_test_results.csv").open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

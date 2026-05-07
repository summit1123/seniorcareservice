from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from src.agents.ai_simulation_agent import AISimulationAgent, TRIP_FIELDS
from src.agents.consistency_check_agent import ConsistencyCheckAgent
from src.agents.contracts import AgentInputPayload, AgentStatus


class TestConsistencyCheckAgent(unittest.TestCase):
    def test_ai_simulation_agent_runs_with_shared_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trip_output = Path(tmpdir) / "senior_trip_logs.csv"
            manifest_output = Path(tmpdir) / "simulation_manifest.json"
            agent = AISimulationAgent()
            payload = AgentInputPayload(
                run_id="simulation-contract-test",
                agent_id="ai_simulation_agent",
                parameters={
                    "trip_output": str(trip_output),
                    "manifest_output": str(manifest_output),
                },
            )

            result = agent.run(payload)

            result.validate()
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertTrue(trip_output.exists())
            self.assertTrue(manifest_output.exists())
            self.assertIsNotNone(result.output_payload)
            assert result.output_payload is not None
            self.assertEqual(
                [artifact.artifact_id for artifact in result.output_payload.output_artifacts],
                ["senior_trip_logs.csv", "simulation_manifest.json"],
            )
            self.assertEqual(result.output_payload.metrics["customer_count"], 30)
            self.assertEqual(result.output_payload.metrics["persona_count"], 6)
            self.assertEqual(result.output_payload.metrics["risk_change_target_customer_count"], 5)
            self.assertTrue(result.output_payload.validation["passed"])

    def test_consistency_check_agent_runs_with_shared_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trip_output = Path(tmpdir) / "senior_trip_logs.csv"
            manifest_output = Path(tmpdir) / "simulation_manifest.json"
            report_output = Path(tmpdir) / "validation_report.md"
            AISimulationAgent().write_fixture(trip_output, manifest_output)
            agent = ConsistencyCheckAgent()
            payload = AgentInputPayload(
                run_id="consistency-contract-test",
                agent_id="consistency_check_agent",
                parameters={
                    "trip_input": str(trip_output),
                    "manifest_input": str(manifest_output),
                    "report_output": str(report_output),
                },
            )

            result = agent.run(payload)

            result.validate()
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertTrue(report_output.exists())
            self.assertIsNotNone(result.output_payload)
            assert result.output_payload is not None
            self.assertEqual(result.output_payload.output_artifacts[0].artifact_id, "validation_report.md")
            self.assertEqual(result.output_payload.metrics["customer_count"], 30)
            self.assertEqual(result.output_payload.metrics["persona_count"], 6)
            self.assertEqual(result.output_payload.metrics["failed_check_count"], 0)
            self.assertTrue(result.output_payload.validation["passed"])

    def test_consistency_check_rejects_risk_signal_code_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trip_output = Path(tmpdir) / "senior_trip_logs.csv"
            manifest_output = Path(tmpdir) / "simulation_manifest.json"
            AISimulationAgent().write_fixture(trip_output, manifest_output)

            with trip_output.open(newline="", encoding="utf-8") as csvfile:
                rows = list(csv.DictReader(csvfile))
            rows[0]["night_driving_signal"] = "1"
            rows[0]["night_drive_flag"] = "1"
            rows[0]["risk_signal_codes"] = "none"
            with trip_output.open("w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=TRIP_FIELDS)
                writer.writeheader()
                writer.writerows(rows)

            report = ConsistencyCheckAgent().validate_fixture(trip_output, manifest_output)

            self.assertFalse(report.passed)
            self.assertTrue(any("risk_signal_codes mismatch" in error for error in report.errors))

    def test_consistency_check_rejects_manifest_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trip_output = Path(tmpdir) / "senior_trip_logs.csv"
            manifest_output = Path(tmpdir) / "simulation_manifest.json"
            AISimulationAgent().write_fixture(trip_output, manifest_output)

            manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
            manifest["trip_count"] = manifest["trip_count"] + 1
            manifest_output.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report = ConsistencyCheckAgent().validate_fixture(trip_output, manifest_output)

            self.assertFalse(report.passed)
            self.assertTrue(any("manifest trip_count mismatch" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()

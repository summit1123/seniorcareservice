from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.agents.ai_simulation_agent import AISimulationAgent
from src.agents.consistency_check_agent import ConsistencyCheckAgent
from src.agents.contracts import AgentArtifact, AgentExecutionResult, AgentInputPayload, AgentStatus
from src.agents.orchestrator import AGENT_REGISTRY
from src.agents.persona_agent import PersonaAgent
from src.agents.policy_search_agent import PolicySearchAgent
from src.agents.scenario_agent import ScenarioAgent


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTED_AGENT_IDS = (
    "persona_agent",
    "scenario_agent",
    "ai_simulation_agent",
    "consistency_check_agent",
    "policy_search_agent",
)


class TestFiveAgentContractFixtures(unittest.TestCase):
    def test_all_five_implemented_agents_emit_contract_valid_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            scenario_output = workspace / "scenario_config.json"
            trip_output = workspace / "senior_trip_logs.csv"
            manifest_output = workspace / "simulation_manifest.json"
            validation_output = workspace / "validation_report.md"
            candidate_output = workspace / "candidate_rules.json"

            results = [
                PersonaAgent().run(AgentInputPayload(run_id="five-agent-contract-run", agent_id="persona_agent")),
            ]
            results.append(
                ScenarioAgent().run(
                    AgentInputPayload(
                        run_id="five-agent-contract-run",
                        agent_id="scenario_agent",
                        input_artifacts=_latest_artifacts(results),
                        parameters={"output_path": str(scenario_output)},
                    )
                )
            )
            results.append(
                AISimulationAgent().run(
                    AgentInputPayload(
                        run_id="five-agent-contract-run",
                        agent_id="ai_simulation_agent",
                        input_artifacts=_latest_artifacts(results),
                        parameters={
                            "trip_output": str(trip_output),
                            "manifest_output": str(manifest_output),
                        },
                    )
                )
            )
            results.append(
                ConsistencyCheckAgent().run(
                    AgentInputPayload(
                        run_id="five-agent-contract-run",
                        agent_id="consistency_check_agent",
                        input_artifacts=_latest_artifacts(results),
                        parameters={"report_output": str(validation_output)},
                    )
                )
            )
            results.append(
                PolicySearchAgent().run(
                    AgentInputPayload(
                        run_id="five-agent-contract-run",
                        agent_id="policy_search_agent",
                        input_artifacts=_latest_artifacts(results),
                        parameters={"output_path": str(candidate_output)},
                    )
                )
            )

            self.assertEqual([result.metadata.agent_id for result in results], list(IMPLEMENTED_AGENT_IDS))
            for result in results:
                with self.subTest(agent_id=result.metadata.agent_id):
                    result.validate()
                    self.assertEqual(result.status, AgentStatus.SUCCEEDED)
                    self.assertEqual(result.metadata, AGENT_REGISTRY[result.metadata.agent_id])
                    self.assertIsNotNone(result.output_payload)
                    assert result.output_payload is not None
                    self.assertEqual(
                        tuple(artifact.artifact_id for artifact in result.output_payload.output_artifacts),
                        AGENT_REGISTRY[result.metadata.agent_id].produces,
                    )
                    self.assertTrue(result.output_payload.reason_codes)
                    self.assertTrue(result.output_payload.validation["passed"])
                    for artifact in result.output_payload.output_artifacts:
                        self.assertTrue(_artifact_path(artifact).exists(), artifact.artifact_id)

            policy_result = results[-1]
            assert policy_result.output_payload is not None
            self.assertTrue(policy_result.output_payload.metrics["passes_approval_gate"])
            self.assertEqual(policy_result.output_payload.metrics["selected_capture_count"], 5)
            self.assertLessEqual(policy_result.output_payload.metrics["selected_false_positive_count"], 3)

    def test_five_agent_registry_contract_matches_implemented_agent_metadata(self) -> None:
        implemented_metadata = {
            "persona_agent": PersonaAgent.metadata,
            "scenario_agent": ScenarioAgent.metadata,
            "ai_simulation_agent": AISimulationAgent.metadata,
            "consistency_check_agent": ConsistencyCheckAgent.metadata,
            "policy_search_agent": PolicySearchAgent.metadata,
        }

        self.assertEqual(tuple(implemented_metadata), IMPLEMENTED_AGENT_IDS)
        for agent_id, metadata in implemented_metadata.items():
            with self.subTest(agent_id=agent_id):
                self.assertEqual(metadata, AGENT_REGISTRY[agent_id])
                self.assertTrue(metadata.produces)
                if agent_id != "persona_agent":
                    self.assertTrue(metadata.consumes)


def _latest_artifacts(results: list[AgentExecutionResult]) -> tuple[AgentArtifact, ...]:
    artifacts: list[AgentArtifact] = []
    for result in results:
        if result.output_payload is None:
            continue
        artifacts.extend(result.output_payload.output_artifacts)
    return tuple(artifacts)


def _artifact_path(artifact: AgentArtifact) -> Path:
    if artifact.path is None:
        raise AssertionError(f"artifact path is required: {artifact.artifact_id}")
    path = Path(artifact.path)
    if path.is_absolute():
        return path
    return ROOT / path


if __name__ == "__main__":
    unittest.main()

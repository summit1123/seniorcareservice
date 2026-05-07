from __future__ import annotations

import unittest

from src.agents.contracts import (
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentStatus,
    ArtifactType,
    REQUIRED_AGENT_IDS,
)
from src.agents.orchestrator import (
    AGENT_REGISTRY,
    build_orchestrator_spec,
    execute_default_agent_pipeline,
)


class ExecutionSpyAgent:
    def __init__(self, metadata: AgentMetadata, execution_log: list[str]) -> None:
        self.metadata = metadata
        self.execution_log = execution_log
        self.payloads: list[AgentInputPayload] = []

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        if self.payloads:
            raise AssertionError(f"{self.metadata.agent_id} executed more than once")
        if payload.agent_id != self.metadata.agent_id:
            raise AssertionError(f"payload routed to wrong agent: {payload.agent_id}")

        self.execution_log.append(self.metadata.agent_id)
        self.payloads.append(payload)
        output = AgentOutputPayload(
            run_id=payload.run_id,
            agent_id=self.metadata.agent_id,
            output_artifacts=tuple(
                AgentArtifact(
                    artifact_id=artifact_name,
                    artifact_type=ArtifactType.CSV if artifact_name.endswith(".csv") else ArtifactType.JSON,
                    path=artifact_name,
                    summary={"producer_agent_id": self.metadata.agent_id},
                )
                for artifact_name in self.metadata.produces
            ),
            metrics={"executed": True},
            decisions={"agent_id": self.metadata.agent_id},
            reason_codes=(f"{self.metadata.agent_id.upper()}_EXECUTED",),
            validation={"passed": True},
        )
        return AgentExecutionResult(
            run_id=payload.run_id,
            metadata=self.metadata,
            status=AgentStatus.SUCCEEDED,
            input_payload=payload,
            output_payload=output,
        )


class TestOrchestratorAgentExecution(unittest.TestCase):
    def test_default_pipeline_executes_each_required_agent_exactly_once(self) -> None:
        execution_log: list[str] = []
        agents = {
            agent_id: ExecutionSpyAgent(metadata, execution_log)
            for agent_id, metadata in AGENT_REGISTRY.items()
        }
        unreferenced_agent = ExecutionSpyAgent(AGENT_REGISTRY["report_agent"], execution_log)
        agents["unreferenced_agent"] = unreferenced_agent

        execution = execute_default_agent_pipeline("exact-agent-execution-test", agents=agents)

        self.assertTrue(execution.succeeded)
        self.assertEqual(tuple(execution_log), REQUIRED_AGENT_IDS)
        self.assertEqual(tuple(result.metadata.agent_id for result in execution.results), REQUIRED_AGENT_IDS)
        self.assertEqual(tuple(result.status for result in execution.results), (AgentStatus.SUCCEEDED,) * len(REQUIRED_AGENT_IDS))
        self.assertEqual(unreferenced_agent.payloads, [])

        for agent_id in REQUIRED_AGENT_IDS:
            with self.subTest(agent_id=agent_id):
                self.assertEqual(len(agents[agent_id].payloads), 1)
                result = execution.get_result(agent_id)
                self.assertEqual(result.input_payload.agent_id, agent_id)
                self.assertEqual(result.output_payload.agent_id, agent_id)

    def test_required_agents_receive_expected_dependency_payloads(self) -> None:
        spec = build_orchestrator_spec("dependency-payload-execution-test")
        execution_log: list[str] = []
        agents = {
            agent_id: ExecutionSpyAgent(metadata, execution_log)
            for agent_id, metadata in spec.registry.items()
        }

        execution = execute_default_agent_pipeline(spec.run_id, agents=agents)

        self.assertTrue(execution.succeeded)
        produced_artifacts: set[str] = set()
        for index, step in enumerate(spec.steps):
            with self.subTest(agent_id=step.agent_id):
                payload = agents[step.agent_id].payloads[0]
                expected_input_artifacts = tuple(
                    artifact_name
                    for artifact_name in step.required_artifacts
                    if artifact_name in produced_artifacts
                )
                self.assertEqual(payload.upstream_results, step.depends_on)
                self.assertEqual(
                    tuple(artifact.artifact_id for artifact in payload.input_artifacts),
                    expected_input_artifacts,
                )
                if index == 0:
                    self.assertEqual(payload.shared_state.completed_agents, ())
                    self.assertEqual(payload.parameters, {})
                else:
                    previous_agent_id = spec.steps[index - 1].agent_id
                    previous_step_id = spec.steps[index - 1].step_id
                    self.assertEqual(payload.shared_state.completed_agents[-1], previous_agent_id)
                    self.assertIn(previous_step_id, payload.parameters["upstream_results"])
                    self.assertEqual(
                        payload.parameters["upstream_results"][previous_step_id]["metadata"]["agent_id"],
                        previous_agent_id,
                    )
                produced_artifacts.update(step.output_artifacts)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from src.agents.contracts import (
    AgentValidationPipelineResult,
    AgentExecutionResult,
    AgentInputPayload,
    AgentStatus,
    FORBIDDEN_EXTERNAL_API_FIELDS,
    REQUIRED_AGENT_IDS,
    SeniorMileageAgent,
    validate_agent_validation_pipeline_result,
)
from src.agents.orchestrator import (
    build_default_agent_map,
    build_orchestrator_spec,
    execute_agent_pipeline,
)
from src.llm import OpenAIClientAPIError


class CapturingAgent:
    def __init__(self, wrapped: SeniorMileageAgent) -> None:
        self.wrapped = wrapped
        self.metadata = wrapped.metadata
        self.inputs: list[AgentInputPayload] = []
        self.raw_results: list[AgentExecutionResult] = []

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        self.inputs.append(payload)
        result = self.wrapped.run(payload)
        self.raw_results.append(result)
        return result


class OpenAIFailureInjectingAgent:
    def __init__(self, wrapped: SeniorMileageAgent, openai_client: object, output_dir: Path) -> None:
        self.wrapped = wrapped
        self.metadata = wrapped.metadata
        self.openai_client = openai_client
        self.output_dir = output_dir
        self.inputs: list[AgentInputPayload] = []
        self.raw_results: list[AgentExecutionResult] = []

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        self.inputs.append(payload)
        injected_payload = replace(
            payload,
            parameters={
                **payload.parameters,
                "openai_client": self.openai_client,
                "report_output": str(self.output_dir / "simulation_summary.md"),
                "structured_output": str(self.output_dir / "simulation_summary.json"),
                "llm_auxiliary_output": str(self.output_dir / "llm_report_auxiliary_results.json"),
            },
        )
        result = self.wrapped.run(injected_payload)
        self.raw_results.append(result)
        return result


class FailingOpenAIReportClient:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def generate_insurer_report(self, request: object) -> object:
        self.requests.append(request)
        raise OpenAIClientAPIError("mocked OpenAI outage during agent validation")


class TestAgentStateHandoffIntegration(unittest.TestCase):
    def test_default_agents_receive_transformed_shared_state_and_artifact_handoffs(self) -> None:
        spec = build_orchestrator_spec("state-handoff-integration-test")
        agents = {
            agent_id: CapturingAgent(agent)
            for agent_id, agent in build_default_agent_map().items()
        }

        execution = execute_agent_pipeline(spec, agents)

        self.assertTrue(execution.succeeded)
        self.assertEqual(tuple(result.status for result in execution.results), (AgentStatus.SUCCEEDED,) * 8)
        self.assertEqual(tuple(result.metadata.agent_id for result in execution.results), REQUIRED_AGENT_IDS)

        scenario_input = agents["scenario_agent"].inputs[0]
        self.assertEqual(scenario_input.shared_state.completed_agents, ("persona_agent",))
        self.assertEqual(
            tuple(artifact.artifact_id for artifact in scenario_input.input_artifacts),
            ("persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"),
        )
        self.assertEqual(scenario_input.shared_state.metrics["persona_agent"]["customer_count"], 30)
        self.assertEqual(scenario_input.shared_state.validation["persona_agent"]["passed"], True)

        simulation_input = agents["ai_simulation_agent"].inputs[0]
        self.assertEqual(simulation_input.shared_state.completed_agents[-1], "scenario_agent")
        self.assertEqual(
            tuple(artifact.artifact_id for artifact in simulation_input.input_artifacts),
            ("scenario_config.json",),
        )
        self.assertEqual(simulation_input.shared_state.metrics["scenario_agent"]["baseline_days"], 60)
        self.assertEqual(simulation_input.shared_state.metrics["scenario_agent"]["recent_days"], 30)
        self.assertEqual(
            simulation_input.shared_state.validation["scenario_agent"]["risk_change_target_persona"],
            "recent_outer_risk_change",
        )

        consistency_input = agents["consistency_check_agent"].inputs[0]
        self.assertEqual(
            tuple(artifact.artifact_id for artifact in consistency_input.input_artifacts),
            ("senior_trip_logs.csv", "simulation_manifest.json"),
        )
        self.assertEqual(consistency_input.shared_state.metrics["ai_simulation_agent"]["customer_count"], 30)
        self.assertGreater(consistency_input.shared_state.metrics["ai_simulation_agent"]["trip_count"], 0)
        trip_observation_period = consistency_input.shared_state.artifacts["senior_trip_logs.csv"]["summary"][
            "observation_period"
        ]
        self.assertEqual(trip_observation_period["baseline_days"], 60)
        self.assertEqual(trip_observation_period["recent_days"], 30)
        self.assertEqual(trip_observation_period["baseline_start_date"], "2026-01-01")
        self.assertEqual(trip_observation_period["recent_end_date"], "2026-03-31")

        policy_input = agents["policy_search_agent"].inputs[0]
        self.assertIn("validation_report.md", [artifact.artifact_id for artifact in policy_input.input_artifacts])
        self.assertEqual(policy_input.shared_state.validation["consistency_check_agent"]["passed"], True)
        self.assertIn("BASELINE_60_RECENT_30_COVERAGE_VALIDATED", policy_input.shared_state.reason_codes["ai_simulation_agent"])

        evaluation_input = agents["evaluation_agent"].inputs[0]
        self.assertIn("candidate_rules.json", [artifact.artifact_id for artifact in evaluation_input.input_artifacts])
        self.assertEqual(evaluation_input.shared_state.metrics["policy_search_agent"]["passes_approval_gate"], True)
        self.assertIn("selected_candidate_id", evaluation_input.shared_state.decisions["policy_search_agent"])

        critic_input = agents["critic_agent"].inputs[0]
        self.assertEqual(
            tuple(artifact.artifact_id for artifact in critic_input.input_artifacts),
            ("ab_test_results.csv", "candidate_rules.json"),
        )
        self.assertEqual(critic_input.shared_state.metrics["evaluation_agent"]["proposed_capture_count"], 5)
        self.assertEqual(critic_input.shared_state.metrics["evaluation_agent"]["baseline_capture_count"], 0)

        report_input = agents["report_agent"].inputs[0]
        self.assertEqual(
            tuple(artifact.artifact_id for artifact in report_input.input_artifacts),
            ("evaluation_view_model.json", "rule_review.json"),
        )
        self.assertEqual(report_input.shared_state.completed_agents[-1], "critic_agent")
        self.assertNotIn("report_agent", report_input.shared_state.completed_agents)
        self.assertEqual(report_input.shared_state.metrics["critic_agent"]["passed"], True)
        self.assertEqual(report_input.shared_state.decisions["critic_agent"]["approval_gate_passed"], True)

    def test_upstream_result_payloads_contain_merged_output_state_for_next_agent(self) -> None:
        spec = build_orchestrator_spec("upstream-state-transform-integration-test")
        agents = {
            agent_id: CapturingAgent(agent)
            for agent_id, agent in build_default_agent_map().items()
        }

        execution = execute_agent_pipeline(spec, agents)

        self.assertTrue(execution.succeeded)
        report_input = agents["report_agent"].inputs[0]
        critic_step_id = spec.steps[6].step_id
        critic_upstream = report_input.parameters["upstream_results"][critic_step_id]
        critic_state = critic_upstream["output_payload"]["shared_state"]

        self.assertEqual(critic_upstream["metadata"]["agent_id"], "critic_agent")
        self.assertEqual(critic_state["completed_agents"], list(REQUIRED_AGENT_IDS[:-1]))
        self.assertEqual(critic_state["agent_statuses"]["critic_agent"], "succeeded")
        self.assertEqual(critic_state["metrics"]["evaluation_agent"]["proposed_capture_count"], 5)
        selected_candidate_id = critic_state["decisions"]["policy_search_agent"]["selected_candidate_id"]
        self.assertTrue(selected_candidate_id)
        self.assertIn(
            selected_candidate_id,
            critic_state["decisions"]["policy_search_agent"]["ranked_candidate_ids"],
        )
        self.assertIn("critic_agent", critic_state["validation"])
        self.assertNotIn("report_agent", critic_state["metrics"])

    def test_report_output_merges_llm_safe_request_features_without_forbidden_fields(self) -> None:
        execution = execute_agent_pipeline(
            build_orchestrator_spec("privacy-state-transform-integration-test"),
            {
                agent_id: CapturingAgent(agent)
                for agent_id, agent in build_default_agent_map().items()
            },
        )

        self.assertTrue(execution.succeeded)
        report_output = execution.get_result("report_agent").output_payload
        self.assertIsNotNone(report_output)
        assert report_output is not None

        state = report_output.shared_state
        self.assertEqual(state.completed_agents, REQUIRED_AGENT_IDS)
        self.assertEqual(state.metrics["report_agent"]["customer_count"], 30)
        self.assertEqual(state.decisions["report_agent"]["approval_gate_passed"], True)
        self.assertIn("report_agent", state.llm_reports)
        self.assertIn("report_agent", state.privacy_filtered_features)
        self.assertEqual(
            state.privacy_filtered_features["report_agent"],
            state.llm_reports["report_agent"]["request_features"],
        )

        serialized_features = json.dumps(state.privacy_filtered_features["report_agent"], ensure_ascii=False)
        flattened_keys = _flatten_keys(state.privacy_filtered_features["report_agent"])
        self.assertFalse(flattened_keys & FORBIDDEN_EXTERNAL_API_FIELDS)
        self.assertNotIn("cust_", serialized_features)
        self.assertNotIn("trip_", serialized_features)

    def test_openai_failure_does_not_stop_agent_validation_loop_and_returns_fallback_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = build_orchestrator_spec("openai-failure-agent-validation-test")
            default_agents = build_default_agent_map()
            failing_client = FailingOpenAIReportClient()
            agents = {
                agent_id: CapturingAgent(agent)
                for agent_id, agent in default_agents.items()
            }
            agents["report_agent"] = OpenAIFailureInjectingAgent(
                default_agents["report_agent"],
                failing_client,
                Path(tmpdir),
            )

            execution = execute_agent_pipeline(spec, agents)

            self.assertTrue(execution.succeeded)
            self.assertEqual(tuple(result.status for result in execution.results), (AgentStatus.SUCCEEDED,) * 8)
            self.assertGreaterEqual(len(failing_client.requests), 1)

            validation_result = AgentValidationPipelineResult.from_execution_results(
                execution.run_id,
                execution.results,
            ).to_dict()
            validate_agent_validation_pipeline_result(validation_result)
            self.assertTrue(validation_result["summary"]["passed"])
            self.assertEqual(validation_result["summary"]["validation_pass_rate"], 1.0)

            report_output = execution.get_result("report_agent").output_payload
            self.assertIsNotNone(report_output)
            assert report_output is not None

            self.assertTrue(report_output.validation["passed"])
            self.assertEqual(report_output.validation["fallback_report_count"], 30)
            self.assertEqual(report_output.metrics["customer_count"], 30)
            self.assertEqual(report_output.metrics["risk_change_capture_count"], 5)
            self.assertGreaterEqual(report_output.metrics["agent_validation_pass_rate"], 0.95)
            self.assertTrue(report_output.decisions["approval_gate_passed"])

            llm_report = report_output.llm_report
            self.assertEqual(llm_report["mode"], "fallback_template")
            self.assertEqual(llm_report["llm_service_status"]["status"], "failed")
            self.assertFalse(llm_report["llm_service_status"]["active"])
            self.assertTrue(llm_report["llm_service_status"]["core_outputs_continue"])
            self.assertEqual(llm_report["empty_report_result"]["text"], "")
            self.assertTrue(llm_report["empty_report_result"]["core_outputs_continue"])


def _flatten_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys: set[str] = set()
        for key, nested in value.items():
            keys.add(str(key).strip().lower())
            keys.update(_flatten_keys(nested))
        return keys
    if isinstance(value, list):
        keys = set()
        for item in value:
            keys.update(_flatten_keys(item))
        return keys
    return set()


if __name__ == "__main__":
    unittest.main()

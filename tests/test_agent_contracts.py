from __future__ import annotations

import json
import unittest

from src.agents.contracts import (
    ABComparison,
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentSharedState,
    AgentStatus,
    AgentValidationCheckResult,
    AgentValidationPipelineResult,
    AgentValidationSummary,
    ArtifactType,
    CustomerDecisionSnapshot,
    ObservationPeriod,
    PolicyCandidate,
    REQUIRED_AGENT_IDS,
    REQUIRED_SHARED_STATE_FIELDS,
    AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION,
    validate_agent_validation_pipeline_result,
    validate_customer_decision_snapshot,
)
from src.agents.orchestrator import AGENT_REGISTRY, AgentRegistry, build_orchestrator_spec, build_pipeline_steps
from src.agents.orchestrator import build_default_agent_map, execute_agent_pipeline
from src.agents.orchestrator import execute_default_agent_pipeline


class RecordingAgent:
    def __init__(self, metadata: AgentMetadata, calls: list[AgentInputPayload], *, fail: bool = False) -> None:
        self.metadata = metadata
        self.calls = calls
        self.fail = fail

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        self.calls.append(payload)
        if self.fail:
            raise RuntimeError(f"{self.metadata.agent_id} planned failure")
        artifact_name = self.metadata.produces[0] if self.metadata.produces else f"{self.metadata.agent_id}.json"
        output = AgentOutputPayload(
            run_id=payload.run_id,
            agent_id=self.metadata.agent_id,
            output_artifacts=(
                AgentArtifact(
                    artifact_id=artifact_name,
                    artifact_type=ArtifactType.JSON,
                    path=artifact_name,
                    summary={"agent_id": self.metadata.agent_id},
                ),
            ),
            messages=(f"{self.metadata.agent_id} completed",),
        )
        return AgentExecutionResult(
            run_id=payload.run_id,
            metadata=self.metadata,
            status=AgentStatus.SUCCEEDED,
            input_payload=payload,
            output_payload=output,
        )


class ProducingAgent(RecordingAgent):
    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        self.calls.append(payload)
        output = AgentOutputPayload(
            run_id=payload.run_id,
            agent_id=self.metadata.agent_id,
            output_artifacts=tuple(
                AgentArtifact(
                    artifact_id=artifact_name,
                    artifact_type=ArtifactType.CSV if artifact_name.endswith(".csv") else ArtifactType.JSON,
                    path=artifact_name,
                    summary={
                        "agent_id": self.metadata.agent_id,
                        "upstream_artifact_count": len(payload.input_artifacts),
                    },
                )
                for artifact_name in self.metadata.produces
            ),
            messages=(f"{self.metadata.agent_id} produced {len(self.metadata.produces)} artifacts",),
        )
        return AgentExecutionResult(
            run_id=payload.run_id,
            metadata=self.metadata,
            status=AgentStatus.SUCCEEDED,
            input_payload=payload,
            output_payload=output,
        )


class TestAgentContracts(unittest.TestCase):
    def test_orchestrator_registry_defines_all_required_agents(self) -> None:
        self.assertEqual(tuple(AGENT_REGISTRY), REQUIRED_AGENT_IDS)

        for agent_id in REQUIRED_AGENT_IDS:
            metadata = AGENT_REGISTRY[agent_id]
            self.assertEqual(metadata.agent_id, agent_id)
            self.assertTrue(metadata.display_name)
            self.assertTrue(metadata.description)
            self.assertEqual(metadata.input_schema, "AgentInputPayload")
            self.assertEqual(metadata.output_schema, "AgentOutputPayload")

    def test_orchestrator_steps_preserve_required_execution_order_and_dependencies(self) -> None:
        spec = build_orchestrator_spec("contract-test-run")

        self.assertEqual(tuple(step.agent_id for step in spec.steps), REQUIRED_AGENT_IDS)
        self.assertEqual(spec.steps[0].depends_on, ())
        for index, step in enumerate(spec.steps[1:], start=1):
            self.assertEqual(step.depends_on, (spec.steps[index - 1].step_id,))
            self.assertEqual(step.required_artifacts, AGENT_REGISTRY[step.agent_id].consumes)
            self.assertEqual(step.output_artifacts, AGENT_REGISTRY[step.agent_id].produces)

    def test_agent_registry_resolves_agents_by_name_id_and_type(self) -> None:
        self.assertEqual(AGENT_REGISTRY.get_by_name("Policy Search Agent").agent_id, "policy_search_agent")
        self.assertEqual(AGENT_REGISTRY.resolve("policy_search_agent").agent_id, "policy_search_agent")
        self.assertEqual(AGENT_REGISTRY.get_by_type(AgentRole.POLICY_SEARCH).agent_id, "policy_search_agent")
        self.assertEqual(AGENT_REGISTRY.get_by_type("policy_search").display_name, "Policy Search Agent")

    def test_agent_registry_rejects_duplicate_ids_and_roles_without_replace(self) -> None:
        registry = AgentRegistry((AGENT_REGISTRY["persona_agent"],))

        with self.assertRaisesRegex(ValueError, "agent_id already registered"):
            registry.register(AGENT_REGISTRY["persona_agent"])

        with self.assertRaisesRegex(ValueError, "agent role already registered"):
            registry.register(
                AgentMetadata(
                    agent_id="alternate_persona_agent",
                    role=AgentRole.PERSONA,
                    display_name="Alternate Persona Agent",
                    description="Duplicate persona role for registration guard tests.",
                )
            )

    def test_pipeline_steps_can_be_built_from_ordered_agent_references(self) -> None:
        steps = build_pipeline_steps(
            (
                "Persona Agent",
                AgentRole.SCENARIO,
                "ai-simulation-agent",
                "consistency_check",
                AGENT_REGISTRY["policy_search_agent"],
                "Evaluation Agent",
                AgentRole.CRITIC,
                "report",
            )
        )

        self.assertEqual(tuple(step.agent_id for step in steps), REQUIRED_AGENT_IDS)
        self.assertEqual(steps[4].required_artifacts, AGENT_REGISTRY["policy_search_agent"].consumes)
        self.assertEqual(steps[4].depends_on, (steps[3].step_id,))

    def test_orchestrator_spec_accepts_registered_agent_references(self) -> None:
        registry = AgentRegistry()
        for metadata in AGENT_REGISTRY.values():
            registry.register(metadata)
        registry.register(
            AgentMetadata(
                agent_id="shadow_report_agent",
                role=AgentRole.REPORT,
                display_name="Shadow Report Agent",
                description="Replacement report agent for local pipeline experiments.",
                consumes=("rule_review.md",),
                produces=("shadow_report.md",),
            ),
            replace=True,
        )

        spec = build_orchestrator_spec(
            "custom-agent-ref-run",
            agent_refs=(
                "Persona Agent",
                "Scenario Agent",
                "AI Simulation Agent",
                "Consistency Check Agent",
                "Policy Search Agent",
                "Evaluation Agent",
                "Critic Agent",
                "Shadow Report Agent",
            ),
            registry=registry,
        )

        self.assertEqual(spec.steps[-1].agent_id, "shadow_report_agent")
        self.assertEqual(spec.registry.get_by_type("report").agent_id, "shadow_report_agent")

    def test_input_and_output_payloads_are_json_serializable(self) -> None:
        artifact = AgentArtifact(
            artifact_id="candidate_rules",
            artifact_type=ArtifactType.JSON,
            path="data/fixtures/candidate_rules.json",
            summary={"candidate_count": 3},
        )
        payload = AgentInputPayload(
            run_id="contract-test-run",
            agent_id="policy_search_agent",
            input_artifacts=(artifact,),
            parameters={"weight_grid": {"w1": [0.3, 0.35]}},
            privacy_filtered_features={"persona_type": "recent_outer_risk_change", "recent_trip_count": 12},
        )
        output = AgentOutputPayload(
            run_id="contract-test-run",
            agent_id="policy_search_agent",
            output_artifacts=(artifact,),
            metrics={"candidate_count": 3, "passes_gate": True},
            decisions={"selected_candidate_id": "policy_v1"},
            reason_codes=("LOW_MILEAGE_RISK_CHANGE",),
            validation={"passed": True},
            messages=("policy candidates generated",),
        )
        result = AgentExecutionResult(
            run_id="contract-test-run",
            metadata=AGENT_REGISTRY["policy_search_agent"],
            status=AgentStatus.SUCCEEDED,
            input_payload=payload,
            output_payload=output,
            completed_at="2026-05-07T00:00:00+00:00",
            duration_ms=10,
        )

        result.validate()
        encoded = json.dumps(result.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["schema_version"], "senior-safe-mileage-agent-contract/v1")
        self.assertEqual(decoded["metadata"]["agent_id"], "policy_search_agent")
        self.assertEqual(decoded["status"], "succeeded")
        self.assertEqual(decoded["output_payload"]["reason_codes"], ["LOW_MILEAGE_RISK_CHANGE"])
        self.assertEqual(set(decoded["input_payload"]["shared_state"]), REQUIRED_SHARED_STATE_FIELDS)
        self.assertEqual(set(decoded["output_payload"]["shared_state"]), REQUIRED_SHARED_STATE_FIELDS)

    def test_privacy_filter_rejects_forbidden_external_llm_fields(self) -> None:
        payload = AgentInputPayload(
            run_id="contract-test-run",
            agent_id="report_agent",
            privacy_filtered_features={
                "persona_type": "stable_local_low_mileage",
                "summary": {"trip_id": "raw-trip-001"},
            },
        )

        with self.assertRaisesRegex(ValueError, "forbidden external API fields"):
            payload.validate(AGENT_REGISTRY["report_agent"])

    def test_shared_state_contract_requires_all_handoff_fields_and_privacy_filter(self) -> None:
        state = AgentSharedState(
            completed_agents=("report_agent",),
            agent_statuses={"report_agent": "succeeded"},
            artifacts={"simulation_summary.json": {"artifact_id": "simulation_summary.json"}},
            metrics={"report_agent": {"customer_count": 30}},
            decisions={"report_agent": {"approval_gate_passed": True}},
            reason_codes={"report_agent": ("REPORT_READY",)},
            validation={"report_agent": {"passed": True}},
            llm_reports={"report_agent": {"request_features": {"customer_count": 30}}},
            privacy_filtered_features={"report_agent": {"customer_count": 30}},
        )

        decoded = AgentSharedState.from_dict(json.loads(json.dumps(state.to_dict(), ensure_ascii=False)))

        self.assertEqual(set(decoded.to_dict()), REQUIRED_SHARED_STATE_FIELDS)
        self.assertEqual(decoded.completed_agents, ("report_agent",))

        unsafe = state.to_dict()
        unsafe["privacy_filtered_features"]["report_agent"] = {"trip_id": "raw-trip-001"}
        with self.assertRaisesRegex(ValueError, "forbidden external API fields"):
            AgentSharedState.from_dict(unsafe)

    def test_report_agent_contract_requires_llm_privacy_filter(self) -> None:
        metadata = AGENT_REGISTRY["report_agent"]

        self.assertTrue(metadata.uses_llm)
        self.assertTrue(metadata.requires_privacy_filter)

    def test_customer_decision_snapshot_contract_covers_product_ontology(self) -> None:
        snapshot = CustomerDecisionSnapshot(
            customer_id="cust_011",
            persona_type="recent_outer_risk_change",
            observation_period=ObservationPeriod(),
            living_zone={"cluster_count": 2, "out_zone_ratio_recent": 0.42},
            mileage_baseline_score=88.0,
            senior_safe_mileage_score=58.5,
            risk_change_score=91.2,
            policy_candidate=PolicyCandidate(
                candidate_id="policy_v1",
                weights={
                    "w_mileage": 0.35,
                    "w_in_zone": 0.35,
                    "w_out_zone_safe": 0.15,
                    "w_out_zone_change": 0.15,
                },
                thresholds={"care_threshold": 80, "tier_threshold": {"S": 85, "A": 70}},
                rationale="Captures low-mileage recent outer-zone risk change.",
            ),
            care_decision="예방 케어",
            reason_codes=("LOW_MILEAGE_RISK_CHANGE", "OUT_ZONE_NIGHT_RISK"),
            ab_comparison=ABComparison(
                baseline_detected=False,
                proposed_detected=True,
                baseline_score=88.0,
                proposed_score=58.5,
                metrics={"risk_change_capture": True},
            ),
            agent_validation=AgentValidationSummary(passed=True, validation_pass_rate=1.0),
            llm_report={
                "mode": "fallback",
                "request_features": {
                    "persona_type": "recent_outer_risk_change",
                    "risk_change_score": 91.2,
                    "care_decision": "예방 케어",
                    "reason_codes": ["LOW_MILEAGE_RISK_CHANGE"],
                },
            },
            privacy_filtered_features={
                "persona_type": "recent_outer_risk_change",
                "baseline_total_km": 280.0,
                "recent_out_zone_ratio": 0.42,
                "risk_change_score": 91.2,
                "senior_safe_mileage_score": 58.5,
                "care_decision": "예방 케어",
                "reason_codes": ["LOW_MILEAGE_RISK_CHANGE", "OUT_ZONE_NIGHT_RISK"],
            },
        )

        snapshot.validate()
        decoded = json.loads(json.dumps(snapshot.to_dict(), ensure_ascii=False))

        self.assertEqual(decoded["observation_period"]["baseline_days"], 60)
        self.assertEqual(decoded["observation_period"]["recent_days"], 30)
        self.assertEqual(decoded["policy_candidate"]["candidate_id"], "policy_v1")
        self.assertTrue(decoded["ab_comparison"]["proposed_detected"])

    def test_customer_decision_snapshot_dict_validator_rejects_missing_required_concepts(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required keys"):
            validate_customer_decision_snapshot({"customer_id": "cust_001"})

    def test_customer_decision_snapshot_rejects_unsafe_llm_request_features(self) -> None:
        snapshot = {
            "customer_id": "cust_011",
            "persona_type": "recent_outer_risk_change",
            "observation_period": {"baseline_days": 60, "recent_days": 30},
            "living_zone": {"cluster_count": 2},
            "mileage_baseline_score": 88.0,
            "senior_safe_mileage_score": 58.5,
            "risk_change_score": 91.2,
            "policy_candidate": {
                "candidate_id": "policy_v1",
                "weights": {
                    "w_mileage": 0.35,
                    "w_in_zone": 0.35,
                    "w_out_zone_safe": 0.15,
                    "w_out_zone_change": 0.15,
                },
                "thresholds": {"care_threshold": 80},
            },
            "care_decision": "예방 케어",
            "reason_codes": ["LOW_MILEAGE_RISK_CHANGE"],
            "ab_comparison": {
                "baseline_detected": False,
                "proposed_detected": True,
                "baseline_score": 88.0,
                "proposed_score": 58.5,
            },
            "agent_validation": {"passed": True, "validation_pass_rate": 0.97},
            "llm_report": {"request_features": {"customer_id": "cust_011"}},
            "privacy_filtered_features": {"persona_type": "recent_outer_risk_change"},
        }

        with self.assertRaisesRegex(ValueError, "forbidden external API fields"):
            validate_customer_decision_snapshot(snapshot)

    def test_agent_validation_pipeline_result_schema_covers_full_agent_loop(self) -> None:
        checks = tuple(
            AgentValidationCheckResult(
                agent_id=agent_id,
                status=AgentStatus.SUCCEEDED,
                passed=True,
                validation={"passed": True, "evidence_codes": [f"{agent_id.upper()}_PASS"]},
                metrics={"customer_count": 30} if agent_id == "evaluation_agent" else {},
                artifacts=(
                    AgentArtifact(
                        artifact_id=AGENT_REGISTRY[agent_id].produces[0],
                        artifact_type=ArtifactType.JSON,
                        path=f"data/fixtures/{AGENT_REGISTRY[agent_id].produces[0]}",
                    ),
                )
                if AGENT_REGISTRY[agent_id].produces
                else (),
                reason_codes=(f"{agent_id.upper()}_VALIDATED",),
                privacy_filtered_features={"customer_count": 30} if agent_id == "report_agent" else {},
            )
            for agent_id in REQUIRED_AGENT_IDS
        )
        pipeline_result = AgentValidationPipelineResult(
            run_id="agent-validation-schema-test",
            checks=checks,
            critic_review={"verdict": "pass", "findings": []},
            artifacts=(
                AgentArtifact(
                    artifact_id="agent_validation_pipeline.json",
                    artifact_type=ArtifactType.JSON,
                    path="data/fixtures/agent_validation_pipeline.json",
                ),
            ),
        )

        encoded = json.dumps(pipeline_result.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["schema_version"], AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION)
        self.assertEqual(tuple(decoded["required_agent_ids"]), REQUIRED_AGENT_IDS)
        self.assertEqual(len(decoded["checks"]), 8)
        self.assertEqual(decoded["summary"]["total_agent_count"], 8)
        self.assertEqual(decoded["summary"]["validation_pass_rate"], 1.0)
        self.assertTrue(decoded["summary"]["passed"])
        self.assertEqual(decoded["approval_gate_thresholds"]["agent_validation_pass_rate_minimum"], 0.95)
        validate_agent_validation_pipeline_result(decoded)

    def test_agent_validation_pipeline_result_rejects_missing_agent_and_summary_mismatch(self) -> None:
        checks = tuple(
            AgentValidationCheckResult(
                agent_id=agent_id,
                status=AgentStatus.SUCCEEDED,
                passed=True,
                validation={"passed": True},
            )
            for agent_id in REQUIRED_AGENT_IDS[:-1]
        )

        with self.assertRaisesRegex(ValueError, "cover every required agent"):
            AgentValidationPipelineResult(
                run_id="agent-validation-missing-agent-test",
                checks=checks,
            ).validate()

        valid_payload = AgentValidationPipelineResult(
            run_id="agent-validation-summary-test",
            checks=tuple(
                AgentValidationCheckResult(
                    agent_id=agent_id,
                    status=AgentStatus.SUCCEEDED,
                    passed=True,
                    validation={"passed": True},
                )
                for agent_id in REQUIRED_AGENT_IDS
            ),
        ).to_dict()
        valid_payload["summary"] = {**valid_payload["summary"], "passed_agent_count": 7}

        with self.assertRaisesRegex(ValueError, "summary does not match checks"):
            validate_agent_validation_pipeline_result(valid_payload)

    def test_agent_validation_pipeline_result_rejects_forbidden_api_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden external API fields"):
            AgentValidationCheckResult(
                agent_id="report_agent",
                status=AgentStatus.SUCCEEDED,
                passed=True,
                validation={"passed": True},
                privacy_filtered_features={"trip_id": "raw-trip-001"},
            ).validate()

    def test_execute_agent_pipeline_runs_sequentially_and_passes_upstream_result(self) -> None:
        spec = build_orchestrator_spec("sequential-test-run")
        calls: list[AgentInputPayload] = []
        agents = {
            agent_id: RecordingAgent(metadata, calls)
            for agent_id, metadata in spec.registry.items()
        }

        execution = execute_agent_pipeline(spec, agents)

        self.assertTrue(execution.succeeded)
        self.assertEqual(tuple(result.status for result in execution.results), (AgentStatus.SUCCEEDED,) * 8)
        self.assertEqual([payload.agent_id for payload in calls], list(REQUIRED_AGENT_IDS))
        self.assertEqual(calls[0].parameters, {})

        second_payload = calls[1]
        self.assertEqual(second_payload.upstream_results, (spec.steps[0].step_id,))
        self.assertIn(spec.steps[0].step_id, second_payload.parameters["upstream_results"])
        self.assertEqual(
            second_payload.parameters["upstream_results"][spec.steps[0].step_id]["metadata"]["agent_id"],
            "persona_agent",
        )
        self.assertEqual(second_payload.shared_state.completed_agents, ("persona_agent",))
        self.assertEqual(second_payload.shared_state.agent_statuses["persona_agent"], "succeeded")
        self.assertEqual(second_payload.shared_state.metrics["persona_agent"], {})
        self.assertEqual(
            second_payload.shared_state.artifacts["persona_templates.yaml"]["summary"]["agent_id"],
            "persona_agent",
        )
        report_output = execution.get_result("report_agent").output_payload
        self.assertIsNotNone(report_output)
        assert report_output is not None
        report_state = report_output.shared_state
        self.assertEqual(report_state.completed_agents, REQUIRED_AGENT_IDS)
        self.assertIn("report_agent", report_state.metrics)
        self.assertIn("report_agent", report_state.decisions)
        self.assertIn("report_agent", report_state.reason_codes)
        self.assertIn("report_agent", report_state.validation)
        self.assertGreaterEqual(execution.get_result("persona_agent").duration_ms, 0)
        self.assertIsNotNone(execution.get_result("report_agent").completed_at)

    def test_execute_agent_pipeline_propagates_required_artifacts_between_ordered_agents(self) -> None:
        spec = build_orchestrator_spec("artifact-propagation-test-run")
        calls: list[AgentInputPayload] = []
        agents = {
            agent_id: ProducingAgent(metadata, calls)
            for agent_id, metadata in spec.registry.items()
        }

        execution = execute_agent_pipeline(spec, agents)

        self.assertTrue(execution.succeeded)
        calls_by_agent = {payload.agent_id: payload for payload in calls}
        self.assertEqual(
            [artifact.artifact_id for artifact in calls_by_agent["scenario_agent"].input_artifacts],
            ["persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"],
        )
        self.assertEqual(
            [artifact.artifact_id for artifact in calls_by_agent["ai_simulation_agent"].input_artifacts],
            ["scenario_config.json"],
        )
        self.assertEqual(
            [artifact.artifact_id for artifact in calls_by_agent["consistency_check_agent"].input_artifacts],
            ["senior_trip_logs.csv", "simulation_manifest.json"],
        )
        self.assertEqual(
            [artifact.artifact_id for artifact in calls_by_agent["critic_agent"].input_artifacts],
            ["ab_test_results.csv", "candidate_rules.json"],
        )

    def test_execute_agent_pipeline_records_errors_and_skips_blocked_downstream_agents(self) -> None:
        spec = build_orchestrator_spec("failure-test-run")
        calls: list[AgentInputPayload] = []
        agents = {
            agent_id: RecordingAgent(metadata, calls, fail=(agent_id == "ai_simulation_agent"))
            for agent_id, metadata in spec.registry.items()
        }

        execution = execute_agent_pipeline(spec, agents)

        self.assertTrue(execution.failed)
        simulation_result = execution.get_result("ai_simulation_agent")
        consistency_result = execution.get_result("consistency_check_agent")

        self.assertEqual(simulation_result.status, AgentStatus.FAILED)
        self.assertRegex(simulation_result.errors[0], "planned failure")
        self.assertIsNotNone(simulation_result.completed_at)
        self.assertGreaterEqual(simulation_result.duration_ms, 0)
        self.assertEqual(consistency_result.status, AgentStatus.SKIPPED)
        self.assertIn("dependency step_03_ai_simulation_agent ended with status=failed", consistency_result.warnings)
        self.assertNotIn("consistency_check_agent", [payload.agent_id for payload in calls])

    def test_execute_agent_pipeline_fails_missing_agent_implementation_and_skips_dependents(self) -> None:
        spec = build_orchestrator_spec("missing-agent-test-run")
        calls: list[AgentInputPayload] = []
        agents = {
            agent_id: RecordingAgent(metadata, calls)
            for agent_id, metadata in spec.registry.items()
            if agent_id != "scenario_agent"
        }

        execution = execute_agent_pipeline(spec, agents)

        self.assertTrue(execution.failed)
        scenario_result = execution.get_result("scenario_agent")
        simulation_result = execution.get_result("ai_simulation_agent")
        self.assertEqual(scenario_result.status, AgentStatus.FAILED)
        self.assertEqual(scenario_result.errors, ("agent implementation not registered: scenario_agent",))
        self.assertEqual(simulation_result.status, AgentStatus.SKIPPED)
        self.assertIn("dependency step_02_scenario_agent ended with status=failed", simulation_result.warnings)
        self.assertEqual([payload.agent_id for payload in calls], ["persona_agent"])

    def test_default_agent_map_wires_all_required_concrete_agents(self) -> None:
        agents = build_default_agent_map()

        self.assertEqual(tuple(agents), REQUIRED_AGENT_IDS)
        for agent_id in REQUIRED_AGENT_IDS:
            self.assertEqual(agents[agent_id].metadata.agent_id, agent_id)

    def test_execute_default_agent_pipeline_invokes_all_required_agents_in_expected_sequence(self) -> None:
        execution = execute_default_agent_pipeline("default-integration-test-run")

        self.assertTrue(execution.succeeded)
        self.assertEqual(tuple(result.metadata.agent_id for result in execution.results), REQUIRED_AGENT_IDS)
        self.assertEqual(tuple(result.status for result in execution.results), (AgentStatus.SUCCEEDED,) * 8)
        self.assertEqual(
            execution.get_result("report_agent").output_payload.metrics["customer_count"],
            30,
        )


if __name__ == "__main__":
    unittest.main()

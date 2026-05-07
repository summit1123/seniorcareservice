"""Orchestrator contract and runner for the Senior Safe Mileage agent loop."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any

from src.agents.contracts import (
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentSharedState,
    AgentStatus,
    REQUIRED_AGENT_IDS,
    SeniorMileageAgent,
    utc_now_iso,
)


DEFAULT_RUN_ID = "senior-safe-mileage-local-run"


AgentReference = str | AgentRole | AgentMetadata
AgentMap = Mapping[str, SeniorMileageAgent]


def _normalize_agent_lookup_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


class AgentRegistry(Mapping[str, AgentMetadata]):
    """Ordered agent metadata registry with id, display-name, and role lookup."""

    def __init__(self, agents: Iterable[AgentMetadata] = ()) -> None:
        self._agents: dict[str, AgentMetadata] = {}
        self._name_index: dict[str, str] = {}
        self._role_index: dict[AgentRole, str] = {}
        for metadata in agents:
            self.register(metadata)

    def __getitem__(self, agent_id: str) -> AgentMetadata:
        return self._agents[agent_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._agents)

    def __len__(self) -> int:
        return len(self._agents)

    def register(self, metadata: AgentMetadata, *, replace: bool = False) -> None:
        if metadata.agent_id in self._agents and not replace:
            raise ValueError(f"agent_id already registered: {metadata.agent_id}")
        existing_for_role = self._role_index.get(metadata.role)
        if existing_for_role and existing_for_role != metadata.agent_id and not replace:
            raise ValueError(f"agent role already registered: {metadata.role.value}")

        if replace and metadata.agent_id in self._agents:
            old = self._agents[metadata.agent_id]
            self._name_index.pop(_normalize_agent_lookup_key(old.display_name), None)
            if self._role_index.get(old.role) == old.agent_id:
                self._role_index.pop(old.role, None)

        self._agents[metadata.agent_id] = metadata
        self._name_index[_normalize_agent_lookup_key(metadata.agent_id)] = metadata.agent_id
        self._name_index[_normalize_agent_lookup_key(metadata.display_name)] = metadata.agent_id
        self._role_index[metadata.role] = metadata.agent_id

    def resolve(self, reference: AgentReference) -> AgentMetadata:
        if isinstance(reference, AgentMetadata):
            if reference.agent_id not in self._agents:
                self.register(reference)
            return self._agents[reference.agent_id]
        if isinstance(reference, AgentRole):
            return self.get_by_type(reference)

        key = _normalize_agent_lookup_key(reference)
        if key in self._name_index:
            return self._agents[self._name_index[key]]
        try:
            return self.get_by_type(AgentRole(key))
        except ValueError:
            pass
        raise KeyError(f"unknown agent reference: {reference}")

    def get_by_name(self, name: str) -> AgentMetadata:
        return self.resolve(name)

    def get_by_type(self, role: AgentRole | str) -> AgentMetadata:
        role_value = role if isinstance(role, AgentRole) else AgentRole(_normalize_agent_lookup_key(role))
        try:
            return self._agents[self._role_index[role_value]]
        except KeyError as exc:
            raise KeyError(f"unknown agent type: {role_value.value}") from exc

    def copy(self) -> "AgentRegistry":
        return AgentRegistry(self._agents.values())


_DEFAULT_AGENT_METADATA: tuple[AgentMetadata, ...] = (
    AgentMetadata(
        agent_id="persona_agent",
        role=AgentRole.PERSONA,
        display_name="Persona Agent",
        description="Defines six senior driver personas and edge cases.",
        produces=("persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"),
    ),
    AgentMetadata(
        agent_id="scenario_agent",
        role=AgentRole.SCENARIO,
        display_name="Scenario Agent",
        description="Builds 60-day baseline and 30-day recent behavior-change scenarios.",
        consumes=("persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"),
        produces=("scenario_config.json",),
    ),
    AgentMetadata(
        agent_id="ai_simulation_agent",
        role=AgentRole.SIMULATION,
        display_name="AI Simulation Agent",
        description="Generates reproducible synthetic 90-day trip logs.",
        consumes=("scenario_config.json",),
        produces=("senior_trip_logs.csv", "simulation_manifest.json"),
    ),
    AgentMetadata(
        agent_id="consistency_check_agent",
        role=AgentRole.CONSISTENCY_CHECK,
        display_name="Consistency Check Agent",
        description="Checks trip coordinate, distance, time, and risk-event consistency.",
        consumes=("senior_trip_logs.csv", "simulation_manifest.json"),
        produces=("validation_report.md",),
    ),
    AgentMetadata(
        agent_id="policy_search_agent",
        role=AgentRole.POLICY_SEARCH,
        display_name="Policy Search Agent",
        description="Proposes Senior Safe Mileage Score weights and thresholds.",
        consumes=("validation_report.md", "model_feature_table.csv"),
        produces=("candidate_rules.json", "policy_candidate_scores.csv"),
    ),
    AgentMetadata(
        agent_id="evaluation_agent",
        role=AgentRole.EVALUATION,
        display_name="Evaluation Agent",
        description="Compares baseline mileage scoring with proposed integrated scoring.",
        consumes=("candidate_rules.json", "decision_table.csv"),
        produces=("ab_test_results.csv", "evaluation_view_model.json"),
    ),
    AgentMetadata(
        agent_id="critic_agent",
        role=AgentRole.CRITIC,
        display_name="Critic Agent",
        description="Reviews unfair decisions, exaggerated claims, and misclassifications.",
        consumes=("ab_test_results.csv", "candidate_rules.json"),
        produces=("rule_review.md", "rule_review.json"),
    ),
    AgentMetadata(
        agent_id="report_agent",
        role=AgentRole.REPORT,
        display_name="Report Agent",
        description="Creates insurer-facing reports with XAI reason codes and LLM fallback support.",
        consumes=("evaluation_view_model.json", "rule_review.json"),
        produces=("simulation_summary.md", "simulation_summary.json"),
        uses_llm=True,
        requires_privacy_filter=True,
    ),
)


AGENT_REGISTRY = AgentRegistry(_DEFAULT_AGENT_METADATA)


DEFAULT_AGENT_ORDER = tuple(REQUIRED_AGENT_IDS)


def build_default_agent_map() -> dict[str, SeniorMileageAgent]:
    """Instantiate the concrete local agents required by the product loop."""

    from src.agents.ai_simulation_agent import AISimulationAgent
    from src.agents.consistency_check_agent import ConsistencyCheckAgent
    from src.agents.critic_agent import CriticAgent
    from src.agents.evaluation_agent import EvaluationAgent
    from src.agents.persona_agent import PersonaAgent
    from src.agents.policy_search_agent import PolicySearchAgent
    from src.agents.report_agent import ReportAgent
    from src.agents.scenario_agent import ScenarioAgent

    persona_agent = PersonaAgent()
    return {
        "persona_agent": persona_agent,
        "scenario_agent": ScenarioAgent(persona_agent=persona_agent),
        "ai_simulation_agent": AISimulationAgent(),
        "consistency_check_agent": ConsistencyCheckAgent(),
        "policy_search_agent": PolicySearchAgent(),
        "evaluation_agent": EvaluationAgent(),
        "critic_agent": CriticAgent(),
        "report_agent": ReportAgent(),
    }


def execute_default_agent_pipeline(
    run_id: str = DEFAULT_RUN_ID,
    *,
    agent_refs: Iterable[AgentReference] | None = None,
    registry: AgentRegistry | None = None,
    agents: AgentMap | None = None,
) -> PipelineExecutionResult:
    """Build the standard spec and execute all required local agents in order."""

    spec = build_orchestrator_spec(run_id=run_id, agent_refs=agent_refs, registry=registry)
    return execute_agent_pipeline(spec, agents or build_default_agent_map())


@dataclass(frozen=True)
class OrchestratorStep:
    step_id: str
    agent_id: str
    depends_on: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    output_artifacts: tuple[str, ...] = ()

    def to_input_payload(
        self,
        run_id: str = DEFAULT_RUN_ID,
        input_artifacts: tuple[AgentArtifact, ...] = (),
        parameters: dict[str, Any] | None = None,
        privacy_filtered_features: dict[str, Any] | None = None,
        shared_state: AgentSharedState | None = None,
    ) -> AgentInputPayload:
        return AgentInputPayload(
            run_id=run_id,
            agent_id=self.agent_id,
            input_artifacts=input_artifacts,
            parameters=parameters or {},
            privacy_filtered_features=privacy_filtered_features or {},
            shared_state=shared_state or AgentSharedState(),
            upstream_results=self.depends_on,
        )


@dataclass(frozen=True)
class OrchestratorSpec:
    run_id: str = DEFAULT_RUN_ID
    registry: AgentRegistry = field(default_factory=lambda: AGENT_REGISTRY.copy())
    steps: tuple[OrchestratorStep, ...] = field(default_factory=lambda: build_default_steps())
    approval_gates: dict[str, Any] = field(default_factory=lambda: {
        "risk_change_recall": {"target_customers": 5, "minimum_detected": 4},
        "false_positive_limit": {"non_target_customers": 25, "maximum_false_positives": 3},
        "overall_misclassification_limit": 4,
        "agent_validation_pass_rate_minimum": 0.95,
    })

    def validate(self) -> None:
        missing = [agent_id for agent_id in REQUIRED_AGENT_IDS if agent_id not in self.registry]
        if missing:
            raise ValueError(f"orchestrator registry missing required agents: {missing}")

        step_agent_ids = tuple(step.agent_id for step in self.steps)
        required_roles = tuple(self.registry[agent_id].role for agent_id in REQUIRED_AGENT_IDS)
        step_required_roles = tuple(
            self.registry[agent_id].role
            for agent_id in step_agent_ids
            if agent_id in self.registry and self.registry[agent_id].role in required_roles
        )
        if step_required_roles != required_roles:
            raise ValueError(f"orchestrator steps must follow required order: {REQUIRED_AGENT_IDS}")

        known_steps: set[str] = set()
        for step in self.steps:
            if step.agent_id not in self.registry:
                raise ValueError(f"step {step.step_id} references unknown agent_id={step.agent_id}")
            unresolved = sorted(set(step.depends_on) - known_steps)
            if unresolved:
                raise ValueError(f"step {step.step_id} has unresolved dependencies: {unresolved}")
            known_steps.add(step.step_id)

    def initial_results(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for step in self.steps:
            metadata = self.registry[step.agent_id]
            payload = step.to_input_payload(run_id=self.run_id)
            output = AgentOutputPayload(run_id=self.run_id, agent_id=step.agent_id, messages=("contract placeholder",))
            rows.append(
                {
                    "step_id": step.step_id,
                    "agent_id": step.agent_id,
                    "status": AgentStatus.PENDING.value,
                    "metadata": metadata.to_dict(),
                    "input_payload": payload.to_dict(),
                    "output_payload_schema": output.to_dict(),
                }
            )
        return rows


@dataclass(frozen=True)
class PipelineExecutionResult:
    """Full sequential execution trace for one orchestrator run."""

    run_id: str
    status: AgentStatus
    results: tuple[AgentExecutionResult, ...]

    @property
    def succeeded(self) -> bool:
        return self.status == AgentStatus.SUCCEEDED

    @property
    def failed(self) -> bool:
        return self.status == AgentStatus.FAILED

    def get_result(self, agent_id: str) -> AgentExecutionResult:
        for result in self.results:
            if result.metadata.agent_id == agent_id:
                return result
        raise KeyError(f"agent result not found: {agent_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "agent_statuses": [
                {
                    "agent_id": result.metadata.agent_id,
                    "display_name": result.metadata.display_name,
                    "status": result.status.value,
                    "started_at": result.started_at,
                    "completed_at": result.completed_at,
                    "duration_ms": result.duration_ms,
                    "errors": list(result.errors),
                }
                for result in self.results
            ],
            "results": [result.to_dict() for result in self.results],
        }


def execute_agent_pipeline(spec: OrchestratorSpec, agents: AgentMap) -> PipelineExecutionResult:
    """Run orchestrator steps in order and pass each result to the next step.

    The runner is intentionally small and framework-neutral.  Concrete agents can
    be plain Python classes or adapters around LangGraph/OpenAI Agents SDK nodes
    as long as they expose ``run(AgentInputPayload)``.
    """

    spec.validate()
    results_by_step: dict[str, AgentExecutionResult] = {}
    artifact_ledger: dict[str, AgentArtifact] = {}
    shared_state = AgentSharedState()
    ordered_results: list[AgentExecutionResult] = []

    for step in spec.steps:
        metadata = spec.registry[step.agent_id]
        blocked_errors = _dependency_errors(step, results_by_step)
        if blocked_errors:
            result = _build_skipped_result(
                spec.run_id,
                step,
                metadata,
                blocked_errors,
                artifact_ledger,
                results_by_step,
                shared_state,
            )
            results_by_step[step.step_id] = result
            ordered_results.append(result)
            continue

        payload = _build_step_payload(spec.run_id, step, artifact_ledger, results_by_step, shared_state)
        agent = agents.get(step.agent_id)
        if agent is None:
            result = _build_failed_result(
                spec.run_id,
                metadata,
                payload,
                started_at=utc_now_iso(),
                start_time=perf_counter(),
                errors=(f"agent implementation not registered: {step.agent_id}",),
            )
        else:
            result = _run_agent(agent, spec.run_id, metadata, payload)

        result.validate()
        if result.status == AgentStatus.SUCCEEDED and result.output_payload:
            shared_state = _merge_output_into_shared_state(shared_state, metadata, result.output_payload)
            result = replace(result, output_payload=replace(result.output_payload, shared_state=shared_state))
            result.validate()
        results_by_step[step.step_id] = result
        ordered_results.append(result)
        if result.output_payload:
            for artifact in result.output_payload.output_artifacts:
                artifact_ledger[artifact.artifact_id] = artifact
                if artifact.path:
                    artifact_ledger[artifact.path] = artifact

    pipeline_status = AgentStatus.SUCCEEDED
    if any(result.status == AgentStatus.FAILED for result in ordered_results):
        pipeline_status = AgentStatus.FAILED
    elif any(result.status == AgentStatus.SKIPPED for result in ordered_results):
        pipeline_status = AgentStatus.SKIPPED

    return PipelineExecutionResult(
        run_id=spec.run_id,
        status=pipeline_status,
        results=tuple(ordered_results),
    )


def _run_agent(
    agent: SeniorMileageAgent,
    run_id: str,
    metadata: AgentMetadata,
    payload: AgentInputPayload,
) -> AgentExecutionResult:
    started_at = utc_now_iso()
    start_time = perf_counter()
    try:
        result = agent.run(payload)
    except Exception as exc:  # pragma: no cover - concrete exception is tested.
        return _build_failed_result(
            run_id,
            metadata,
            payload,
            started_at=started_at,
            start_time=start_time,
            errors=(f"{exc.__class__.__name__}: {exc}",),
        )

    completed_at = result.completed_at or utc_now_iso()
    duration_ms = result.duration_ms
    if duration_ms is None:
        duration_ms = max(0, int((perf_counter() - start_time) * 1000))
    return AgentExecutionResult(
        run_id=run_id,
        metadata=metadata,
        status=result.status,
        input_payload=payload,
        output_payload=result.output_payload,
        started_at=result.started_at or started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        warnings=result.warnings,
        errors=result.errors,
    )


def _build_step_payload(
    run_id: str,
    step: OrchestratorStep,
    artifact_ledger: Mapping[str, AgentArtifact],
    results_by_step: Mapping[str, AgentExecutionResult],
    shared_state: AgentSharedState,
) -> AgentInputPayload:
    input_artifacts = _resolve_input_artifacts(step, artifact_ledger)
    upstream_result_rows = {
        dependency: results_by_step[dependency].to_dict()
        for dependency in step.depends_on
        if dependency in results_by_step
    }
    return step.to_input_payload(
        run_id=run_id,
        input_artifacts=input_artifacts,
        parameters={"upstream_results": upstream_result_rows} if upstream_result_rows else {},
        shared_state=shared_state,
    )


def _merge_output_into_shared_state(
    previous: AgentSharedState,
    metadata: AgentMetadata,
    output: AgentOutputPayload,
) -> AgentSharedState:
    agent_id = metadata.agent_id
    artifacts = dict(previous.artifacts)
    for artifact in output.output_artifacts:
        artifact_row = artifact.to_dict()
        artifacts[artifact.artifact_id] = artifact_row
        if artifact.path:
            artifacts[artifact.path] = artifact_row

    metrics = dict(previous.metrics)
    metrics[agent_id] = dict(output.metrics)

    decisions = dict(previous.decisions)
    decisions[agent_id] = dict(output.decisions)

    reason_codes = dict(previous.reason_codes)
    reason_codes[agent_id] = tuple(output.reason_codes)

    validation = dict(previous.validation)
    validation[agent_id] = dict(output.validation)

    llm_reports = dict(previous.llm_reports)
    if output.llm_report:
        llm_reports[agent_id] = dict(output.llm_report)

    privacy_filtered_features = dict(previous.privacy_filtered_features)
    if output.llm_report.get("request_features"):
        privacy_filtered_features[agent_id] = dict(output.llm_report["request_features"])

    agent_statuses = dict(previous.agent_statuses)
    agent_statuses[agent_id] = AgentStatus.SUCCEEDED.value

    completed_agents = tuple(
        dict.fromkeys(
            (
                *previous.completed_agents,
                agent_id,
            )
        )
    )

    state = AgentSharedState(
        completed_agents=completed_agents,
        agent_statuses=agent_statuses,
        artifacts=artifacts,
        metrics=metrics,
        decisions=decisions,
        reason_codes=reason_codes,
        validation=validation,
        llm_reports=llm_reports,
        privacy_filtered_features=privacy_filtered_features,
    )
    state.validate()
    return state


def _resolve_input_artifacts(
    step: OrchestratorStep,
    artifact_ledger: Mapping[str, AgentArtifact],
) -> tuple[AgentArtifact, ...]:
    artifacts: list[AgentArtifact] = []
    seen: set[str] = set()
    for artifact_name in step.required_artifacts:
        artifact = artifact_ledger.get(artifact_name)
        if not artifact:
            continue
        artifact_key = artifact.artifact_id
        if artifact_key in seen:
            continue
        artifacts.append(artifact)
        seen.add(artifact_key)
    return tuple(artifacts)


def _dependency_errors(
    step: OrchestratorStep,
    results_by_step: Mapping[str, AgentExecutionResult],
) -> tuple[str, ...]:
    errors: list[str] = []
    for dependency in step.depends_on:
        dependency_result = results_by_step.get(dependency)
        if dependency_result is None:
            errors.append(f"dependency not executed: {dependency}")
        elif dependency_result.status != AgentStatus.SUCCEEDED:
            errors.append(
                f"dependency {dependency} ended with status={dependency_result.status.value}"
            )
    return tuple(errors)


def _build_failed_result(
    run_id: str,
    metadata: AgentMetadata,
    payload: AgentInputPayload,
    *,
    started_at: str,
    start_time: float,
    errors: tuple[str, ...],
) -> AgentExecutionResult:
    return AgentExecutionResult(
        run_id=run_id,
        metadata=metadata,
        status=AgentStatus.FAILED,
        input_payload=payload,
        started_at=started_at,
        completed_at=utc_now_iso(),
        duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
        errors=errors,
    )


def _build_skipped_result(
    run_id: str,
    step: OrchestratorStep,
    metadata: AgentMetadata,
    errors: tuple[str, ...],
    artifact_ledger: Mapping[str, AgentArtifact],
    results_by_step: Mapping[str, AgentExecutionResult],
    shared_state: AgentSharedState,
) -> AgentExecutionResult:
    started_at = utc_now_iso()
    payload = _build_step_payload(run_id, step, artifact_ledger, results_by_step, shared_state)
    return AgentExecutionResult(
        run_id=run_id,
        metadata=metadata,
        status=AgentStatus.SKIPPED,
        input_payload=payload,
        started_at=started_at,
        completed_at=started_at,
        duration_ms=0,
        warnings=errors,
    )


def build_pipeline_steps(
    agent_refs: Iterable[AgentReference],
    *,
    registry: AgentRegistry | None = None,
) -> tuple[OrchestratorStep, ...]:
    agent_registry = registry or AGENT_REGISTRY
    steps: list[OrchestratorStep] = []
    previous_step_id: str | None = None
    for index, agent_ref in enumerate(agent_refs, start=1):
        metadata = agent_registry.resolve(agent_ref)
        step = OrchestratorStep(
            step_id=f"step_{index:02d}_{metadata.agent_id}",
            agent_id=metadata.agent_id,
            depends_on=(previous_step_id,) if previous_step_id else (),
            required_artifacts=metadata.consumes,
            output_artifacts=metadata.produces,
        )
        steps.append(step)
        previous_step_id = step.step_id
    return tuple(steps)


def build_default_steps(registry: AgentRegistry | None = None) -> tuple[OrchestratorStep, ...]:
    return build_pipeline_steps(DEFAULT_AGENT_ORDER, registry=registry)


def build_orchestrator_spec(
    run_id: str = DEFAULT_RUN_ID,
    agent_refs: Iterable[AgentReference] | None = None,
    registry: AgentRegistry | None = None,
) -> OrchestratorSpec:
    agent_registry = registry or AGENT_REGISTRY.copy()
    steps = build_pipeline_steps(agent_refs or DEFAULT_AGENT_ORDER, registry=agent_registry)
    spec = OrchestratorSpec(run_id=run_id, registry=agent_registry, steps=steps)
    spec.validate()
    return spec

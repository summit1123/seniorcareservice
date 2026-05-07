"""Shared contracts for the Senior Safe Mileage agent loop.

The contracts are intentionally framework-neutral.  LangGraph, OpenAI Agents
SDK, or plain Python agents can all implement this surface while preserving the
same metadata, payload, and execution result schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable


CONTRACT_SCHEMA_VERSION = "senior-safe-mileage-agent-contract/v1"
AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION = "senior-safe-mileage-agent-validation-pipeline/v1"

REQUIRED_AGENT_IDS = (
    "persona_agent",
    "scenario_agent",
    "ai_simulation_agent",
    "consistency_check_agent",
    "policy_search_agent",
    "evaluation_agent",
    "critic_agent",
    "report_agent",
)

FORBIDDEN_EXTERNAL_API_FIELDS = frozenset(
    {
        "customer_id",
        "driver_id",
        "customer_name",
        "name",
        "phone_number",
        "phone",
        "address",
        "home_address",
        "vehicle_number",
        "license_plate",
        "car_number",
        "start_lat",
        "start_lon",
        "start_gps_x",
        "start_gps_y",
        "end_lat",
        "end_lon",
        "end_gps_x",
        "end_gps_y",
        "latitude",
        "longitude",
        "gps",
        "raw_gps",
        "trip_id",
        "raw_trip_id",
        "trip_start_time",
        "trip_end_time",
    }
)

ALLOWED_CARE_DECISIONS = frozenset({"우대", "기본", "예방 케어", "additional_reward", "maintain", "preventive_care"})

REQUIRED_CUSTOMER_SNAPSHOT_FIELDS = frozenset(
    {
        "customer_id",
        "persona_type",
        "observation_period",
        "living_zone",
        "mileage_baseline_score",
        "senior_safe_mileage_score",
        "risk_change_score",
        "policy_candidate",
        "care_decision",
        "reason_codes",
        "ab_comparison",
        "agent_validation",
        "llm_report",
        "privacy_filtered_features",
    }
)

REQUIRED_SHARED_STATE_FIELDS = frozenset(
    {
        "completed_agents",
        "agent_statuses",
        "artifacts",
        "metrics",
        "decisions",
        "reason_codes",
        "validation",
        "llm_reports",
        "privacy_filtered_features",
    }
)

REQUIRED_AGENT_VALIDATION_CHECK_FIELDS = frozenset(
    {
        "agent_id",
        "status",
        "passed",
        "validation",
        "metrics",
        "artifacts",
        "reason_codes",
        "warnings",
        "errors",
    }
)

REQUIRED_AGENT_VALIDATION_PIPELINE_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "generated_at",
        "required_agent_ids",
        "checks",
        "summary",
        "approval_gate_thresholds",
        "critic_review",
        "artifacts",
    }
)

REQUIRED_AGENT_VALIDATION_PIPELINE_SUMMARY_FIELDS = frozenset(
    {
        "total_agent_count",
        "passed_agent_count",
        "failed_agent_count",
        "validation_pass_rate",
        "passed",
        "failed_agents",
    }
)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentRole(str, Enum):
    PERSONA = "persona"
    SCENARIO = "scenario"
    SIMULATION = "simulation"
    CONSISTENCY_CHECK = "consistency_check"
    POLICY_SEARCH = "policy_search"
    EVALUATION = "evaluation"
    CRITIC = "critic"
    REPORT = "report"


class ArtifactType(str, Enum):
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"
    TABLE = "table"
    WEB_VIEW_MODEL = "web_view_model"


@dataclass(frozen=True)
class AgentMetadata:
    agent_id: str
    role: AgentRole
    display_name: str
    description: str
    version: str = CONTRACT_SCHEMA_VERSION
    uses_llm: bool = False
    requires_privacy_filter: bool = False
    input_schema: str = "AgentInputPayload"
    output_schema: str = "AgentOutputPayload"
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["role"] = self.role.value
        return row


@dataclass(frozen=True)
class AgentArtifact:
    artifact_id: str
    artifact_type: ArtifactType
    path: str | None = None
    rows: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["artifact_type"] = self.artifact_type.value
        return row


@dataclass(frozen=True)
class ObservationPeriod:
    baseline_days: int = 60
    recent_days: int = 30

    @property
    def total_days(self) -> int:
        return self.baseline_days + self.recent_days

    def validate(self) -> None:
        if self.baseline_days != 60 or self.recent_days != 30:
            raise ValueError("observation_period must be baseline 60 days and recent 30 days")

    def to_dict(self) -> dict[str, int]:
        self.validate()
        return {
            "baseline_days": self.baseline_days,
            "recent_days": self.recent_days,
            "total_days": self.total_days,
        }


@dataclass(frozen=True)
class PolicyCandidate:
    candidate_id: str
    weights: dict[str, float]
    thresholds: dict[str, Any]
    rationale: str = ""

    def validate(self) -> None:
        if not self.candidate_id:
            raise ValueError("policy_candidate.candidate_id is required")
        required_weights = {"w_mileage", "w_in_zone", "w_out_zone_safe", "w_out_zone_change"}
        missing = sorted(required_weights - set(self.weights))
        if missing:
            raise ValueError(f"policy_candidate missing weights: {missing}")
        for key in required_weights:
            weight = float(self.weights[key])
            if not 0 <= weight <= 1:
                raise ValueError(f"policy_candidate weight must be between 0 and 1: {key}={weight}")
        if "care_threshold" not in self.thresholds:
            raise ValueError("policy_candidate.thresholds must include care_threshold")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "candidate_id": self.candidate_id,
            "weights": self.weights,
            "thresholds": self.thresholds,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ABComparison:
    baseline_detected: bool
    proposed_detected: bool
    baseline_score: float
    proposed_score: float
    metrics: dict[str, float | int | bool] = field(default_factory=dict)

    def validate(self) -> None:
        assert_score_range("ab_comparison.baseline_score", self.baseline_score)
        assert_score_range("ab_comparison.proposed_score", self.proposed_score)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "baseline_detected": self.baseline_detected,
            "proposed_detected": self.proposed_detected,
            "baseline_score": self.baseline_score,
            "proposed_score": self.proposed_score,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class AgentValidationSummary:
    passed: bool
    validation_pass_rate: float
    critic_findings: tuple[str, ...] = ()
    failed_agents: tuple[str, ...] = ()

    def validate(self) -> None:
        if not 0 <= self.validation_pass_rate <= 1:
            raise ValueError("agent_validation.validation_pass_rate must be between 0 and 1")
        if self.passed and self.failed_agents:
            raise ValueError("agent_validation cannot pass with failed_agents")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "passed": self.passed,
            "validation_pass_rate": self.validation_pass_rate,
            "critic_findings": list(self.critic_findings),
            "failed_agents": list(self.failed_agents),
        }


@dataclass(frozen=True)
class AgentValidationCheckResult:
    """One agent step's normalized validation result for dashboard/fixture use."""

    agent_id: str
    status: AgentStatus | str
    passed: bool
    validation: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float | int | bool] = field(default_factory=dict)
    artifacts: tuple[AgentArtifact, ...] = ()
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    privacy_filtered_features: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.agent_id not in REQUIRED_AGENT_IDS:
            raise ValueError(f"agent_validation_check.agent_id is not registered: {self.agent_id}")
        status = self.status if isinstance(self.status, AgentStatus) else AgentStatus(str(self.status))
        if self.passed and status != AgentStatus.SUCCEEDED:
            raise ValueError("agent validation check cannot pass unless status is succeeded")
        if self.passed and self.errors:
            raise ValueError("agent validation check cannot pass with errors")
        validate_privacy_filtered_features(self.privacy_filtered_features)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "agent_id": self.agent_id,
            "status": (self.status if isinstance(self.status, AgentStatus) else AgentStatus(str(self.status))).value,
            "passed": self.passed,
            "validation": self.validation,
            "metrics": self.metrics,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "reason_codes": list(self.reason_codes),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "privacy_filtered_features": self.privacy_filtered_features,
        }


@dataclass(frozen=True)
class AgentValidationPipelineResult:
    """Full Agent-in-the-loop validation pipeline result schema.

    This contract is intentionally product-level rather than framework-level:
    it captures the required Senior Safe Mileage agents, their validation
    evidence, gate thresholds, critic result, and reproducible artifacts in one
    JSON-serializable shape for the local webapp and fixtures.
    """

    run_id: str
    checks: tuple[AgentValidationCheckResult, ...]
    generated_at: str = field(default_factory=lambda: utc_now_iso())
    schema_version: str = AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION
    required_agent_ids: tuple[str, ...] = REQUIRED_AGENT_IDS
    approval_gate_thresholds: dict[str, float | int | bool] = field(
        default_factory=lambda: {
            "agent_validation_pass_rate_minimum": 0.95,
            "low_mileage_risk_change_capture_minimum": 4,
            "non_target_false_positive_limit": 3,
            "total_misclassification_limit": 4,
        }
    )
    critic_review: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[AgentArtifact, ...] = ()

    @property
    def summary(self) -> AgentValidationSummary:
        total = len(self.checks)
        passed_agent_ids = tuple(check.agent_id for check in self.checks if check.passed)
        failed_agent_ids = tuple(check.agent_id for check in self.checks if not check.passed)
        pass_rate = (len(passed_agent_ids) / total) if total else 0.0
        return AgentValidationSummary(
            passed=not failed_agent_ids and total == len(self.required_agent_ids),
            validation_pass_rate=pass_rate,
            critic_findings=tuple(self.critic_review.get("findings", ())),
            failed_agents=failed_agent_ids,
        )

    def validate(self) -> None:
        if self.schema_version != AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION:
            raise ValueError("invalid agent validation pipeline schema_version")
        if not self.run_id:
            raise ValueError("agent validation pipeline run_id is required")
        if tuple(self.required_agent_ids) != REQUIRED_AGENT_IDS:
            raise ValueError("agent validation pipeline required_agent_ids must match product agent loop")
        check_ids = tuple(check.agent_id for check in self.checks)
        if set(check_ids) != set(self.required_agent_ids):
            raise ValueError("agent validation pipeline checks must cover every required agent exactly once")
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("agent validation pipeline checks contain duplicate agent_id")
        for check in self.checks:
            check.validate()
        self.summary.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        summary = self.summary
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "required_agent_ids": list(self.required_agent_ids),
            "checks": [check.to_dict() for check in self.checks],
            "summary": {
                "total_agent_count": len(self.checks),
                "passed_agent_count": len([check for check in self.checks if check.passed]),
                "failed_agent_count": len(summary.failed_agents),
                "validation_pass_rate": summary.validation_pass_rate,
                "passed": summary.passed,
                "failed_agents": list(summary.failed_agents),
            },
            "approval_gate_thresholds": self.approval_gate_thresholds,
            "critic_review": self.critic_review,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }

    @classmethod
    def from_execution_results(
        cls,
        run_id: str,
        results: tuple[AgentExecutionResult, ...] | list[AgentExecutionResult],
        *,
        critic_review: dict[str, Any] | None = None,
        artifacts: tuple[AgentArtifact, ...] = (),
    ) -> "AgentValidationPipelineResult":
        checks = []
        for result in results:
            output = result.output_payload
            checks.append(
                AgentValidationCheckResult(
                    agent_id=result.metadata.agent_id,
                    status=result.status,
                    passed=result.status == AgentStatus.SUCCEEDED
                    and bool((output.validation if output else {}).get("passed", result.status == AgentStatus.SUCCEEDED)),
                    validation=dict(output.validation) if output else {},
                    metrics=dict(output.metrics) if output else {},
                    artifacts=tuple(output.output_artifacts) if output else (),
                    reason_codes=tuple(output.reason_codes) if output else (),
                    warnings=tuple(result.warnings),
                    errors=tuple(result.errors),
                    privacy_filtered_features=dict(output.shared_state.privacy_filtered_features.get(result.metadata.agent_id, {}))
                    if output
                    else {},
                )
            )
        return cls(
            run_id=run_id,
            checks=tuple(checks),
            critic_review=dict(critic_review or {}),
            artifacts=artifacts,
        )


@dataclass(frozen=True)
class AgentSharedState:
    """Accumulated orchestrator handoff state passed between agent steps."""

    completed_agents: tuple[str, ...] = ()
    agent_statuses: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, dict[str, float | int | bool]] = field(default_factory=dict)
    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    reason_codes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    validation: dict[str, dict[str, Any]] = field(default_factory=dict)
    llm_reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    privacy_filtered_features: dict[str, dict[str, Any]] = field(default_factory=dict)

    def validate(self) -> None:
        for agent_id, features in self.privacy_filtered_features.items():
            validate_privacy_filtered_features(features)
            if not agent_id:
                raise ValueError("shared_state privacy_filtered_features contains empty agent id")
        for agent_id, report in self.llm_reports.items():
            validate_privacy_filtered_features(report.get("request_features", {}))
            if not agent_id:
                raise ValueError("shared_state llm_reports contains empty agent id")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "completed_agents": list(self.completed_agents),
            "agent_statuses": self.agent_statuses,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "decisions": self.decisions,
            "reason_codes": {agent_id: list(codes) for agent_id, codes in self.reason_codes.items()},
            "validation": self.validation,
            "llm_reports": self.llm_reports,
            "privacy_filtered_features": self.privacy_filtered_features,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any] | None) -> "AgentSharedState":
        if not row:
            return cls()
        assert_required_keys("shared_state", row, REQUIRED_SHARED_STATE_FIELDS)
        state = cls(
            completed_agents=tuple(str(agent_id) for agent_id in row["completed_agents"]),
            agent_statuses={str(agent_id): str(status) for agent_id, status in row["agent_statuses"].items()},
            artifacts={str(key): dict(value) for key, value in row["artifacts"].items()},
            metrics={str(agent_id): dict(value) for agent_id, value in row["metrics"].items()},
            decisions={str(agent_id): dict(value) for agent_id, value in row["decisions"].items()},
            reason_codes={
                str(agent_id): tuple(str(code) for code in codes)
                for agent_id, codes in row["reason_codes"].items()
            },
            validation={str(agent_id): dict(value) for agent_id, value in row["validation"].items()},
            llm_reports={str(agent_id): dict(value) for agent_id, value in row["llm_reports"].items()},
            privacy_filtered_features={
                str(agent_id): dict(value) for agent_id, value in row["privacy_filtered_features"].items()
            },
        )
        state.validate()
        return state


@dataclass(frozen=True)
class CustomerDecisionSnapshot:
    """Screen/API contract for one customer-level product decision.

    This is the shared shape consumed by policy dashboards, customer detail
    views, report generation, and downstream agent validation.  It keeps
    internal customer ids available for local UI joins while requiring a
    separate LLM-safe feature envelope for external report calls.
    """

    customer_id: str
    persona_type: str
    observation_period: ObservationPeriod
    living_zone: dict[str, Any]
    mileage_baseline_score: float
    senior_safe_mileage_score: float
    risk_change_score: float
    policy_candidate: PolicyCandidate
    care_decision: str
    reason_codes: tuple[str, ...]
    ab_comparison: ABComparison
    agent_validation: AgentValidationSummary
    llm_report: dict[str, Any]
    privacy_filtered_features: dict[str, Any]

    def validate(self) -> None:
        if not self.customer_id:
            raise ValueError("customer_id is required")
        if not self.persona_type:
            raise ValueError("persona_type is required")
        self.observation_period.validate()
        if not self.living_zone:
            raise ValueError("living_zone is required")
        assert_score_range("mileage_baseline_score", self.mileage_baseline_score)
        assert_score_range("senior_safe_mileage_score", self.senior_safe_mileage_score)
        assert_score_range("risk_change_score", self.risk_change_score)
        self.policy_candidate.validate()
        if self.care_decision not in ALLOWED_CARE_DECISIONS:
            raise ValueError(f"care_decision is invalid: {self.care_decision}")
        if not self.reason_codes:
            raise ValueError("reason_codes must include at least one XAI reason code")
        self.ab_comparison.validate()
        self.agent_validation.validate()
        validate_privacy_filtered_features(self.privacy_filtered_features)
        validate_privacy_filtered_features(self.llm_report.get("request_features", {}))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "customer_id": self.customer_id,
            "persona_type": self.persona_type,
            "observation_period": self.observation_period.to_dict(),
            "living_zone": self.living_zone,
            "mileage_baseline_score": self.mileage_baseline_score,
            "senior_safe_mileage_score": self.senior_safe_mileage_score,
            "risk_change_score": self.risk_change_score,
            "policy_candidate": self.policy_candidate.to_dict(),
            "care_decision": self.care_decision,
            "reason_codes": list(self.reason_codes),
            "ab_comparison": self.ab_comparison.to_dict(),
            "agent_validation": self.agent_validation.to_dict(),
            "llm_report": self.llm_report,
            "privacy_filtered_features": self.privacy_filtered_features,
        }


@dataclass(frozen=True)
class AgentInputPayload:
    run_id: str
    agent_id: str
    schema_version: str = CONTRACT_SCHEMA_VERSION
    customer_scope: tuple[str, ...] = ()
    input_artifacts: tuple[AgentArtifact, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    privacy_filtered_features: dict[str, Any] = field(default_factory=dict)
    shared_state: AgentSharedState = field(default_factory=AgentSharedState)
    upstream_results: tuple[str, ...] = ()

    def validate(self, metadata: AgentMetadata | None = None) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if metadata and self.agent_id != metadata.agent_id:
            raise ValueError(f"payload agent_id={self.agent_id} does not match metadata agent_id={metadata.agent_id}")
        validate_privacy_filtered_features(self.privacy_filtered_features)
        self.shared_state.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "customer_scope": list(self.customer_scope),
            "input_artifacts": [artifact.to_dict() for artifact in self.input_artifacts],
            "parameters": self.parameters,
            "privacy_filtered_features": self.privacy_filtered_features,
            "shared_state": self.shared_state.to_dict(),
            "upstream_results": list(self.upstream_results),
        }


@dataclass(frozen=True)
class AgentOutputPayload:
    run_id: str
    agent_id: str
    schema_version: str = CONTRACT_SCHEMA_VERSION
    output_artifacts: tuple[AgentArtifact, ...] = ()
    metrics: dict[str, float | int | bool] = field(default_factory=dict)
    decisions: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    validation: dict[str, Any] = field(default_factory=dict)
    llm_report: dict[str, Any] = field(default_factory=dict)
    shared_state: AgentSharedState = field(default_factory=AgentSharedState)
    messages: tuple[str, ...] = ()

    def validate(self, metadata: AgentMetadata | None = None) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if metadata and self.agent_id != metadata.agent_id:
            raise ValueError(f"output agent_id={self.agent_id} does not match metadata agent_id={metadata.agent_id}")
        validate_privacy_filtered_features(self.llm_report.get("request_features", {}))
        self.shared_state.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "output_artifacts": [artifact.to_dict() for artifact in self.output_artifacts],
            "metrics": self.metrics,
            "decisions": self.decisions,
            "reason_codes": list(self.reason_codes),
            "validation": self.validation,
            "llm_report": self.llm_report,
            "shared_state": self.shared_state.to_dict(),
            "messages": list(self.messages),
        }


@dataclass(frozen=True)
class AgentExecutionResult:
    run_id: str
    metadata: AgentMetadata
    status: AgentStatus
    input_payload: AgentInputPayload
    output_payload: AgentOutputPayload | None = None
    started_at: str = field(default_factory=lambda: utc_now_iso())
    completed_at: str | None = None
    duration_ms: int | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def validate(self) -> None:
        self.input_payload.validate(self.metadata)
        if self.output_payload:
            self.output_payload.validate(self.metadata)
        if self.status == AgentStatus.SUCCEEDED and self.output_payload is None:
            raise ValueError("succeeded execution requires output_payload")
        if self.status == AgentStatus.FAILED and not self.errors:
            raise ValueError("failed execution requires at least one error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "metadata": self.metadata.to_dict(),
            "status": self.status.value,
            "input_payload": self.input_payload.to_dict(),
            "output_payload": self.output_payload.to_dict() if self.output_payload else None,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@runtime_checkable
class SeniorMileageAgent(Protocol):
    metadata: AgentMetadata

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        """Execute one agent step and return the standard execution result."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_privacy_filtered_features(features: dict[str, Any]) -> None:
    forbidden = sorted(set(_flatten_keys(features)) & FORBIDDEN_EXTERNAL_API_FIELDS)
    if forbidden:
        raise ValueError(f"privacy_filtered_features contains forbidden external API fields: {forbidden}")


def assert_required_keys(label: str, payload: dict[str, Any], required_keys: set[str] | frozenset[str]) -> None:
    missing = sorted(required_keys - set(payload))
    if missing:
        raise ValueError(f"{label} missing required keys: {missing}")


def assert_score_range(label: str, value: float | int) -> None:
    score = float(value)
    if not 0 <= score <= 100:
        raise ValueError(f"{label} must be between 0 and 100; actual={value}")


def validate_customer_decision_snapshot(snapshot: CustomerDecisionSnapshot | dict[str, Any]) -> None:
    if isinstance(snapshot, CustomerDecisionSnapshot):
        snapshot.validate()
        return

    assert_required_keys("customer_decision_snapshot", snapshot, REQUIRED_CUSTOMER_SNAPSHOT_FIELDS)
    CustomerDecisionSnapshot(
        customer_id=str(snapshot["customer_id"]),
        persona_type=str(snapshot["persona_type"]),
        observation_period=ObservationPeriod(
            baseline_days=int(snapshot["observation_period"]["baseline_days"]),
            recent_days=int(snapshot["observation_period"]["recent_days"]),
        ),
        living_zone=dict(snapshot["living_zone"]),
        mileage_baseline_score=float(snapshot["mileage_baseline_score"]),
        senior_safe_mileage_score=float(snapshot["senior_safe_mileage_score"]),
        risk_change_score=float(snapshot["risk_change_score"]),
        policy_candidate=PolicyCandidate(
            candidate_id=str(snapshot["policy_candidate"]["candidate_id"]),
            weights={key: float(value) for key, value in snapshot["policy_candidate"]["weights"].items()},
            thresholds=dict(snapshot["policy_candidate"]["thresholds"]),
            rationale=str(snapshot["policy_candidate"].get("rationale", "")),
        ),
        care_decision=str(snapshot["care_decision"]),
        reason_codes=tuple(str(code) for code in snapshot["reason_codes"]),
        ab_comparison=ABComparison(
            baseline_detected=bool(snapshot["ab_comparison"]["baseline_detected"]),
            proposed_detected=bool(snapshot["ab_comparison"]["proposed_detected"]),
            baseline_score=float(snapshot["ab_comparison"]["baseline_score"]),
            proposed_score=float(snapshot["ab_comparison"]["proposed_score"]),
            metrics=dict(snapshot["ab_comparison"].get("metrics", {})),
        ),
        agent_validation=AgentValidationSummary(
            passed=bool(snapshot["agent_validation"]["passed"]),
            validation_pass_rate=float(snapshot["agent_validation"]["validation_pass_rate"]),
            critic_findings=tuple(snapshot["agent_validation"].get("critic_findings", ())),
            failed_agents=tuple(snapshot["agent_validation"].get("failed_agents", ())),
        ),
        llm_report=dict(snapshot["llm_report"]),
        privacy_filtered_features=dict(snapshot["privacy_filtered_features"]),
    ).validate()


def validate_agent_validation_pipeline_result(
    pipeline_result: AgentValidationPipelineResult | dict[str, Any],
) -> None:
    if isinstance(pipeline_result, AgentValidationPipelineResult):
        pipeline_result.validate()
        return

    assert_required_keys("agent_validation_pipeline_result", pipeline_result, REQUIRED_AGENT_VALIDATION_PIPELINE_FIELDS)
    if pipeline_result["schema_version"] != AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION:
        raise ValueError("invalid agent validation pipeline schema_version")
    summary = dict(pipeline_result["summary"])
    assert_required_keys("agent_validation_pipeline.summary", summary, REQUIRED_AGENT_VALIDATION_PIPELINE_SUMMARY_FIELDS)
    checks: list[AgentValidationCheckResult] = []
    for raw_check in pipeline_result["checks"]:
        assert_required_keys("agent_validation_pipeline.check", raw_check, REQUIRED_AGENT_VALIDATION_CHECK_FIELDS)
        checks.append(
            AgentValidationCheckResult(
                agent_id=str(raw_check["agent_id"]),
                status=str(raw_check["status"]),
                passed=bool(raw_check["passed"]),
                validation=dict(raw_check["validation"]),
                metrics=dict(raw_check["metrics"]),
                artifacts=tuple(
                    AgentArtifact(
                        artifact_id=str(artifact["artifact_id"]),
                        artifact_type=ArtifactType(str(artifact["artifact_type"])),
                        path=artifact.get("path"),
                        rows=artifact.get("rows"),
                        summary=dict(artifact.get("summary", {})),
                    )
                    for artifact in raw_check["artifacts"]
                ),
                reason_codes=tuple(str(code) for code in raw_check["reason_codes"]),
                warnings=tuple(str(warning) for warning in raw_check["warnings"]),
                errors=tuple(str(error) for error in raw_check["errors"]),
                privacy_filtered_features=dict(raw_check.get("privacy_filtered_features", {})),
            )
        )
    normalized = AgentValidationPipelineResult(
        run_id=str(pipeline_result["run_id"]),
        generated_at=str(pipeline_result["generated_at"]),
        required_agent_ids=tuple(str(agent_id) for agent_id in pipeline_result["required_agent_ids"]),
        checks=tuple(checks),
        approval_gate_thresholds=dict(pipeline_result["approval_gate_thresholds"]),
        critic_review=dict(pipeline_result["critic_review"]),
        artifacts=tuple(
            AgentArtifact(
                artifact_id=str(artifact["artifact_id"]),
                artifact_type=ArtifactType(str(artifact["artifact_type"])),
                path=artifact.get("path"),
                rows=artifact.get("rows"),
                summary=dict(artifact.get("summary", {})),
            )
            for artifact in pipeline_result["artifacts"]
        ),
    )
    normalized.validate()
    normalized_summary = normalized.to_dict()["summary"]
    if summary != normalized_summary:
        raise ValueError("agent validation pipeline summary does not match checks")


def _flatten_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys: list[str] = []
        for key, nested in value.items():
            keys.append(str(key).strip().lower())
            keys.extend(_flatten_keys(nested))
        return keys
    if isinstance(value, list):
        keys = []
        for item in value:
            keys.extend(_flatten_keys(item))
        return keys
    return []

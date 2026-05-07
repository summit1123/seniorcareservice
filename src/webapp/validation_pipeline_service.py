"""Service functions for querying saved Agent-in-the-loop validation results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agents.contracts import (
    AgentArtifact,
    AgentStatus,
    AgentValidationCheckResult,
    AgentValidationPipelineResult,
    ArtifactType,
    REQUIRED_AGENT_IDS,
    validate_agent_validation_pipeline_result,
)
from src.agents.critic_agent import DEFAULT_STRUCTURED_OUTPUT as DEFAULT_CRITIC_REVIEW_INPUT
from src.agents.evaluation_agent import DEFAULT_VIEW_MODEL_OUTPUT as DEFAULT_EVALUATION_VIEW_MODEL_INPUT
from src.agents.orchestrator import AGENT_REGISTRY, DEFAULT_RUN_ID
from src.agents.report_agent import DEFAULT_STRUCTURED_OUTPUT as DEFAULT_REPORT_VIEW_MODEL_INPUT
from src.agents.structured_outputs import (
    validate_critic_review,
    validate_evaluation_view_model,
    validate_report_view_model,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PERSONA_CUSTOMERS_INPUT = ROOT / "data" / "fixtures" / "senior_customers.json"
DEFAULT_PERSONA_TEMPLATES_INPUT = ROOT / "data" / "fixtures" / "persona_templates.yaml"
DEFAULT_PERSONA_PARAMETERS_INPUT = ROOT / "data" / "fixtures" / "customer_driving_parameters.json"
DEFAULT_SCENARIO_CONFIG_INPUT = ROOT / "data" / "fixtures" / "scenario_config.json"
DEFAULT_TRIP_LOG_INPUT = ROOT / "data" / "fixtures" / "senior_trip_logs.csv"
DEFAULT_SIMULATION_MANIFEST_INPUT = ROOT / "data" / "fixtures" / "simulation_manifest.json"
DEFAULT_CONSISTENCY_REPORT_INPUT = ROOT / "data" / "fixtures" / "validation_report.md"
DEFAULT_POLICY_CANDIDATE_RULES_INPUT = ROOT / "data" / "fixtures" / "candidate_rules.json"
DEFAULT_POLICY_CANDIDATE_SCORES_INPUT = ROOT / "data" / "fixtures" / "policy_candidate_scores.csv"
DEFAULT_AB_RESULTS_INPUT = ROOT / "data" / "fixtures" / "ab_test_results.csv"
VALIDATION_PIPELINE_TAB_MODEL_SCHEMA = "senior-safe-mileage-validation-pipeline-tab-model/v1"


def load_validation_pipeline_result(
    *,
    run_id: str = DEFAULT_RUN_ID,
    persona_customers_input: Path = DEFAULT_PERSONA_CUSTOMERS_INPUT,
    persona_templates_input: Path = DEFAULT_PERSONA_TEMPLATES_INPUT,
    persona_parameters_input: Path = DEFAULT_PERSONA_PARAMETERS_INPUT,
    scenario_config_input: Path = DEFAULT_SCENARIO_CONFIG_INPUT,
    trip_log_input: Path = DEFAULT_TRIP_LOG_INPUT,
    simulation_manifest_input: Path = DEFAULT_SIMULATION_MANIFEST_INPUT,
    consistency_report_input: Path = DEFAULT_CONSISTENCY_REPORT_INPUT,
    policy_candidate_rules_input: Path = DEFAULT_POLICY_CANDIDATE_RULES_INPUT,
    policy_candidate_scores_input: Path = DEFAULT_POLICY_CANDIDATE_SCORES_INPUT,
    ab_results_input: Path = DEFAULT_AB_RESULTS_INPUT,
    evaluation_view_model_input: Path = DEFAULT_EVALUATION_VIEW_MODEL_INPUT,
    critic_review_input: Path = DEFAULT_CRITIC_REVIEW_INPUT,
    report_view_model_input: Path = DEFAULT_REPORT_VIEW_MODEL_INPUT,
    selected_candidate_id: str | None = None,
    selected_scenario_id: str | None = None,
) -> dict[str, Any]:
    """Return a queryable validation-pipeline result from saved local artifacts.

    The function is intentionally read-only: it does not run agents or mutate
    fixtures.  Downstream web views can call it to populate evidence/audit tabs.
    """

    execution_input = build_validation_execution_input(
        scenario_config_input=scenario_config_input,
        policy_candidate_rules_input=policy_candidate_rules_input,
        selected_candidate_id=selected_candidate_id,
        selected_scenario_id=selected_scenario_id,
    )
    checks = (
        _persona_agent_check(persona_customers_input, persona_templates_input, persona_parameters_input),
        _scenario_agent_check(scenario_config_input, execution_input["selected_scenario"]),
        _ai_simulation_agent_check(trip_log_input, simulation_manifest_input),
        _consistency_check_agent_check(consistency_report_input),
        _policy_search_agent_check(
            policy_candidate_rules_input,
            policy_candidate_scores_input,
            execution_input["selected_policy"],
        ),
        _evaluation_agent_check(
            ab_results_input,
            evaluation_view_model_input,
            execution_input=execution_input,
        ),
        _critic_agent_check(critic_review_input),
        _report_agent_check(report_view_model_input),
    )
    critic_review = _load_json_or_empty(critic_review_input).get("validation", {})
    pipeline_result = AgentValidationPipelineResult(
        run_id=run_id,
        checks=checks,
        critic_review=critic_review,
        artifacts=(
            _artifact("agent_validation_pipeline.json", ROOT / "data" / "fixtures" / "agent_validation_pipeline.json"),
        ),
    ).to_dict()
    pipeline_result["execution_input"] = execution_input
    validate_agent_validation_pipeline_result(pipeline_result)
    return pipeline_result


def get_validation_pipeline_check(pipeline_result: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """Look up one agent check from a validation-pipeline service result."""

    validate_agent_validation_pipeline_result(pipeline_result)
    for check in pipeline_result["checks"]:
        if check["agent_id"] == agent_id:
            return dict(check)
    raise KeyError(f"validation pipeline check not found: {agent_id}")


def normalize_validation_pipeline_tab_model(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize pipeline output into evidence/audit tab sections for local UI use."""

    validate_agent_validation_pipeline_result(pipeline_result)
    summary = dict(pipeline_result["summary"])
    checks = [_normalized_validation_check(dict(check)) for check in pipeline_result["checks"]]
    evidence_items = _validation_evidence_items(checks)
    audit_log_entries = _validation_audit_log_entries(pipeline_result, checks)
    artifact_index = _validation_artifact_index(pipeline_result, checks)
    model = {
        "schema_version": VALIDATION_PIPELINE_TAB_MODEL_SCHEMA,
        "run_id": str(pipeline_result["run_id"]),
        "generated_at": str(pipeline_result["generated_at"]),
        "tabs": [
            {
                "tab_id": "evidence",
                "label": "근거",
                "item_count": len(evidence_items),
                "section_ids": ["execution_input", "validation_results", "artifacts"],
            },
            {
                "tab_id": "audit",
                "label": "감사",
                "item_count": len(audit_log_entries),
                "section_ids": ["audit_log", "privacy_contract"],
            },
        ],
        "summary": {
            "passed": bool(summary["passed"]),
            "validation_pass_rate": float(summary["validation_pass_rate"]),
            "total_agent_count": int(summary["total_agent_count"]),
            "passed_agent_count": int(summary["passed_agent_count"]),
            "failed_agent_count": int(summary["failed_agent_count"]),
            "failed_agents": [str(agent_id) for agent_id in summary.get("failed_agents", ())],
            "critic_findings": [str(item) for item in summary.get("critic_findings", ())],
        },
        "approval_gate_thresholds": dict(pipeline_result["approval_gate_thresholds"]),
        "execution_input": dict(pipeline_result.get("execution_input", {})),
        "checks": checks,
        "evidence_items": evidence_items,
        "audit_log_entries": audit_log_entries,
        "artifact_index": artifact_index,
        "privacy_contract": {
            "schema_version": "senior-safe-mileage-validation-pipeline-privacy-contract/v1",
            "external_api_payload_scope": "privacy_filtered_features_only",
            "forbidden_fields": ["customer_id", "trip_id", "phone_number", "address", "vehicle_number", "gps_coordinates"],
            "checks_with_privacy_filtered_features": [
                check["agent_id"] for check in checks if check["privacy_filtered_features"]
            ],
        },
    }
    validate_validation_pipeline_tab_model(model)
    return model


def validate_validation_pipeline_tab_model(model: dict[str, Any]) -> None:
    """Validate the normalized evidence/audit tab model contract."""

    if model.get("schema_version") != VALIDATION_PIPELINE_TAB_MODEL_SCHEMA:
        raise ValueError("invalid validation pipeline tab model schema_version")
    summary = dict(model.get("summary", {}))
    checks = list(model.get("checks", ()))
    evidence_items = list(model.get("evidence_items", ()))
    audit_log_entries = list(model.get("audit_log_entries", ()))
    tabs = {str(tab.get("tab_id")): dict(tab) for tab in model.get("tabs", ())}
    if set(tabs) != {"evidence", "audit"}:
        raise ValueError("validation pipeline tab model must expose evidence and audit tabs")
    if int(summary.get("total_agent_count", -1)) != len(checks):
        raise ValueError("validation pipeline tab model summary/check count mismatch")
    if tabs["evidence"].get("item_count") != len(evidence_items):
        raise ValueError("validation pipeline evidence tab item_count mismatch")
    if tabs["audit"].get("item_count") != len(audit_log_entries):
        raise ValueError("validation pipeline audit tab item_count mismatch")
    if {str(check.get("agent_id")) for check in checks} != set(REQUIRED_AGENT_IDS):
        raise ValueError("validation pipeline tab model must cover every required agent")
    if not evidence_items:
        raise ValueError("validation pipeline tab model requires evidence items")
    if not audit_log_entries:
        raise ValueError("validation pipeline tab model requires audit log entries")


def _normalized_validation_check(check: dict[str, Any]) -> dict[str, Any]:
    artifacts = [dict(artifact) for artifact in check.get("artifacts", ())]
    validation = dict(check.get("validation", {}))
    metrics = dict(check.get("metrics", {}))
    reason_codes = [str(code) for code in check.get("reason_codes", ())]
    return {
        "agent_id": str(check.get("agent_id", "")),
        "status": str(check.get("status", "")),
        "passed": bool(check.get("passed")),
        "validation": validation,
        "metrics": metrics,
        "artifacts": artifacts,
        "artifact_ids": [str(artifact.get("artifact_id", "")) for artifact in artifacts],
        "reason_codes": reason_codes,
        "warnings": [str(item) for item in check.get("warnings", ())],
        "errors": [str(item) for item in check.get("errors", ())],
        "privacy_filtered_features": dict(check.get("privacy_filtered_features", {})),
        "privacy_filtered_feature_keys": sorted(str(key) for key in dict(check.get("privacy_filtered_features", {}))),
        "summary": _validation_check_summary(check, validation, metrics),
    }


def _validation_check_summary(check: dict[str, Any], validation: dict[str, Any], metrics: dict[str, Any]) -> str:
    fragments = [
        f"status={check.get('status', '')}",
        f"passed={bool(check.get('passed'))}",
    ]
    for key in (
        "customer_count",
        "persona_count",
        "candidate_count",
        "risk_change_capture_count",
        "non_target_false_positive_count",
        "total_misclassification_count",
        "agent_validation_pass_rate",
    ):
        if key in metrics:
            fragments.append(f"{key}={metrics[key]}")
    if "report_mode" in validation:
        fragments.append(f"report_mode={validation['report_mode']}")
    return ", ".join(fragments)


def _validation_evidence_items(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for check in checks:
        items.append(
            {
                "evidence_id": f"{check['agent_id']}_validation_evidence",
                "agent_id": check["agent_id"],
                "passed": check["passed"],
                "status": check["status"],
                "summary": check["summary"],
                "metric_keys": sorted(str(key) for key in check["metrics"]),
                "validation_keys": sorted(str(key) for key in check["validation"]),
                "reason_codes": list(check["reason_codes"]),
                "artifact_refs": list(check["artifact_ids"]),
                "privacy_filtered_feature_keys": list(check["privacy_filtered_feature_keys"]),
            }
        )
    return items


def _validation_audit_log_entries(
    pipeline_result: dict[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {
            "event_id": "agent_validation_pipeline_loaded",
            "agent_id": "orchestrator",
            "event_type": "pipeline_loaded",
            "severity": "info",
            "message": f"run_id={pipeline_result.get('run_id', '')} checks={len(checks)}",
            "artifact_refs": [
                str(artifact.get("artifact_id", ""))
                for artifact in pipeline_result.get("artifacts", ())
            ],
        }
    ]
    for check in checks:
        entries.append(
            {
                "event_id": f"{check['agent_id']}_validation_{check['status']}",
                "agent_id": check["agent_id"],
                "event_type": "agent_validation_check",
                "severity": "info" if check["passed"] else "warning",
                "message": check["summary"],
                "artifact_refs": list(check["artifact_ids"]),
            }
        )
    return entries


def _validation_artifact_index(
    pipeline_result: dict[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_artifact_id: dict[str, dict[str, Any]] = {}
    for artifact in list(pipeline_result.get("artifacts", ())) + [
        artifact for check in checks for artifact in check.get("artifacts", ())
    ]:
        artifact_id = str(artifact.get("artifact_id", ""))
        if artifact_id and artifact_id not in by_artifact_id:
            by_artifact_id[artifact_id] = dict(artifact)
    return [by_artifact_id[key] for key in sorted(by_artifact_id)]


def build_validation_execution_input(
    *,
    scenario_config_input: Path = DEFAULT_SCENARIO_CONFIG_INPUT,
    policy_candidate_rules_input: Path = DEFAULT_POLICY_CANDIDATE_RULES_INPUT,
    selected_candidate_id: str | None = None,
    selected_scenario_id: str | None = None,
) -> dict[str, Any]:
    """Build the selected policy/scenario state passed into validation checks."""

    scenario = _load_json(scenario_config_input)
    policy_rules = _load_json(policy_candidate_rules_input)
    selected_scenario = _selected_scenario_state(
        scenario,
        scenario_config_input=scenario_config_input,
        selected_scenario_id=selected_scenario_id,
    )
    selected_policy = _selected_policy_state(
        policy_rules,
        policy_candidate_rules_input=policy_candidate_rules_input,
        selected_candidate_id=selected_candidate_id,
    )
    return {
        "schema_version": "senior-safe-mileage-validation-execution-input/v1",
        "selected_scenario": selected_scenario,
        "selected_policy": selected_policy,
        "source_artifacts": {
            "scenario_config_input": _relative_project_path(scenario_config_input),
            "policy_candidate_rules_input": _relative_project_path(policy_candidate_rules_input),
        },
    }


def _persona_agent_check(
    customers_input: Path,
    templates_input: Path,
    parameters_input: Path,
) -> AgentValidationCheckResult:
    customers = _load_json(customers_input)
    customer_rows = list(customers.get("customers", ()))
    persona_types = {str(row.get("persona_type")) for row in customer_rows}
    validation = {
        "passed": int(customers.get("customer_count", 0)) == 30
        and len(customer_rows) == 30
        and len(persona_types) == 6
        and templates_input.exists()
        and parameters_input.exists(),
        "customer_count": len(customer_rows),
        "persona_count": len(persona_types),
        "customer_count_per_persona": customers.get("customer_count_per_persona"),
    }
    return _check(
        "persona_agent",
        validation=validation,
        metrics={"customer_count": len(customer_rows), "persona_count": len(persona_types)},
        artifacts=(
            _artifact("senior_customers.json", customers_input),
            _artifact("persona_templates.yaml", templates_input),
            _artifact("customer_driving_parameters.json", parameters_input),
        ),
        reason_codes=("PERSONA_FIXTURES_QUERYABLE",),
    )


def _scenario_agent_check(
    scenario_input: Path,
    selected_scenario: dict[str, Any],
) -> AgentValidationCheckResult:
    scenario = _load_json(scenario_input)
    period = dict(scenario.get("observation_period", {}))
    validation = {
        "passed": scenario.get("schema_version") == "senior-scenario-config/v1"
        and int(scenario.get("customer_count", 0)) == 30
        and int(scenario.get("customer_count_per_persona", 0)) == 5
        and int(period.get("baseline_days", 0)) == 60
        and int(period.get("recent_days", 0)) == 30
        and str(selected_scenario.get("source_artifact")) == _relative_project_path(scenario_input),
        "customer_count": scenario.get("customer_count"),
        "customer_count_per_persona": scenario.get("customer_count_per_persona"),
        "observation_period": period,
        "selected_scenario_id": selected_scenario.get("scenario_id"),
        "selected_scenario_connected_to_execution_input": True,
    }
    return _check(
        "scenario_agent",
        validation=validation,
        metrics={"customer_count": int(scenario.get("customer_count", 0))},
        artifacts=(_artifact("scenario_config.json", scenario_input),),
        reason_codes=("SCENARIO_FIXTURE_QUERYABLE",),
    )


def _ai_simulation_agent_check(trip_log_input: Path, manifest_input: Path) -> AgentValidationCheckResult:
    manifest = _load_json(manifest_input)
    coverage = dict(manifest.get("customer_90_day_coverage_validation", {}))
    downstream = dict(manifest.get("downstream_signal_validation", {}))
    validation = {
        "passed": trip_log_input.exists()
        and bool(coverage.get("passed"))
        and bool(manifest.get("baseline_coverage_validation", {}).get("passed"))
        and bool(manifest.get("recent_coverage_validation", {}).get("passed"))
        and all(bool(row.get("passed")) for row in downstream.values()),
        "customer_90_day_coverage_validation": coverage.get("passed"),
        "baseline_coverage_validation": manifest.get("baseline_coverage_validation", {}).get("passed"),
        "recent_coverage_validation": manifest.get("recent_coverage_validation", {}).get("passed"),
        "downstream_signal_validation_passed": all(bool(row.get("passed")) for row in downstream.values()),
    }
    return _check(
        "ai_simulation_agent",
        validation=validation,
        metrics={
            "customer_count": int(coverage.get("customer_count", 0)),
            "complete_customer_count": int(coverage.get("complete_customer_count", 0)),
        },
        artifacts=(_artifact("senior_trip_logs.csv", trip_log_input), _artifact("simulation_manifest.json", manifest_input)),
        reason_codes=("SIMULATION_90_DAY_COVERAGE_QUERYABLE",),
    )


def _consistency_check_agent_check(report_input: Path) -> AgentValidationCheckResult:
    text = report_input.read_text(encoding="utf-8")
    validation = {
        "passed": "- passed: `true`" in text.lower(),
        "report_contains_schema": "senior-trip-consistency-validation/v1" in text,
        "report_contains_customer_count": "customer_count: `30`" in text,
    }
    return _check(
        "consistency_check_agent",
        validation=validation,
        metrics={"customer_count": 30 if validation["report_contains_customer_count"] else 0},
        artifacts=(_artifact("validation_report.md", report_input),),
        reason_codes=("CONSISTENCY_REPORT_QUERYABLE",),
    )


def _policy_search_agent_check(
    rules_input: Path,
    scores_input: Path,
    selected_policy: dict[str, Any],
) -> AgentValidationCheckResult:
    rules = _load_json(rules_input)
    ranked_candidates = list(rules.get("ranked_candidates", ()))
    selected_candidate_id = str(selected_policy.get("candidate_id", ""))
    selected_exists = any(str(candidate.get("candidate_id")) == selected_candidate_id for candidate in ranked_candidates)
    validation = {
        "passed": rules.get("schema_version") == "senior-policy-candidate-rules/v1"
        and bool(ranked_candidates)
        and selected_exists
        and scores_input.exists()
        and str(selected_policy.get("source_artifact")) == _relative_project_path(rules_input),
        "selected_candidate_id": selected_candidate_id,
        "ranked_candidate_count": len(ranked_candidates),
        "objective_constraints": rules.get("search_input", {}).get("objective_constraints", {}),
        "selected_policy_connected_to_execution_input": True,
    }
    return _check(
        "policy_search_agent",
        validation=validation,
        metrics={"candidate_count": len(ranked_candidates)},
        artifacts=(_artifact("candidate_rules.json", rules_input), _artifact("policy_candidate_scores.csv", scores_input)),
        reason_codes=("POLICY_SEARCH_RESULTS_QUERYABLE",),
    )


def _evaluation_agent_check(
    ab_results_input: Path,
    view_model_input: Path,
    *,
    execution_input: dict[str, Any],
) -> AgentValidationCheckResult:
    view_model = _load_json(view_model_input)
    validate_evaluation_view_model(view_model)
    metrics = dict(view_model["summary_metrics"])
    selected_policy = dict(execution_input["selected_policy"])
    selected_scenario = dict(execution_input["selected_scenario"])
    view_model_policy = dict(view_model.get("selected_policy", {}))
    view_model_scenario = dict(view_model.get("selected_scenario", {}))
    policy_state_matches = str(view_model_policy.get("candidate_id", "")) == str(selected_policy["candidate_id"])
    scenario_state_matches = (
        not view_model_scenario
        or str(view_model_scenario.get("scenario_id", "")) == str(selected_scenario["scenario_id"])
    )
    validation = {
        "passed": ab_results_input.exists()
        and bool(metrics["passes_approval_gate"])
        and policy_state_matches
        and scenario_state_matches,
        "approval_gate_passed": metrics["passes_approval_gate"],
        "risk_change_capture_count": metrics["proposed_capture_count"],
        "non_target_false_positive_count": metrics["non_target_false_positive_count"],
        "total_misclassification_count": metrics["total_misclassification_count"],
        "agent_validation_pass_rate": metrics["agent_validation_pass_rate"],
        "selected_candidate_id": selected_policy["candidate_id"],
        "selected_scenario_id": selected_scenario["scenario_id"],
        "selected_state_connected_to_execution_input": True,
        "policy_state_matches_evaluation_artifact": policy_state_matches,
        "scenario_state_matches_evaluation_artifact": scenario_state_matches,
    }
    return _check(
        "evaluation_agent",
        validation=validation,
        metrics={
            "customer_count": int(metrics["customer_count"]),
            "risk_change_capture_count": int(metrics["proposed_capture_count"]),
            "non_target_false_positive_count": int(metrics["non_target_false_positive_count"]),
            "total_misclassification_count": int(metrics["total_misclassification_count"]),
            "agent_validation_pass_rate": float(metrics["agent_validation_pass_rate"]),
        },
        artifacts=(_artifact("ab_test_results.csv", ab_results_input), _artifact("evaluation_view_model.json", view_model_input)),
        reason_codes=tuple(str(code) for code in view_model.get("evaluation_reason_codes", ())),
    )


def _selected_scenario_state(
    scenario: dict[str, Any],
    *,
    scenario_config_input: Path,
    selected_scenario_id: str | None,
) -> dict[str, Any]:
    scenario_id = str(
        scenario.get("scenario_id")
        or f"scenario_seed_{scenario.get('simulation_seed', 'unknown')}_baseline60_recent30"
    )
    if selected_scenario_id and str(selected_scenario_id) != scenario_id:
        raise ValueError(f"selected scenario not found: {selected_scenario_id}")
    return {
        "schema_version": "senior-safe-mileage-selected-scenario-state/v1",
        "scenario_id": scenario_id,
        "source_artifact": _relative_project_path(scenario_config_input),
        "simulation_seed": scenario.get("simulation_seed"),
        "customer_count": int(scenario.get("customer_count", 0)),
        "customer_count_per_persona": int(scenario.get("customer_count_per_persona", 0)),
        "observation_period": dict(scenario.get("observation_period", {})),
    }


def _selected_policy_state(
    policy_rules: dict[str, Any],
    *,
    policy_candidate_rules_input: Path,
    selected_candidate_id: str | None,
) -> dict[str, Any]:
    candidate_id = str(selected_candidate_id or policy_rules.get("selected_candidate_id", ""))
    ranked_candidates = [dict(candidate) for candidate in policy_rules.get("ranked_candidates", ())]
    selected = next(
        (candidate for candidate in ranked_candidates if str(candidate.get("candidate_id")) == candidate_id),
        None,
    )
    if selected is None:
        raise ValueError(f"selected policy candidate not found: {candidate_id}")
    return {
        "schema_version": "senior-safe-mileage-selected-policy-state/v1",
        "candidate_id": candidate_id,
        "source_artifact": _relative_project_path(policy_candidate_rules_input),
        "rank": int(selected.get("rank", 0)),
        "weights": dict(selected.get("weights", {})),
        "thresholds": dict(selected.get("thresholds", {})),
        "scores": dict(selected.get("scores", {})),
        "reason_codes": list(selected.get("reason_metadata", {}).get("reason_codes", ())),
    }


def _critic_agent_check(review_input: Path) -> AgentValidationCheckResult:
    review = _load_json(review_input)
    validate_critic_review(review)
    validation = dict(review["validation"])
    return _check(
        "critic_agent",
        validation=validation,
        metrics=dict(review["metrics"]),
        artifacts=(_artifact("rule_review.json", review_input),),
        reason_codes=tuple(str(code) for code in review.get("reason_codes", ())),
    )


def _report_agent_check(report_input: Path) -> AgentValidationCheckResult:
    try:
        report = _load_json(report_input)
        validate_report_view_model(report)
    except Exception as exc:
        return _check(
            "report_agent",
            validation={
                "passed": False,
                "report_mode": "unavailable",
                "fallback_available": True,
                "core_outputs_continue": True,
                "error_type": exc.__class__.__name__,
            },
            metrics={"customer_count": 0, "fallback_report_count": 0},
            artifacts=(_artifact("simulation_summary.json", report_input),),
            reason_codes=("LLM_REPORT_SERVICE_FALLBACK_READY",),
            warnings=(f"report artifact unavailable; UI should show fallback status: {exc.__class__.__name__}",),
        )
    approval = dict(report["approval"])
    llm_service_status = dict(report.get("portfolio_llm_report", {}).get("llm_service_status", {}))
    validation = {
        "passed": bool(report["validation"]["passed"]) and bool(approval["ready_for_insurer_review"]),
        "report_mode": report["report_mode"],
        "approval": approval,
        "privacy_filter": report["validation"].get("privacy_filter"),
        "fallback_available": True,
        "service_status": str(llm_service_status.get("status", "inactive")),
        "service_active": bool(llm_service_status.get("active")),
        "failure_detected": bool(llm_service_status.get("failure_detected")),
        "core_outputs_continue": True,
    }
    return _check(
        "report_agent",
        validation=validation,
        metrics={
            "customer_count": int(report["summary_metrics"]["customer_count"]),
            "fallback_report_count": int(report["validation"].get("fallback_report_count", 0)),
        },
        artifacts=(_artifact("simulation_summary.json", report_input),),
        reason_codes=tuple(str(code) for code in report.get("reason_codes", ())),
        privacy_filtered_features=dict(report["portfolio_llm_report"]["request_features"]),
    )


def _check(
    agent_id: str,
    *,
    validation: dict[str, Any],
    metrics: dict[str, float | int | bool],
    artifacts: tuple[AgentArtifact, ...],
    reason_codes: tuple[str, ...],
    privacy_filtered_features: dict[str, Any] | None = None,
    warnings: tuple[str, ...] = (),
) -> AgentValidationCheckResult:
    passed = bool(validation.get("passed"))
    return AgentValidationCheckResult(
        agent_id=agent_id,
        status=AgentStatus.SUCCEEDED if passed else AgentStatus.FAILED,
        passed=passed,
        validation=validation,
        metrics=metrics,
        artifacts=artifacts,
        reason_codes=reason_codes,
        warnings=warnings,
        errors=() if passed else (f"{AGENT_REGISTRY[agent_id].display_name} validation failed",),
        privacy_filtered_features=privacy_filtered_features or {},
    )


def _artifact(artifact_id: str, path: Path) -> AgentArtifact:
    return AgentArtifact(
        artifact_id=artifact_id,
        artifact_type=_artifact_type(path),
        path=_relative_project_path(path),
    )


def _artifact_type(path: Path) -> ArtifactType:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return ArtifactType.CSV
    if suffix == ".md":
        return ArtifactType.MARKDOWN
    return ArtifactType.JSON


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_or_empty(path: Path) -> dict[str, Any]:
    return _load_json(path) if path.exists() else {}


def _relative_project_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)

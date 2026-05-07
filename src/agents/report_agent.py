"""Report Agent for insurer-facing Senior Safe Mileage report data.

The Report Agent is the final deterministic step in the local agent loop.  It
accepts approved Evaluation Agent outputs and Critic Agent review results,
preserves local customer ids for UI joins, and builds LLM-safe report envelopes
from privacy-filtered summary features only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents.contracts import (
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentStatus,
    ArtifactType,
    FORBIDDEN_EXTERNAL_API_FIELDS,
    validate_customer_decision_snapshot,
    validate_privacy_filtered_features,
    utc_now_iso,
)
from src.agents.critic_agent import DEFAULT_STRUCTURED_OUTPUT as DEFAULT_CRITIC_REVIEW_INPUT
from src.agents.evaluation_agent import DEFAULT_VIEW_MODEL_OUTPUT as DEFAULT_EVALUATION_VIEW_MODEL_INPUT
from src.agents.structured_outputs import (
    build_ui_dashboard_bundle,
    load_structured_json,
    validate_llm_report_auxiliary_results,
    validate_report_view_model,
    write_structured_json,
)
from src.llm.openai_client import OpenAIClient, OpenAIReportRequest


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_OUTPUT = ROOT / "data" / "fixtures" / "simulation_summary.md"
DEFAULT_STRUCTURED_OUTPUT = ROOT / "data" / "fixtures" / "simulation_summary.json"
DEFAULT_LLM_AUXILIARY_OUTPUT = ROOT / "data" / "fixtures" / "llm_report_auxiliary_results.json"
SCHEMA_VERSION = "senior-report-agent/v1"
LLM_AUXILIARY_SCHEMA_VERSION = "senior-llm-report-auxiliary-results/v1"


class ReportAgent:
    """Convert approved evaluation and critic outputs into report view data."""

    metadata = AgentMetadata(
        agent_id="report_agent",
        role=AgentRole.REPORT,
        display_name="Report Agent",
        description="Creates insurer-facing structured reports with XAI reason codes and LLM fallback support.",
        consumes=("evaluation_view_model.json", "rule_review.json"),
        produces=("simulation_summary.md", "simulation_summary.json"),
        uses_llm=True,
        requires_privacy_filter=True,
    )

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            evaluation_input = _resolve_artifact_path(
                payload,
                "evaluation_view_model.json",
                "evaluation_view_model_input",
                DEFAULT_EVALUATION_VIEW_MODEL_INPUT,
            )
            critic_review_input = _resolve_artifact_path(
                payload,
                "rule_review.json",
                "critic_review_input",
                DEFAULT_CRITIC_REVIEW_INPUT,
            )
            report_output = Path(str(payload.parameters.get("report_output", DEFAULT_REPORT_OUTPUT)))
            structured_output = Path(str(payload.parameters.get("structured_output", DEFAULT_STRUCTURED_OUTPUT)))
            llm_auxiliary_output = Path(
                str(payload.parameters.get("llm_auxiliary_output", DEFAULT_LLM_AUXILIARY_OUTPUT))
            )
            force_llm_failure = bool(payload.parameters.get("force_llm_failure", False))
            openai_client = _resolve_openai_client(payload.parameters, force_llm_failure=force_llm_failure)

            evaluation = load_report_inputs(
                evaluation_view_model_input=evaluation_input,
                critic_review_input=critic_review_input,
            )
            report = build_insurer_report(
                evaluation,
                force_llm_failure=force_llm_failure,
                openai_client=openai_client,
            )
            llm_auxiliary_results = build_llm_report_auxiliary_results(report)
            write_report_json(report, structured_output)
            write_llm_report_auxiliary_json(llm_auxiliary_results, llm_auxiliary_output)
            write_report_markdown(report, report_output)

            validation = report["validation"]
            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="simulation_summary.md",
                        artifact_type=ArtifactType.MARKDOWN,
                        path=_relative_project_path(report_output),
                        rows=len(report["customer_reports"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "critic_verdict": report["critic_review"]["verdict"],
                            "report_mode": report["report_mode"],
                        },
                    ),
                    AgentArtifact(
                        artifact_id="simulation_summary.json",
                        artifact_type=ArtifactType.WEB_VIEW_MODEL,
                        path=_relative_project_path(structured_output),
                        rows=len(report["customer_reports"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "customer_report_count": len(report["customer_reports"]),
                            "fallback_report_count": validation["fallback_report_count"],
                        },
                    ),
                    AgentArtifact(
                        artifact_id="llm_report_auxiliary_results.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_project_path(llm_auxiliary_output),
                        rows=len(llm_auxiliary_results["customer_auxiliary_results"]),
                        summary={
                            "schema_version": LLM_AUXILIARY_SCHEMA_VERSION,
                            "report_mode": llm_auxiliary_results["report_mode"],
                            "privacy_checked": llm_auxiliary_results["validation"]["privacy_checked"],
                        },
                    ),
                ),
                metrics={
                    "customer_count": report["summary_metrics"]["customer_count"],
                    "risk_change_capture_count": report["summary_metrics"]["proposed_capture_count"],
                    "non_target_false_positive_count": report["summary_metrics"]["non_target_false_positive_count"],
                    "total_misclassification_count": report["summary_metrics"]["total_misclassification_count"],
                    "agent_validation_pass_rate": report["summary_metrics"]["agent_validation_pass_rate"],
                    "fallback_report_count": validation["fallback_report_count"],
                    "privacy_checked": validation["privacy_checked"],
                },
                decisions={
                    "approval_gate_passed": report["approval"]["approval_gate_passed"],
                    "critic_verdict": report["critic_review"]["verdict"],
                    "selected_candidate_id": report["selected_policy"]["candidate_id"],
                },
                reason_codes=tuple(report["reason_codes"]),
                validation=validation,
                llm_report=report["portfolio_llm_report"],
                messages=("insurer-facing report data generated from approved evaluation and critic outputs",),
            )
            return AgentExecutionResult(
                run_id=payload.run_id,
                metadata=self.metadata,
                status=AgentStatus.SUCCEEDED,
                input_payload=payload,
                output_payload=output,
                started_at=started_at,
                completed_at=utc_now_iso(),
                duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
            )
        except Exception as exc:
            return AgentExecutionResult(
                run_id=payload.run_id,
                metadata=self.metadata,
                status=AgentStatus.FAILED,
                input_payload=payload,
                started_at=started_at,
                completed_at=utc_now_iso(),
                duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
                errors=(f"{exc.__class__.__name__}: {exc}",),
            )


def load_report_inputs(
    *,
    evaluation_view_model_input: Path = DEFAULT_EVALUATION_VIEW_MODEL_INPUT,
    critic_review_input: Path = DEFAULT_CRITIC_REVIEW_INPUT,
) -> dict[str, Any]:
    evaluation = load_structured_json(evaluation_view_model_input)
    critic_review = load_structured_json(critic_review_input)
    return {
        "schema_version": f"{SCHEMA_VERSION}/input",
        "source_artifacts": {
            "evaluation_view_model_input": _relative_project_path(evaluation_view_model_input),
            "critic_review_input": _relative_project_path(critic_review_input),
        },
        "evaluation": evaluation,
        "critic_review": critic_review,
    }


def build_insurer_report(
    report_input: dict[str, Any],
    *,
    force_llm_failure: bool = False,
    openai_client: Any | None = None,
) -> dict[str, Any]:
    evaluation = dict(report_input["evaluation"])
    critic_review = dict(report_input["critic_review"])
    _validate_approved_inputs(evaluation, critic_review)

    customer_reports = [
        _build_customer_report(snapshot, critic_review, force_llm_failure=force_llm_failure)
        for snapshot in evaluation["customer_snapshots"]
    ]
    portfolio_features = _portfolio_request_features(evaluation, critic_review)
    validate_privacy_filtered_features(portfolio_features)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source_artifacts": dict(report_input["source_artifacts"]),
        "report_mode": "pending",
        "approval": {
            "approval_gate_passed": bool(evaluation["summary_metrics"]["passes_approval_gate"]),
            "critic_passed": bool(critic_review["validation"]["passed"]),
            "ready_for_insurer_review": True,
        },
        "selected_policy": dict(evaluation["selected_policy"]),
        "summary_metrics": dict(evaluation["summary_metrics"]),
        "critic_review": {
            "verdict": critic_review["validation"]["verdict"],
            "risk_count": len(critic_review["risks"]),
            "blocking_finding_count": critic_review["validation"]["blocking_finding_count"],
            "required_follow_ups": list(critic_review["required_follow_ups"]),
            "risks": list(critic_review["risks"]),
        },
        "portfolio_llm_report": {
            "mode": "fallback_template" if force_llm_failure else "deterministic_template",
            "request_features": portfolio_features,
            "fallback_available": True,
            "audience": "insurer_staff",
            "summary": _portfolio_summary(evaluation, critic_review),
            "llm_service_status": _llm_service_status(
                mode="fallback_template" if force_llm_failure else "deterministic_template",
                purpose="insurer_portfolio_report",
            ),
        },
        "customer_reports": customer_reports,
        "reason_codes": [],
        "validation": {
            "passed": True,
            "approved_inputs": True,
            "customer_report_count": len(customer_reports),
            "fallback_report_count": 0,
            "privacy_checked": True,
            "forbidden_external_api_fields_present": [],
        },
    }
    if openai_client is not None and not force_llm_failure:
        _apply_openai_report_generation(report, openai_client)
    _refresh_llm_report_status(report, evaluation, critic_review)
    validate_report(report)
    build_ui_dashboard_bundle(evaluation, critic_review=critic_review, report_view_model=report)
    return report


def build_llm_report_auxiliary_results(report: dict[str, Any]) -> dict[str, Any]:
    """Build reproducible insurer-staff LLM report support data.

    The auxiliary artifact is local UI data.  It may carry the local
    ``customer_id`` for joins, but the nested ``request_features`` envelope is
    the only payload eligible for an external LLM request and is privacy
    validated separately.
    """

    validate_report(report)
    portfolio_request_features = dict(report["portfolio_llm_report"]["request_features"])
    validate_privacy_filtered_features(portfolio_request_features)
    customer_results = [
        _customer_llm_auxiliary_result(customer_report)
        for customer_report in report["customer_reports"]
    ]
    auxiliary = {
        "schema_version": LLM_AUXILIARY_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source_artifacts": {
            **dict(report["source_artifacts"]),
            "report_view_model": "data/fixtures/simulation_summary.json",
        },
        "report_mode": report["report_mode"],
        "portfolio_auxiliary_result": {
            "audience": "insurer_staff",
            "language": "ko",
            "generation_mode": report["portfolio_llm_report"]["mode"],
            "request_features": portfolio_request_features,
            "empty_report_result": dict(
                report["portfolio_llm_report"].get("empty_report_result", {})
            ),
            "llm_service_status": dict(report["portfolio_llm_report"].get("llm_service_status", {})),
            "prompt_purpose": "30명 합성 시뮬레이션의 정책 검증 결과를 보험사 직원용 요약문으로 변환",
            "section_drafts": {
                "portfolio_summary": report["portfolio_llm_report"]["summary"],
                "approval_gate": _approval_gate_text(report),
                "critic_context": _critic_context_text(report),
            },
            "privacy_contract": _privacy_contract(),
        },
        "customer_auxiliary_results": customer_results,
        "validation": {
            "passed": True,
            "customer_auxiliary_result_count": len(customer_results),
            "privacy_checked": True,
            "forbidden_external_api_fields_present": [],
            "fallback_ready_count": sum(1 for row in customer_results if row["fallback_available"]),
        },
    }
    validate_llm_report_auxiliary_results(auxiliary, expected_schema_version=LLM_AUXILIARY_SCHEMA_VERSION)
    return auxiliary


def validate_report(report: dict[str, Any]) -> None:
    validate_report_view_model(report, expected_schema_version=SCHEMA_VERSION)


def write_report_json(report: dict[str, Any], output_path: str | Path = DEFAULT_STRUCTURED_OUTPUT) -> None:
    write_structured_json(report, output_path)


def write_llm_report_auxiliary_json(
    auxiliary_results: dict[str, Any],
    output_path: str | Path = DEFAULT_LLM_AUXILIARY_OUTPUT,
) -> None:
    validate_llm_report_auxiliary_results(
        auxiliary_results,
        expected_schema_version=LLM_AUXILIARY_SCHEMA_VERSION,
    )
    write_structured_json(auxiliary_results, output_path)


def write_report_markdown(report: dict[str, Any], output_path: str | Path = DEFAULT_REPORT_OUTPUT) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = report["summary_metrics"]
    lines = [
        "# Senior Safe Mileage Simulation Summary",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Report mode: `{report['report_mode']}`",
        f"- Selected policy: `{report['selected_policy']['candidate_id']}`",
        f"- Approval gate passed: `{report['approval']['approval_gate_passed']}`",
        f"- Critic verdict: `{report['critic_review']['verdict']}`",
        f"- Risk-change capture: `{metrics['proposed_capture_count']}/{metrics['risk_change_target_count']}`",
        f"- Non-target false positives: `{metrics['non_target_false_positive_count']}`",
        f"- Total misclassifications: `{metrics['total_misclassification_count']}`",
        "",
        "## Portfolio Report",
        "",
        report["portfolio_llm_report"]["summary"],
        "",
        "## Critic Follow-ups",
    ]
    for follow_up in report["critic_review"]["required_follow_ups"]:
        lines.append(f"- {follow_up}")
    lines.extend(["", "## Customer Reports"])
    for row in report["customer_reports"]:
        llm_report = row["llm_report"]
        lines.extend(
            [
                "",
                f"### {row['customer_id']} / {row['persona_type']}",
                "",
                f"- Decision: `{row['care_decision']}`",
                f"- Scores: baseline `{row['scores']['mileage_baseline_score']}`, senior `{row['scores']['senior_safe_mileage_score']}`, risk change `{row['scores']['risk_change_score']}`",
                f"- XAI reason codes: `{', '.join(row['xai_reason_codes'])}`",
                f"- Hybrid evaluation: proposed `{row['hybrid_evaluation']['proposed']['verdict']}` "
                f"score `{row['hybrid_evaluation']['proposed']['score']}` / threshold "
                f"`{row['hybrid_evaluation']['proposed']['pass_threshold']}`",
                f"- Hybrid rationale: {llm_report['hybrid_pass_fail_rationale']}",
                f"- Report mode: `{llm_report['mode']}`",
                f"- Staff summary: {llm_report['summary']}",
                f"- Recommended action: {llm_report['recommended_action']}",
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _resolve_openai_client(parameters: dict[str, Any], *, force_llm_failure: bool) -> Any | None:
    if force_llm_failure:
        return None
    if "openai_client" in parameters:
        return parameters["openai_client"]
    if bool(parameters.get("enable_openai_api", False)):
        return OpenAIClient()
    return None


def _apply_openai_report_generation(report: dict[str, Any], openai_client: Any) -> None:
    """Generate LLM text through the shared client without exposing failures."""

    try:
        customer_responses = []
        for row in report["customer_reports"]:
            llm_report = row["llm_report"]
            customer_responses.append(
                openai_client.generate_insurer_report(
                    OpenAIReportRequest(
                        system_prompt=_insurer_report_system_prompt(),
                        user_prompt=_customer_report_user_prompt(row),
                        request_features=dict(llm_report["request_features"]),
                        purpose="insurer_customer_report",
                    )
                )
            )
        portfolio_response = openai_client.generate_insurer_report(
            OpenAIReportRequest(
                system_prompt=_insurer_report_system_prompt(),
                user_prompt=_portfolio_report_user_prompt(report),
                request_features=dict(report["portfolio_llm_report"]["request_features"]),
                purpose="insurer_portfolio_report",
            )
        )
    except Exception as exc:
        _mark_llm_fallback(report, exc)
        return

    for row, response in zip(report["customer_reports"], customer_responses):
        row["llm_report"]["mode"] = "llm_generated"
        row["llm_report"]["summary"] = response.text
        row["llm_report"]["llm_service_status"] = _llm_service_status(
            mode="llm_generated",
            purpose="insurer_customer_report",
        )
        row["llm_report"]["generation"] = {
            "provider": "openai",
            "model": response.model,
            "attempts": response.attempts,
        }
    report["portfolio_llm_report"]["mode"] = "llm_generated"
    report["portfolio_llm_report"]["summary"] = portfolio_response.text
    report["portfolio_llm_report"]["llm_service_status"] = _llm_service_status(
        mode="llm_generated",
        purpose="insurer_portfolio_report",
    )
    report["portfolio_llm_report"]["generation"] = {
        "provider": "openai",
        "model": portfolio_response.model,
        "attempts": portfolio_response.attempts,
    }


def _mark_llm_fallback(report: dict[str, Any], exc: BaseException) -> None:
    error = {
        "error_type": exc.__class__.__name__,
        "message": str(exc),
        "handled_by": "report_agent",
    }
    report["portfolio_llm_report"]["mode"] = "fallback_template"
    report["portfolio_llm_report"]["llm_client_error"] = error
    report["portfolio_llm_report"]["llm_service_status"] = _llm_service_status(
        mode="fallback_template",
        purpose="insurer_portfolio_report",
        exc=exc,
    )
    report["portfolio_llm_report"]["empty_report_result"] = _empty_llm_report_result(
        exc,
        purpose="insurer_portfolio_report",
    )
    for row in report["customer_reports"]:
        row["llm_report"]["mode"] = "fallback_template"
        row["llm_report"]["llm_client_error"] = error
        row["llm_report"]["llm_service_status"] = _llm_service_status(
            mode="fallback_template",
            purpose="insurer_customer_report",
            exc=exc,
        )
        row["llm_report"]["empty_report_result"] = _empty_llm_report_result(
            exc,
            purpose="insurer_customer_report",
        )


def _empty_llm_report_result(exc: BaseException, *, purpose: str) -> dict[str, Any]:
    """Represent a failed external LLM generation as an explicit empty result."""

    return {
        "status": "empty",
        "text": "",
        "purpose": purpose,
        "fallback_reason": "openai_api_call_failed",
        "error_type": exc.__class__.__name__,
        "message": str(exc),
        "handled_by": "report_agent",
        "core_outputs_continue": True,
    }


def _llm_service_status(
    *,
    mode: str,
    purpose: str,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    """Expose external LLM service health separately from local fallback text."""

    if exc is not None:
        return {
            "status": "failed",
            "active": False,
            "available": False,
            "failure_detected": True,
            "report_mode": mode,
            "fallback_active": True,
            "fallback_reason": "openai_api_call_failed",
            "purpose": purpose,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
            "handled_by": "report_agent",
            "core_outputs_continue": True,
        }
    if mode == "llm_generated":
        return {
            "status": "available",
            "active": True,
            "available": True,
            "failure_detected": False,
            "report_mode": mode,
            "fallback_active": False,
            "purpose": purpose,
            "handled_by": "report_agent",
            "core_outputs_continue": True,
        }
    return {
        "status": "inactive",
        "active": False,
        "available": mode != "fallback_template",
        "failure_detected": mode == "fallback_template",
        "report_mode": mode,
        "fallback_active": mode == "fallback_template",
        "fallback_reason": "openai_api_disabled" if mode == "deterministic_template" else "openai_api_call_failed",
        "purpose": purpose,
        "handled_by": "report_agent",
        "core_outputs_continue": True,
    }


def _refresh_llm_report_status(
    report: dict[str, Any],
    evaluation: dict[str, Any],
    critic_review: dict[str, Any],
) -> None:
    customer_modes = [str(row["llm_report"]["mode"]) for row in report["customer_reports"]]
    fallback_count = sum(1 for mode in customer_modes if mode == "fallback_template")
    if fallback_count:
        report["report_mode"] = "fallback_template"
    elif customer_modes and all(mode == "llm_generated" for mode in customer_modes):
        report["report_mode"] = "llm_generated"
    else:
        report["report_mode"] = "deterministic_template"
    report["validation"]["fallback_report_count"] = fallback_count
    report["reason_codes"] = _report_reason_codes(evaluation, critic_review, fallback_count)


def _insurer_report_system_prompt() -> str:
    return (
        "You write concise Korean insurer-staff review notes for Senior Safe Mileage. "
        "Use only the provided deidentified summary features. Do not infer names, "
        "phone numbers, addresses, vehicle numbers, exact GPS coordinates, or raw trip ids."
    )


def _customer_report_user_prompt(customer_report: dict[str, Any]) -> str:
    llm_report = customer_report["llm_report"]
    return (
        "고객별 Senior Safe Mileage 판정 리포트를 작성하세요. "
        f"care_decision={customer_report['care_decision']!r}; "
        f"reason_codes={customer_report['xai_reason_codes']!r}; "
        f"fallback_summary={llm_report['summary']!r}; "
        f"recommended_action={llm_report['recommended_action']!r}"
    )


def _portfolio_report_user_prompt(report: dict[str, Any]) -> str:
    metrics = report["summary_metrics"]
    return (
        "30명 합성 시뮬레이션의 정책 검증 결과를 보험사 직원용 요약문으로 작성하세요. "
        f"approval_gate_passed={report['approval']['approval_gate_passed']}; "
        f"proposed_capture_count={metrics['proposed_capture_count']}; "
        f"risk_change_target_count={metrics['risk_change_target_count']}; "
        f"non_target_false_positive_count={metrics['non_target_false_positive_count']}; "
        f"critic_verdict={report['critic_review']['verdict']!r}"
    )


def _validate_approved_inputs(evaluation: dict[str, Any], critic_review: dict[str, Any]) -> None:
    if not bool(evaluation.get("summary_metrics", {}).get("passes_approval_gate")):
        raise ValueError("Report Agent requires Evaluation Agent approval gate to pass")
    if not bool(critic_review.get("validation", {}).get("passed")):
        raise ValueError("Report Agent requires Critic Agent validation to pass")
    snapshots = list(evaluation.get("customer_snapshots", ()))
    if len(snapshots) != 30:
        raise ValueError("Report Agent requires 30 evaluation customer snapshots")
    for snapshot in snapshots:
        validate_customer_decision_snapshot(snapshot)


def _build_customer_report(
    snapshot: dict[str, Any],
    critic_review: dict[str, Any],
    *,
    force_llm_failure: bool,
) -> dict[str, Any]:
    request_features = dict(snapshot["privacy_filtered_features"])
    validate_privacy_filtered_features(request_features)
    llm_report = _fallback_customer_llm_report(snapshot, critic_review, request_features)
    llm_report["mode"] = "fallback_template" if force_llm_failure else "deterministic_template"
    llm_report["llm_service_status"] = _llm_service_status(
        mode=llm_report["mode"],
        purpose="insurer_customer_report",
    )
    return {
        "customer_id": snapshot["customer_id"],
        "persona_type": snapshot["persona_type"],
        "care_decision": snapshot["care_decision"],
        "scores": {
            "mileage_baseline_score": snapshot["mileage_baseline_score"],
            "senior_safe_mileage_score": snapshot["senior_safe_mileage_score"],
            "risk_change_score": snapshot["risk_change_score"],
        },
        "xai_reason_codes": list(snapshot["reason_codes"]),
        "hybrid_evaluation": dict(snapshot["hybrid_evaluation"]),
        "ab_comparison": dict(snapshot["ab_comparison"]),
        "agent_validation": {
            **dict(snapshot["agent_validation"]),
            "critic_verdict": critic_review["validation"]["verdict"],
        },
        "llm_report": llm_report,
    }


def _customer_llm_auxiliary_result(customer_report: dict[str, Any]) -> dict[str, Any]:
    llm_report = dict(customer_report["llm_report"])
    request_features = dict(llm_report["request_features"])
    validate_privacy_filtered_features(request_features)
    return {
        "customer_id": customer_report["customer_id"],
        "persona_type": customer_report["persona_type"],
        "care_decision": customer_report["care_decision"],
        "audience": "insurer_staff",
        "language": "ko",
        "generation_mode": llm_report["mode"],
        "request_features": request_features,
        "fallback_available": bool(llm_report["fallback_available"]),
        "xai_reason_codes": list(customer_report["xai_reason_codes"]),
        "section_drafts": {
            "title": llm_report["title"],
            "staff_summary": llm_report["summary"],
            "decision_explanation": llm_report["decision_explanation"],
            "recommended_action": llm_report["recommended_action"],
        },
        "privacy_contract": _privacy_contract(),
    }


def _fallback_customer_llm_report(
    snapshot: dict[str, Any],
    critic_review: dict[str, Any],
    request_features: dict[str, Any],
) -> dict[str, Any]:
    decision = str(snapshot["care_decision"])
    risk_score = float(snapshot["risk_change_score"])
    senior_score = float(snapshot["senior_safe_mileage_score"])
    baseline_detected = bool(snapshot["ab_comparison"]["baseline_detected"])
    proposed_detected = bool(snapshot["ab_comparison"]["proposed_detected"])
    reason_codes = list(snapshot["reason_codes"])
    reason_code_narratives = _reason_code_narratives(snapshot)
    summary = _decision_summary(decision, risk_score, senior_score, proposed_detected)
    hybrid_evaluation = dict(snapshot["hybrid_evaluation"])
    return {
        "audience": "insurer_staff",
        "language": "ko",
        "request_features": request_features,
        "fallback_available": True,
        "title": f"Senior Safe Mileage {decision} 판정 리포트",
        "summary": summary,
        "decision_explanation": _decision_explanation(
            reason_codes,
            baseline_detected,
            proposed_detected,
            reason_code_narratives=reason_code_narratives,
        ),
        "hybrid_pass_fail_rationale": _hybrid_pass_fail_rationale(hybrid_evaluation),
        "recommended_action": _recommended_action(decision),
        "xai_reason_codes": reason_codes,
        "reason_code_narratives": reason_code_narratives,
        "hybrid_evaluation": hybrid_evaluation,
        "critic_context": {
            "verdict": critic_review["validation"]["verdict"],
            "required_follow_up_count": len(critic_review["required_follow_ups"]),
        },
        "privacy_notice": "외부 LLM 요청에는 고객 식별자, 원본 trip id, 정확한 GPS 좌표를 포함하지 않습니다.",
    }


def _customer_llm_auxiliary_result(customer_report: dict[str, Any]) -> dict[str, Any]:
    llm_report = dict(customer_report["llm_report"])
    request_features = dict(llm_report["request_features"])
    validate_privacy_filtered_features(request_features)
    return {
        "customer_id": customer_report["customer_id"],
        "persona_type": customer_report["persona_type"],
        "care_decision": customer_report["care_decision"],
        "audience": "insurer_staff",
        "language": "ko",
        "generation_mode": llm_report["mode"],
        "request_features": request_features,
        "empty_report_result": dict(llm_report.get("empty_report_result", {})),
        "llm_service_status": dict(llm_report.get("llm_service_status", {})),
        "prompt_purpose": "고객별 Senior Safe Mileage 판정 근거를 보험사 직원 검토용 문장으로 변환",
        "section_drafts": {
            "title": llm_report["title"],
            "staff_summary": llm_report["summary"],
            "decision_explanation": llm_report["decision_explanation"],
            "reason_code_narrative_summary": _reason_code_narrative_summary(
                list(llm_report.get("reason_code_narratives", ()))
            ),
            "hybrid_pass_fail_rationale": llm_report["hybrid_pass_fail_rationale"],
            "recommended_action": llm_report["recommended_action"],
            "privacy_notice": llm_report["privacy_notice"],
            "caution_notice": llm_report["privacy_notice"],
        },
        "evidence_cards": _customer_evidence_cards(customer_report),
        "xai_reason_codes": list(customer_report["xai_reason_codes"]),
        "reason_code_narratives": list(llm_report.get("reason_code_narratives", ())),
        "hybrid_evaluation": dict(customer_report["hybrid_evaluation"]),
        "ab_comparison": dict(customer_report["ab_comparison"]),
        "fallback_available": bool(llm_report["fallback_available"]),
        "privacy_contract": _privacy_contract(),
    }


def _customer_evidence_cards(customer_report: dict[str, Any]) -> list[dict[str, Any]]:
    scores = customer_report["scores"]
    ab = customer_report["ab_comparison"]
    validation = customer_report["agent_validation"]
    return [
        {
            "card_id": "score_snapshot",
            "title": "판정 점수",
            "metrics": {
                "mileage_baseline_score": scores["mileage_baseline_score"],
                "senior_safe_mileage_score": scores["senior_safe_mileage_score"],
                "risk_change_score": scores["risk_change_score"],
            },
        },
        {
            "card_id": "ab_comparison",
            "title": "A/B 비교",
            "metrics": {
                "baseline_detected": ab["baseline_detected"],
                "proposed_detected": ab["proposed_detected"],
                "baseline_score": ab["baseline_score"],
                "proposed_score": ab["proposed_score"],
            },
        },
        {
            "card_id": "hybrid_evaluation",
            "title": "Hybrid 평가 pass/fail",
            "metrics": {
                "baseline_verdict": customer_report["hybrid_evaluation"]["baseline"]["verdict"],
                "baseline_score": customer_report["hybrid_evaluation"]["baseline"]["score"],
                "proposed_verdict": customer_report["hybrid_evaluation"]["proposed"]["verdict"],
                "proposed_score": customer_report["hybrid_evaluation"]["proposed"]["score"],
                "pass_threshold": customer_report["hybrid_evaluation"]["proposed"]["pass_threshold"],
                "exception_rule": customer_report["hybrid_evaluation"]["proposed"]["exception_rule"] or "none",
            },
        },
        {
            "card_id": "agent_validation",
            "title": "Agent 검증",
            "metrics": {
                "passed": validation["passed"],
                "validation_pass_rate": validation["validation_pass_rate"],
                "critic_verdict": validation["critic_verdict"],
            },
        },
    ]


def _portfolio_request_features(evaluation: dict[str, Any], critic_review: dict[str, Any]) -> dict[str, Any]:
    metrics = evaluation["summary_metrics"]
    return {
        "customer_count": metrics["customer_count"],
        "risk_change_target_count": metrics["risk_change_target_count"],
        "proposed_capture_count": metrics["proposed_capture_count"],
        "non_target_false_positive_count": metrics["non_target_false_positive_count"],
        "total_misclassification_count": metrics["total_misclassification_count"],
        "agent_validation_pass_rate": metrics["agent_validation_pass_rate"],
        "critic_verdict": critic_review["validation"]["verdict"],
        "critic_risk_count": len(critic_review["risks"]),
        "selected_policy_weights": evaluation["selected_policy"]["weights"],
        "selected_policy_thresholds": evaluation["selected_policy"]["thresholds"],
    }


def _portfolio_summary(evaluation: dict[str, Any], critic_review: dict[str, Any]) -> str:
    metrics = evaluation["summary_metrics"]
    return (
        "제안 Senior Safe Mileage Score는 합성 30명 fixture에서 "
        f"저주행 위험변화 대상 {metrics['risk_change_target_count']}명 중 "
        f"{metrics['proposed_capture_count']}명을 포착했고, "
        f"비대상 오탐은 {metrics['non_target_false_positive_count']}명입니다. "
        f"Critic Agent verdict는 {critic_review['validation']['verdict']}입니다."
    )


def _approval_gate_text(report: dict[str, Any]) -> str:
    metrics = report["summary_metrics"]
    return (
        f"승인 게이트는 {metrics['proposed_capture_count']}/"
        f"{metrics['risk_change_target_count']} 위험변화 대상 포착, "
        f"비대상 오탐 {metrics['non_target_false_positive_count']}명, "
        f"전체 오분류 {metrics['total_misclassification_count']}건으로 "
        f"{'통과' if report['approval']['approval_gate_passed'] else '미통과'}했습니다."
    )


def _critic_context_text(report: dict[str, Any]) -> str:
    critic = report["critic_review"]
    return (
        f"Critic Agent verdict는 {critic['verdict']}이며, "
        f"차단 finding {critic['blocking_finding_count']}건과 "
        f"후속 검토 {len(critic['required_follow_ups'])}건이 기록되었습니다."
    )


def _privacy_contract() -> dict[str, Any]:
    return {
        "external_request_source": "request_features",
        "local_join_fields_not_sent": ["customer_id"],
        "forbidden_fields": sorted(FORBIDDEN_EXTERNAL_API_FIELDS),
        "allowed_feature_type": "deidentified_summary_features_only",
    }


def _decision_summary(decision: str, risk_score: float, senior_score: float, proposed_detected: bool) -> str:
    if decision == "예방 케어" or proposed_detected:
        return (
            f"최근 생활권 밖 위험변화 점수 {risk_score:.1f}와 통합 점수 {senior_score:.1f}를 기준으로 "
            "예방 케어 검토가 필요한 고객입니다."
        )
    if decision == "우대":
        return (
            f"통합 점수 {senior_score:.1f}와 낮은 위험변화 점수 {risk_score:.1f}를 기준으로 "
            "생활권 중심 안정 주행 우대 대상입니다."
        )
    return (
        f"통합 점수 {senior_score:.1f}와 위험변화 점수 {risk_score:.1f}를 기준으로 "
        "기본 조건 유지가 적절한 고객입니다."
    )


def _decision_explanation(
    reason_codes: list[str],
    baseline_detected: bool,
    proposed_detected: bool,
    *,
    reason_code_narratives: list[dict[str, str]] | None = None,
) -> str:
    baseline_text = "기존 거리 산식도 위험변화를 포착했습니다" if baseline_detected else "기존 거리 산식은 위험변화 신호를 포착하지 않았습니다"
    proposed_text = "제안 모델은 예방 케어 신호로 분류했습니다" if proposed_detected else "제안 모델은 예방 케어 신호로 분류하지 않았습니다"
    narrative_summary = _reason_code_narrative_summary(reason_code_narratives or [])
    if narrative_summary:
        return f"{baseline_text}. {proposed_text}. {narrative_summary}"
    return f"{baseline_text}. {proposed_text}. 주요 XAI reason code는 {', '.join(reason_codes)}입니다."


def _reason_code_narratives(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    scores = {
        "mileage_baseline_score": float(snapshot["mileage_baseline_score"]),
        "senior_safe_mileage_score": float(snapshot["senior_safe_mileage_score"]),
        "risk_change_score": float(snapshot["risk_change_score"]),
    }
    decision = str(snapshot["care_decision"])
    ab = dict(snapshot["ab_comparison"])
    baseline_detected = bool(ab.get("baseline_detected"))
    proposed_detected = bool(ab.get("proposed_detected"))
    context = {
        "decision": decision,
        "baseline_detected": baseline_detected,
        "proposed_detected": proposed_detected,
        "score_delta": _ab_score_delta(snapshot),
        **scores,
    }
    narratives = [
        {
            "code": str(code),
            "contribution_type": _reason_contribution_type(str(code), baseline_detected, proposed_detected),
            "staff_sentence": _reason_staff_sentence(str(code), context),
            "change_reason": _reason_change_explanation(str(code), context),
        }
        for code in snapshot["reason_codes"]
    ]
    return [row for row in narratives if row["staff_sentence"]]


def _ab_score_delta(snapshot: dict[str, Any]) -> float:
    comparison = dict(snapshot.get("model_comparison_record") or {})
    metrics = dict(comparison.get("metrics") or snapshot.get("ab_comparison", {}).get("metrics") or {})
    core_metrics = dict(comparison.get("core_metrics") or metrics.get("core_metrics") or {})
    difference = dict(core_metrics.get("difference") or {})
    return float(difference.get("score_delta", 0.0))


def _reason_contribution_type(code: str, baseline_detected: bool, proposed_detected: bool) -> str:
    if code == "PROPOSED_MODEL_PREVENTIVE_CARE":
        return "decision_change" if proposed_detected and not baseline_detected else "decision"
    if code in {"OUT_ZONE_PATTERN_CHANGE_RISK", "RECENT_NIGHT_DRIVING_INCREASE", "RISK_EVENT_RATE_INCREASE"}:
        return "risk_change_score"
    if code in {"LIVING_ZONE_STABLE_DRIVING", "LIVING_ZONE_HIGH_STABILITY", "REPEATED_ROUTE_PATTERN"}:
        return "stability_score"
    if code == "LOW_MILEAGE_BASELINE_ELIGIBLE":
        return "baseline_mileage"
    return "supporting_signal"


def _reason_staff_sentence(code: str, context: dict[str, Any]) -> str:
    risk_score = float(context["risk_change_score"])
    senior_score = float(context["senior_safe_mileage_score"])
    baseline_score = float(context["mileage_baseline_score"])
    decision = str(context["decision"])
    templates = {
        "LOW_MILEAGE_BASELINE_ELIGIBLE": (
            f"기존 마일리지 점수 {baseline_score:.1f} 기준으로 저주행 할인 조건은 충족했지만, "
            "이 신호만으로는 최근 위험변화 여부를 설명하기 어렵습니다."
        ),
        "LIVING_ZONE_DBSCAN_P90_INPUT_USED": (
            "DBSCAN/P90 생활권 기준을 적용해 평소 생활권 안팎의 주행 변화를 분리해 검토했습니다."
        ),
        "LIVING_ZONE_STABLE_DRIVING": (
            f"생활권 내 주행은 안정 신호로 반영되어 통합 점수 {senior_score:.1f} 산정에 긍정적으로 기여했습니다."
        ),
        "LIVING_ZONE_HIGH_STABILITY": (
            f"생활권 중심 주행 안정성이 높아 {decision} 판정의 안정성 근거로 활용했습니다."
        ),
        "REPEATED_ROUTE_PATTERN": (
            "반복 경로 비중이 확인되어 일상 생활권 주행 패턴의 예측 가능성을 긍정 신호로 보았습니다."
        ),
        "NEW_DESTINATION_OUT_ZONE_SIGNAL": (
            "최근 생활권 밖 신규 목적지 신호가 있어 기존 저주행 산식보다 변화 검토 필요성이 커졌습니다."
        ),
        "OUT_ZONE_PATTERN_CHANGE_RISK": (
            f"생활권 밖 주행 패턴 변화가 위험변화 점수 {risk_score:.1f} 상승의 핵심 근거입니다."
        ),
        "BORDERLINE_PATTERN_CHANGE_MONITORED": (
            f"위험변화 점수 {risk_score:.1f}가 경계권에 있어 즉시 불이익보다 추적 관찰 근거로 반영했습니다."
        ),
        "NO_STRONG_RISK_CHANGE": (
            f"위험변화 점수 {risk_score:.1f} 기준으로 강한 예방 케어 신호는 확인되지 않았습니다."
        ),
        "RECENT_NIGHT_DRIVING_INCREASE": (
            "최근 야간주행 증가가 생활권 밖 변화와 함께 관찰되어 예방 케어 검토 근거를 보강했습니다."
        ),
        "RISK_EVENT_RATE_INCREASE": (
            "급가감속 등 위험행동 빈도 증가가 최근 30일 위험변화 판단에 영향을 줬습니다."
        ),
        "PROPOSED_MODEL_PREVENTIVE_CARE": (
            "제안 모델은 저주행 할인 여부와 별개로 최근 위험변화를 반영해 예방 케어 판정으로 전환했습니다."
        ),
        "PROPOSED_MODEL_FAVORABLE_OR_STANDARD": (
            f"제안 모델은 위험변화가 제한적이라고 판단해 {decision} 판정을 유지했습니다."
        ),
    }
    return templates.get(code, f"{code} 신호는 {decision} 판정의 보조 근거로 기록했습니다.")


def _reason_change_explanation(code: str, context: dict[str, Any]) -> str:
    baseline_detected = bool(context["baseline_detected"])
    proposed_detected = bool(context["proposed_detected"])
    score_delta = float(context["score_delta"])
    if code == "PROPOSED_MODEL_PREVENTIVE_CARE" and proposed_detected and not baseline_detected:
        return (
            "기존 산식은 연환산 거리 중심이라 위험변화를 놓쳤지만, 제안 모델은 생활권 밖 변화와 "
            f"최근 위험 신호를 반영해 점수 차이 {score_delta:+.1f} 및 판정 변경을 만들었습니다."
        )
    if code in {"OUT_ZONE_PATTERN_CHANGE_RISK", "RECENT_NIGHT_DRIVING_INCREASE", "RISK_EVENT_RATE_INCREASE"}:
        return "baseline 60일 대비 recent 30일 변화가 통합 위험변화 점수에 반영된 사유입니다."
    if code in {"NO_STRONG_RISK_CHANGE", "PROPOSED_MODEL_FAVORABLE_OR_STANDARD"}:
        return "위험변화가 예방 케어 기준을 넘지 않아 판정 변경을 제한한 사유입니다."
    if code == "LOW_MILEAGE_BASELINE_ELIGIBLE":
        return "기존 산식의 할인 가능성을 보여주지만, 제안 모델에서는 위험변화 신호와 함께 재해석됩니다."
    return "점수 산정 또는 판정 설명에 사용된 보조 근거입니다."


def _reason_code_narrative_summary(reason_code_narratives: list[dict[str, str]]) -> str:
    if not reason_code_narratives:
        return ""
    priority = {
        "decision_change": 0,
        "risk_change_score": 1,
        "stability_score": 2,
        "baseline_mileage": 3,
        "decision": 4,
        "supporting_signal": 5,
    }
    selected = sorted(
        reason_code_narratives,
        key=lambda row: priority.get(str(row.get("contribution_type", "")), 99),
    )[:3]
    sentences = [str(row["staff_sentence"]) for row in selected if row.get("staff_sentence")]
    return " ".join(sentences)


def _hybrid_pass_fail_rationale(hybrid_evaluation: dict[str, Any]) -> str:
    proposed = dict(hybrid_evaluation["proposed"])
    baseline = dict(hybrid_evaluation["baseline"])
    exception_rule = proposed.get("exception_rule") or "none"
    return (
        "hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. "
        f"제안 모델은 {float(proposed['score']):.1f}점으로 기준 "
        f"{float(proposed['pass_threshold']):.1f}점 대비 {proposed['verdict']}이며, "
        f"기존 산식은 {float(baseline['score']):.1f}점 {baseline['verdict']}입니다. "
        f"제안 모델 decision_detected={proposed['decision_detected']}, "
        f"ground_truth_target={proposed['ground_truth_target']}, "
        f"proxy_label_target={proposed['proxy_label_target']}, exception_rule={exception_rule}."
    )


def _recommended_action(decision: str) -> str:
    if decision == "예방 케어":
        return "상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다."
    if decision == "우대":
        return "생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다."
    return "기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다."


def _report_reason_codes(evaluation: dict[str, Any], critic_review: dict[str, Any], fallback_count: int) -> list[str]:
    codes = ["REPORT_AGENT_COMPLETED", "INSURER_REPORT_DATA_READY", "XAI_REASON_CODES_ATTACHED"]
    if evaluation["summary_metrics"]["passes_approval_gate"] and critic_review["validation"]["passed"]:
        codes.append("APPROVED_EVALUATION_AND_CRITIC_INPUTS")
    if fallback_count:
        codes.append("LLM_REPORT_FALLBACK_READY")
    codes.extend(str(code) for code in evaluation.get("evaluation_reason_codes", ()))
    codes.extend(str(code) for code in critic_review.get("reason_codes", ()))
    return list(dict.fromkeys(codes))


def _resolve_artifact_path(payload: AgentInputPayload, artifact_id: str, parameter_name: str, default_path: Path) -> Path:
    if parameter_name in payload.parameters:
        return Path(str(payload.parameters[parameter_name]))
    for artifact in payload.input_artifacts:
        if artifact.artifact_id == artifact_id and artifact.path:
            return _project_path(artifact.path)
    return default_path


def _project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def _relative_project_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate insurer-facing Senior Safe Mileage reports.")
    parser.add_argument("--evaluation-view-model", default=str(DEFAULT_EVALUATION_VIEW_MODEL_INPUT))
    parser.add_argument("--critic-review", default=str(DEFAULT_CRITIC_REVIEW_INPUT))
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT_OUTPUT))
    parser.add_argument("--structured-output", default=str(DEFAULT_STRUCTURED_OUTPUT))
    parser.add_argument("--llm-auxiliary-output", default=str(DEFAULT_LLM_AUXILIARY_OUTPUT))
    parser.add_argument("--enable-openai-api", action="store_true")
    parser.add_argument("--require-openai-success", action="store_true")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--force-llm-failure", action="store_true")
    args = parser.parse_args(argv)
    if args.enable_openai_api:
        _load_openai_env_file(Path(args.env_file))

    result = ReportAgent().run(
        AgentInputPayload(
            run_id="report-cli",
            agent_id="report_agent",
            parameters={
                "evaluation_view_model_input": args.evaluation_view_model,
                "critic_review_input": args.critic_review,
                "report_output": args.report_output,
                "structured_output": args.structured_output,
                "llm_auxiliary_output": args.llm_auxiliary_output,
                "force_llm_failure": args.force_llm_failure,
                "enable_openai_api": args.enable_openai_api,
            },
        )
    )
    if result.status != AgentStatus.SUCCEEDED:
        for error in result.errors:
            print(error)
        return 1
    assert result.output_payload is not None
    print(f"report markdown: {args.report_output}")
    print(f"report json: {args.structured_output}")
    print(f"llm auxiliary json: {args.llm_auxiliary_output}")
    print(result.output_payload.metrics)
    print(f"report mode: {result.output_payload.llm_report.get('mode')}")
    print(f"llm service status: {result.output_payload.llm_report.get('llm_service_status', {}).get('status')}")
    if args.require_openai_success and result.output_payload.llm_report.get("mode") != "llm_generated":
        print("OpenAI generation was required but report mode is not llm_generated")
        return 2
    return 0


def _load_openai_env_file(path: Path) -> None:
    """Load OpenAI API settings from a dotenv-style file without echoing secrets."""

    if not path.exists():
        return
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            parsed[key] = value
    api_key = (
        parsed.get("OPENAI_API_KEY")
        or parsed.get("openai_api_key")
        or parsed.get("OPENAI_APIKEY")
        or parsed.get("openai_apikey")
    )
    if api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = api_key
    model = parsed.get("OPENAI_MODEL") or parsed.get("openai_model")
    if model and not os.environ.get("OPENAI_MODEL"):
        os.environ["OPENAI_MODEL"] = model


if __name__ == "__main__":
    raise SystemExit(main())

"""Critic Agent for Evaluation Agent outputs.

The critic is a deterministic reviewer.  It does not rescore customers; it
checks whether Evaluation Agent claims are supported by the A/B results,
whether approval-gate constraints hold, and whether follow-up risks are visible
for the insurer workflow.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents.contracts import (
    FORBIDDEN_EXTERNAL_API_FIELDS,
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentStatus,
    ArtifactType,
    validate_customer_decision_snapshot,
    validate_privacy_filtered_features,
    utc_now_iso,
)
from src.agents.evaluation_agent import DEFAULT_OUTPUT as DEFAULT_AB_RESULTS_INPUT
from src.agents.evaluation_agent import DEFAULT_VIEW_MODEL_OUTPUT
from src.agents.structured_outputs import load_structured_json, validate_critic_review, write_structured_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_OUTPUT = ROOT / "data" / "fixtures" / "rule_review.md"
DEFAULT_STRUCTURED_OUTPUT = ROOT / "data" / "fixtures" / "rule_review.json"
SCHEMA_VERSION = "senior-critic-rule-review/v1"


class CriticAgent:
    """Review evaluation outputs for gate failures, fairness risks, and follow-ups."""

    metadata = AgentMetadata(
        agent_id="critic_agent",
        role=AgentRole.CRITIC,
        display_name="Critic Agent",
        description="Reviews Evaluation Agent outputs for validation findings, risks, and follow-ups.",
        consumes=("ab_test_results.csv", "candidate_rules.json"),
        produces=("rule_review.md", "rule_review.json"),
    )

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            ab_results_input = _resolve_artifact_path(
                payload,
                "ab_test_results.csv",
                "ab_results_input",
                DEFAULT_AB_RESULTS_INPUT,
            )
            view_model_input = _resolve_artifact_path(
                payload,
                "evaluation_view_model.json",
                "view_model_input",
                DEFAULT_VIEW_MODEL_OUTPUT,
            )
            review_output = Path(str(payload.parameters.get("review_output", DEFAULT_REVIEW_OUTPUT)))
            structured_output = Path(str(payload.parameters.get("structured_output", DEFAULT_STRUCTURED_OUTPUT)))

            evaluation = load_evaluation_outputs(ab_results_input=ab_results_input, view_model_input=view_model_input)
            review = review_evaluation_outputs(evaluation)
            write_rule_review_markdown(review, review_output)
            write_rule_review_json(review, structured_output)

            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="rule_review.md",
                        artifact_type=ArtifactType.MARKDOWN,
                        path=_relative_project_path(review_output),
                        rows=len(review["findings"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "passed": review["validation"]["passed"],
                            "blocking_findings": review["validation"]["blocking_finding_count"],
                        },
                    ),
                    AgentArtifact(
                        artifact_id="rule_review.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_project_path(structured_output),
                        rows=len(review["findings"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "risk_count": len(review["risks"]),
                            "required_follow_up_count": len(review["required_follow_ups"]),
                        },
                    ),
                ),
                metrics={
                    "customer_count": review["metrics"]["customer_count"],
                    "risk_change_target_count": review["metrics"]["risk_change_target_count"],
                    "risk_change_capture_count": review["metrics"]["risk_change_capture_count"],
                    "non_target_false_positive_count": review["metrics"]["non_target_false_positive_count"],
                    "total_misclassification_count": review["metrics"]["total_misclassification_count"],
                    "agent_validation_pass_rate": review["metrics"]["agent_validation_pass_rate"],
                    "blocking_finding_count": review["validation"]["blocking_finding_count"],
                    "required_follow_up_count": len(review["required_follow_ups"]),
                    "passed": review["validation"]["passed"],
                },
                decisions={
                    "approval_gate_passed": review["validation"]["approval_gate_passed"],
                    "critic_verdict": review["validation"]["verdict"],
                    "persona_misclassification_counts": review["persona_misclassification_counts"],
                },
                reason_codes=tuple(review["reason_codes"]),
                validation={
                    **review["validation"],
                    "findings": review["findings"],
                    "risks": review["risks"],
                    "required_follow_ups": review["required_follow_ups"],
                },
                messages=("critic review generated for Evaluation Agent outputs",),
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


def load_evaluation_outputs(
    *,
    ab_results_input: Path = DEFAULT_AB_RESULTS_INPUT,
    view_model_input: Path = DEFAULT_VIEW_MODEL_OUTPUT,
) -> dict[str, Any]:
    customer_rows = _read_ab_rows(ab_results_input)
    view_model = load_structured_json(view_model_input) if view_model_input.exists() else {}
    return {
        "schema_version": SCHEMA_VERSION + "/input",
        "source_artifacts": {
            "ab_results_input": _relative_project_path(ab_results_input),
            "view_model_input": _relative_project_path(view_model_input),
        },
        "summary_metrics": dict(view_model.get("summary_metrics") or _summary_metrics_from_rows(customer_rows)),
        "evaluation_reason_codes": list(view_model.get("evaluation_reason_codes", ())),
        "selected_policy": dict(view_model.get("selected_policy", {})),
        "customer_rows": customer_rows,
        "customer_snapshots": list(view_model.get("customer_snapshots", ())),
    }


def review_evaluation_outputs(evaluation: dict[str, Any]) -> dict[str, Any]:
    rows = list(evaluation["customer_rows"])
    snapshots = list(evaluation.get("customer_snapshots", ()))
    metrics = _normalize_metrics(evaluation.get("summary_metrics") or _summary_metrics_from_rows(rows))
    findings: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    follow_ups: list[dict[str, Any]] = []

    _add_gate_findings(metrics, findings, follow_ups)
    persona_counts = _persona_misclassification_counts(rows)
    _add_persona_findings(persona_counts, findings, risks, follow_ups)
    _add_claim_findings(evaluation, metrics, findings, follow_ups)
    _add_privacy_findings(rows, snapshots, findings, follow_ups)
    _add_fairness_risks(rows, persona_counts, risks, follow_ups)

    risks.append(
        {
            "code": "SYNTHETIC_ONLY_GENERALIZATION_RISK",
            "severity": "medium",
            "message": "Current approval evidence is based on the 30-customer synthetic fixture only.",
            "evidence": {"fixture_customer_count": metrics["customer_count"]},
            "required_follow_up": "Before launch, rerun the same gate on a larger de-identified holdout fixture.",
        }
    )
    if not follow_ups:
        follow_ups.append("Keep Critic Agent review attached to every candidate policy promotion.")

    blocking_count = sum(1 for finding in findings if finding["blocking"])
    approval_gate_passed = _approval_gate_passed(metrics)
    passed = blocking_count == 0 and approval_gate_passed
    reason_codes = ["CRITIC_REVIEW_COMPLETED"]
    reason_codes.append("CRITIC_APPROVAL_GATE_PASSED" if passed else "CRITIC_APPROVAL_GATE_BLOCKED")
    if risks:
        reason_codes.append("CRITIC_RISKS_RECORDED")
    if follow_ups:
        reason_codes.append("CRITIC_FOLLOW_UPS_RECORDED")

    review = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source_artifacts": evaluation["source_artifacts"],
        "selected_policy": evaluation.get("selected_policy", {}),
        "metrics": metrics,
        "findings": findings,
        "risks": risks,
        "required_follow_ups": _unique(follow_ups),
        "persona_misclassification_counts": persona_counts,
        "validation": {
            "passed": passed,
            "approval_gate_passed": approval_gate_passed,
            "verdict": "pass" if passed else "requires_follow_up",
            "blocking_finding_count": blocking_count,
            "finding_count": len(findings),
            "risk_count": len(risks),
            "required_follow_up_count": len(_unique(follow_ups)),
            "criteria": {
                "risk_change_capture_minimum": 4,
                "non_target_false_positive_maximum": 3,
                "total_misclassification_maximum": 4,
                "agent_validation_pass_rate_minimum": 0.95,
            },
        },
        "reason_codes": reason_codes,
    }
    validate_rule_review(review)
    return review


def validate_rule_review(review: dict[str, Any]) -> None:
    validate_critic_review(review, expected_schema_version=SCHEMA_VERSION)


def write_rule_review_json(review: dict[str, Any], output_path: str | Path = DEFAULT_STRUCTURED_OUTPUT) -> None:
    write_structured_json(review, output_path)


def write_rule_review_markdown(review: dict[str, Any], output_path: str | Path = DEFAULT_REVIEW_OUTPUT) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = review["metrics"]
    lines = [
        "# Critic Agent Rule Review",
        "",
        f"- Schema: `{review['schema_version']}`",
        f"- Verdict: `{review['validation']['verdict']}`",
        f"- Approval gate passed: `{review['validation']['approval_gate_passed']}`",
        f"- Customer count: `{metrics['customer_count']}`",
        f"- Risk-change capture: `{metrics['risk_change_capture_count']}/{metrics['risk_change_target_count']}`",
        f"- Non-target false positives: `{metrics['non_target_false_positive_count']}`",
        f"- Total misclassifications: `{metrics['total_misclassification_count']}`",
        f"- Agent validation pass rate: `{metrics['agent_validation_pass_rate']}`",
        "",
        "## Findings",
    ]
    for finding in review["findings"] or [{"code": "NO_BLOCKING_FINDINGS", "severity": "info", "message": "No blocking critic findings.", "blocking": False}]:
        lines.append(
            f"- `{finding['severity']}` `{finding['code']}` blocking=`{finding['blocking']}`: {finding['message']}"
        )
    lines.extend(["", "## Risks"])
    for risk in review["risks"]:
        lines.append(f"- `{risk['severity']}` `{risk['code']}`: {risk['message']}")
    lines.extend(["", "## Required Follow-ups"])
    for follow_up in review["required_follow_ups"]:
        lines.append(f"- {follow_up}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _read_ab_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = [_normalize_row(row) for row in csv.DictReader(file)]
    if len(rows) != 30:
        raise ValueError("critic review expects 30 customer rows from Evaluation Agent")
    return rows


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(row)
    for key in (
        "risk_change_target",
        "baseline_detected",
        "proposed_detected",
    ):
        normalized[key] = bool(int(row[key]))
    for key in (
        "mileage_baseline_score",
        "in_zone_safe_score",
        "out_zone_safe_score",
        "risk_change_score",
        "senior_safe_mileage_score",
    ):
        normalized[key] = float(row[key])
    normalized["reason_codes"] = json.loads(row.get("reason_codes_json") or "[]")
    normalized["ab_comparison"] = json.loads(row.get("ab_comparison_json") or "{}")
    normalized["privacy_filtered_features"] = json.loads(row.get("privacy_filtered_features_json") or "{}")
    return normalized


def _normalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_count": int(metrics["customer_count"]),
        "risk_change_target_count": int(metrics["risk_change_target_count"]),
        "baseline_capture_count": int(metrics["baseline_capture_count"]),
        "risk_change_capture_count": int(metrics.get("proposed_capture_count", metrics.get("risk_change_capture_count", 0))),
        "baseline_low_mileage_high_risk_capture": float(metrics["baseline_low_mileage_high_risk_capture"]),
        "proposed_low_mileage_high_risk_capture": float(metrics["proposed_low_mileage_high_risk_capture"]),
        "non_target_false_positive_count": int(metrics["non_target_false_positive_count"]),
        "false_negative_count": int(metrics["false_negative_count"]),
        "total_misclassification_count": int(metrics["total_misclassification_count"]),
        "agent_validation_pass_rate": float(metrics["agent_validation_pass_rate"]),
        "passes_approval_gate": bool(metrics["passes_approval_gate"]),
    }


def _summary_metrics_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_rows = [row for row in rows if row["risk_change_target"]]
    non_target_rows = [row for row in rows if not row["risk_change_target"]]
    proposed_capture_count = sum(1 for row in target_rows if row["proposed_detected"])
    baseline_capture_count = sum(1 for row in target_rows if row["baseline_detected"])
    false_positive_count = sum(1 for row in non_target_rows if row["proposed_detected"])
    false_negative_count = len(target_rows) - proposed_capture_count
    misclassification_count = false_positive_count + false_negative_count
    pass_rate = 1.0 if proposed_capture_count >= 4 and false_positive_count <= 3 and misclassification_count <= 4 else 0.9
    return {
        "customer_count": len(rows),
        "risk_change_target_count": len(target_rows),
        "baseline_capture_count": baseline_capture_count,
        "proposed_capture_count": proposed_capture_count,
        "baseline_low_mileage_high_risk_capture": round(baseline_capture_count / max(1, len(target_rows)), 4),
        "proposed_low_mileage_high_risk_capture": round(proposed_capture_count / max(1, len(target_rows)), 4),
        "non_target_false_positive_count": false_positive_count,
        "false_negative_count": false_negative_count,
        "total_misclassification_count": misclassification_count,
        "agent_validation_pass_rate": pass_rate,
        "passes_approval_gate": _approval_gate_passed(
            {
                "risk_change_capture_count": proposed_capture_count,
                "non_target_false_positive_count": false_positive_count,
                "total_misclassification_count": misclassification_count,
                "agent_validation_pass_rate": pass_rate,
            }
        ),
    }


def _add_gate_findings(metrics: dict[str, Any], findings: list[dict[str, Any]], follow_ups: list[str]) -> None:
    checks = (
        ("RISK_CHANGE_CAPTURE_BELOW_GATE", metrics["risk_change_capture_count"] >= 4, "저주행 위험변화형 5명 중 4명 이상 포착 필요"),
        ("FALSE_POSITIVE_ABOVE_GATE", metrics["non_target_false_positive_count"] <= 3, "나머지 25명 중 오탐 3명 이하 필요"),
        ("MISCLASSIFICATION_ABOVE_GATE", metrics["total_misclassification_count"] <= 4, "전체 오분류 4건 이하 필요"),
        ("AGENT_VALIDATION_RATE_BELOW_GATE", metrics["agent_validation_pass_rate"] >= 0.95, "Agent 검증 통과율 95% 이상 필요"),
    )
    for code, passed, message in checks:
        if passed:
            continue
        findings.append(
            {
                "code": code,
                "severity": "high",
                "message": message,
                "evidence": metrics,
                "required_follow_up": "Policy Search Agent must propose a revised candidate and Evaluation Agent must rerun A/B metrics.",
                "blocking": True,
            }
        )
        follow_ups.append("Revise policy candidate and rerun Evaluation Agent before Report Agent promotion.")


def _add_persona_findings(
    persona_counts: dict[str, int],
    findings: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    follow_ups: list[str],
) -> None:
    for persona_type, count in persona_counts.items():
        if count == 0:
            continue
        risks.append(
            {
                "code": "PERSONA_MISCLASSIFICATION_REVIEW",
                "severity": "medium",
                "message": f"{persona_type} persona has {count} proposed-model misclassification(s).",
                "evidence": {"persona_type": persona_type, "misclassification_count": count},
                "required_follow_up": "Inspect customer-level reason codes and scenario assumptions for this persona.",
            }
        )
        follow_ups.append(f"Review misclassified `{persona_type}` customers before using the candidate in demos.")
        if count >= 3:
            findings.append(
                {
                    "code": "PERSONA_CLUSTER_FAILURE",
                    "severity": "high",
                    "message": f"{persona_type} has concentrated misclassification count {count}.",
                    "evidence": {"persona_type": persona_type, "misclassification_count": count},
                    "required_follow_up": "Add persona-specific thresholds or regenerate scenarios for this cluster.",
                    "blocking": True,
                }
            )


def _add_claim_findings(
    evaluation: dict[str, Any],
    metrics: dict[str, Any],
    findings: list[dict[str, Any]],
    follow_ups: list[str],
) -> None:
    reason_codes = set(evaluation.get("evaluation_reason_codes", ()))
    if "PROPOSED_MODEL_OUTPERFORMS_DISTANCE_BASELINE" in reason_codes:
        if metrics["proposed_low_mileage_high_risk_capture"] <= metrics["baseline_low_mileage_high_risk_capture"]:
            findings.append(
                {
                    "code": "UNSUPPORTED_AB_SUPERIORITY_CLAIM",
                    "severity": "high",
                    "message": "Evaluation claims proposed-model superiority, but capture metrics do not support it.",
                    "evidence": metrics,
                    "required_follow_up": "Remove superiority claim or rerun Evaluation Agent with corrected metrics.",
                    "blocking": True,
                }
            )
            follow_ups.append("Reconcile Evaluation Agent reason codes with A/B metric evidence.")


def _add_privacy_findings(
    rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    follow_ups: list[str],
) -> None:
    privacy_errors: list[str] = []
    for row in rows:
        try:
            validate_privacy_filtered_features(row["privacy_filtered_features"])
        except ValueError as exc:
            privacy_errors.append(f"{row['customer_id']}: {exc}")
    for snapshot in snapshots:
        try:
            validate_customer_decision_snapshot(snapshot)
        except ValueError as exc:
            privacy_errors.append(f"{snapshot.get('customer_id', 'unknown')}: {exc}")
    forbidden_text_hits = [
        field
        for field in sorted(FORBIDDEN_EXTERNAL_API_FIELDS)
        if field in json.dumps([row["privacy_filtered_features"] for row in rows], ensure_ascii=True).lower()
    ]
    if forbidden_text_hits:
        privacy_errors.append(f"privacy feature envelope contains forbidden field text: {forbidden_text_hits}")
    if privacy_errors:
        findings.append(
            {
                "code": "PRIVACY_FILTER_FAILURE",
                "severity": "critical",
                "message": "Evaluation output contains fields forbidden for external LLM requests.",
                "evidence": {"errors": privacy_errors[:10]},
                "required_follow_up": "Strip forbidden identifiers and exact trip/GPS fields before Report Agent calls any LLM.",
                "blocking": True,
            }
        )
        follow_ups.append("Fix privacy-filtered feature envelopes and rerun Evaluation Agent.")


def _add_fairness_risks(
    rows: list[dict[str, Any]],
    persona_counts: dict[str, int],
    risks: list[dict[str, Any]],
    follow_ups: list[str],
) -> None:
    preventive_by_persona: dict[str, int] = defaultdict(int)
    totals_by_persona: dict[str, int] = defaultdict(int)
    for row in rows:
        totals_by_persona[row["persona_type"]] += 1
        if row["care_decision"] == "예방 케어":
            preventive_by_persona[row["persona_type"]] += 1
    for persona_type, total in sorted(totals_by_persona.items()):
        rate = preventive_by_persona[persona_type] / max(1, total)
        if rate >= 0.8 and persona_counts.get(persona_type, 0):
            risks.append(
                {
                    "code": "PREVENTIVE_CARE_CONCENTRATION_RISK",
                    "severity": "medium",
                    "message": f"{persona_type} has concentrated preventive-care outcomes with observed errors.",
                    "evidence": {"preventive_care_rate": round(rate, 4), "misclassification_count": persona_counts.get(persona_type, 0)},
                    "required_follow_up": "Check whether thresholds are proxying persona membership rather than risk change evidence.",
                }
            )
            follow_ups.append(f"Audit `{persona_type}` preventive-care concentration for fairness narrative.")


def _persona_misclassification_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if bool(row["proposed_detected"]) != bool(row["risk_change_target"]):
            counts[row["persona_type"]] += 1
    return dict(sorted(counts.items()))


def _approval_gate_passed(metrics: dict[str, Any]) -> bool:
    return (
        int(metrics["risk_change_capture_count"]) >= 4
        and int(metrics["non_target_false_positive_count"]) <= 3
        and int(metrics["total_misclassification_count"]) <= 4
        and float(metrics["agent_validation_pass_rate"]) >= 0.95
    )


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items


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
    parser = argparse.ArgumentParser(description="Review Evaluation Agent outputs with the Critic Agent.")
    parser.add_argument("--ab-results", default=str(DEFAULT_AB_RESULTS_INPUT), help="A/B CSV input path")
    parser.add_argument("--view-model", default=str(DEFAULT_VIEW_MODEL_OUTPUT), help="Evaluation view-model JSON input path")
    parser.add_argument("--review-output", default=str(DEFAULT_REVIEW_OUTPUT), help="Markdown review output path")
    parser.add_argument("--structured-output", default=str(DEFAULT_STRUCTURED_OUTPUT), help="Structured JSON review output path")
    args = parser.parse_args(argv)

    result = CriticAgent().run(
        AgentInputPayload(
            run_id="critic-cli",
            agent_id="critic_agent",
            parameters={
                "ab_results_input": args.ab_results,
                "view_model_input": args.view_model,
                "review_output": args.review_output,
                "structured_output": args.structured_output,
            },
        )
    )
    if result.status != AgentStatus.SUCCEEDED:
        for error in result.errors:
            print(error)
        return 1
    assert result.output_payload is not None
    print(f"rule review: {args.review_output}")
    print(f"structured review: {args.structured_output}")
    print(result.output_payload.validation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Structured output schemas for Evaluation, Critic, Report, and UI views."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.contracts import (
    assert_required_keys,
    validate_customer_decision_snapshot,
    validate_privacy_filtered_features,
)


EVALUATION_VIEW_MODEL_SCHEMA = "senior-evaluation-results/v1"
CRITIC_REVIEW_SCHEMA = "senior-critic-rule-review/v1"
REPORT_VIEW_MODEL_SCHEMA = "senior-report-agent/v1"
LLM_REPORT_AUXILIARY_SCHEMA = "senior-llm-report-auxiliary-results/v1"
UI_DASHBOARD_BUNDLE_SCHEMA = "senior-safe-mileage-ui-dashboard/v1"
AGENT_VALIDATION_PASS_RATE_MINIMUM = 0.95

REQUIRED_EVALUATION_VIEW_MODEL_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "source_artifacts",
        "selected_policy",
        "summary_metrics",
        "evaluation_reason_codes",
        "customer_rows",
        "customer_snapshots",
    }
)

REQUIRED_EVALUATION_METRIC_KEYS = frozenset(
    {
        "customer_count",
        "risk_change_target_count",
        "non_target_count",
        "baseline_capture_count",
        "proposed_capture_count",
        "baseline_low_mileage_high_risk_capture",
        "proposed_low_mileage_high_risk_capture",
        "non_target_false_positive_count",
        "non_target_false_positive_limit",
        "passes_non_target_false_positive_gate",
        "false_negative_count",
        "total_misclassification_count",
        "total_misclassification_limit",
        "passes_misclassification_check",
        "misclassification_check",
        "agent_validation_pass_rate",
        "passes_approval_gate",
    }
)

REQUIRED_CRITIC_REVIEW_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "source_artifacts",
        "metrics",
        "findings",
        "risks",
        "required_follow_ups",
        "persona_misclassification_counts",
        "validation",
        "reason_codes",
    }
)

REQUIRED_REPORT_VIEW_MODEL_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "source_artifacts",
        "report_mode",
        "approval",
        "selected_policy",
        "summary_metrics",
        "critic_review",
        "portfolio_llm_report",
        "customer_reports",
        "reason_codes",
        "validation",
    }
)

REQUIRED_LLM_REPORT_AUXILIARY_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "source_artifacts",
        "report_mode",
        "portfolio_auxiliary_result",
        "customer_auxiliary_results",
        "validation",
    }
)


@dataclass(frozen=True)
class StructuredOutputEnvelope:
    """Small file/API envelope used by downstream local web views."""

    artifact_id: str
    schema_version: str
    payload: dict[str, Any]

    def validate(self) -> None:
        if not self.artifact_id:
            raise ValueError("structured output artifact_id is required")
        if self.payload.get("schema_version") != self.schema_version:
            raise ValueError(
                f"{self.artifact_id} schema_version mismatch: expected={self.schema_version} "
                f"actual={self.payload.get('schema_version')}"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }


def load_structured_json(path: str | Path, *, expected_schema_version: str | None = None) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if expected_schema_version and payload.get("schema_version") != expected_schema_version:
        raise ValueError(
            f"invalid structured output schema_version for {path}: "
            f"expected={expected_schema_version} actual={payload.get('schema_version')}"
        )
    return payload


def write_structured_json(payload: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_evaluation_view_model(
    view_model: dict[str, Any],
    *,
    expected_schema_version: str = EVALUATION_VIEW_MODEL_SCHEMA,
    expected_customer_count: int = 30,
) -> None:
    assert_required_keys("evaluation_view_model", view_model, REQUIRED_EVALUATION_VIEW_MODEL_KEYS)
    if view_model["schema_version"] != expected_schema_version:
        raise ValueError("invalid evaluation schema_version")
    metrics = dict(view_model["summary_metrics"])
    assert_required_keys("evaluation.summary_metrics", metrics, REQUIRED_EVALUATION_METRIC_KEYS)
    if int(metrics["customer_count"]) != expected_customer_count:
        raise ValueError(f"evaluation customer_count must be {expected_customer_count}")
    if int(metrics["risk_change_target_count"]) != 5:
        raise ValueError("evaluation fixture must include five risk-change targets")
    if int(metrics["non_target_count"]) != expected_customer_count - 5:
        raise ValueError("evaluation fixture must include 25 non-target customers")
    if int(metrics["non_target_false_positive_count"]) > int(metrics["non_target_false_positive_limit"]):
        raise ValueError("non-target false positives exceed approval limit")
    if not bool(metrics["passes_non_target_false_positive_gate"]):
        raise ValueError("non-target false-positive gate must pass")
    misclassification_check = dict(metrics["misclassification_check"])
    if misclassification_check.get("schema_version") != "senior-safe-mileage-misclassification-check/v1":
        raise ValueError("invalid misclassification_check schema_version")
    if int(misclassification_check["customer_count"]) != expected_customer_count:
        raise ValueError(f"misclassification_check must cover {expected_customer_count} customers")
    if int(metrics["total_misclassification_limit"]) != int(misclassification_check["limit"]):
        raise ValueError("total_misclassification_limit must match misclassification_check")
    if int(metrics["total_misclassification_count"]) != int(misclassification_check["count"]):
        raise ValueError("total_misclassification_count must match misclassification_check")
    if int(misclassification_check["count"]) > int(misclassification_check["limit"]):
        raise ValueError("misclassification_check count exceeds approval limit")
    if not bool(metrics["passes_misclassification_check"]) or not bool(misclassification_check["passed"]):
        raise ValueError("misclassification_check must pass")
    if len(view_model["customer_rows"]) != expected_customer_count:
        raise ValueError(f"evaluation customer_rows must include {expected_customer_count} customers")
    if len(view_model["customer_snapshots"]) != expected_customer_count:
        raise ValueError(f"evaluation customer_snapshots must include {expected_customer_count} customers")
    for snapshot in view_model["customer_snapshots"]:
        validate_customer_decision_snapshot(snapshot)
    comparison_dataset = view_model.get("comparison_dataset")
    if comparison_dataset is not None:
        if comparison_dataset.get("schema_version") != "senior-safe-mileage-ab-comparison-dataset/v1":
            raise ValueError("invalid comparison_dataset schema_version")
        if int(comparison_dataset.get("customer_count", 0)) != expected_customer_count:
            raise ValueError(f"comparison_dataset must include {expected_customer_count} customers")
        if not comparison_dataset.get("same_input_contract", {}).get(
            "baseline_and_proposed_share_input_data_ref"
        ):
            raise ValueError("comparison_dataset must prove baseline/proposed same input")
        if len(comparison_dataset.get("by_customer_id", {})) != expected_customer_count:
            raise ValueError("comparison_dataset by_customer_id must support every customer lookup")
        comparison_summary = dict(comparison_dataset.get("comparison_summary") or {})
        if comparison_summary.get("schema_version") != "senior-safe-mileage-ab-comparison-summary/v1":
            raise ValueError("comparison_dataset must include a valid comparison_summary")
        if int(comparison_summary.get("customer_count", 0)) != expected_customer_count:
            raise ValueError("comparison_summary must cover every customer")
        if not comparison_summary.get("customer_decision_differences"):
            raise ValueError("comparison_summary must include customer decision differences")
    if (
        float(metrics["proposed_low_mileage_high_risk_capture"])
        <= float(metrics["baseline_low_mileage_high_risk_capture"])
    ):
        raise ValueError("proposed model must outperform the distance-only baseline for risk-change capture")
    if float(metrics["agent_validation_pass_rate"]) < AGENT_VALIDATION_PASS_RATE_MINIMUM:
        raise ValueError(
            "evaluation agent_validation_pass_rate must be at least "
            f"{AGENT_VALIDATION_PASS_RATE_MINIMUM}"
        )


def validate_critic_review(
    review: dict[str, Any],
    *,
    expected_schema_version: str = CRITIC_REVIEW_SCHEMA,
) -> None:
    assert_required_keys("critic_review", review, REQUIRED_CRITIC_REVIEW_KEYS)
    if review["schema_version"] != expected_schema_version:
        raise ValueError("invalid critic review schema_version")
    validation = dict(review["validation"])
    if validation.get("passed") and int(validation.get("blocking_finding_count", 0)):
        raise ValueError("critic review cannot pass with blocking findings")
    if not review["risks"]:
        raise ValueError("critic review must include at least one risk entry")
    if not review["required_follow_ups"]:
        raise ValueError("critic review must include required follow-ups")


def validate_report_view_model(
    report: dict[str, Any],
    *,
    expected_schema_version: str = REPORT_VIEW_MODEL_SCHEMA,
    expected_customer_count: int = 30,
) -> None:
    assert_required_keys("report_view_model", report, REQUIRED_REPORT_VIEW_MODEL_KEYS)
    if report["schema_version"] != expected_schema_version:
        raise ValueError("invalid report schema_version")
    if not report["approval"]["ready_for_insurer_review"]:
        raise ValueError("report is not approved for insurer review")
    if len(report["customer_reports"]) != expected_customer_count:
        raise ValueError(f"report must include {expected_customer_count} customer reports")
    validate_privacy_filtered_features(report["portfolio_llm_report"]["request_features"])
    for customer_report in report["customer_reports"]:
        validate_privacy_filtered_features(customer_report["llm_report"]["request_features"])
        if not customer_report["xai_reason_codes"]:
            raise ValueError("customer report must include XAI reason codes")
        if not customer_report["llm_report"].get("reason_code_narratives"):
            raise ValueError("customer report must include insurer-staff reason code narratives")


def validate_llm_report_auxiliary_results(
    auxiliary: dict[str, Any],
    *,
    expected_schema_version: str = LLM_REPORT_AUXILIARY_SCHEMA,
    expected_customer_count: int = 30,
) -> None:
    assert_required_keys("llm_report_auxiliary_results", auxiliary, REQUIRED_LLM_REPORT_AUXILIARY_KEYS)
    if auxiliary["schema_version"] != expected_schema_version:
        raise ValueError("invalid LLM report auxiliary schema_version")
    customers = list(auxiliary["customer_auxiliary_results"])
    if len(customers) != expected_customer_count:
        raise ValueError(f"LLM report auxiliary results must include {expected_customer_count} customers")
    validate_privacy_filtered_features(auxiliary["portfolio_auxiliary_result"]["request_features"])
    for customer in customers:
        validate_privacy_filtered_features(customer["request_features"])
        if not customer.get("xai_reason_codes"):
            raise ValueError("LLM report auxiliary customer result must include XAI reason codes")
        if not customer.get("reason_code_narratives"):
            raise ValueError("LLM report auxiliary customer result must include reason code narratives")
        if not customer.get("section_drafts", {}).get("staff_summary"):
            raise ValueError("LLM report auxiliary customer result must include staff summary draft")
        if not customer.get("section_drafts", {}).get("decision_explanation"):
            raise ValueError("LLM report auxiliary customer result must include key evidence draft")
        if not customer.get("section_drafts", {}).get("recommended_action"):
            raise ValueError("LLM report auxiliary customer result must include recommended action draft")
        if not (
            customer.get("section_drafts", {}).get("caution_notice")
            or customer.get("section_drafts", {}).get("privacy_notice")
        ):
            raise ValueError("LLM report auxiliary customer result must include caution notice draft")
    validation = dict(auxiliary["validation"])
    if not validation.get("privacy_checked"):
        raise ValueError("LLM report auxiliary results must pass privacy checks")
    if validation.get("forbidden_external_api_fields_present"):
        raise ValueError("LLM report auxiliary results contain forbidden external API fields")


def build_ui_dashboard_bundle(
    evaluation_view_model: dict[str, Any],
    *,
    critic_review: dict[str, Any] | None = None,
    report_view_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine agent outputs into the local webapp's display-ready view model."""

    validate_evaluation_view_model(evaluation_view_model)
    if critic_review is not None:
        validate_critic_review(critic_review)
    if report_view_model is not None:
        validate_report_view_model(report_view_model)

    metrics = evaluation_view_model["summary_metrics"]
    customers = [
        {
            "customer_id": snapshot["customer_id"],
            "persona_type": snapshot["persona_type"],
            "care_decision": snapshot["care_decision"],
            "scores": {
                "mileage_baseline_score": snapshot["mileage_baseline_score"],
                "senior_safe_mileage_score": snapshot["senior_safe_mileage_score"],
                "risk_change_score": snapshot["risk_change_score"],
            },
            "xai_reason_codes": list(snapshot["reason_codes"]),
            "proxy_label": dict(snapshot.get("proxy_label", {})),
            "hybrid_evaluation": dict(snapshot.get("hybrid_evaluation", {})),
            "ab_comparison": dict(snapshot["ab_comparison"]),
            "model_comparison_record": dict(snapshot.get("model_comparison_record", {})),
            "agent_validation": dict(snapshot["agent_validation"]),
            "llm_report": _customer_report_lookup(report_view_model).get(snapshot["customer_id"], snapshot["llm_report"]),
        }
        for snapshot in evaluation_view_model["customer_snapshots"]
    ]
    bundle = {
        "schema_version": UI_DASHBOARD_BUNDLE_SCHEMA,
        "selected_policy": dict(evaluation_view_model["selected_policy"]),
        "approval_gate": {
            "passed": bool(metrics["passes_approval_gate"]),
            "risk_change_capture_count": int(metrics["proposed_capture_count"]),
            "risk_change_target_count": int(metrics["risk_change_target_count"]),
            "non_target_count": int(metrics["non_target_count"]),
            "non_target_false_positive_count": int(metrics["non_target_false_positive_count"]),
            "non_target_false_positive_limit": int(metrics["non_target_false_positive_limit"]),
            "passes_non_target_false_positive_gate": bool(metrics["passes_non_target_false_positive_gate"]),
            "non_target_false_positive_customer_ids": list(
                metrics.get("non_target_false_positive_customer_ids", ())
            ),
            "total_misclassification_count": int(metrics["total_misclassification_count"]),
            "total_misclassification_limit": int(metrics["total_misclassification_limit"]),
            "passes_misclassification_check": bool(metrics["passes_misclassification_check"]),
            "misclassified_customer_ids": list(metrics.get("misclassified_customer_ids", ())),
            "misclassification_check": dict(metrics["misclassification_check"]),
            "agent_validation_pass_rate": float(metrics["agent_validation_pass_rate"]),
        },
        "ab_comparison": {
            "baseline_capture_rate": float(metrics["baseline_low_mileage_high_risk_capture"]),
            "proposed_capture_rate": float(metrics["proposed_low_mileage_high_risk_capture"]),
            "baseline_capture_count": int(metrics["baseline_capture_count"]),
            "proposed_capture_count": int(metrics["proposed_capture_count"]),
            "comparison_summary": dict(evaluation_view_model.get("comparison_summary") or {}),
        },
        "comparison_dataset": dict(evaluation_view_model.get("comparison_dataset", {})),
        "critic_review": _critic_display_summary(critic_review),
        "report": _report_display_summary(report_view_model),
        "hybrid_case_results": [
            dict(case)
            for case in evaluation_view_model.get("hybrid_case_results", ())
        ],
        "customers": customers,
        "reason_codes": list(
            dict.fromkeys(
                list(evaluation_view_model.get("evaluation_reason_codes", ()))
                + list((critic_review or {}).get("reason_codes", ()))
                + list((report_view_model or {}).get("reason_codes", ()))
            )
        ),
    }
    validate_ui_dashboard_bundle(bundle)
    return bundle


def validate_ui_dashboard_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != UI_DASHBOARD_BUNDLE_SCHEMA:
        raise ValueError("invalid UI dashboard schema_version")
    if len(bundle.get("customers", ())) != 30:
        raise ValueError("UI dashboard bundle must include 30 customers")
    if not bundle.get("selected_policy", {}).get("candidate_id"):
        raise ValueError("UI dashboard bundle requires selected policy candidate_id")
    if "approval_gate" not in bundle or "ab_comparison" not in bundle:
        raise ValueError("UI dashboard bundle requires approval_gate and ab_comparison")
    hybrid_cases = list(bundle.get("hybrid_case_results", ()))
    if hybrid_cases and len(hybrid_cases) != 6:
        raise ValueError("UI dashboard bundle hybrid_case_results must include six persona cases")


def _customer_report_lookup(report_view_model: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not report_view_model:
        return {}
    return {
        str(row["customer_id"]): dict(row["llm_report"])
        for row in report_view_model.get("customer_reports", ())
    }


def _critic_display_summary(critic_review: dict[str, Any] | None) -> dict[str, Any]:
    if not critic_review:
        return {
            "available": False,
            "verdict": "pending",
            "risk_count": 0,
            "blocking_finding_count": 0,
            "required_follow_ups": [],
        }
    return {
        "available": True,
        "verdict": critic_review["validation"]["verdict"],
        "risk_count": len(critic_review["risks"]),
        "blocking_finding_count": int(critic_review["validation"]["blocking_finding_count"]),
        "required_follow_ups": list(critic_review["required_follow_ups"]),
    }


def _report_display_summary(report_view_model: dict[str, Any] | None) -> dict[str, Any]:
    if not report_view_model:
        return {
            "available": False,
            "report_mode": "pending",
            "fallback_report_count": 0,
            "portfolio_summary": "",
        }
    return {
        "available": True,
        "report_mode": report_view_model["report_mode"],
        "fallback_report_count": int(report_view_model["validation"]["fallback_report_count"]),
        "portfolio_summary": report_view_model["portfolio_llm_report"]["summary"],
    }

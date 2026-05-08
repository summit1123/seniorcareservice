"""Customer decision screen for the local Senior Safe Mileage webapp."""

from __future__ import annotations

import argparse
import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.agents.critic_agent import DEFAULT_STRUCTURED_OUTPUT as DEFAULT_CRITIC_REVIEW_INPUT
from src.agents.evaluation_agent import DEFAULT_VIEW_MODEL_OUTPUT as DEFAULT_EVALUATION_VIEW_MODEL_INPUT
from src.agents.report_agent import (
    DEFAULT_LLM_AUXILIARY_OUTPUT as DEFAULT_LLM_AUXILIARY_INPUT,
    DEFAULT_STRUCTURED_OUTPUT as DEFAULT_REPORT_VIEW_MODEL_INPUT,
)
from src.agents.policy_search_agent import DEFAULT_OUTPUT as DEFAULT_POLICY_CANDIDATE_RULES_INPUT
from src.agents.structured_outputs import (
    build_ui_dashboard_bundle,
    load_structured_json,
    validate_llm_report_auxiliary_results,
    validate_report_view_model,
)
from src.webapp.contest_demo_view import render_contest_demo_page
from src.webapp.validation_pipeline_service import (
    get_validation_pipeline_check,
    load_validation_pipeline_result,
    normalize_validation_pipeline_tab_model,
)


ROOT = Path(__file__).resolve().parents[2]

REASON_CODE_LABELS = {
    "LOW_MILEAGE_BASELINE_ELIGIBLE": "기존 저주행 마일리지 조건 충족",
    "LIVING_ZONE_DBSCAN_P90_INPUT_USED": "DBSCAN/P90 생활권 분석 반영",
    "LIVING_ZONE_STABLE_DRIVING": "생활권 중심 안정 주행",
    "LIVING_ZONE_HIGH_STABILITY": "생활권 안정성 높음",
    "REPEATED_ROUTE_PATTERN": "반복 경로 패턴 확인",
    "NEW_DESTINATION_OUT_ZONE_SIGNAL": "생활권 밖 신규 목적지 신호",
    "OUT_ZONE_PATTERN_CHANGE_RISK": "생활권 밖 위험변화 감지",
    "BORDERLINE_PATTERN_CHANGE_MONITORED": "경계권 변화 모니터링",
    "NO_STRONG_RISK_CHANGE": "강한 위험변화 없음",
    "RECENT_NIGHT_DRIVING_INCREASE": "최근 야간주행 증가",
    "RISK_EVENT_RATE_INCREASE": "위험행동 빈도 증가",
    "PROPOSED_MODEL_PREVENTIVE_CARE": "제안 모델 예방 케어 판정",
    "PROPOSED_MODEL_FAVORABLE_OR_STANDARD": "제안 모델 우대/기본 판정",
    "PROXY_LABEL_RULE_BASED": "규칙 기반 proxy label",
    "PROXY_LOW_MILEAGE_Y": "저주행 조건 충족",
    "PROXY_LOW_MILEAGE_N": "저주행 조건 미충족",
    "PROXY_RISK_CHANGE_SCORE_HIGH": "위험변화 점수 높음",
    "PROXY_OUT_ZONE_RATIO_DELTA_HIGH": "생활권 밖 주행 비중 증가",
    "PROXY_NIGHT_RATIO_DELTA_HIGH": "야간주행 비중 증가",
    "PROXY_RISK_RATE_DELTA_HIGH": "위험행동 빈도 증가",
    "PROXY_OUT_ZONE_RISK_CONFIRMED": "생활권 밖 위험 노출 확인",
    "PROXY_RISK_CHANGE_TARGET_Y": "proxy label target",
    "PROXY_RISK_CHANGE_TARGET_N": "proxy label non-target",
    "HYBRID_EVALUATION_GROUND_TRUTH_PRIORITY": "hybrid 평가 ground truth 우선",
    "HYBRID_GROUND_TRUTH_PROXY_ALIGNED": "ground truth와 proxy label 일치",
    "HYBRID_PROXY_CORRECTION_APPLIED": "proxy label 보정 반영",
    "HYBRID_DECISION_MATCHES_GROUND_TRUTH": "판정이 ground truth와 일치",
    "HYBRID_DECISION_MISSES_GROUND_TRUTH": "판정이 ground truth와 불일치",
    "HYBRID_DECISION_MATCHES_PROXY": "판정이 proxy label과 일치",
    "HYBRID_DECISION_MISSES_PROXY": "판정이 proxy label과 불일치",
    "HYBRID_PASS_FAIL_PASSED": "hybrid pass/fail 기준 통과",
    "HYBRID_PASS_FAIL_FAILED": "hybrid pass/fail 기준 미통과",
    "HYBRID_EXCEPTION_PROXY_DISAGREEMENT_ALLOWED_WHEN_GROUND_TRUTH_MATCHES": "ground truth 일치 우선 예외",
    "HYBRID_EXCEPTION_PROXY_ONLY_MATCH_DOES_NOT_OVERRIDE_GROUND_TRUTH": "proxy 단독 일치는 통과 근거 제외",
}

LLM_REPORT_SERVICE_SCHEMA = "senior-safe-mileage-llm-report-service-status/v1"

LLM_REPORT_STATUS_MESSAGES = {
    "pending": "Report Agent 산출물이 아직 없어 기본 판정/검증/A-B 결과를 먼저 표시합니다.",
    "fallback_template": "OpenAI API 응답을 사용할 수 없어 보험사 직원용 리포트는 안전한 fallback 템플릿으로 표시합니다.",
    "deterministic_template": "외부 LLM 호출 없이 로컬 템플릿 기반 리포트를 표시합니다.",
    "llm_generated": "개인정보 필터링을 통과한 요약 피처만 사용한 LLM 리포트를 표시합니다.",
    "unavailable": "리포트 보조 산출물을 읽을 수 없어 기본 판정/검증/A-B 결과를 먼저 표시합니다.",
}

VALIDATION_API_SCHEMA = "senior-safe-mileage-validation-api-response/v1"


def load_dashboard_bundle(
    *,
    evaluation_view_model_input: Path = DEFAULT_EVALUATION_VIEW_MODEL_INPUT,
    critic_review_input: Path = DEFAULT_CRITIC_REVIEW_INPUT,
    report_view_model_input: Path = DEFAULT_REPORT_VIEW_MODEL_INPUT,
    llm_auxiliary_input: Path = DEFAULT_LLM_AUXILIARY_INPUT,
    candidate_rules_input: Path = DEFAULT_POLICY_CANDIDATE_RULES_INPUT,
) -> dict[str, Any]:
    """Load saved agent outputs and return the display-ready dashboard bundle."""

    evaluation = load_structured_json(
        evaluation_view_model_input,
        expected_schema_version="senior-evaluation-results/v1",
    )
    critic_review = (
        load_structured_json(critic_review_input, expected_schema_version="senior-critic-rule-review/v1")
        if critic_review_input.exists()
        else None
    )
    report_view_model, report_status = _load_report_view_model_for_ui(report_view_model_input)
    llm_auxiliary_results, auxiliary_status = _load_llm_auxiliary_results_for_ui(llm_auxiliary_input)
    bundle = build_ui_dashboard_bundle(
        evaluation,
        critic_review=critic_review,
        report_view_model=report_view_model,
    )
    bundle["llm_report_service_status"] = _merge_llm_report_service_status(
        report_status,
        auxiliary_status,
    )
    bundle["agent_audit"] = build_agent_audit_view_model(
        load_validation_pipeline_result(
            evaluation_view_model_input=evaluation_view_model_input,
            critic_review_input=critic_review_input,
            report_view_model_input=report_view_model_input,
            policy_candidate_rules_input=candidate_rules_input,
        )
    )
    if llm_auxiliary_results is not None:
        bundle["llm_report_auxiliary_results"] = llm_auxiliary_results
    if candidate_rules_input.exists():
        bundle["policy_candidate_comparison"] = build_policy_candidate_comparison_view_model(
            candidate_rules_input=candidate_rules_input,
            selected_candidate_id=str(bundle["selected_policy"]["candidate_id"]),
        )
    return bundle


def build_agent_audit_view_model(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    """Shape Agent-in-the-loop validation checks and audit events for the audit tab."""

    tab_model = (
        dict(pipeline_result)
        if pipeline_result.get("schema_version") == "senior-safe-mileage-validation-pipeline-tab-model/v1"
        else normalize_validation_pipeline_tab_model(pipeline_result)
    )
    summary = dict(tab_model.get("summary", {}))
    checks = [dict(check) for check in tab_model.get("checks", ())]
    execution_input = dict(tab_model.get("execution_input", {}))
    audit_log_entries = [dict(entry) for entry in tab_model.get("audit_log_entries", ())]
    failed_agents = [str(agent_id) for agent_id in summary.get("failed_agents", ())]
    return {
        "schema_version": "senior-safe-mileage-agent-audit-tab/v1",
        "source_model_schema_version": tab_model["schema_version"],
        "run_id": str(tab_model.get("run_id", "")),
        "execution_input": execution_input,
        "passed": bool(summary.get("passed")),
        "validation_pass_rate": float(summary.get("validation_pass_rate", 0.0)),
        "required_agent_count": int(summary.get("total_agent_count", len(checks))),
        "check_count": len(checks),
        "failed_agents": failed_agents,
        "critic_findings": [str(item) for item in summary.get("critic_findings", ())],
        "approval_gate_thresholds": dict(tab_model.get("approval_gate_thresholds", {})),
        "checks": checks,
        "evidence_items": [dict(item) for item in tab_model.get("evidence_items", ())],
        "audit_log_entries": audit_log_entries,
        "audit_log_display_mode": "timeline",
        "artifact_index": [dict(item) for item in tab_model.get("artifact_index", ())],
        "privacy_contract": dict(tab_model.get("privacy_contract", {})),
    }


def build_policy_candidate_comparison_view_model(
    *,
    candidate_rules_input: Path = DEFAULT_POLICY_CANDIDATE_RULES_INPUT,
    selected_candidate_id: str | None = None,
) -> dict[str, Any]:
    """Load searched policy candidates and shape them for side-by-side UI comparison."""

    candidate_rules = json.loads(candidate_rules_input.read_text(encoding="utf-8"))
    ranked_candidates = [dict(candidate) for candidate in candidate_rules.get("ranked_candidates", ())]
    if not ranked_candidates:
        raise ValueError("policy candidate comparison requires ranked_candidates")

    selected = selected_candidate_id or str(candidate_rules.get("selected_candidate_id", ""))
    rows = [
        _policy_candidate_comparison_row(candidate, selected_candidate_id=selected)
        for candidate in ranked_candidates
    ]
    selected_candidate = next(
        (candidate for candidate in ranked_candidates if str(candidate.get("candidate_id")) == selected),
        ranked_candidates[0],
    )
    return {
        "schema_version": "senior-safe-mileage-policy-candidate-comparison/v1",
        "candidate_count": len(rows),
        "selected_candidate_id": selected,
        "selected_candidate_detail": _selected_policy_candidate_detail(selected_candidate),
        "weight_columns": [
            {"key": "w_mileage", "label": "마일리지"},
            {"key": "w_in_zone", "label": "생활권 내"},
            {"key": "w_out_zone_safe", "label": "생활권 밖 안전"},
            {"key": "w_out_zone_change", "label": "위험변화"},
        ],
        "threshold_columns": [
            {"key": "care_threshold", "label": "예방 기준"},
            {"key": "care_threshold_percentile", "label": "상위 percentile"},
            {"key": "tier_threshold", "label": "S/A/B/C 기준"},
        ],
        "rows": rows,
    }


def _load_report_view_model_for_ui(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not path.exists():
        return None, _pending_llm_report_status(source=str(path))
    try:
        report = load_structured_json(path, expected_schema_version="senior-report-agent/v1")
        validate_report_view_model(report)
    except Exception as exc:
        return None, _unavailable_llm_report_status(source=str(path), exc=exc)
    mode = str(report.get("report_mode", "deterministic_template"))
    fallback_count = int(report.get("validation", {}).get("fallback_report_count", 0))
    llm_service_status = dict(report.get("portfolio_llm_report", {}).get("llm_service_status", {}))
    return report, {
        "schema_version": LLM_REPORT_SERVICE_SCHEMA,
        "available": True,
        "report_mode": mode,
        "fallback_active": mode == "fallback_template" or fallback_count > 0,
        "service_status": str(llm_service_status.get("status") or _default_llm_service_status(mode)),
        "service_active": bool(llm_service_status.get("active")),
        "failure_detected": bool(llm_service_status.get("failure_detected")),
        "llm_service_status": llm_service_status,
        "message": LLM_REPORT_STATUS_MESSAGES.get(mode, LLM_REPORT_STATUS_MESSAGES["deterministic_template"]),
        "source": str(path),
        "fallback_report_count": fallback_count,
        "handled_by": "report_agent" if fallback_count else "local_webapp",
    }


def _load_llm_auxiliary_results_for_ui(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not path.exists():
        return None, _pending_llm_report_status(source=str(path))
    try:
        auxiliary = load_structured_json(path, expected_schema_version="senior-llm-report-auxiliary-results/v1")
        validate_llm_report_auxiliary_results(auxiliary)
    except Exception as exc:
        return None, _unavailable_llm_report_status(source=str(path), exc=exc)
    mode = str(auxiliary.get("report_mode", "deterministic_template"))
    fallback_count = int(auxiliary.get("validation", {}).get("fallback_ready_count", 0))
    llm_service_status = dict(auxiliary.get("portfolio_auxiliary_result", {}).get("llm_service_status", {}))
    return auxiliary, {
        "schema_version": LLM_REPORT_SERVICE_SCHEMA,
        "available": True,
        "report_mode": mode,
        "fallback_active": mode == "fallback_template" or fallback_count > 0,
        "service_status": str(llm_service_status.get("status") or _default_llm_service_status(mode)),
        "service_active": bool(llm_service_status.get("active")),
        "failure_detected": bool(llm_service_status.get("failure_detected")),
        "llm_service_status": llm_service_status,
        "message": LLM_REPORT_STATUS_MESSAGES.get(mode, LLM_REPORT_STATUS_MESSAGES["deterministic_template"]),
        "source": str(path),
        "fallback_report_count": fallback_count,
        "handled_by": "report_agent" if fallback_count else "local_webapp",
    }


def _merge_llm_report_service_status(
    report_status: dict[str, Any],
    auxiliary_status: dict[str, Any],
) -> dict[str, Any]:
    if (
        report_status.get("report_mode") == "fallback_template"
        or auxiliary_status.get("report_mode") == "fallback_template"
    ):
        mode = "fallback_template"
    elif not report_status.get("available") or not auxiliary_status.get("available"):
        mode = str(report_status.get("report_mode") or auxiliary_status.get("report_mode") or "pending")
    else:
        mode = str(report_status.get("report_mode") or auxiliary_status.get("report_mode") or "deterministic_template")
    service_status = _merge_external_llm_service_status(report_status, auxiliary_status, mode)
    return {
        "schema_version": LLM_REPORT_SERVICE_SCHEMA,
        "available": bool(report_status.get("available")) and bool(auxiliary_status.get("available")),
        "report_mode": mode,
        "fallback_active": bool(report_status.get("fallback_active")) or bool(auxiliary_status.get("fallback_active")),
        **service_status,
        "message": LLM_REPORT_STATUS_MESSAGES.get(mode, LLM_REPORT_STATUS_MESSAGES["unavailable"]),
        "report_artifact_status": dict(report_status),
        "auxiliary_artifact_status": dict(auxiliary_status),
        "core_outputs_continue": True,
        "safe_default_result": "customer_decision_and_ab_comparison",
    }


def _pending_llm_report_status(*, source: str = "") -> dict[str, Any]:
    return {
        "schema_version": LLM_REPORT_SERVICE_SCHEMA,
        "available": False,
        "report_mode": "pending",
        "fallback_active": True,
        "service_status": "inactive",
        "service_active": False,
        "failure_detected": False,
        "llm_service_status": {},
        "message": LLM_REPORT_STATUS_MESSAGES["pending"],
        "source": source,
        "fallback_report_count": 0,
        "handled_by": "local_webapp",
    }


def _unavailable_llm_report_status(*, source: str, exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": LLM_REPORT_SERVICE_SCHEMA,
        "available": False,
        "report_mode": "unavailable",
        "fallback_active": True,
        "service_status": "inactive",
        "service_active": False,
        "failure_detected": False,
        "llm_service_status": {},
        "message": LLM_REPORT_STATUS_MESSAGES["unavailable"],
        "source": source,
        "fallback_report_count": 0,
        "handled_by": "local_webapp",
        "error_type": exc.__class__.__name__,
    }


def _merge_external_llm_service_status(
    report_status: dict[str, Any],
    auxiliary_status: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    nested_statuses = [
        dict(status.get("llm_service_status", {}))
        for status in (report_status, auxiliary_status)
        if status.get("llm_service_status")
    ]
    if any(status.get("status") == "failed" for status in nested_statuses):
        failed = next(status for status in nested_statuses if status.get("status") == "failed")
        return {
            "service_status": "failed",
            "service_active": False,
            "failure_detected": True,
            "llm_service_status": failed,
        }
    if any(bool(status.get("active")) for status in nested_statuses):
        active = next(status for status in nested_statuses if status.get("active"))
        return {
            "service_status": str(active.get("status", "available")),
            "service_active": True,
            "failure_detected": False,
            "llm_service_status": active,
        }
    fallback_failure = (
        bool(report_status.get("failure_detected"))
        or bool(auxiliary_status.get("failure_detected"))
        or mode == "fallback_template"
    )
    return {
        "service_status": "inactive",
        "service_active": False,
        "failure_detected": fallback_failure,
        "llm_service_status": nested_statuses[0] if nested_statuses else {},
    }


def _default_llm_service_status(mode: str) -> str:
    if mode == "llm_generated":
        return "available"
    return "inactive"


def build_customer_decision_view_model(
    bundle: dict[str, Any],
    *,
    selected_customer_id: str | None = None,
) -> dict[str, Any]:
    """Shape one customer decision for the customer detail screen."""

    customers = list(bundle.get("customers", ()))
    if not customers:
        raise ValueError("dashboard bundle has no customers")
    selected_customer = _select_customer(customers, selected_customer_id)
    reason_codes = [str(code) for code in selected_customer.get("xai_reason_codes", ())]
    if not reason_codes:
        raise ValueError(f"customer {selected_customer['customer_id']} has no XAI reason codes")
    llm_auxiliary_result = _llm_auxiliary_result_for_customer(
        bundle.get("llm_report_auxiliary_results"),
        str(selected_customer["customer_id"]),
        service_status=dict(bundle.get("llm_report_service_status", {})),
    )
    proxy_label_auxiliary_result = _proxy_label_auxiliary_result(selected_customer)
    hybrid_evaluation_result = _hybrid_evaluation_result(selected_customer)
    hybrid_case_results = _hybrid_case_results(bundle)
    customer_ab_comparison = _customer_ab_comparison_layout_model(selected_customer)
    policy_candidate_comparison = dict(
        bundle.get("policy_candidate_comparison")
        or build_policy_candidate_comparison_view_model(
            selected_candidate_id=str(bundle["selected_policy"]["candidate_id"])
        )
    )
    agent_audit = dict(
        bundle.get("agent_audit")
        or build_agent_audit_view_model(load_validation_pipeline_result())
    )
    policy_judgment_evidence = _policy_judgment_evidence_result(
        selected_customer,
        selected_policy=dict(bundle["selected_policy"]),
        reason_items=[
            _reason_code_item(code, selected_customer)
            for code in reason_codes
        ],
        customer_ab_comparison=customer_ab_comparison,
        selected_policy_detail=dict(policy_candidate_comparison.get("selected_candidate_detail", {})),
    )
    evidence_audit_tab = _evidence_audit_tab_result(
        selected_customer,
        selected_policy=dict(bundle["selected_policy"]),
        agent_audit=agent_audit,
        policy_judgment_evidence=policy_judgment_evidence,
    )
    llm_report_service_status = dict(bundle.get("llm_report_service_status", _pending_llm_report_status()))
    local_rule_decision_result = _local_rule_decision_result(
        selected_customer,
        reason_items=policy_judgment_evidence["xai_reason_codes"],
        llm_report_service_status=llm_report_service_status,
    )
    ui_render_state = _ui_render_state(
        llm_report_service_status=llm_report_service_status,
        agent_audit=agent_audit,
        customer_ab_comparison=customer_ab_comparison,
    )
    return {
        "schema_version": "senior-safe-mileage-customer-decision-screen/v1",
        "entry_dashboard": _policy_validation_entry_dashboard(
            bundle,
            policy_candidate_comparison=policy_candidate_comparison,
            agent_audit=agent_audit,
        ),
        "selected_policy": dict(bundle["selected_policy"]),
        "ui_render_state": ui_render_state,
        "policy_candidate_comparison": policy_candidate_comparison,
        "policy_judgment_evidence": policy_judgment_evidence,
        "evidence_audit_tab": evidence_audit_tab,
        "approval_gate": dict(bundle["approval_gate"]),
        "ab_comparison": dict(bundle["ab_comparison"]),
        "customer_ab_comparison": customer_ab_comparison,
        "hybrid_case_results": hybrid_case_results,
        "agent_audit": agent_audit,
        "customer_options": [
            {
                "customer_id": customer["customer_id"],
                "persona_type": customer["persona_type"],
                "care_decision": customer["care_decision"],
            }
            for customer in customers
        ],
        "customer": selected_customer,
        "local_rule_decision_result": local_rule_decision_result,
        "xai_reason_code_auxiliary_results": policy_judgment_evidence["xai_reason_codes"],
        "proxy_label_auxiliary_result": proxy_label_auxiliary_result,
        "hybrid_evaluation_result": hybrid_evaluation_result,
        "llm_report_auxiliary_result": llm_auxiliary_result,
        "llm_report_service_status": llm_report_service_status,
    }


def _policy_validation_entry_dashboard(
    bundle: dict[str, Any],
    *,
    policy_candidate_comparison: dict[str, Any],
    agent_audit: dict[str, Any],
) -> dict[str, Any]:
    approval_gate = dict(bundle["approval_gate"])
    ab_comparison = dict(bundle["ab_comparison"])
    summary = dict(ab_comparison.get("comparison_summary", {}))
    decision_differences = dict(summary.get("decision_differences", {}))
    return {
        "schema_version": "senior-safe-mileage-policy-validation-entry-dashboard/v1",
        "screen_role": "first_entry_screen",
        "first_entry_screen": True,
        "section_order": [
            "policy_validation_dashboard",
            "agent_simulation_validation",
            "policy_candidate_search",
            "ab_comparison",
            "customer_decision_flow",
        ],
        "selected_candidate_id": str(bundle["selected_policy"]["candidate_id"]),
        "policy_candidate_count": int(policy_candidate_comparison.get("candidate_count", 0)),
        "agent_validation_passed": bool(agent_audit.get("passed")),
        "agent_validation_pass_rate": float(agent_audit.get("validation_pass_rate", 0.0)),
        "agent_validation_check_count": int(agent_audit.get("check_count", 0)),
        "approval_gate_passed": bool(approval_gate.get("passed")),
        "risk_change_capture": {
            "count": int(approval_gate.get("risk_change_capture_count", 0)),
            "target_count": int(approval_gate.get("risk_change_target_count", 0)),
        },
        "false_positive_gate": {
            "count": int(approval_gate.get("non_target_false_positive_count", 0)),
            "limit": int(approval_gate.get("non_target_false_positive_limit", 0)),
            "passed": bool(approval_gate.get("passes_non_target_false_positive_gate")),
        },
        "misclassification_check": dict(approval_gate.get("misclassification_check", {})),
        "ab_summary": {
            "customer_count": int(summary.get("customer_count", 0)),
            "baseline_capture_rate": float(ab_comparison.get("baseline_capture_rate", 0.0)),
            "proposed_capture_rate": float(ab_comparison.get("proposed_capture_rate", 0.0)),
            "decision_changed_count": int(decision_differences.get("decision_changed_count", 0)),
        },
        "primary_flow_links": [
            {"label": "Agent 시뮬레이션/검증", "href": "#agent-audit-tab"},
            {"label": "정책 후보 탐색", "href": "#policy-candidate-comparison"},
            {"label": "A/B 비교", "href": "#customer-ab-comparison"},
            {"label": "고객별 판정/리포트", "href": "#customer-decision-flow"},
        ],
    }


def render_customer_decision_page(
    bundle: dict[str, Any],
    *,
    selected_customer_id: str | None = None,
) -> str:
    view_model = build_customer_decision_view_model(bundle, selected_customer_id=selected_customer_id)
    customer = view_model["customer"]
    scores = customer["scores"]
    llm_report = customer.get("llm_report", {})
    llm_service_status = view_model["llm_report_service_status"]
    llm_report_body_section = _llm_report_body_section(llm_report, llm_service_status)
    reason_items = view_model["xai_reason_code_auxiliary_results"]
    local_rule_decision_result = view_model["local_rule_decision_result"]
    policy_judgment_evidence = view_model["policy_judgment_evidence"]
    proxy_label_result = view_model["proxy_label_auxiliary_result"]
    hybrid_evaluation_result = view_model["hybrid_evaluation_result"]
    hybrid_case_results = view_model["hybrid_case_results"]
    policy_candidate_comparison = view_model["policy_candidate_comparison"]
    agent_audit = view_model["agent_audit"]
    evidence_audit_tab = view_model["evidence_audit_tab"]
    entry_dashboard = view_model["entry_dashboard"]
    llm_auxiliary_result = view_model["llm_report_auxiliary_result"]
    score_panel_section = _score_panel_section(scores, dict(view_model["ui_render_state"]["score_panel"]))
    entry_dashboard_section = _policy_validation_entry_dashboard_section(entry_dashboard)
    ab_comparison_section = _ab_comparison_section(view_model["customer_ab_comparison"])
    false_positive_gate = view_model["approval_gate"]
    options = "\n".join(
        _customer_option(option, customer["customer_id"])
        for option in view_model["customer_options"]
    )
    reason_cards = "\n".join(_reason_card(item) for item in reason_items)
    policy_judgment_evidence_section = _policy_judgment_evidence_section(policy_judgment_evidence)
    proxy_label_section = _proxy_label_section(proxy_label_result)
    hybrid_evaluation_section = _hybrid_evaluation_section(hybrid_evaluation_result)
    hybrid_case_section = _hybrid_case_results_section(hybrid_case_results)
    agent_audit_section = _agent_audit_section(agent_audit)
    evidence_audit_tab_section = _evidence_audit_tab_section(evidence_audit_tab)
    policy_candidate_section = _policy_candidate_comparison_section(policy_candidate_comparison)
    local_rule_decision_section = _local_rule_decision_section(local_rule_decision_result)
    llm_auxiliary_section = _llm_auxiliary_section(llm_auxiliary_result)
    llm_status_section = _llm_report_status_section(llm_service_status)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Senior Safe Mileage 고객별 판정</title>
  <style>
    :root {{ color-scheme: light; --ink: #17212b; --muted: #5c6670; --line: #d9dee5; --soft: #f4f6f8; --accent: #126d67; --warn: #a34317; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #ffffff; }}
    header {{ padding: 24px 32px 18px; border-bottom: 1px solid var(--line); background: #fbfcfd; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px 28px 40px; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; line-height: 1.25; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.55; }}
    .tabs {{ display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }}
    .tab {{ border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 6px; padding: 8px 10px; font-size: 14px; text-decoration: none; }}
    .tab.active {{ border-color: var(--accent); color: var(--accent); font-weight: 700; }}
    .section-tabs {{ display: flex; gap: 8px; margin: 14px 0; flex-wrap: wrap; }}
    .section-tab {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 6px; padding: 7px 10px; font-size: 13px; text-decoration: none; }}
    .section-tab.active {{ border-color: var(--accent); color: var(--accent); font-weight: 700; background: #eef8f6; }}
    .toolbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }}
    select {{ min-width: 260px; max-width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 9px 10px; background: #fff; color: var(--ink); }}
    .grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 0.75fr); gap: 18px; align-items: start; }}
    section {{ border-top: 1px solid var(--line); padding-top: 18px; margin-top: 18px; }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; padding: 18px; background: #fff; }}
    .decision {{ display: inline-flex; align-items: center; min-height: 34px; padding: 6px 10px; border-radius: 6px; background: var(--soft); font-weight: 700; }}
    .decision.preventive {{ color: var(--warn); }}
    .status-pill {{ display: inline-flex; align-items: center; min-height: 28px; border-radius: 999px; padding: 5px 9px; border: 1px solid var(--line); font-size: 12px; font-weight: 700; }}
    .status-pill.passed {{ color: #0b6b49; border-color: #9fd3bd; background: #edf8f2; }}
    .status-pill.review {{ color: var(--warn); border-color: #e1c5b4; background: #fff7f2; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }}
    .metric {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfd; }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 22px; }}
    .entry-dashboard {{ border-top: 0; padding-top: 0; margin-top: 0; }}
    .entry-dashboard-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }}
    .entry-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }}
    .entry-card h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .entry-card strong {{ display: block; margin-top: 8px; font-size: 20px; }}
    .entry-actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }}
    .entry-action {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid var(--line); border-radius: 6px; padding: 7px 10px; text-decoration: none; color: var(--ink); background: #fff; font-size: 13px; }}
    .ab-compare {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }}
    .ab-model {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }}
    .ab-model h3 {{ margin: 0 0 10px; font-size: 15px; }}
    .ab-row {{ display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid var(--line); padding: 8px 0; font-size: 13px; }}
    .ab-row:first-of-type {{ border-top: 0; }}
    .ab-row span {{ color: var(--muted); }}
    .ab-row strong {{ text-align: right; }}
    .ab-delta {{ margin-top: 12px; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfd; }}
    .ab-highlight {{ margin-top: 12px; border: 1px solid #b8d8d3; border-radius: 8px; background: #f2faf8; overflow: hidden; }}
    .ab-highlight-row {{ display: grid; grid-template-columns: 110px minmax(0, 1fr) minmax(0, 1fr) 88px; gap: 10px; align-items: center; border-top: 1px solid #cfe4e0; padding: 10px 12px; font-size: 13px; }}
    .ab-highlight-row:first-child {{ border-top: 0; }}
    .ab-highlight-label {{ color: var(--muted); font-weight: 700; }}
    .ab-highlight-value {{ overflow-wrap: anywhere; }}
    .ab-highlight-delta {{ justify-self: end; font-weight: 700; color: var(--accent); }}
    .ab-highlight-row.changed .ab-highlight-delta {{ color: var(--warn); }}
    .reason-list {{ display: grid; gap: 10px; }}
    .reason-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }}
    .code {{ display: inline-block; max-width: 100%; overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--accent); background: #eaf5f3; border-radius: 5px; padding: 4px 6px; }}
    .reason-card strong {{ display: block; margin: 8px 0 4px; }}
    .report-text {{ white-space: pre-wrap; line-height: 1.55; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 9px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #fbfcfd; color: var(--muted); font-weight: 700; }}
    tr.selected {{ background: #eef8f6; }}
    .compact {{ white-space: nowrap; }}
    .threshold-list {{ display: grid; gap: 3px; }}
    .audit-log {{ display: grid; gap: 8px; margin-top: 12px; }}
    .audit-event {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: #fbfcfd; }}
    .audit-event.warning {{ border-color: #e1c5b4; background: #fff7f2; }}
    .message-area {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .message-area.failure {{ border-color: #d18a8a; background: #fff3f3; }}
    .message-area.warning {{ border-color: #d8b26a; background: #fff8e8; }}
    .message-area.failure h3 {{ color: #8f1d1d; }}
    .message-area.warning h3 {{ color: #8a5417; }}
    .message-list {{ margin: 8px 0 0; padding-left: 18px; }}
    .aux-section-list {{ display: grid; gap: 10px; margin: 12px 0; }}
    .aux-section {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfd; }}
    .aux-section h3 {{ margin: 0 0 6px; font-size: 15px; }}
    @media (max-width: 820px) {{ header {{ padding: 20px; }} main {{ padding: 20px; }} .grid, .metrics, .ab-compare, .ab-highlight-row, .entry-dashboard-grid {{ grid-template-columns: 1fr; }} .toolbar {{ align-items: flex-start; flex-direction: column; }} .ab-highlight-delta {{ justify-self: start; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Senior Safe Mileage 정책/검증 대시보드</h1>
    <p>첫 진입 화면에서 정책/검증 대시보드를 확인한 뒤 Agent 시뮬레이션/검증, 정책 후보 탐색, A/B 비교, 고객별 판정/리포트 순서로 이어집니다.</p>
    <nav class="tabs" aria-label="제품 흐름" data-primary-navigation-order="agent_simulation_validation,policy_candidate_search,ab_comparison,customer_decision_report">
      <a class="tab active" href="#agent-audit-tab" data-primary-nav-item="agent_simulation_validation" aria-current="page">Agent 시뮬레이션/검증</a>
      <a class="tab" href="#policy-candidate-comparison" data-primary-nav-item="policy_candidate_search">정책 후보 탐색</a>
      <a class="tab" href="#customer-ab-comparison" data-primary-nav-item="ab_comparison">A/B 비교</a>
      <a class="tab" href="#customer-decision-flow" data-primary-nav-item="customer_decision_report">고객별 판정/리포트</a>
    </nav>
  </header>
  <main>
{entry_dashboard_section}
{agent_audit_section}
{policy_candidate_section}
{evidence_audit_tab_section}
{policy_judgment_evidence_section}
{ab_comparison_section}
    <section id="customer-decision-flow" data-customer-decision-flow="after-ab-comparison" aria-labelledby="customer-decision-flow-heading">
      <div class="toolbar">
        <div>
          <h2 id="customer-decision-flow-heading">{escape(str(customer["customer_id"]))} / {escape(str(customer["persona_type"]))}</h2>
          <span class="{_decision_class(customer["care_decision"])}">{escape(str(customer["care_decision"]))}</span>
        </div>
        <form method="get" action="/">
          <label for="customer_id">고객 선택</label>
          <select id="customer_id" name="customer_id" onchange="this.form.submit()">
{options}
          </select>
        </form>
      </div>
      <div class="grid">
        <div>
{score_panel_section}
{local_rule_decision_section}
        <section id="xai-reason-codes" aria-labelledby="xai-heading">
          <h2 id="xai-heading">XAI reason code 보조 결과</h2>
          <p>판정 엔진이 남긴 구조화 신호입니다. LLM 리포트는 이 코드를 설명문으로 바꾸며, 보험료나 등급을 직접 결정하지 않습니다.</p>
          <div class="reason-list" data-reason-code-count="{len(reason_items)}">
{reason_cards}
          </div>
        </section>
{hybrid_case_section}
{proxy_label_section}
{hybrid_evaluation_section}
{llm_auxiliary_section}
        </div>
        <aside class="panel" aria-labelledby="report-heading">
          <h2 id="report-heading">보험사 직원용 리포트</h2>
{llm_report_body_section}
{llm_status_section}
          <section id="false-positive-gate" data-false-positive-gate-passed="{str(bool(false_positive_gate["passes_non_target_false_positive_gate"])).lower()}">
            <h2>오탐 제한 게이트</h2>
            <p>비위험군 {escape(str(false_positive_gate["non_target_count"]))}명 중 오탐 {escape(str(false_positive_gate["non_target_false_positive_count"]))}명 / 허용 {escape(str(false_positive_gate["non_target_false_positive_limit"]))}명</p>
          </section>
          <section id="misclassification-check" data-misclassification-check-passed="{str(bool(false_positive_gate["passes_misclassification_check"])).lower()}">
            <h2>전체 오분류 체크</h2>
            <p>30명 중 오분류 {escape(str(false_positive_gate["total_misclassification_count"]))}건 / 허용 {escape(str(false_positive_gate["total_misclassification_limit"]))}건</p>
          </section>
          <section>
            <h2>Hybrid 평가</h2>
            <p>제안 모델: {escape(str(hybrid_evaluation_result["proposed"]["verdict"]))} / {escape(str(hybrid_evaluation_result["proposed"]["score"]))}점, 기준 {escape(str(hybrid_evaluation_result["proposed"]["pass_threshold"]))}점</p>
            <p>{escape(str(hybrid_evaluation_result["proposed"]["rationale"]))}</p>
          </section>
        </aside>
      </div>
    </section>
  </main>
</body>
</html>
"""


def build_validation_api_response(path: str) -> tuple[int, dict[str, Any]]:
    """Return the local JSON API response for Agent validation endpoints."""

    parsed = urlparse(path)
    if parsed.path not in ("/api/validation", "/api/validation/agent"):
        return 404, {
            "schema_version": VALIDATION_API_SCHEMA,
            "ok": False,
            "error": "validation API endpoint not found",
            "path": parsed.path,
        }

    query = parse_qs(parsed.query)
    run_id = query.get("run_id", [None])[0]
    selected_candidate_id = query.get("selected_candidate_id", [None])[0]
    selected_scenario_id = query.get("selected_scenario_id", [None])[0]
    try:
        pipeline_result = (
            load_validation_pipeline_result(
                run_id=run_id,
                selected_candidate_id=selected_candidate_id,
                selected_scenario_id=selected_scenario_id,
            )
            if run_id
            else load_validation_pipeline_result(
                selected_candidate_id=selected_candidate_id,
                selected_scenario_id=selected_scenario_id,
            )
        )
    except ValueError as exc:
        return 400, {
            "schema_version": VALIDATION_API_SCHEMA,
            "ok": False,
            "error": str(exc),
            "selected_candidate_id": selected_candidate_id,
            "selected_scenario_id": selected_scenario_id,
        }
    agent_id = query.get("agent_id", [None])[0]
    if parsed.path == "/api/validation/agent" and not agent_id:
        return 400, {
            "schema_version": VALIDATION_API_SCHEMA,
            "ok": False,
            "error": "agent_id query parameter is required",
        }
    if agent_id:
        try:
            result: dict[str, Any] = get_validation_pipeline_check(pipeline_result, agent_id)
        except KeyError as exc:
            return 404, {
                "schema_version": VALIDATION_API_SCHEMA,
                "ok": False,
                "error": str(exc),
                "agent_id": agent_id,
            }
        return 200, {
            "schema_version": VALIDATION_API_SCHEMA,
            "ok": True,
            "result_type": "agent_validation_check",
            "run_id": pipeline_result["run_id"],
            "agent_id": agent_id,
            "execution_input": pipeline_result.get("execution_input", {}),
            "result": result,
        }

    return 200, {
        "schema_version": VALIDATION_API_SCHEMA,
        "ok": True,
        "result_type": "agent_validation_pipeline",
        "run_id": pipeline_result["run_id"],
        "execution_input": pipeline_result.get("execution_input", {}),
        "result": pipeline_result,
    }


def render_webapp_page(path: str, bundle: dict[str, Any]) -> str:
    """Render the public contest page or the detailed operator view for a web path."""

    parsed = urlparse(path)
    if parsed.path in {"/detail", "/detail/", "/customer", "/customer/"}:
        query = parse_qs(parsed.query)
        customer_id = query.get("customer_id", [None])[0]
        return render_customer_decision_page(bundle, selected_customer_id=customer_id)
    return render_contest_demo_page(bundle, request_path=path)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    bundle: dict[str, Any] | None = None,
) -> ThreadingHTTPServer:
    dashboard_bundle = bundle or load_dashboard_bundle()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib hook
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/validation"):
                status, payload = build_validation_api_response(self.path)
                body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            html = render_webapp_page(self.path, dashboard_bundle)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    return server


def _select_customer(customers: list[dict[str, Any]], selected_customer_id: str | None) -> dict[str, Any]:
    if selected_customer_id:
        for customer in customers:
            if str(customer.get("customer_id")) == selected_customer_id:
                return customer
        raise ValueError(f"unknown customer_id: {selected_customer_id}")
    preventive = [customer for customer in customers if customer.get("care_decision") == "예방 케어"]
    return preventive[0] if preventive else customers[0]


def _reason_code_item(code: str, customer: dict[str, Any]) -> dict[str, str]:
    scores = customer["scores"]
    evidence = {
        "OUT_ZONE_PATTERN_CHANGE_RISK": f"risk_change_score={_format_score(scores['risk_change_score'])}",
        "PROPOSED_MODEL_PREVENTIVE_CARE": f"care_decision={customer['care_decision']}",
        "PROPOSED_MODEL_FAVORABLE_OR_STANDARD": f"care_decision={customer['care_decision']}",
        "LOW_MILEAGE_BASELINE_ELIGIBLE": f"mileage_baseline_score={_format_score(scores['mileage_baseline_score'])}",
        "NO_STRONG_RISK_CHANGE": f"risk_change_score={_format_score(scores['risk_change_score'])}",
        "BORDERLINE_PATTERN_CHANGE_MONITORED": f"risk_change_score={_format_score(scores['risk_change_score'])}",
    }.get(code, f"persona_type={customer['persona_type']}")
    return {
        "code": code,
        "label": REASON_CODE_LABELS.get(code, "정책 엔진 보조 신호"),
        "evidence": evidence,
    }


def _proxy_label_auxiliary_result(customer: dict[str, Any]) -> dict[str, Any]:
    proxy_label = dict(customer.get("proxy_label", {}))
    if not proxy_label:
        raise ValueError(f"customer {customer['customer_id']} has no proxy label result")
    reason_codes = [str(code) for code in proxy_label.get("reason_codes", ())]
    if not reason_codes:
        raise ValueError(f"customer {customer['customer_id']} proxy label has no reason codes")
    thresholds = dict(proxy_label.get("thresholds", {}))
    return {
        "available": True,
        "customer_id": str(customer["customer_id"]),
        "is_target": bool(proxy_label.get("is_target")),
        "expected_care_decision": str(proxy_label.get("expected_care_decision", "")),
        "rule_id": str(proxy_label.get("rule_id", "")),
        "reason_codes": reason_codes,
        "thresholds": thresholds,
        "summary": _proxy_label_summary_text(proxy_label),
    }


def _proxy_label_summary_text(proxy_label: dict[str, Any]) -> str:
    target_label = "target" if proxy_label.get("is_target") else "non-target"
    expected = str(proxy_label.get("expected_care_decision", "기본"))
    return f"proxy label={target_label}, expected_care_decision={expected}"


def _hybrid_evaluation_result(customer: dict[str, Any]) -> dict[str, Any]:
    hybrid = dict(customer.get("hybrid_evaluation", {}))
    if not hybrid:
        raise ValueError(f"customer {customer['customer_id']} has no hybrid evaluation result")
    result = {
        "available": True,
        "customer_id": str(customer["customer_id"]),
        "baseline": _hybrid_model_result(dict(hybrid.get("baseline", {})), model_label="baseline"),
        "proposed": _hybrid_model_result(dict(hybrid.get("proposed", {})), model_label="proposed"),
    }
    return result


def _hybrid_case_results(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    cases = [dict(case) for case in bundle.get("hybrid_case_results", ())]
    if not cases:
        cases = _hybrid_case_results_from_customers(list(bundle.get("customers", ())))
    if len(cases) != 6:
        raise ValueError(f"hybrid case results must include six persona cases: actual={len(cases)}")
    return cases


def _hybrid_case_results_from_customers(customers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for customer in customers:
        grouped.setdefault(str(customer["persona_type"]), []).append(customer)

    cases: list[dict[str, Any]] = []
    for index, persona_type in enumerate(sorted(grouped), start=1):
        rows = sorted(grouped[persona_type], key=lambda row: str(row["customer_id"]))
        representative = next(
            (
                row for row in rows
                if not bool(row["hybrid_evaluation"]["proposed"]["passed"])
            ),
            rows[0],
        )
        baseline_rows = [dict(row["hybrid_evaluation"]["baseline"]) for row in rows]
        proposed_rows = [dict(row["hybrid_evaluation"]["proposed"]) for row in rows]
        cases.append(
            {
                "case_id": f"hybrid_case_{index:02d}",
                "persona_type": persona_type,
                "customer_count": len(rows),
                "representative_customer_id": representative["customer_id"],
                "representative_care_decision": representative["care_decision"],
                "risk_change_target": bool(representative["ab_comparison"]["metrics"]["risk_change_target"]),
                "proxy_label_target": bool(representative["ab_comparison"]["metrics"]["proxy_label_target"]),
                "baseline": _hybrid_case_model_summary(baseline_rows),
                "proposed": _hybrid_case_model_summary(proposed_rows),
                "rationale": _hybrid_rationale(dict(representative["hybrid_evaluation"]["proposed"])),
            }
        )
    return cases


def _hybrid_case_model_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pass_count = sum(1 for row in rows if bool(row.get("passed")))
    scores = [float(row.get("score", 0.0)) for row in rows]
    return {
        "pass_count": pass_count,
        "fail_count": len(rows) - pass_count,
        "pass_rate": round(pass_count / max(1, len(rows)), 4),
        "average_score": round(sum(scores) / max(1, len(scores)), 2),
        "verdict": "pass" if pass_count == len(rows) else "review",
        "pass_threshold": float(rows[0].get("pass_threshold", 0.0)) if rows else 0.0,
        "pass_fail_rule_id": str(rows[0].get("pass_fail_rule_id", "")) if rows else "",
    }


def _hybrid_model_result(row: dict[str, Any], *, model_label: str) -> dict[str, Any]:
    if not row:
        raise ValueError(f"missing {model_label} hybrid evaluation row")
    reason_codes = [str(code) for code in row.get("reason_codes", ())]
    return {
        "model_label": model_label,
        "score": float(row.get("score", 0.0)),
        "passed": bool(row.get("passed")),
        "verdict": str(row.get("verdict", "")),
        "pass_threshold": float(row.get("pass_threshold", 0.0)),
        "rule_id": str(row.get("rule_id", "")),
        "pass_fail_rule_id": str(row.get("pass_fail_rule_id", "")),
        "decision_detected": bool(row.get("decision_detected")),
        "ground_truth_target": bool(row.get("ground_truth_target")),
        "proxy_label_target": bool(row.get("proxy_label_target")),
        "hybrid_target": bool(row.get("hybrid_target")),
        "weights": dict(row.get("weights", {})),
        "exception_rule": row.get("exception_rule"),
        "reason_codes": reason_codes,
        "rationale": _hybrid_rationale(row),
    }


def _hybrid_rationale(row: dict[str, Any]) -> str:
    verdict = str(row.get("verdict", "unknown"))
    score = float(row.get("score", 0.0))
    threshold = float(row.get("pass_threshold", 0.0))
    decision = "포착" if row.get("decision_detected") else "미포착"
    ground_truth = "target" if row.get("ground_truth_target") else "non-target"
    proxy_label = "target" if row.get("proxy_label_target") else "non-target"
    exception = row.get("exception_rule") or "none"
    return (
        f"verdict={verdict}, score={score:.1f}/{threshold:.1f}, decision={decision}, "
        f"ground_truth={ground_truth}, proxy_label={proxy_label}, exception_rule={exception}"
    )


def _customer_option(option: dict[str, Any], selected_customer_id: str) -> str:
    selected = " selected" if option["customer_id"] == selected_customer_id else ""
    label = f"{option['customer_id']} / {option['care_decision']} / {option['persona_type']}"
    return f'          <option value="{escape(str(option["customer_id"]))}"{selected}>{escape(label)}</option>'


def _reason_card(item: dict[str, str]) -> str:
    return f"""            <article class="reason-card">
              <span class="code">{escape(item["code"])}</span>
              <strong>{escape(item["label"])}</strong>
              <p>{escape(item["evidence"])}</p>
            </article>"""


def _policy_judgment_evidence_result(
    customer: dict[str, Any],
    *,
    selected_policy: dict[str, Any],
    reason_items: list[dict[str, str]],
    customer_ab_comparison: dict[str, Any],
    selected_policy_detail: dict[str, Any],
) -> dict[str, Any]:
    scores = dict(customer["scores"])
    thresholds = dict(selected_policy.get("thresholds", {}))
    weights = dict(selected_policy.get("weights", {}))
    proposed = dict(customer_ab_comparison["models"]["proposed"])
    difference = dict(customer_ab_comparison["difference"])
    policy_reason_codes = [str(code) for code in selected_policy_detail.get("reason_codes", ())]
    basis_items = [
        f"candidate_id={selected_policy.get('candidate_id', '')}",
        f"care_decision={customer.get('care_decision', '')}",
        f"senior_safe_mileage_score={_format_score(scores.get('senior_safe_mileage_score', 0.0))}",
        f"risk_change_score={_format_score(scores.get('risk_change_score', 0.0))}",
        f"care_threshold={_format_score(thresholds.get('care_threshold', 0.0))}",
        f"threshold_basis={thresholds.get('care_threshold_source', '')}",
        f"proposed_detected={bool(proposed.get('detected'))}",
    ]
    weight_items = [
        f"{key}={_format_weight(value)}"
        for key, value in weights.items()
    ]
    ab_items = [
        f"baseline_decision={customer_ab_comparison['models']['baseline'].get('decision', '')}",
        f"proposed_decision={proposed.get('decision', '')}",
        f"decision_changed={bool(difference.get('decision_changed'))}",
        f"proposed_only_capture={bool(difference.get('proposed_captures_risk_change_not_baseline'))}",
    ]
    return {
        "schema_version": "senior-safe-mileage-policy-judgment-evidence-tab/v1",
        "customer_id": str(customer["customer_id"]),
        "tab_id": "evidence",
        "display_area": "reason_evidence",
        "separated_from_validation_status": True,
        "validation_status_source": "agent_audit_tab",
        "selected_candidate_id": str(selected_policy.get("candidate_id", "")),
        "policy_basis_items": basis_items,
        "weight_items": weight_items,
        "ab_basis_items": ab_items,
        "policy_reason_codes": policy_reason_codes,
        "xai_reason_codes": reason_items,
        "reason_code_count": len(reason_items),
    }


def _policy_judgment_evidence_section(evidence: dict[str, Any]) -> str:
    reason_cards = "\n".join(
        _reason_card(item)
        for item in evidence.get("xai_reason_codes", ())
    )
    policy_reason_codes = "".join(
        f'              <span class="code">{escape(str(code))}</span>'
        for code in evidence.get("policy_reason_codes", ())
    )
    return f"""        <section id="policy-judgment-evidence-tab" aria-labelledby="policy-judgment-evidence-heading" data-decision-evidence-tab="{escape(str(evidence.get("tab_id", "evidence")))}" data-reason-evidence-area="{escape(str(evidence.get("display_area", "reason_evidence")))}" data-separated-from-validation-status="{str(bool(evidence.get("separated_from_validation_status"))).lower()}" data-validation-status-source="{escape(str(evidence.get("validation_status_source", "agent_audit_tab")))}" data-policy-judgment-customer-id="{escape(str(evidence.get("customer_id", "")))}" data-policy-judgment-reason-code-count="{escape(str(evidence.get("reason_code_count", 0)))}">
          <h2 id="policy-judgment-evidence-heading">근거 탭</h2>
          <p>선택 정책 후보의 판단 기준과 고객별 XAI reason code를 검증 상태와 분리된 reason/evidence 영역에서 확인합니다.</p>
          <div class="aux-section-list">
            <article class="aux-section" data-policy-judgment-section="policy-basis">
              <h3>정책 판단 근거</h3>
              <p><span class="code">{escape(str(evidence.get("selected_candidate_id", "")))}</span></p>
              <ul>{_html_list_items(evidence.get("policy_basis_items", ()))}</ul>
            </article>
            <article class="aux-section" data-policy-judgment-section="weights">
              <h3>정책 가중치</h3>
              <ul>{_html_list_items(evidence.get("weight_items", ()))}</ul>
            </article>
            <article class="aux-section" data-policy-judgment-section="ab-basis">
              <h3>A/B 판정 근거</h3>
              <ul>{_html_list_items(evidence.get("ab_basis_items", ()))}</ul>
            </article>
            <article class="aux-section" data-policy-judgment-section="policy-reason-codes">
              <h3>정책 선택 reason code</h3>
              <p>{policy_reason_codes or "없음"}</p>
            </article>
          </div>
          <div id="evidence-tab-xai-reason-codes" class="reason-list" data-evidence-tab-xai-reason-code-count="{escape(str(evidence.get("reason_code_count", 0)))}">
{reason_cards}
          </div>
        </section>"""


def _evidence_audit_tab_result(
    customer: dict[str, Any],
    *,
    selected_policy: dict[str, Any],
    agent_audit: dict[str, Any],
    policy_judgment_evidence: dict[str, Any],
) -> dict[str, Any]:
    execution_input = dict(agent_audit.get("execution_input", {}))
    execution_policy = dict(execution_input.get("selected_policy", {}))
    selected_scenario = dict(execution_input.get("selected_scenario", {}))
    selected_candidate_id = str(
        selected_policy.get("candidate_id")
        or execution_policy.get("candidate_id")
        or policy_judgment_evidence.get("selected_candidate_id", "")
    )
    selected_scenario_id = str(selected_scenario.get("scenario_id", ""))
    validation_summary = {
        "passed": bool(agent_audit.get("passed")),
        "validation_pass_rate": float(agent_audit.get("validation_pass_rate", 0.0)),
        "required_agent_count": int(agent_audit.get("required_agent_count", 0)),
        "check_count": int(agent_audit.get("check_count", 0)),
        "failed_agents": [str(agent_id) for agent_id in agent_audit.get("failed_agents", ())],
        "critic_findings": [str(item) for item in agent_audit.get("critic_findings", ())],
    }
    evidence_items = [
        {
            "evidence_id": "selected_policy_judgment_basis",
            "source": "policy_judgment_evidence",
            "summary": "; ".join(str(item) for item in policy_judgment_evidence.get("policy_basis_items", ())),
            "artifact_refs": [str(execution_policy.get("source_artifact", ""))],
            "reason_codes": [str(code) for code in policy_judgment_evidence.get("policy_reason_codes", ())],
        }
    ]
    evidence_items.extend(
        {
            "evidence_id": str(item.get("evidence_id", "")),
            "source": str(item.get("agent_id", "")),
            "summary": str(item.get("summary", "")),
            "artifact_refs": [str(ref) for ref in item.get("artifact_refs", ())],
            "reason_codes": [str(code) for code in item.get("reason_codes", ())],
        }
        for item in agent_audit.get("evidence_items", ())
    )
    audit_log_entries = [dict(entry) for entry in agent_audit.get("audit_log_entries", ())]
    return {
        "schema_version": "senior-safe-mileage-evidence-audit-tab/v1",
        "tab_ids": ["evidence", "audit"],
        "customer_id": str(customer["customer_id"]),
        "selected_candidate_id": selected_candidate_id,
        "selected_scenario_id": selected_scenario_id,
        "selected_policy": execution_policy or dict(selected_policy),
        "selected_scenario": selected_scenario,
        "validation_summary": validation_summary,
        "evidence_items": evidence_items,
        "audit_log_entries": audit_log_entries,
        "audit_log_display_mode": "timeline",
        "evidence_item_count": len(evidence_items),
        "audit_log_entry_count": len(audit_log_entries),
    }


def _evidence_audit_tab_section(tab: dict[str, Any]) -> str:
    validation_summary = dict(tab.get("validation_summary", {}))
    selected_policy = dict(tab.get("selected_policy", {}))
    selected_scenario = dict(tab.get("selected_scenario", {}))
    evidence_cards = "\n".join(
        _evidence_audit_item_card(item)
        for item in tab.get("evidence_items", ())
    )
    audit_cards = "\n".join(
        _evidence_audit_log_card(item)
        for item in tab.get("audit_log_entries", ())
    )
    failed_agents = ", ".join(str(agent_id) for agent_id in validation_summary.get("failed_agents", ())) or "없음"
    critic_findings = _bullet_text(validation_summary.get("critic_findings", ()))
    pass_rate = _format_percent(float(validation_summary.get("validation_pass_rate", 0.0)))
    return f"""        <section id="evidence-audit-tab" aria-labelledby="evidence-audit-heading" data-evidence-audit-tab="selected-policy-scenario" data-evidence-audit-customer-id="{escape(str(tab.get("customer_id", "")))}" data-evidence-audit-selected-candidate-id="{escape(str(tab.get("selected_candidate_id", "")))}" data-evidence-audit-selected-scenario-id="{escape(str(tab.get("selected_scenario_id", "")))}" data-evidence-item-count="{escape(str(tab.get("evidence_item_count", 0)))}" data-audit-log-entry-count="{escape(str(tab.get("audit_log_entry_count", 0)))}">
          <h2 id="evidence-audit-heading">근거/감사 탭</h2>
          <p>선택된 정책 후보와 시나리오 실행 입력을 기준으로 검증 결과 요약, 근거 항목, 감사 로그를 연결해 표시합니다.</p>
          <nav class="section-tabs" aria-label="선택 정책/시나리오 근거 및 감사">
            <a class="section-tab active" href="#evidence-audit-validation-summary" data-evidence-audit-nav="validation-summary" aria-current="page">검증 요약</a>
            <a class="section-tab" href="#evidence-audit-items" data-evidence-audit-nav="evidence-items">근거 항목</a>
            <a class="section-tab" href="#evidence-audit-log" data-evidence-audit-nav="audit-log">감사 로그</a>
          </nav>
          <div class="aux-section-list">
            <article class="aux-section" data-evidence-audit-section="selected-state">
              <h3>선택 정책/시나리오 기준</h3>
              <p>정책 <span class="code">{escape(str(tab.get("selected_candidate_id", "")))}</span> · 시나리오 <span class="code">{escape(str(tab.get("selected_scenario_id", "")))}</span></p>
              <p>정책 산출물={escape(str(selected_policy.get("source_artifact", "")))} · 시나리오 산출물={escape(str(selected_scenario.get("source_artifact", "")))}</p>
            </article>
            <article class="aux-section" id="evidence-audit-validation-summary" data-evidence-audit-section="validation-summary" data-evidence-audit-validation-passed="{str(bool(validation_summary.get("passed"))).lower()}">
              <h3>검증 결과 요약</h3>
              <p>pass rate {escape(pass_rate)} · 필수 Agent {escape(str(validation_summary.get("required_agent_count", 0)))}개 · 검증 row {escape(str(validation_summary.get("check_count", 0)))}개</p>
              <p>실패 Agent: {escape(failed_agents)} · Critic 검토: {escape(critic_findings)}</p>
            </article>
          </div>
          <div id="evidence-audit-items" class="reason-list" data-evidence-audit-section="evidence-items">
{evidence_cards}
          </div>
          <div id="evidence-audit-log" class="audit-log" role="list" aria-label="감사 로그 타임라인" data-evidence-audit-section="audit-log" data-audit-log-display="timeline">
{audit_cards}
          </div>
        </section>"""


def _evidence_audit_item_card(item: dict[str, Any]) -> str:
    artifact_refs = ", ".join(str(ref) for ref in item.get("artifact_refs", ()) if str(ref)) or "없음"
    reason_codes = ", ".join(str(code) for code in item.get("reason_codes", ()) if str(code)) or "없음"
    return f"""            <article class="reason-card" data-evidence-audit-item-id="{escape(str(item.get("evidence_id", "")))}" data-evidence-audit-source="{escape(str(item.get("source", "")))}">
              <span class="code">{escape(str(item.get("source", "")))}</span>
              <strong>{escape(str(item.get("evidence_id", "")))}</strong>
              <p>{escape(str(item.get("summary", "")))}</p>
              <p>artifact_refs={escape(artifact_refs)}</p>
              <p>reason_codes={escape(reason_codes)}</p>
            </article>"""


def _evidence_audit_log_card(item: dict[str, Any]) -> str:
    severity = str(item.get("severity", "info"))
    artifact_refs = ", ".join(str(ref) for ref in item.get("artifact_refs", ()) if str(ref)) or "없음"
    return f"""            <article class="audit-event {escape(severity)}" role="listitem" data-audit-timeline-item="true" data-evidence-audit-event-id="{escape(str(item.get("event_id", "")))}" data-evidence-audit-agent-id="{escape(str(item.get("agent_id", "")))}">
              <span class="code">{escape(str(item.get("agent_id", "")))}</span>
              <strong>{escape(str(item.get("event_type", "")))} / {escape(severity)}</strong>
              <p>{escape(str(item.get("message", "")))}</p>
              <p>artifact_refs={escape(artifact_refs)}</p>
            </article>"""


def _local_rule_decision_result(
    customer: dict[str, Any],
    *,
    reason_items: list[dict[str, str]],
    llm_report_service_status: dict[str, Any],
) -> dict[str, Any]:
    reason_codes = [str(item.get("code", "")) for item in reason_items if item.get("code")]
    if not reason_codes:
        raise ValueError(f"customer {customer['customer_id']} local rule result has no reason codes")
    status = dict(llm_report_service_status)
    return {
        "schema_version": "senior-safe-mileage-local-rule-decision-result/v1",
        "available": True,
        "customer_id": str(customer["customer_id"]),
        "care_decision": str(customer["care_decision"]),
        "decision_source": "evaluation_agent_local_rules",
        "reason_code_source": "evaluation_agent_customer_snapshot",
        "reason_codes": reason_codes,
        "reason_items": reason_items,
        "independent_of_openai": True,
        "llm_report_mode": str(status.get("report_mode", "pending")),
        "llm_fallback_active": bool(status.get("fallback_active")),
        "summary": (
            "고객별 케어 판정과 XAI reason code는 OpenAI 응답이 아니라 "
            "Evaluation Agent의 로컬 규칙 산출물에서 표시됩니다."
        ),
    }


def _local_rule_decision_section(local_rule_result: dict[str, Any]) -> str:
    reason_codes = "".join(
        f'              <span class="code">{escape(str(code))}</span>'
        for code in local_rule_result.get("reason_codes", ())
    )
    return f"""        <section id="local-rule-decision-result" aria-labelledby="local-rule-decision-heading" data-local-rule-decision-source="{escape(str(local_rule_result.get("decision_source", "")))}" data-local-rule-reason-code-source="{escape(str(local_rule_result.get("reason_code_source", "")))}" data-local-rule-independent-of-openai="{str(bool(local_rule_result.get("independent_of_openai"))).lower()}" data-local-rule-llm-fallback-active="{str(bool(local_rule_result.get("llm_fallback_active"))).lower()}">
          <h2 id="local-rule-decision-heading">로컬 규칙 기반 판정</h2>
          <p>{escape(str(local_rule_result.get("summary", "")))}</p>
          <div class="aux-section-list">
            <article class="aux-section" data-local-rule-section="decision">
              <h3>판정</h3>
              <p><span class="{_decision_class(str(local_rule_result.get("care_decision", "")))}">{escape(str(local_rule_result.get("care_decision", "")))}</span></p>
            </article>
            <article class="aux-section" data-local-rule-section="reason-codes">
              <h3>XAI reason code</h3>
              <p>{reason_codes or "없음"}</p>
            </article>
          </div>
        </section>"""


def _policy_validation_entry_dashboard_section(dashboard: dict[str, Any]) -> str:
    capture = dict(dashboard.get("risk_change_capture", {}))
    false_positive = dict(dashboard.get("false_positive_gate", {}))
    misclassification = dict(dashboard.get("misclassification_check", {}))
    ab_summary = dict(dashboard.get("ab_summary", {}))
    pass_rate = _format_percent(float(dashboard.get("agent_validation_pass_rate", 0.0)))
    proposed_capture = _format_percent(float(ab_summary.get("proposed_capture_rate", 0.0)))
    baseline_capture = _format_percent(float(ab_summary.get("baseline_capture_rate", 0.0)))
    status_class = "passed" if dashboard.get("agent_validation_passed") else "review"
    gate_class = "passed" if dashboard.get("approval_gate_passed") else "review"
    action_links = "\n".join(
        f'          <a class="entry-action" href="{escape(str(link.get("href", "")))}">{escape(str(link.get("label", "")))}</a>'
        for link in dashboard.get("primary_flow_links", ())
    )
    section_order = ",".join(str(item) for item in dashboard.get("section_order", ()))
    return f"""    <section id="policy-validation-dashboard" class="entry-dashboard" aria-labelledby="policy-validation-dashboard-heading" data-first-entry-screen="true" data-entry-screen-role="{escape(str(dashboard.get("screen_role", "")))}" data-entry-section-order="{escape(section_order)}" data-selected-policy-candidate-id="{escape(str(dashboard.get("selected_candidate_id", "")))}" data-policy-candidate-count="{escape(str(dashboard.get("policy_candidate_count", 0)))}" data-agent-validation-passed="{str(bool(dashboard.get("agent_validation_passed"))).lower()}" data-approval-gate-passed="{str(bool(dashboard.get("approval_gate_passed"))).lower()}">
      <h2 id="policy-validation-dashboard-heading">정책/검증 대시보드</h2>
      <p>Policy Search Agent가 선택한 후보와 Agent-in-the-loop 검증 상태를 첫 화면에서 확인합니다.</p>
      <div class="entry-dashboard-grid">
        <article class="entry-card" data-entry-card="selected-policy">
          <h3>선택 정책 후보</h3>
          <p><span class="code">{escape(str(dashboard.get("selected_candidate_id", "")))}</span></p>
          <strong>{escape(str(dashboard.get("policy_candidate_count", 0)))}개 후보</strong>
        </article>
        <article class="entry-card" data-entry-card="agent-validation">
          <h3>Agent 검증</h3>
          <p><span class="status-pill {escape(status_class)}">{escape("통과" if dashboard.get("agent_validation_passed") else "검토")}</span></p>
          <strong>{escape(pass_rate)}</strong>
          <p>검증 row {escape(str(dashboard.get("agent_validation_check_count", 0)))}개</p>
        </article>
        <article class="entry-card" data-entry-card="approval-gate">
          <h3>승인 게이트</h3>
          <p><span class="status-pill {escape(gate_class)}">{escape("통과" if dashboard.get("approval_gate_passed") else "검토")}</span></p>
          <strong>{escape(str(capture.get("count", 0)))}/{escape(str(capture.get("target_count", 0)))} 포착</strong>
          <p>오탐 {escape(str(false_positive.get("count", 0)))}/{escape(str(false_positive.get("limit", 0)))} · 오분류 {escape(str(misclassification.get("count", 0)))}/{escape(str(misclassification.get("limit", 0)))}</p>
        </article>
        <article class="entry-card" data-entry-card="ab-comparison">
          <h3>A/B 비교</h3>
          <p>제안 {escape(proposed_capture)} · 기존 {escape(baseline_capture)}</p>
          <strong>{escape(str(ab_summary.get("decision_changed_count", 0)))}건 변경</strong>
          <p>{escape(str(ab_summary.get("customer_count", 0)))}명 동일 입력 비교</p>
        </article>
      </div>
      <div class="entry-actions" aria-label="정책/검증 대시보드 주요 흐름">
{action_links}
      </div>
    </section>"""


def _score_panel_section(scores: dict[str, Any], render_state: dict[str, Any]) -> str:
    source = str(render_state.get("source", "evaluation_agent_customer_snapshot"))
    state = str(render_state.get("render_state", "ready"))
    independent = bool(render_state.get("independent_of_llm_report", True))
    return f"""        <div class="panel" id="score-panel" data-score-render-state="{escape(state)}" data-score-independent-of-llm-report="{str(independent).lower()}" data-score-source="{escape(source)}">
          <h2>판정 점수</h2>
          <div class="metrics">
            <div class="metric"><span>기존 마일리지</span><strong>{_format_score(scores["mileage_baseline_score"])}</strong></div>
            <div class="metric"><span>Senior Safe Mileage</span><strong>{_format_score(scores["senior_safe_mileage_score"])}</strong></div>
            <div class="metric"><span>위험변화</span><strong>{_format_score(scores["risk_change_score"])}</strong></div>
          </div>
        </div>"""


def _ui_render_state(
    *,
    llm_report_service_status: dict[str, Any],
    agent_audit: dict[str, Any],
    customer_ab_comparison: dict[str, Any],
) -> dict[str, Any]:
    llm_mode = str(llm_report_service_status.get("report_mode", "pending"))
    llm_available = bool(llm_report_service_status.get("available"))
    return {
        "schema_version": "senior-safe-mileage-ui-render-state/v1",
        "llm_report": {
            "render_state": "ready" if llm_available else llm_mode,
            "available": llm_available,
            "report_mode": llm_mode,
            "fallback_active": bool(llm_report_service_status.get("fallback_active")),
        },
        "score_panel": {
            "render_state": "ready",
            "independent_of_llm_report": True,
            "source": "evaluation_agent_customer_snapshot",
            "required_scores": [
                "mileage_baseline_score",
                "senior_safe_mileage_score",
                "risk_change_score",
            ],
        },
        "agent_validation": {
            "render_state": "ready",
            "independent_of_llm_report": True,
            "source": "validation_pipeline_service",
            "check_count": int(agent_audit.get("check_count", 0)),
            "validation_pass_rate": float(agent_audit.get("validation_pass_rate", 0.0)),
        },
        "ab_comparison": {
            "render_state": "ready",
            "independent_of_llm_report": True,
            "source": "evaluation_agent_customer_snapshot",
            "same_customer_input": bool(customer_ab_comparison.get("same_customer_input")),
        },
        "core_outputs_independent_of_llm_report": True,
    }


def _customer_ab_comparison_layout_model(customer: dict[str, Any]) -> dict[str, Any]:
    record = dict(customer.get("model_comparison_record") or {})
    ab_comparison = dict(customer.get("ab_comparison") or {})
    metrics = dict(record.get("metrics") or ab_comparison.get("metrics") or {})
    core_metrics = dict(record.get("core_metrics") or metrics.get("core_metrics") or {})
    baseline = dict(core_metrics.get("baseline") or {})
    proposed = dict(core_metrics.get("proposed") or {})
    difference = dict(core_metrics.get("difference") or {})
    baseline_model = dict(record.get("baseline_model") or metrics.get("baseline_model") or {})
    proposed_model = dict(record.get("proposed_model") or metrics.get("proposed_model") or {})
    comparison_input = dict(record.get("comparison_input") or metrics.get("comparison_input") or {})

    if not baseline or not proposed:
        raise ValueError(f"customer {customer['customer_id']} has no A/B core metrics")

    models = {
        "baseline": {
            "label": "기존 산식",
            "model_id": str(baseline.get("model_id") or baseline_model.get("model_id", "")),
            "score": float(baseline.get("score", ab_comparison.get("baseline_score", 0.0))),
            "grade": str(baseline.get("grade", "")),
            "decision": str(baseline.get("decision", "")),
            "detected": bool(baseline.get("detected", ab_comparison.get("baseline_detected"))),
            "threshold": baseline_model.get("threshold", metrics.get("baseline_threshold_annualized_km", "")),
            "pricing_action": str(baseline.get("pricing_action", "")),
            "net_premium_adjustment_pct": float(baseline.get("net_premium_adjustment_pct", 0.0)),
            "reason_codes": [str(code) for code in baseline_model.get("reason_codes", ())],
        },
        "proposed": {
            "label": "제안 모델",
            "model_id": str(proposed.get("model_id") or proposed_model.get("model_id", "")),
            "score": float(proposed.get("score", ab_comparison.get("proposed_score", 0.0))),
            "grade": str(proposed.get("grade", "")),
            "decision": str(proposed.get("decision", "")),
            "detected": bool(proposed.get("detected", ab_comparison.get("proposed_detected"))),
            "threshold": proposed_model.get("threshold", metrics.get("proposed_care_threshold", "")),
            "pricing_action": str(proposed.get("pricing_action", "")),
            "net_premium_adjustment_pct": float(proposed.get("net_premium_adjustment_pct", 0.0)),
            "reason_codes": [str(code) for code in proposed_model.get("reason_codes", ())],
        },
    }
    difference_model = {
        "score_delta": float(difference.get("score_delta", 0.0)),
        "grade_changed": bool(difference.get("grade_changed")),
        "decision_changed": bool(difference.get("decision_changed")),
        "premium_adjustment_delta_pct": float(difference.get("premium_adjustment_delta_pct", 0.0)),
        "proposed_captures_risk_change_not_baseline": bool(
            difference.get("proposed_captures_risk_change_not_baseline")
        ),
    }
    difference_highlights = _ab_difference_highlights(models, difference_model)
    business_impact_explanation = _ab_business_impact_explanation(
        models,
        difference_model,
        metrics,
    )

    return {
        "schema_version": "senior-safe-mileage-customer-ab-layout/v1",
        "customer_id": str(customer["customer_id"]),
        "same_customer_input": bool(record.get("same_customer_input", metrics.get("same_customer_input"))),
        "input_data_ref": str(
            record.get("input_data_ref")
            or comparison_input.get("input_data_ref")
            or metrics.get("input_data_ref", "")
        ),
        "observation_period": dict(comparison_input.get("observation_period", {})),
        "models": models,
        "difference": difference_model,
        "difference_highlights": difference_highlights,
        "change_explanation_sections": _ab_change_explanation_sections(
            models,
            difference_model,
            difference_highlights,
            business_impact_explanation,
        ),
        "business_impact_explanation": business_impact_explanation,
    }


def _ab_comparison_section(comparison: dict[str, Any]) -> str:
    baseline = dict(comparison["models"]["baseline"])
    proposed = dict(comparison["models"]["proposed"])
    difference = dict(comparison["difference"])
    highlights = list(comparison.get("difference_highlights", ()))
    business_impact = dict(comparison.get("business_impact_explanation", {}))
    explanation_sections = dict(comparison.get("change_explanation_sections") or {})
    if not explanation_sections:
        explanation_sections = _ab_change_explanation_sections(
            comparison["models"],
            difference,
            highlights,
            business_impact,
        )
    period = dict(comparison.get("observation_period", {}))
    period_text = (
        f"baseline {period.get('baseline_days', 60)}일 + "
        f"recent {period.get('recent_days', 30)}일"
    )
    capture_text = (
        "제안 모델 단독 포착"
        if difference.get("proposed_captures_risk_change_not_baseline")
        else "동일/비포착"
    )
    return f"""        <section id="customer-ab-comparison" aria-labelledby="customer-ab-heading" data-ab-layout="side-by-side" data-same-customer-input="{str(bool(comparison.get("same_customer_input"))).lower()}" data-ab-render-state="ready" data-ab-independent-of-llm-report="true">
          <h2 id="customer-ab-heading">A/B 비교</h2>
          <p>동일 고객의 {escape(period_text)} 입력을 기준으로 기존 산식 결과와 Senior Safe Mileage 제안 모델 결과를 나란히 비교합니다.</p>
          <div class="ab-compare">
{_ab_model_card("baseline", baseline)}
{_ab_model_card("proposed", proposed)}
          </div>
{_ab_difference_highlight_section(highlights)}
{_ab_change_explanation_section(explanation_sections)}
          <div class="ab-delta" data-ab-decision-changed="{str(bool(difference.get("decision_changed"))).lower()}" data-ab-grade-changed="{str(bool(difference.get("grade_changed"))).lower()}">
            <p><strong>차이 요약</strong></p>
            <p>점수 차이 {_format_signed_score(difference.get("score_delta", 0.0))} · 보험료 조정 차이 {_format_signed_percent(difference.get("premium_adjustment_delta_pct", 0.0))} · {escape(capture_text)}</p>
            <p><span class="code">{escape(str(comparison.get("input_data_ref", "")))}</span></p>
          </div>
{_ab_business_impact_section(business_impact)}
        </section>"""


def _ab_difference_highlights(
    models: dict[str, dict[str, Any]],
    difference: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline = dict(models["baseline"])
    proposed = dict(models["proposed"])
    baseline_reason_codes = [str(code) for code in baseline.get("reason_codes", ())]
    proposed_reason_codes = [str(code) for code in proposed.get("reason_codes", ())]
    baseline_only = [code for code in baseline_reason_codes if code not in proposed_reason_codes]
    proposed_only = [code for code in proposed_reason_codes if code not in baseline_reason_codes]
    return [
        {
            "key": "score",
            "label": "점수",
            "baseline_value": _format_score(baseline.get("score", 0.0)),
            "proposed_value": _format_score(proposed.get("score", 0.0)),
            "delta_label": _format_signed_score(difference.get("score_delta", 0.0)),
            "changed": abs(float(difference.get("score_delta", 0.0))) > 0.004,
        },
        {
            "key": "grade",
            "label": "등급",
            "baseline_value": str(baseline.get("grade", "")),
            "proposed_value": str(proposed.get("grade", "")),
            "delta_label": "변경" if difference.get("grade_changed") else "동일",
            "changed": bool(difference.get("grade_changed")),
        },
        {
            "key": "decision",
            "label": "판정",
            "baseline_value": str(baseline.get("decision", "")),
            "proposed_value": str(proposed.get("decision", "")),
            "delta_label": "변경" if difference.get("decision_changed") else "동일",
            "changed": bool(difference.get("decision_changed")),
        },
        {
            "key": "reason_codes",
            "label": "주요 reason code",
            "baseline_value": ", ".join(baseline_only) or "공통/없음",
            "proposed_value": ", ".join(proposed_only) or "공통/없음",
            "delta_label": f"+{len(proposed_only)} / -{len(baseline_only)}",
            "changed": bool(baseline_only or proposed_only),
        },
    ]


def _ab_difference_highlight_section(highlights: list[dict[str, Any]]) -> str:
    rows = "\n".join(_ab_difference_highlight_row(row) for row in highlights)
    return f"""          <div class="ab-highlight" id="ab-difference-highlights" data-ab-difference-highlight-count="{len(highlights)}">
{rows}
          </div>"""


def _ab_difference_highlight_row(row: dict[str, Any]) -> str:
    changed = bool(row.get("changed"))
    return f"""            <div class="ab-highlight-row {'changed' if changed else 'same'}" data-ab-difference-field="{escape(str(row.get("key", "")))}" data-ab-difference-changed="{str(changed).lower()}">
              <span class="ab-highlight-label">{escape(str(row.get("label", "")))}</span>
              <span class="ab-highlight-value"><strong>기존</strong> {escape(str(row.get("baseline_value", "")))}</span>
              <span class="ab-highlight-value"><strong>제안</strong> {escape(str(row.get("proposed_value", "")))}</span>
              <span class="ab-highlight-delta">{escape(str(row.get("delta_label", "")))}</span>
            </div>"""


def _ab_change_explanation_sections(
    models: dict[str, dict[str, Any]],
    difference: dict[str, Any],
    highlights: list[dict[str, Any]],
    business_impact: dict[str, Any],
) -> dict[str, Any]:
    baseline = dict(models["baseline"])
    proposed = dict(models["proposed"])
    changed_fields = [str(row["label"]) for row in highlights if row.get("changed")]
    proposed_reason_codes = [str(code) for code in proposed.get("reason_codes", ())]
    baseline_reason_codes = [str(code) for code in baseline.get("reason_codes", ())]
    proposed_only_reason_codes = [
        code for code in proposed_reason_codes if code not in baseline_reason_codes
    ]
    if difference.get("proposed_captures_risk_change_not_baseline"):
        summary = (
            f"{baseline.get('label', '기존 산식')}은 {baseline.get('decision', '')}으로 유지했지만 "
            f"{proposed.get('label', '제안 모델')}은 {proposed.get('decision', '')}으로 변경했습니다."
        )
    elif difference.get("decision_changed"):
        summary = (
            f"고객 판정이 {baseline.get('decision', '')}에서 "
            f"{proposed.get('decision', '')}으로 변경되었습니다."
        )
    else:
        summary = "고객 판정은 유지되며 점수, 등급, reason code 차이를 보조 근거로 확인합니다."

    reasons = [
        f"변경 항목: {', '.join(changed_fields) if changed_fields else '없음'}",
        f"기존 reason code: {', '.join(baseline_reason_codes) if baseline_reason_codes else '없음'}",
        f"제안 모델 추가 reason code: {', '.join(proposed_only_reason_codes) if proposed_only_reason_codes else '없음'}",
    ]
    if difference.get("proposed_captures_risk_change_not_baseline"):
        reasons.append("생활권 밖 변화와 위험변화 신호가 제안 모델에서만 예방 케어 근거로 반영되었습니다.")

    impact_items = [
        str(business_impact.get("summary", "")),
        f"라우팅 큐: {business_impact.get('routing_queue', '')}",
        f"직원 검토 필요: {bool(business_impact.get('requires_staff_review'))}",
    ]
    return {
        "schema_version": "senior-safe-mileage-ab-change-explanation-sections/v1",
        "section_count": 3,
        "sections": [
            {
                "key": "change-summary",
                "title": "변경 요약",
                "body": summary,
                "items": [
                    f"점수 차이 {_format_signed_score(difference.get('score_delta', 0.0))}",
                    f"등급 변경={bool(difference.get('grade_changed'))}",
                    f"판정 변경={bool(difference.get('decision_changed'))}",
                ],
            },
            {
                "key": "change-reasons",
                "title": "변경 사유",
                "body": "두 모델의 reason code와 변경 필드를 기준으로 사유를 분리해 표시합니다.",
                "items": reasons,
            },
            {
                "key": "impact-explanation",
                "title": "영향 설명",
                "body": "보험사 직원이 후속 업무 큐와 운영 통제를 판단할 수 있는 영향 설명입니다.",
                "items": [item for item in impact_items if item],
            },
        ],
    }


def _ab_change_explanation_section(explanation: dict[str, Any]) -> str:
    sections = "\n".join(
        _ab_change_explanation_card(section)
        for section in explanation.get("sections", ())
    )
    return f"""          <div id="ab-change-explanation-sections" class="aux-section-list" data-ab-change-explanation-section-count="{escape(str(explanation.get("section_count", 0)))}">
{sections}
          </div>"""


def _ab_change_explanation_card(section: dict[str, Any]) -> str:
    return f"""            <article class="aux-section" data-ab-explanation-section="{escape(str(section.get("key", "")))}">
              <h3>{escape(str(section.get("title", "")))}</h3>
              <p>{escape(str(section.get("body", "")))}</p>
              <ul>{_html_list_items(section.get("items", ()))}</ul>
            </article>"""


def _ab_business_impact_explanation(
    models: dict[str, dict[str, Any]],
    difference: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    baseline = dict(models["baseline"])
    proposed = dict(models["proposed"])
    decision_changed = bool(difference.get("decision_changed"))
    proposed_only_capture = bool(difference.get("proposed_captures_risk_change_not_baseline"))
    premium_delta = float(difference.get("premium_adjustment_delta_pct", 0.0))
    requires_staff_review = proposed_only_capture or str(proposed.get("decision")) == "예방 케어"
    routing_queue = "예방 케어 상담" if requires_staff_review else "자동 갱신 심사"

    if proposed_only_capture:
        summary = (
            f"기존 산식은 저주행 할인 관점의 {baseline.get('decision', '')}으로 처리하지만, "
            f"제안 모델은 생활권 밖 변화와 위험변화 신호를 반영해 {proposed.get('decision', '')}으로 전환합니다."
        )
    elif decision_changed:
        summary = (
            f"두 모델의 고객 판정이 {baseline.get('decision', '')}에서 "
            f"{proposed.get('decision', '')}으로 달라져 갱신 심사와 안내 문구가 변경됩니다."
        )
    else:
        summary = "두 모델의 판정이 같아 보험 업무 흐름은 유지되며, 제안 모델 근거만 보조 확인 자료로 사용합니다."

    workflow_impacts = [
        f"라우팅 큐: {routing_queue}",
        f"판정 처리: 기존 {baseline.get('decision', '')} -> 제안 {proposed.get('decision', '')}",
        f"보험료 조정 차이: {_format_signed_percent(premium_delta)}",
    ]
    if proposed_only_capture:
        workflow_impacts.append("저주행 할인 자동 처리 전에 예방 케어 안내 대상 여부를 확인합니다.")
    else:
        workflow_impacts.append("기존 마일리지 업무 흐름과 제안 모델 보조 근거를 함께 확인합니다.")

    staff_actions = [
        "고객 상세 화면의 XAI reason code와 생활권 변화 근거를 확인",
        "상담 스크립트에는 예방 안내와 안전 운전 지원 목적을 우선 반영",
    ]
    if requires_staff_review:
        staff_actions.append("보험료 불이익이 아닌 예방 케어 안내 대상으로 수동 검토")
    else:
        staff_actions.append("자동 갱신 처리 후 제안 모델 근거를 내부 메모로 보관")

    operational_controls = [
        "동일 고객 요약 피처 input_data_ref 기준으로 A/B 결과를 비교",
        "OpenAI API에는 식별자 없는 요약 피처만 전달하고 원본 trip id/GPS는 제외",
        "Agent 검증과 오탐 제한 게이트를 통과한 정책 후보 기준으로만 업무 활용",
    ]

    return {
        "schema_version": "senior-safe-mileage-ab-business-impact/v1",
        "audience": "보험사 직원",
        "summary": summary,
        "requires_staff_review": requires_staff_review,
        "routing_queue": routing_queue,
        "workflow_impacts": workflow_impacts,
        "staff_actions": staff_actions,
        "operational_controls": operational_controls,
        "same_customer_input": bool(metrics.get("same_customer_input")),
        "risk_change_target": bool(metrics.get("risk_change_target")),
    }


def _ab_business_impact_section(impact: dict[str, Any]) -> str:
    if not impact:
        return ""
    workflow_items = _html_list_items(impact.get("workflow_impacts", ()))
    staff_action_items = _html_list_items(impact.get("staff_actions", ()))
    control_items = _html_list_items(impact.get("operational_controls", ()))
    return f"""          <div id="ab-business-impact" class="aux-section-list" data-ab-business-impact-review-required="{str(bool(impact.get("requires_staff_review"))).lower()}" data-ab-business-impact-routing="{escape(str(impact.get("routing_queue", "")))}">
            <article class="aux-section">
              <h3>보험 업무 영향</h3>
              <p>{escape(str(impact.get("summary", "")))}</p>
              <p>대상 업무 큐: {escape(str(impact.get("routing_queue", "")))} · 직원 검토 필요={escape(str(bool(impact.get("requires_staff_review"))))}</p>
            </article>
            <article class="aux-section" data-ab-business-impact-section="workflow">
              <h3>업무 처리 차이</h3>
              <ul>{workflow_items}</ul>
            </article>
            <article class="aux-section" data-ab-business-impact-section="staff-actions">
              <h3>직원 조치</h3>
              <ul>{staff_action_items}</ul>
            </article>
            <article class="aux-section" data-ab-business-impact-section="controls">
              <h3>운영 통제</h3>
              <ul>{control_items}</ul>
            </article>
          </div>"""


def _html_list_items(items: Any) -> str:
    values = [str(item) for item in items if str(item)]
    if not values:
        return "<li>없음</li>"
    return "".join(f"<li>{escape(value)}</li>" for value in values)


def _ab_model_card(model_key: str, model: dict[str, Any]) -> str:
    reason_codes = ", ".join(str(code) for code in model.get("reason_codes", ())) or "없음"
    detected = "포착" if model.get("detected") else "미포착"
    return f"""            <article class="ab-model" data-ab-model="{escape(model_key)}">
              <h3>{escape(str(model.get("label", "")))}</h3>
              <div class="ab-row"><span>모델 ID</span><strong>{escape(str(model.get("model_id", "")))}</strong></div>
              <div class="ab-row"><span>점수</span><strong>{escape(_format_score(model.get("score", 0.0)))}</strong></div>
              <div class="ab-row"><span>등급</span><strong>{escape(str(model.get("grade", "")))}</strong></div>
              <div class="ab-row"><span>판정</span><strong>{escape(str(model.get("decision", "")))}</strong></div>
              <div class="ab-row"><span>위험변화</span><strong>{escape(detected)}</strong></div>
              <div class="ab-row"><span>기준값</span><strong>{escape(_format_threshold(model.get("threshold", "")))}</strong></div>
              <div class="ab-row"><span>보험료 영향</span><strong>{escape(_format_signed_percent(model.get("net_premium_adjustment_pct", 0.0)))}</strong></div>
              <div class="ab-row"><span>reason code</span><strong>{escape(reason_codes)}</strong></div>
            </article>"""


def _policy_candidate_comparison_row(
    candidate: dict[str, Any],
    *,
    selected_candidate_id: str,
) -> dict[str, Any]:
    weights = {key: float(value) for key, value in dict(candidate.get("weights", {})).items()}
    thresholds = dict(candidate.get("thresholds", {}))
    metrics = dict(candidate.get("metrics", {}))
    scores = dict(candidate.get("scores", {}))
    tier_threshold = dict(thresholds.get("tier_threshold", {}))
    return {
        "candidate_id": str(candidate["candidate_id"]),
        "rank": int(candidate["rank"]),
        "is_selected": str(candidate["candidate_id"]) == selected_candidate_id,
        "weights": weights,
        "thresholds": {
            "threshold_candidate_id": str(thresholds.get("threshold_candidate_id", "")),
            "care_threshold": float(thresholds.get("care_threshold", 0.0)),
            "care_threshold_percentile": float(thresholds.get("care_threshold_percentile", 0.0)),
            "care_threshold_expected_top_n": int(thresholds.get("care_threshold_expected_top_n", 0)),
            "tier_threshold": tier_threshold,
        },
        "metrics": {
            "risk_change_target_capture_count": int(metrics.get("risk_change_target_capture_count", 0)),
            "non_target_false_positive_count": int(metrics.get("non_target_false_positive_count", 0)),
            "total_misclassification_count": int(metrics.get("total_misclassification_count", 0)),
            "passes_approval_gate": bool(metrics.get("passes_approval_gate")),
            "ranking_score": float(scores.get("ranking_score", metrics.get("ranking_score", 0.0))),
        },
    }


def _selected_policy_candidate_detail(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(candidate.get("metrics", {}))
    scores = dict(candidate.get("scores", {}))
    thresholds = dict(candidate.get("thresholds", {}))
    metadata = dict(candidate.get("metadata", {}))
    reason_metadata = dict(candidate.get("reason_metadata", {}))
    reason_codes = [str(code) for code in reason_metadata.get("selected_reason_codes", ())]
    strengths = [str(item) for item in reason_metadata.get("strengths", ())]
    tradeoffs = [str(item) for item in reason_metadata.get("tradeoffs", ())]
    fairness_notes = [str(item) for item in reason_metadata.get("fairness_notes", ())]
    return {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "rank": int(candidate.get("rank", 0)),
        "rationale": str(
            metadata.get("rationale")
            or candidate.get("rationale")
            or "Policy Search Agent ranking rationale unavailable"
        ),
        "selection_summary": (
            f"포착 {int(metrics.get('risk_change_target_capture_count', 0))}/5, "
            f"오탐 {int(metrics.get('non_target_false_positive_count', 0))}/25, "
            f"오분류 {int(metrics.get('total_misclassification_count', 0))}, "
            f"ranking_score={float(scores.get('ranking_score', metrics.get('ranking_score', 0.0))):.4f}"
        ),
        "approval_gate_passed": bool(metrics.get("passes_approval_gate")),
        "reason_codes": reason_codes,
        "strengths": strengths,
        "tradeoffs": tradeoffs,
        "fairness_notes": fairness_notes,
        "threshold_basis": str(thresholds.get("care_threshold_source", "")),
        "threshold_candidate_id": str(thresholds.get("threshold_candidate_id", "")),
        "persona_detection_counts": dict(reason_metadata.get("persona_detection_counts", {})),
    }


def _policy_candidate_comparison_section(comparison: dict[str, Any]) -> str:
    rows = list(comparison.get("rows", ()))
    table_rows = "\n".join(_policy_candidate_table_row(row) for row in rows)
    selected_detail = dict(comparison.get("selected_candidate_detail", {}))
    selected_detail_section = _selected_policy_candidate_detail_section(selected_detail)
    return f"""        <section id="policy-candidate-comparison" aria-labelledby="policy-candidate-heading" data-policy-candidate-count="{escape(str(comparison.get("candidate_count", len(rows))))}" data-selected-policy-candidate-id="{escape(str(comparison.get("selected_candidate_id", "")))}">
          <h2 id="policy-candidate-heading">정책 후보 탐색 비교</h2>
          <p>Policy Search Agent가 탐색한 후보별 가중치와 기준값을 같은 컬럼 구조로 비교합니다.</p>
          <nav class="section-tabs" aria-label="정책 탐색 근거 및 감사">
            <a class="section-tab active" href="#selected-policy-candidate-rationale" data-policy-search-tab="evidence" aria-current="page">근거</a>
            <a class="section-tab" href="#policy-candidate-audit-table" data-policy-search-tab="audit">감사</a>
          </nav>
          <div class="table-wrap">
            <table id="policy-candidate-audit-table" aria-label="정책 후보 감사 테이블">
              <thead>
                <tr>
                  <th scope="col">순위</th>
                  <th scope="col">후보</th>
                  <th scope="col">마일리지</th>
                  <th scope="col">생활권 내</th>
                  <th scope="col">생활권 밖 안전</th>
                  <th scope="col">위험변화</th>
                  <th scope="col">예방 기준</th>
                  <th scope="col">상위 percentile</th>
                  <th scope="col">S/A/B/C 기준</th>
                  <th scope="col">검증 지표</th>
                </tr>
              </thead>
              <tbody>
{table_rows}
              </tbody>
            </table>
          </div>
{selected_detail_section}
        </section>"""


def _policy_candidate_table_row(row: dict[str, Any]) -> str:
    weights = dict(row.get("weights", {}))
    thresholds = dict(row.get("thresholds", {}))
    metrics = dict(row.get("metrics", {}))
    tier_threshold = dict(thresholds.get("tier_threshold", {}))
    selected_class = " selected" if row.get("is_selected") else ""
    selected_label = " · 선택" if row.get("is_selected") else ""
    tier_text = " / ".join(
        f"{tier}:{_format_score(tier_threshold.get(tier, 0))}"
        for tier in ("S", "A", "B", "C")
    )
    gate = "통과" if metrics.get("passes_approval_gate") else "검토"
    metric_text = (
        f"포착 {metrics.get('risk_change_target_capture_count', 0)}/5 · "
        f"오탐 {metrics.get('non_target_false_positive_count', 0)}/25 · "
        f"오분류 {metrics.get('total_misclassification_count', 0)} · "
        f"{gate}"
    )
    return f"""                <tr class="{selected_class.strip()}" data-policy-candidate-id="{escape(str(row.get("candidate_id", "")))}" data-policy-candidate-rank="{escape(str(row.get("rank", "")))}" data-policy-candidate-selected="{str(bool(row.get("is_selected"))).lower()}">
                  <td class="compact">{escape(str(row.get("rank", "")))}</td>
                  <td><span class="code">{escape(str(row.get("candidate_id", "")))}</span>{escape(selected_label)}</td>
                  <td class="compact">{escape(_format_weight(weights.get("w_mileage", 0.0)))}</td>
                  <td class="compact">{escape(_format_weight(weights.get("w_in_zone", 0.0)))}</td>
                  <td class="compact">{escape(_format_weight(weights.get("w_out_zone_safe", 0.0)))}</td>
                  <td class="compact">{escape(_format_weight(weights.get("w_out_zone_change", 0.0)))}</td>
                  <td class="compact">{escape(_format_score(thresholds.get("care_threshold", 0.0)))}</td>
                  <td class="compact">{escape(_format_percentile(thresholds.get("care_threshold_percentile", 0.0)))}</td>
                  <td><span class="threshold-list">{escape(tier_text)}</span></td>
                  <td>{escape(metric_text)}<br><span class="code">{escape(str(thresholds.get("threshold_candidate_id", "")))}</span></td>
                </tr>"""


def _selected_policy_candidate_detail_section(detail: dict[str, Any]) -> str:
    reason_codes = "\n".join(
        f'              <span class="code">{escape(str(code))}</span>'
        for code in detail.get("reason_codes", ())
    )
    strengths = _bullet_text(detail.get("strengths", ()))
    tradeoffs = _bullet_text(detail.get("tradeoffs", ()))
    fairness_notes = _bullet_text(detail.get("fairness_notes", ()))
    persona_counts = _persona_detection_count_text(detail.get("persona_detection_counts", {}))
    gate = "통과" if detail.get("approval_gate_passed") else "검토"
    return f"""          <div id="selected-policy-candidate-rationale" class="aux-section-list" data-selected-policy-rationale-candidate-id="{escape(str(detail.get("candidate_id", "")))}" data-selected-policy-rationale-gate="{escape(gate)}">
            <article class="aux-section">
              <h3>선택된 정책 후보 선택 근거</h3>
              <p><span class="code">{escape(str(detail.get("candidate_id", "")))}</span> rank {escape(str(detail.get("rank", "")))} · 승인 게이트 {escape(gate)}</p>
              <p>{escape(str(detail.get("rationale", "")))}</p>
              <p>{escape(str(detail.get("selection_summary", "")))}</p>
              <p>threshold_basis={escape(str(detail.get("threshold_basis", "")))} · threshold_candidate_id={escape(str(detail.get("threshold_candidate_id", "")))}</p>
            </article>
            <article class="aux-section" data-selected-policy-rationale-section="reason-codes">
              <h3>선택 reason code</h3>
              <p>{reason_codes or "없음"}</p>
            </article>
            <article class="aux-section" data-selected-policy-rationale-section="strengths">
              <h3>강점</h3>
              <p>{escape(strengths)}</p>
            </article>
            <article class="aux-section" data-selected-policy-rationale-section="tradeoffs">
              <h3>Trade-off</h3>
              <p>{escape(tradeoffs)}</p>
            </article>
            <article class="aux-section" data-selected-policy-rationale-section="fairness-notes">
              <h3>오분류 통제 메모</h3>
              <p>{escape(fairness_notes)}</p>
              <p>{escape(persona_counts)}</p>
            </article>
          </div>"""


def _agent_audit_section(agent_audit: dict[str, Any]) -> str:
    checks = list(agent_audit.get("checks", ()))
    audit_entries = list(agent_audit.get("audit_log_entries", ()))
    check_rows = "\n".join(_agent_audit_check_table_row(row) for row in checks)
    log_rows = "\n".join(_agent_audit_log_card(row) for row in audit_entries)
    message_panels = _agent_audit_message_panels(checks)
    pass_rate = _format_percent(float(agent_audit.get("validation_pass_rate", 0.0)))
    gate_minimum = _format_percent(
        dict(agent_audit.get("approval_gate_thresholds", {})).get("agent_validation_pass_rate_minimum", 0.95)
    )
    passed = bool(agent_audit.get("passed"))
    status_label = "통과" if passed else "검토"
    status_class = "passed" if passed else "review"
    failed_agents = ", ".join(str(agent_id) for agent_id in agent_audit.get("failed_agents", ())) or "없음"
    critic_findings = _bullet_text(agent_audit.get("critic_findings", ()))
    execution_input = dict(agent_audit.get("execution_input", {}))
    selected_policy = dict(execution_input.get("selected_policy", {}))
    selected_scenario = dict(execution_input.get("selected_scenario", {}))
    return f"""        <section id="agent-audit-tab" aria-labelledby="agent-audit-heading" data-agent-audit-passed="{str(bool(agent_audit.get("passed"))).lower()}" data-agent-validation-pass-rate="{escape(str(agent_audit.get("validation_pass_rate", 0.0)))}" data-agent-audit-check-count="{escape(str(agent_audit.get("check_count", len(checks))))}" data-agent-audit-log-count="{escape(str(len(audit_entries)))}" data-agent-validation-render-state="ready" data-agent-validation-independent-of-llm-report="true">
          <h2 id="agent-audit-heading">감사 탭</h2>
          <p>Agent-in-the-loop 검증 결과와 감사 로그를 같은 화면에서 확인합니다.</p>
          <nav class="section-tabs" aria-label="Agent 검증 결과 및 감사 로그">
            <a class="section-tab active" href="#agent-validation-results" data-agent-audit-tab="validation-results" aria-current="page">검증 결과</a>
            <a class="section-tab" href="#agent-audit-log" data-agent-audit-tab="audit-log">감사 로그</a>
          </nav>
          <div class="aux-section-list">
            <article class="aux-section" id="agent-validation-status-panel" data-agent-validation-status-panel="independent" data-agent-validation-status="{escape(status_class)}" data-agent-validation-visual-state="{escape(status_class)}">
              <h3>Agent 검증 상태</h3>
              <p><span class="status-pill {escape(status_class)}" data-agent-validation-status-badge="{escape(status_class)}">{escape(status_label)}</span></p>
              <p>검증 상태는 LLM 리포트 상태와 분리된 독립 영역으로 표시됩니다.</p>
            </article>
            <article class="aux-section" data-agent-audit-section="summary">
              <h3>Agent 검증 요약</h3>
              <p><span class="code">{escape(str(agent_audit.get("run_id", "")))}</span> · {escape(status_label)} · pass rate {escape(pass_rate)} / 기준 {escape(gate_minimum)}</p>
              <p>필수 Agent {escape(str(agent_audit.get("required_agent_count", 0)))}개 중 검증 row {escape(str(agent_audit.get("check_count", 0)))}개 · 실패 Agent: {escape(failed_agents)}</p>
              <p>Critic 검토: {escape(critic_findings)}</p>
            </article>
            <article class="aux-section" id="validation-execution-input" data-validation-execution-input="selected-policy-scenario" data-validation-selected-candidate-id="{escape(str(selected_policy.get("candidate_id", "")))}" data-validation-selected-scenario-id="{escape(str(selected_scenario.get("scenario_id", "")))}">
              <h3>검증 실행 입력</h3>
              <p>선택 정책 <span class="code">{escape(str(selected_policy.get("candidate_id", "")))}</span> · 선택 시나리오 <span class="code">{escape(str(selected_scenario.get("scenario_id", "")))}</span></p>
              <p>관측기간 baseline {escape(str(dict(selected_scenario.get("observation_period", {})).get("baseline_days", "")))}일 + recent {escape(str(dict(selected_scenario.get("observation_period", {})).get("recent_days", "")))}일 · 후보 rank {escape(str(selected_policy.get("rank", "")))}</p>
            </article>
          </div>
{message_panels}
          <div class="table-wrap" id="agent-validation-results" data-agent-validation-result-count="{escape(str(len(checks)))}">
            <table aria-label="Agent-in-the-loop 검증 결과">
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">상태</th>
                  <th scope="col">검증 요약</th>
                  <th scope="col">reason code</th>
                  <th scope="col">산출물</th>
                </tr>
              </thead>
              <tbody>
{check_rows}
              </tbody>
            </table>
          </div>
          <div id="agent-audit-log" class="audit-log" role="list" aria-label="Agent 감사 로그 타임라인" data-agent-audit-log-entry-count="{escape(str(len(audit_entries)))}" data-agent-audit-section="audit-log" data-audit-log-display="timeline">
{log_rows}
          </div>
        </section>"""


def _agent_audit_message_panels(checks: list[Any]) -> str:
    failures = _agent_audit_messages(checks, field="errors")
    warnings = _agent_audit_messages(checks, field="warnings")
    if not failures and not warnings:
        return ""
    failure_panel = _agent_audit_message_panel(
        "failure",
        "실패 메시지",
        failures,
        role="alert",
    )
    warning_panel = _agent_audit_message_panel(
        "warning",
        "경고 메시지",
        warnings,
        role="status",
    )
    return f"""          <div id="agent-validation-message-panels" class="aux-section-list" data-agent-message-panels="failure-warning" data-agent-failure-message-count="{len(failures)}" data-agent-warning-message-count="{len(warnings)}">
{failure_panel}
{warning_panel}
          </div>"""


def _agent_audit_messages(checks: list[Any], *, field: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for row in checks:
        check = dict(row)
        agent_id = str(check.get("agent_id", ""))
        for message in check.get(field, ()):
            text = str(message)
            if text:
                messages.append({"agent_id": agent_id, "message": text})
    return messages


def _agent_audit_message_panel(
    message_type: str,
    heading: str,
    messages: list[dict[str, str]],
    *,
    role: str,
) -> str:
    items = "".join(
        f'<li data-agent-message-type="{escape(message_type)}" data-agent-message-agent-id="{escape(item["agent_id"])}"><span class="code">{escape(item["agent_id"])}</span> {escape(item["message"])}</li>'
        for item in messages
    )
    if not items:
        items = '<li data-agent-message-empty="true">없음</li>'
    return f"""            <article class="message-area {escape(message_type)}" role="{escape(role)}" data-agent-message-area="{escape(message_type)}">
              <h3>{escape(heading)}</h3>
              <ul class="message-list">{items}</ul>
            </article>"""


def _agent_audit_check_table_row(row: dict[str, Any]) -> str:
    passed = bool(row.get("passed"))
    status = "통과" if passed else "검토"
    status_class = "passed" if passed else "review"
    reason_codes = ", ".join(str(code) for code in row.get("reason_codes", ())) or "없음"
    artifact_refs = ", ".join(str(artifact_id) for artifact_id in row.get("artifact_ids", ())) or "없음"
    return f"""                <tr data-agent-validation-agent-id="{escape(str(row.get("agent_id", "")))}" data-agent-validation-passed="{str(passed).lower()}">
                  <td><span class="code">{escape(str(row.get("agent_id", "")))}</span></td>
                  <td class="compact"><span class="status-pill {escape(status_class)}" data-agent-validation-row-status="{escape(status_class)}">{escape(status)}</span> / {escape(str(row.get("status", "")))}</td>
                  <td>{escape(str(row.get("summary", "")))}</td>
                  <td>{escape(reason_codes)}</td>
                  <td>{escape(artifact_refs)}</td>
                </tr>"""


def _agent_audit_log_card(row: dict[str, Any]) -> str:
    severity = str(row.get("severity", "info"))
    artifact_refs = ", ".join(str(ref) for ref in row.get("artifact_refs", ())) or "없음"
    return f"""            <article class="audit-event {escape(severity)}" role="listitem" data-audit-timeline-item="true" data-agent-audit-event-id="{escape(str(row.get("event_id", "")))}" data-agent-audit-agent-id="{escape(str(row.get("agent_id", "")))}" data-agent-audit-event-type="{escape(str(row.get("event_type", "")))}">
              <span class="code">{escape(str(row.get("agent_id", "")))}</span>
              <strong>{escape(str(row.get("event_type", "")))} / {escape(severity)}</strong>
              <p>{escape(str(row.get("message", "")))}</p>
              <p>artifact_refs={escape(artifact_refs)}</p>
            </article>"""


def _bullet_text(items: Any) -> str:
    values = [str(item) for item in items if str(item)]
    return " / ".join(values) if values else "없음"


def _persona_detection_count_text(counts: dict[str, Any]) -> str:
    if not counts:
        return "persona_detection_counts=없음"
    parts = []
    for persona_type, row in sorted(counts.items()):
        metrics = dict(row)
        parts.append(
            f"{persona_type}: proposed {metrics.get('proposed_detected', 0)}/{metrics.get('customer_count', 0)}, "
            f"baseline {metrics.get('baseline_detected', 0)}/{metrics.get('customer_count', 0)}"
        )
    return "persona_detection_counts=" + " / ".join(parts)


def _proxy_label_section(proxy_label_result: dict[str, Any]) -> str:
    thresholds = ", ".join(
        f"{key}={value}"
        for key, value in dict(proxy_label_result.get("thresholds", {})).items()
    )
    reason_code_items = "\n".join(
        _reason_card(
            {
                "code": code,
                "label": REASON_CODE_LABELS.get(code, "proxy label 보조 신호"),
                "evidence": proxy_label_result["summary"],
            }
        )
        for code in proxy_label_result.get("reason_codes", ())
    )
    return f"""        <section id="proxy-label-result" aria-labelledby="proxy-label-heading" data-proxy-label-target="{str(bool(proxy_label_result.get("is_target"))).lower()}">
          <h2 id="proxy-label-heading">Proxy label 결과</h2>
          <p>실제 사고/클레임 데이터 없이 합성 trip log의 비식별 요약 피처로 만든 평가용 정답 라벨입니다.</p>
          <div class="reason-list" data-proxy-label-rule-id="{escape(str(proxy_label_result.get("rule_id", "")))}">
            <article class="reason-card">
              <span class="code">{escape(str(proxy_label_result.get("rule_id", "")))}</span>
              <strong>{escape(str(proxy_label_result.get("summary", "")))}</strong>
              <p>expected_care_decision={escape(str(proxy_label_result.get("expected_care_decision", "")))}</p>
              <p>thresholds: {escape(thresholds)}</p>
            </article>
{reason_code_items}
          </div>
        </section>"""


def _hybrid_evaluation_section(hybrid_result: dict[str, Any]) -> str:
    baseline = dict(hybrid_result["baseline"])
    proposed = dict(hybrid_result["proposed"])
    proposed_reason_cards = "\n".join(
        _reason_card(
            {
                "code": code,
                "label": REASON_CODE_LABELS.get(code, "hybrid 평가 보조 신호"),
                "evidence": proposed["rationale"],
            }
        )
        for code in proposed.get("reason_codes", ())
    )
    return f"""        <section id="hybrid-evaluation-result" aria-labelledby="hybrid-heading" data-hybrid-proposed-verdict="{escape(str(proposed.get("verdict", "")))}" data-hybrid-proposed-passed="{str(bool(proposed.get("passed"))).lower()}">
          <h2 id="hybrid-heading">Hybrid 평가 결과 및 pass/fail 근거</h2>
          <p>합성 ground truth를 우선하고 proxy label을 보정 신호로 쓰는 고객별 판정 검증입니다.</p>
          <div class="reason-list">
            <article class="reason-card">
              <span class="code">{escape(str(proposed.get("pass_fail_rule_id", "")))}</span>
              <strong>제안 모델 {escape(str(proposed.get("verdict", "")))}</strong>
              <p>{escape(str(proposed.get("rationale", "")))}</p>
            </article>
            <article class="reason-card">
              <span class="code">{escape(str(baseline.get("pass_fail_rule_id", "")))}</span>
              <strong>기존 산식 {escape(str(baseline.get("verdict", "")))}</strong>
              <p>{escape(str(baseline.get("rationale", "")))}</p>
            </article>
{proposed_reason_cards}
          </div>
        </section>"""


def _hybrid_case_results_section(cases: list[dict[str, Any]]) -> str:
    cards = "\n".join(_hybrid_case_card(case) for case in cases)
    return f"""        <section id="hybrid-case-results" aria-labelledby="hybrid-case-heading" data-hybrid-case-count="{len(cases)}">
          <h2 id="hybrid-case-heading">6개 케이스 Hybrid 평가 요약</h2>
          <p>6개 페르소나별 대표 케이스와 5명 묶음의 pass/fail 결과를 한 화면에서 비교합니다.</p>
          <div class="reason-list">
{cards}
          </div>
        </section>"""


def _hybrid_case_card(case: dict[str, Any]) -> str:
    proposed = dict(case.get("proposed", {}))
    baseline = dict(case.get("baseline", {}))
    return f"""            <article class="reason-card" data-hybrid-case-id="{escape(str(case.get("case_id", "")))}" data-hybrid-case-persona="{escape(str(case.get("persona_type", "")))}">
              <span class="code">{escape(str(case.get("case_id", "")))}</span>
              <strong>{escape(str(case.get("persona_type", "")))} / 대표 {escape(str(case.get("representative_customer_id", "")))}</strong>
              <p>제안 모델: {escape(str(proposed.get("verdict", "")))} · pass {escape(str(proposed.get("pass_count", 0)))}/{escape(str(case.get("customer_count", 0)))} · 평균 {escape(_format_score(proposed.get("average_score", 0.0)))}</p>
              <p>기존 산식: {escape(str(baseline.get("verdict", "")))} · pass {escape(str(baseline.get("pass_count", 0)))}/{escape(str(case.get("customer_count", 0)))} · 평균 {escape(_format_score(baseline.get("average_score", 0.0)))}</p>
              <p>{escape(str(case.get("rationale", "")))}</p>
            </article>"""


def _llm_auxiliary_result_for_customer(
    auxiliary_results: Any,
    customer_id: str,
    *,
    service_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = dict(service_status or _pending_llm_report_status())
    if not auxiliary_results:
        return {
            "available": False,
            "report_mode": str(status.get("report_mode", "pending")),
            "message": str(status.get("message", LLM_REPORT_STATUS_MESSAGES["pending"])),
            "section_drafts": {},
            "evidence_cards": [],
            "privacy_contract": {},
            "service_status": status,
        }
    for row in auxiliary_results.get("customer_auxiliary_results", ()):
        if str(row.get("customer_id")) == customer_id:
            return {
                "available": True,
                "report_mode": str(auxiliary_results.get("report_mode", "unknown")),
                "message": str(status.get("message", "")),
                "service_status": status,
                **dict(row),
            }
    raise ValueError(f"LLM report auxiliary results missing customer_id: {customer_id}")


def _llm_auxiliary_section(auxiliary_result: dict[str, Any]) -> str:
    if not auxiliary_result.get("available"):
        return f"""        <section id="llm-report-auxiliary-results" aria-labelledby="llm-aux-heading" data-llm-report-mode="{escape(str(auxiliary_result.get("report_mode", "pending")))}">
          <h2 id="llm-aux-heading">LLM 리포트 보조 결과</h2>
          <p>{escape(str(auxiliary_result.get("message") or LLM_REPORT_STATUS_MESSAGES["pending"]))}</p>
        </section>"""

    drafts = dict(auxiliary_result.get("section_drafts", {}))
    evidence_cards = "\n".join(
        _llm_evidence_card(card)
        for card in auxiliary_result.get("evidence_cards", ())
    )
    reason_narrative_cards = "\n".join(
        _reason_narrative_card(row)
        for row in auxiliary_result.get("reason_code_narratives", ())
    )
    privacy_contract = dict(auxiliary_result.get("privacy_contract", {}))
    local_join_fields = ", ".join(str(field) for field in privacy_contract.get("local_join_fields_not_sent", ()))
    caution_notice = drafts.get("caution_notice") or drafts.get("privacy_notice", "")
    return f"""        <section id="llm-report-auxiliary-results" aria-labelledby="llm-aux-heading" data-llm-report-mode="{escape(str(auxiliary_result.get("report_mode", "unknown")))}">
          <h2 id="llm-aux-heading">LLM 리포트 보조 결과</h2>
          <p>Report Agent가 보험사 직원용 문장 초안, 주요 근거, 권장 조치, 주의 문구, 개인정보 필터링 계약을 구조화한 보조 결과입니다.</p>
          <div class="reason-list">
            <article class="reason-card">
              <span class="code">{escape(str(auxiliary_result.get("generation_mode", "unknown")))}</span>
              <strong>{escape(str(drafts.get("title", "고객별 리포트 초안")))}</strong>
              <div class="aux-section-list">
                <section class="aux-section" data-report-aux-section="summary">
                  <h3>요약</h3>
                  <p>{escape(str(drafts.get("staff_summary", "")))}</p>
                </section>
                <section class="aux-section" data-report-aux-section="key-evidence">
                  <h3>주요 근거</h3>
                  <p>{escape(str(drafts.get("decision_explanation", "")))}</p>
                </section>
                <section class="aux-section" data-report-aux-section="reason-code-narratives">
                  <h3>reason code별 직원 문장</h3>
                  <p>{escape(str(drafts.get("reason_code_narrative_summary", "")))}</p>
                </section>
                <section class="aux-section" data-report-aux-section="recommended-action">
                  <h3>권장 조치</h3>
                  <p>{escape(str(drafts.get("recommended_action", "")))}</p>
                </section>
                <section class="aux-section" data-report-aux-section="caution-notice">
                  <h3>주의 문구</h3>
                  <p>{escape(str(caution_notice))}</p>
                </section>
              </div>
            </article>
            <div id="reason-code-staff-sentences" data-reason-code-narrative-count="{len(auxiliary_result.get("reason_code_narratives", ()))}">
{reason_narrative_cards}
            </div>
{evidence_cards}
            <article class="reason-card">
              <span class="code">privacy_filter</span>
              <strong>외부 LLM 요청 제한</strong>
              <p>전송 허용 필드: {escape(str(privacy_contract.get("allowed_feature_type", "deidentified_summary_features_only")))}</p>
              <p>로컬 조인 전용 미전송 필드: {escape(local_join_fields or "없음")}</p>
            </article>
          </div>
        </section>"""


def _llm_report_status_section(status: dict[str, Any]) -> str:
    mode = str(status.get("report_mode", "pending"))
    fallback_active = bool(status.get("fallback_active"))
    available = bool(status.get("available"))
    service_status = str(status.get("service_status", "inactive"))
    service_active = bool(status.get("service_active"))
    failure_detected = bool(status.get("failure_detected"))
    return f"""        <section id="llm-report-service-status" data-llm-report-mode="{escape(mode)}" data-llm-fallback-active="{str(fallback_active).lower()}" data-llm-report-available="{str(available).lower()}" data-llm-service-status="{escape(service_status)}" data-llm-service-active="{str(service_active).lower()}" data-llm-failure-detected="{str(failure_detected).lower()}" data-core-outputs-continue="{str(bool(status.get("core_outputs_continue", True))).lower()}">
          <h2>LLM 리포트 상태</h2>
          <p>{escape(str(status.get("message") or LLM_REPORT_STATUS_MESSAGES.get(mode, LLM_REPORT_STATUS_MESSAGES["unavailable"])))}</p>
          <p>외부 LLM 서비스: {escape(service_status)} · active={escape(str(service_active).lower())}</p>
          <p>핵심 점수, Agent 검증, 정책 탐색, A/B 비교는 로컬 산출물로 계속 표시됩니다.</p>
        </section>"""


def _llm_report_body_section(llm_report: dict[str, Any], status: dict[str, Any]) -> str:
    render_state = _llm_report_body_render_state(status)
    mode = str(status.get("report_mode", "pending"))
    if render_state["body_rendered"]:
        body = str(llm_report.get("summary") or llm_report.get("decision_explanation") or "리포트 생성 대기 중")
        return f"""        <p class="report-text" data-llm-report-body-rendered="true" data-llm-report-mode="{escape(mode)}">{escape(body)}</p>"""

    message = str(status.get("message") or LLM_REPORT_STATUS_MESSAGES.get(mode, LLM_REPORT_STATUS_MESSAGES["unavailable"]))
    service_status = str(status.get("service_status", "inactive"))
    return f"""        <section id="llm-report-body-status" class="aux-section" data-llm-report-body-rendered="false" data-llm-report-body-blocked-reason="{escape(str(render_state["blocked_reason"]))}" data-llm-report-mode="{escape(mode)}" data-llm-service-status="{escape(service_status)}">
          <h3>{escape(str(render_state["title"]))}</h3>
          <p>{escape(message)}</p>
          <p>리포트 본문은 외부 LLM 서비스가 활성 상태인 경우에만 표시됩니다.</p>
        </section>"""


def _llm_report_body_render_state(status: dict[str, Any]) -> dict[str, Any]:
    service_status = str(status.get("service_status", "inactive"))
    service_active = bool(status.get("service_active"))
    available = bool(status.get("available"))
    if service_status == "failed":
        return {
            "body_rendered": False,
            "blocked_reason": "failed",
            "title": "LLM 리포트 생성 실패",
        }
    if not available:
        return {
            "body_rendered": False,
            "blocked_reason": str(status.get("report_mode", "pending")),
            "title": "LLM 리포트 대기",
        }
    if not service_active:
        return {
            "body_rendered": False,
            "blocked_reason": "inactive",
            "title": "LLM 리포트 비활성",
        }
    return {
        "body_rendered": True,
        "blocked_reason": "",
        "title": "LLM 리포트 활성",
    }


def _reason_narrative_card(row: dict[str, Any]) -> str:
    return f"""              <article class="reason-card" data-reason-code-narrative="{escape(str(row.get("code", "")))}">
                <span class="code">{escape(str(row.get("code", "")))}</span>
                <strong>{escape(str(row.get("contribution_type", "supporting_signal")))}</strong>
                <p>{escape(str(row.get("staff_sentence", "")))}</p>
                <p>{escape(str(row.get("change_reason", "")))}</p>
              </article>"""


def _llm_evidence_card(card: dict[str, Any]) -> str:
    metrics = ", ".join(
        f"{key}={value}"
        for key, value in dict(card.get("metrics", {})).items()
    )
    return f"""            <article class="reason-card">
              <span class="code">{escape(str(card.get("card_id", "evidence")))}</span>
              <strong>{escape(str(card.get("title", "근거 카드")))}</strong>
              <p>{escape(metrics)}</p>
            </article>"""


def _decision_class(decision: str) -> str:
    extra = " preventive" if decision == "예방 케어" else ""
    return f"decision{extra}"


def _format_score(value: object) -> str:
    return f"{float(value):.1f}"


def _format_signed_score(value: object) -> str:
    return f"{float(value):+.1f}"


def _format_signed_percent(value: object) -> str:
    return f"{float(value):+.1f}%"


def _format_threshold(value: object) -> str:
    if value == "":
        return ""
    try:
        return _format_score(value)
    except (TypeError, ValueError):
        return str(value)


def _format_weight(value: object) -> str:
    return f"{float(value):.2f}"


def _format_percent(value: object) -> str:
    return f"{float(value) * 100:.0f}%"


def _format_percentile(value: object) -> str:
    return f"top {float(value) * 100:.0f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the Senior Safe Mileage local customer decision webapp.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = serve(host=args.host, port=args.port)
    print(f"Senior Safe Mileage webapp: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

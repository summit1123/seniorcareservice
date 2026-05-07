from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.agents.evaluation_agent import build_evaluation_input, evaluate_selected_policy
from src.agents.report_agent import build_insurer_report, build_llm_report_auxiliary_results, load_report_inputs
from src.agents.structured_outputs import build_ui_dashboard_bundle
from src.webapp.customer_decision_app import (
    build_agent_audit_view_model,
    build_policy_candidate_comparison_view_model,
    build_customer_decision_view_model,
    load_dashboard_bundle,
    render_customer_decision_page,
)
from src.webapp.validation_pipeline_service import load_validation_pipeline_result, get_validation_pipeline_check


class TestCustomerDecisionWebapp(unittest.TestCase):
    def test_policy_validation_dashboard_is_first_entry_screen(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        dashboard = view_model["entry_dashboard"]

        self.assertEqual(
            dashboard["schema_version"],
            "senior-safe-mileage-policy-validation-entry-dashboard/v1",
        )
        self.assertEqual(dashboard["screen_role"], "first_entry_screen")
        self.assertTrue(dashboard["first_entry_screen"])
        self.assertEqual(
            dashboard["section_order"],
            [
                "policy_validation_dashboard",
                "agent_simulation_validation",
                "policy_candidate_search",
                "ab_comparison",
                "customer_decision_flow",
            ],
        )
        self.assertEqual(dashboard["selected_candidate_id"], bundle["selected_policy"]["candidate_id"])
        self.assertEqual(dashboard["policy_candidate_count"], 114)
        self.assertTrue(dashboard["agent_validation_passed"])
        self.assertEqual(dashboard["agent_validation_pass_rate"], 1.0)
        self.assertEqual(dashboard["agent_validation_check_count"], 8)
        self.assertTrue(dashboard["approval_gate_passed"])
        self.assertEqual(dashboard["risk_change_capture"], {"count": 5, "target_count": 5})
        self.assertEqual(dashboard["false_positive_gate"]["limit"], 3)
        self.assertLessEqual(
            dashboard["false_positive_gate"]["count"],
            dashboard["false_positive_gate"]["limit"],
        )
        self.assertEqual(dashboard["misclassification_check"]["limit"], 4)
        self.assertIn('id="policy-validation-dashboard"', html)
        self.assertIn('data-first-entry-screen="true"', html)
        self.assertIn('data-entry-screen-role="first_entry_screen"', html)
        self.assertIn(
            'data-entry-section-order="policy_validation_dashboard,agent_simulation_validation,policy_candidate_search,ab_comparison,customer_decision_flow"',
            html,
        )
        self.assertIn('data-customer-decision-flow="after-ab-comparison"', html)
        self.assertIn("Senior Safe Mileage 정책/검증 대시보드", html)
        self.assertIn("정책/검증 대시보드", html)
        self.assertIn("선택 정책 후보", html)
        self.assertIn("Agent 시뮬레이션/검증", html)
        self.assertIn("승인 게이트", html)
        self.assertIn("A/B 비교", html)
        self.assertIn('href="#agent-audit-tab"', html)
        self.assertIn('href="#policy-candidate-comparison"', html)
        self.assertIn('href="#customer-ab-comparison"', html)
        self.assertIn('href="#customer-decision-flow"', html)

        dashboard_start = html.index('id="policy-validation-dashboard"')
        agent_audit_start = html.index('id="agent-audit-tab"')
        policy_candidate_start = html.index('id="policy-candidate-comparison"')
        ab_comparison_start = html.index('id="customer-ab-comparison"')
        customer_flow_start = html.index('id="customer-decision-flow"')
        score_panel_start = html.index('id="score-panel"')
        self.assertLess(dashboard_start, agent_audit_start)
        self.assertLess(agent_audit_start, policy_candidate_start)
        self.assertLess(policy_candidate_start, ab_comparison_start)
        self.assertLess(ab_comparison_start, customer_flow_start)
        self.assertLess(dashboard_start, customer_flow_start)
        self.assertLess(customer_flow_start, score_panel_start)

    def test_primary_navigation_uses_required_product_flow_order(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        dashboard = view_model["entry_dashboard"]

        self.assertEqual(
            [link["label"] for link in dashboard["primary_flow_links"]],
            ["Agent 시뮬레이션/검증", "정책 후보 탐색", "A/B 비교", "고객별 판정/리포트"],
        )
        self.assertIn(
            'data-primary-navigation-order="agent_simulation_validation,policy_candidate_search,ab_comparison,customer_decision_report"',
            html,
        )
        nav_start = html.index('aria-label="제품 흐름"')
        nav_agent = html.index('data-primary-nav-item="agent_simulation_validation"', nav_start)
        nav_policy = html.index('data-primary-nav-item="policy_candidate_search"', nav_start)
        nav_ab = html.index('data-primary-nav-item="ab_comparison"', nav_start)
        nav_customer = html.index('data-primary-nav-item="customer_decision_report"', nav_start)
        self.assertLess(nav_agent, nav_policy)
        self.assertLess(nav_policy, nav_ab)
        self.assertLess(nav_ab, nav_customer)

    def test_customer_decision_screen_renders_xai_reason_code_auxiliary_results(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        self.assertEqual(view_model["schema_version"], "senior-safe-mileage-customer-decision-screen/v1")
        self.assertEqual(view_model["customer"]["customer_id"], "cust_011")
        self.assertTrue(view_model["xai_reason_code_auxiliary_results"])
        self.assertIn('id="xai-reason-codes"', html)
        self.assertIn("XAI reason code 보조 결과", html)
        self.assertIn("data-reason-code-count=", html)
        for item in view_model["xai_reason_code_auxiliary_results"]:
            self.assertIn(item["code"], html)
            self.assertIn(item["label"], html)
            self.assertIn(item["evidence"], html)

    def test_evidence_tab_combines_policy_judgment_basis_and_xai_reason_codes(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        evidence = view_model["policy_judgment_evidence"]

        self.assertEqual(
            evidence["schema_version"],
            "senior-safe-mileage-policy-judgment-evidence-tab/v1",
        )
        self.assertEqual(evidence["tab_id"], "evidence")
        self.assertEqual(evidence["customer_id"], "cust_011")
        self.assertEqual(evidence["selected_candidate_id"], bundle["selected_policy"]["candidate_id"])
        self.assertTrue(evidence["policy_basis_items"])
        self.assertTrue(evidence["weight_items"])
        self.assertTrue(evidence["ab_basis_items"])
        self.assertTrue(evidence["policy_reason_codes"])
        self.assertEqual(evidence["xai_reason_codes"], view_model["xai_reason_code_auxiliary_results"])
        self.assertIn("care_decision=예방 케어", evidence["policy_basis_items"])
        self.assertIn("proposed_decision=예방 케어", evidence["ab_basis_items"])
        self.assertIn('id="policy-judgment-evidence-tab"', html)
        self.assertIn('data-decision-evidence-tab="evidence"', html)
        self.assertIn('data-policy-judgment-customer-id="cust_011"', html)
        self.assertIn('id="evidence-tab-xai-reason-codes"', html)
        self.assertIn("근거 탭", html)
        self.assertIn("정책 판단 근거", html)
        self.assertIn("정책 가중치", html)
        self.assertIn("A/B 판정 근거", html)
        self.assertIn("정책 선택 reason code", html)
        self.assertIn("XAI reason code", html)
        for item in evidence["policy_basis_items"] + evidence["ab_basis_items"]:
            self.assertIn(item, html)
        for code in evidence["policy_reason_codes"]:
            self.assertIn(code, html)
        for item in evidence["xai_reason_codes"]:
            self.assertIn(item["code"], html)

    def test_audit_tab_renders_agent_validation_results_and_audit_log(self) -> None:
        pipeline = load_validation_pipeline_result()
        audit = build_agent_audit_view_model(pipeline)
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        bundle["agent_audit"] = audit
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        self.assertEqual(
            audit["schema_version"],
            "senior-safe-mileage-agent-audit-tab/v1",
        )
        self.assertEqual(
            audit["source_model_schema_version"],
            "senior-safe-mileage-validation-pipeline-tab-model/v1",
        )
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["validation_pass_rate"], 1.0)
        self.assertEqual(
            audit["execution_input"]["schema_version"],
            "senior-safe-mileage-validation-execution-input/v1",
        )
        self.assertEqual(
            audit["execution_input"]["selected_policy"]["candidate_id"],
            bundle["selected_policy"]["candidate_id"],
        )
        self.assertEqual(audit["required_agent_count"], 8)
        self.assertEqual(audit["check_count"], 8)
        self.assertEqual(len(audit["evidence_items"]), 8)
        self.assertIn("privacy_filtered_features_only", audit["privacy_contract"]["external_api_payload_scope"])
        self.assertGreaterEqual(len(audit["audit_log_entries"]), 9)
        self.assertEqual(audit["audit_log_display_mode"], "timeline")
        self.assertEqual(view_model["agent_audit"]["run_id"], audit["run_id"])
        self.assertIn('id="agent-audit-tab"', html)
        self.assertIn("감사 탭", html)
        self.assertIn("Agent-in-the-loop 검증 결과", html)
        self.assertIn('aria-label="Agent 검증 결과 및 감사 로그"', html)
        self.assertIn('data-agent-audit-tab="validation-results"', html)
        self.assertIn('data-agent-audit-tab="audit-log"', html)
        self.assertIn('id="agent-validation-results"', html)
        self.assertIn('id="agent-audit-log"', html)
        self.assertIn('aria-label="Agent 감사 로그 타임라인"', html)
        self.assertIn('data-agent-audit-section="audit-log"', html)
        self.assertIn('data-audit-log-display="timeline"', html)
        self.assertIn('data-agent-audit-passed="true"', html)
        self.assertIn('data-agent-validation-pass-rate="1.0"', html)
        self.assertIn('data-agent-audit-check-count="8"', html)
        self.assertIn('id="validation-execution-input"', html)
        self.assertIn('data-validation-execution-input="selected-policy-scenario"', html)
        self.assertIn(
            f'data-validation-selected-candidate-id="{bundle["selected_policy"]["candidate_id"]}"',
            html,
        )
        self.assertIn("검증 실행 입력", html)
        self.assertIn("Agent 검증 요약", html)
        self.assertIn("pass rate 100% / 기준 95%", html)
        self.assertIn("필수 Agent 8개", html)
        agent_log_start = html.index('id="agent-audit-log"')
        agent_log_end = html.index("</section>", agent_log_start)
        agent_log_html = html[agent_log_start:agent_log_end]
        self.assertEqual(agent_log_html.count('data-audit-timeline-item="true"'), len(audit["audit_log_entries"]))
        for agent_id in pipeline["required_agent_ids"]:
            self.assertIn(f'data-agent-validation-agent-id="{agent_id}"', html)
            self.assertIn(f'data-agent-audit-agent-id="{agent_id}"', html)
        self.assertIn("candidate_rules.json", html)
        self.assertIn("evaluation_view_model.json", html)
        self.assertIn("simulation_summary.json", html)

    def test_agent_validation_status_has_independent_visual_display(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        self.assertTrue(view_model["agent_audit"]["passed"])
        self.assertEqual(view_model["ui_render_state"]["agent_validation"]["render_state"], "ready")
        self.assertTrue(view_model["ui_render_state"]["agent_validation"]["independent_of_llm_report"])
        self.assertIn('id="agent-validation-status-panel"', html)
        self.assertIn('data-agent-validation-status-panel="independent"', html)
        self.assertIn('data-agent-validation-status="passed"', html)
        self.assertIn('data-agent-validation-visual-state="passed"', html)
        self.assertIn('class="status-pill passed"', html)
        self.assertIn('data-agent-validation-status-badge="passed"', html)
        self.assertEqual(html.count('data-agent-validation-row-status="passed"'), 8)
        self.assertIn("Agent 검증 상태", html)
        self.assertIn("검증 상태는 LLM 리포트 상태와 분리된 독립 영역으로 표시됩니다.", html)

    def test_failure_and_warning_messages_render_in_distinct_styles_and_areas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bundle = load_dashboard_bundle(report_view_model_input=workspace / "missing_report.json")
            view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
            html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

            report_check = next(
                check for check in view_model["agent_audit"]["checks"]
                if check["agent_id"] == "report_agent"
            )
            self.assertFalse(report_check["passed"])
            self.assertTrue(report_check["errors"])
            self.assertTrue(report_check["warnings"])
            self.assertIn('id="agent-validation-message-panels"', html)
            self.assertIn('data-agent-message-panels="failure-warning"', html)
            self.assertIn('data-agent-failure-message-count="1"', html)
            self.assertIn('data-agent-warning-message-count="1"', html)
            self.assertIn('class="message-area failure"', html)
            self.assertIn('class="message-area warning"', html)
            self.assertIn('role="alert" data-agent-message-area="failure"', html)
            self.assertIn('role="status" data-agent-message-area="warning"', html)
            self.assertIn('data-agent-message-type="failure" data-agent-message-agent-id="report_agent"', html)
            self.assertIn('data-agent-message-type="warning" data-agent-message-agent-id="report_agent"', html)
            self.assertIn("실패 메시지", html)
            self.assertIn("경고 메시지", html)
            self.assertIn("Report Agent validation failed", html)
            self.assertIn("report artifact unavailable", html)

            failure_start = html.index('data-agent-message-area="failure"')
            failure_end = html.index("</article>", failure_start)
            warning_start = html.index('data-agent-message-area="warning"')
            warning_end = html.index("</article>", warning_start)
            failure_html = html[failure_start:failure_end]
            warning_html = html[warning_start:warning_end]
            self.assertLess(failure_end, warning_start)
            self.assertIn("Report Agent validation failed", failure_html)
            self.assertNotIn("report artifact unavailable", failure_html)
            self.assertIn("report artifact unavailable", warning_html)
            self.assertNotIn("Report Agent validation failed", warning_html)

    def test_judgment_basis_renders_in_reason_evidence_area_separate_from_validation_status(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        evidence = view_model["policy_judgment_evidence"]

        self.assertEqual(evidence["display_area"], "reason_evidence")
        self.assertTrue(evidence["separated_from_validation_status"])
        self.assertEqual(evidence["validation_status_source"], "agent_audit_tab")
        self.assertIn('id="policy-judgment-evidence-tab"', html)
        self.assertIn('data-reason-evidence-area="reason_evidence"', html)
        self.assertIn('data-separated-from-validation-status="true"', html)
        self.assertIn('data-validation-status-source="agent_audit_tab"', html)
        self.assertIn("검증 상태와 분리된 reason/evidence 영역", html)

        evidence_start = html.index('id="policy-judgment-evidence-tab"')
        evidence_end = html.index('id="customer-ab-comparison"', evidence_start)
        validation_status_start = html.index('id="agent-validation-status-panel"')
        validation_status_end = html.index('data-agent-audit-section="summary"', validation_status_start)
        evidence_html = html[evidence_start:evidence_end]
        validation_status_html = html[validation_status_start:validation_status_end]

        self.assertLess(validation_status_start, evidence_start)
        self.assertIn("정책 판단 근거", evidence_html)
        self.assertIn("XAI reason code", evidence_html)
        self.assertIn("PROPOSED_MODEL_PREVENTIVE_CARE", evidence_html)
        self.assertIn("Agent 검증 상태", validation_status_html)
        self.assertNotIn("정책 판단 근거", validation_status_html)
        self.assertNotIn("PROPOSED_MODEL_PREVENTIVE_CARE", validation_status_html)
        self.assertNotIn('data-agent-validation-status-panel="independent"', evidence_html)

    def test_evidence_audit_tab_renders_selected_policy_scenario_validation_evidence_and_log(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        tab = view_model["evidence_audit_tab"]
        selected_policy = tab["selected_policy"]
        selected_scenario = tab["selected_scenario"]

        self.assertEqual(tab["schema_version"], "senior-safe-mileage-evidence-audit-tab/v1")
        self.assertEqual(tab["tab_ids"], ["evidence", "audit"])
        self.assertEqual(tab["customer_id"], "cust_011")
        self.assertEqual(tab["selected_candidate_id"], bundle["selected_policy"]["candidate_id"])
        self.assertEqual(tab["selected_candidate_id"], selected_policy["candidate_id"])
        self.assertEqual(
            selected_scenario["schema_version"],
            "senior-safe-mileage-selected-scenario-state/v1",
        )
        self.assertEqual(selected_scenario["observation_period"]["baseline_days"], 60)
        self.assertEqual(selected_scenario["observation_period"]["recent_days"], 30)
        self.assertTrue(tab["validation_summary"]["passed"])
        self.assertEqual(tab["validation_summary"]["validation_pass_rate"], 1.0)
        self.assertGreaterEqual(tab["evidence_item_count"], 9)
        self.assertGreaterEqual(tab["audit_log_entry_count"], 9)
        self.assertEqual(tab["audit_log_display_mode"], "timeline")
        self.assertIn("selected_policy_judgment_basis", [item["evidence_id"] for item in tab["evidence_items"]])

        self.assertIn('id="evidence-audit-tab"', html)
        self.assertIn('data-evidence-audit-tab="selected-policy-scenario"', html)
        self.assertIn(f'data-evidence-audit-selected-candidate-id="{tab["selected_candidate_id"]}"', html)
        self.assertIn(f'data-evidence-audit-selected-scenario-id="{tab["selected_scenario_id"]}"', html)
        self.assertIn('id="evidence-audit-validation-summary"', html)
        self.assertIn('id="evidence-audit-items"', html)
        self.assertIn('id="evidence-audit-log"', html)
        self.assertIn('aria-label="감사 로그 타임라인"', html)
        self.assertIn('data-evidence-audit-section="audit-log"', html)
        self.assertIn('data-audit-log-display="timeline"', html)
        self.assertIn("근거/감사 탭", html)
        self.assertIn("선택 정책/시나리오 기준", html)
        self.assertIn("검증 결과 요약", html)
        self.assertIn("근거 항목", html)
        self.assertIn("감사 로그", html)
        self.assertIn("selected_policy_judgment_basis", html)
        self.assertIn("scenario_config.json", html)
        self.assertIn("candidate_rules.json", html)
        evidence_log_start = html.index('id="evidence-audit-log"')
        evidence_log_end = html.index("</section>", evidence_log_start)
        evidence_log_html = html[evidence_log_start:evidence_log_end]
        self.assertEqual(evidence_log_html.count('data-audit-timeline-item="true"'), len(tab["audit_log_entries"]))

    def test_customer_decision_screen_defaults_to_preventive_care_customer_for_review(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle)

        self.assertEqual(view_model["customer"]["care_decision"], "예방 케어")
        self.assertIn(
            "PROPOSED_MODEL_PREVENTIVE_CARE",
            [item["code"] for item in view_model["xai_reason_code_auxiliary_results"]],
        )

    def test_customer_decision_screen_renders_llm_report_auxiliary_results(self) -> None:
        bundle = load_dashboard_bundle()
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        auxiliary = view_model["llm_report_auxiliary_result"]
        self.assertTrue(auxiliary["available"])
        self.assertEqual(auxiliary["customer_id"], "cust_011")
        self.assertIn("staff_summary", auxiliary["section_drafts"])
        self.assertIn("decision_explanation", auxiliary["section_drafts"])
        self.assertIn("recommended_action", auxiliary["section_drafts"])
        self.assertIn("reason_code_narrative_summary", auxiliary["section_drafts"])
        self.assertTrue(auxiliary["reason_code_narratives"])
        self.assertTrue(auxiliary["reason_code_narratives"][0]["staff_sentence"])
        self.assertTrue(auxiliary["reason_code_narratives"][0]["change_reason"])
        self.assertTrue(
            auxiliary["section_drafts"].get("caution_notice")
            or auxiliary["section_drafts"].get("privacy_notice")
        )
        self.assertTrue(auxiliary["evidence_cards"])
        self.assertEqual(auxiliary["privacy_contract"]["external_request_source"], "request_features")
        self.assertNotIn("customer_id", auxiliary["request_features"])
        self.assertIn('id="llm-report-auxiliary-results"', html)
        self.assertIn("LLM 리포트 보조 결과", html)
        self.assertIn("보험사 직원용 문장 초안", html)
        self.assertIn('data-report-aux-section="summary"', html)
        self.assertIn('data-report-aux-section="key-evidence"', html)
        self.assertIn('data-report-aux-section="reason-code-narratives"', html)
        self.assertIn('data-report-aux-section="recommended-action"', html)
        self.assertIn('data-report-aux-section="caution-notice"', html)
        self.assertIn('id="reason-code-staff-sentences"', html)
        self.assertIn("reason code별 직원 문장", html)
        self.assertIn('data-reason-code-narrative="PROPOSED_MODEL_PREVENTIVE_CARE"', html)
        self.assertIn("요약", html)
        self.assertIn("주요 근거", html)
        self.assertIn("권장 조치", html)
        self.assertIn("주의 문구", html)
        self.assertIn(auxiliary["section_drafts"]["staff_summary"], html)
        self.assertIn(auxiliary["section_drafts"]["decision_explanation"], html)
        self.assertIn(auxiliary["section_drafts"]["reason_code_narrative_summary"], html)
        self.assertIn(auxiliary["section_drafts"]["recommended_action"], html)
        self.assertIn("예방 케어 판정으로 전환", html)
        self.assertIn("외부 LLM 요청 제한", html)

    def test_openai_failure_fallback_report_is_exposed_without_blocking_core_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            report_path = workspace / "simulation_summary.json"
            auxiliary_path = workspace / "llm_report_auxiliary_results.json"
            report = build_insurer_report(load_report_inputs(), force_llm_failure=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            auxiliary_path.write_text(
                json.dumps(build_llm_report_auxiliary_results(report), ensure_ascii=False),
                encoding="utf-8",
            )

            bundle = load_dashboard_bundle(
                report_view_model_input=report_path,
                llm_auxiliary_input=auxiliary_path,
            )
            view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
            html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

            status = view_model["llm_report_service_status"]
            self.assertEqual(status["report_mode"], "fallback_template")
            self.assertTrue(status["fallback_active"])
            self.assertEqual(status["service_status"], "inactive")
            self.assertFalse(status["service_active"])
            self.assertTrue(status["failure_detected"])
            self.assertTrue(status["core_outputs_continue"])
            self.assertEqual(view_model["ui_render_state"]["score_panel"]["render_state"], "ready")
            self.assertTrue(view_model["ui_render_state"]["score_panel"]["independent_of_llm_report"])
            self.assertEqual(
                view_model["ui_render_state"]["score_panel"]["source"],
                "evaluation_agent_customer_snapshot",
            )
            self.assertEqual(view_model["ui_render_state"]["agent_validation"]["render_state"], "ready")
            self.assertTrue(view_model["ui_render_state"]["agent_validation"]["independent_of_llm_report"])
            self.assertEqual(view_model["ui_render_state"]["ab_comparison"]["render_state"], "ready")
            self.assertTrue(view_model["ui_render_state"]["ab_comparison"]["independent_of_llm_report"])
            self.assertEqual(view_model["customer"]["care_decision"], "예방 케어")
            self.assertIn(
                "PROPOSED_MODEL_PREVENTIVE_CARE",
                view_model["customer"]["xai_reason_codes"],
            )
            self.assertIn(
                "PROPOSED_MODEL_PREVENTIVE_CARE",
                [item["code"] for item in view_model["xai_reason_code_auxiliary_results"]],
            )
            local_rule_result = view_model["local_rule_decision_result"]
            self.assertTrue(local_rule_result["available"])
            self.assertEqual(local_rule_result["care_decision"], "예방 케어")
            self.assertEqual(local_rule_result["decision_source"], "evaluation_agent_local_rules")
            self.assertTrue(local_rule_result["independent_of_openai"])
            self.assertTrue(local_rule_result["llm_fallback_active"])
            self.assertIn("PROPOSED_MODEL_PREVENTIVE_CARE", local_rule_result["reason_codes"])
            self.assertEqual(view_model["customer_ab_comparison"]["models"]["proposed"]["decision"], "예방 케어")
            self.assertIn('id="score-panel"', html)
            self.assertIn('data-score-render-state="ready"', html)
            self.assertIn('data-score-independent-of-llm-report="true"', html)
            self.assertIn('data-score-source="evaluation_agent_customer_snapshot"', html)
            self.assertIn("Senior Safe Mileage", html)
            self.assertIn("위험변화", html)
            self.assertIn('data-agent-validation-render-state="ready"', html)
            self.assertIn('data-agent-validation-independent-of-llm-report="true"', html)
            self.assertIn('data-ab-render-state="ready"', html)
            self.assertIn('data-ab-independent-of-llm-report="true"', html)
            self.assertIn('id="local-rule-decision-result"', html)
            self.assertIn('data-local-rule-decision-source="evaluation_agent_local_rules"', html)
            self.assertIn('data-local-rule-independent-of-openai="true"', html)
            self.assertIn('data-local-rule-llm-fallback-active="true"', html)
            self.assertIn("로컬 규칙 기반 판정", html)
            self.assertIn('id="llm-report-service-status"', html)
            self.assertIn('data-llm-report-mode="fallback_template"', html)
            self.assertIn('data-llm-fallback-active="true"', html)
            self.assertIn('data-llm-service-status="inactive"', html)
            self.assertIn('data-llm-service-active="false"', html)
            self.assertIn('data-llm-failure-detected="true"', html)
            self.assertIn("OpenAI API 응답을 사용할 수 없어", html)
            self.assertIn("핵심 점수, Agent 검증, 정책 탐색, A/B 비교는 로컬 산출물로 계속 표시됩니다.", html)
            self.assertIn('id="llm-report-body-status"', html)
            self.assertIn('data-llm-report-body-rendered="false"', html)
            self.assertIn('data-llm-report-body-blocked-reason="inactive"', html)
            self.assertNotIn('class="report-text"', html)

    def test_openai_api_exception_is_rendered_as_failed_inactive_llm_service(self) -> None:
        class FailingClient:
            def generate_insurer_report(self, request: object) -> object:
                raise RuntimeError("mocked OpenAI API failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            report_path = workspace / "simulation_summary.json"
            auxiliary_path = workspace / "llm_report_auxiliary_results.json"
            report = build_insurer_report(load_report_inputs(), openai_client=FailingClient())
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            auxiliary_path.write_text(
                json.dumps(build_llm_report_auxiliary_results(report), ensure_ascii=False),
                encoding="utf-8",
            )

            bundle = load_dashboard_bundle(
                report_view_model_input=report_path,
                llm_auxiliary_input=auxiliary_path,
            )
            view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
            html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

            status = view_model["llm_report_service_status"]
            self.assertEqual(status["report_mode"], "fallback_template")
            self.assertEqual(status["service_status"], "failed")
            self.assertFalse(status["service_active"])
            self.assertTrue(status["failure_detected"])
            self.assertEqual(status["llm_service_status"]["error_type"], "RuntimeError")
            self.assertEqual(view_model["customer"]["care_decision"], "예방 케어")
            self.assertEqual(view_model["customer_ab_comparison"]["models"]["proposed"]["decision"], "예방 케어")
            self.assertIn('data-llm-service-status="failed"', html)
            self.assertIn('data-llm-service-active="false"', html)
            self.assertIn('data-llm-failure-detected="true"', html)
            self.assertIn('id="llm-report-body-status"', html)
            self.assertIn('data-llm-report-body-rendered="false"', html)
            self.assertIn('data-llm-report-body-blocked-reason="failed"', html)
            self.assertNotIn('class="report-text"', html)

    def test_mocked_openai_failure_does_not_interrupt_ab_comparison_screen_or_data_generation(self) -> None:
        class FailingClient:
            def __init__(self) -> None:
                self.requests: list[object] = []

            def generate_insurer_report(self, request: object) -> object:
                self.requests.append(request)
                raise RuntimeError("mocked OpenAI API failure for A/B flow")

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            report_path = workspace / "simulation_summary.json"
            auxiliary_path = workspace / "llm_report_auxiliary_results.json"
            ab_screen_path = workspace / "customer_ab_screen.html"
            ab_data_path = workspace / "customer_ab_comparison.json"
            failing_client = FailingClient()

            report = build_insurer_report(load_report_inputs(), openai_client=failing_client)
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            auxiliary_path.write_text(
                json.dumps(build_llm_report_auxiliary_results(report), ensure_ascii=False),
                encoding="utf-8",
            )

            bundle = load_dashboard_bundle(
                report_view_model_input=report_path,
                llm_auxiliary_input=auxiliary_path,
            )
            view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
            html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
            ab_screen_path.write_text(html, encoding="utf-8")
            ab_data_path.write_text(
                json.dumps(view_model["customer_ab_comparison"], ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertGreaterEqual(len(failing_client.requests), 1)
            self.assertEqual(view_model["llm_report_service_status"]["report_mode"], "fallback_template")
            self.assertEqual(view_model["llm_report_service_status"]["service_status"], "failed")
            self.assertTrue(view_model["llm_report_service_status"]["core_outputs_continue"])
            self.assertEqual(view_model["ui_render_state"]["ab_comparison"]["render_state"], "ready")
            self.assertTrue(view_model["ui_render_state"]["ab_comparison"]["independent_of_llm_report"])
            self.assertTrue(view_model["ui_render_state"]["ab_comparison"]["same_customer_input"])

            comparison_dataset = bundle["comparison_dataset"]
            self.assertEqual(
                comparison_dataset["schema_version"],
                "senior-safe-mileage-ab-comparison-dataset/v1",
            )
            self.assertEqual(comparison_dataset["customer_count"], 30)
            self.assertTrue(
                comparison_dataset["same_input_contract"][
                    "baseline_and_proposed_share_input_data_ref"
                ]
            )
            self.assertEqual(
                comparison_dataset["same_input_contract"]["observation_period"],
                {"baseline_days": 60, "recent_days": 30, "total_days": 90},
            )
            self.assertIn("cust_011", comparison_dataset["by_customer_id"])
            customer_lookup = comparison_dataset["by_customer_id"]["cust_011"]
            self.assertEqual(customer_lookup["input_data_ref"], view_model["customer_ab_comparison"]["input_data_ref"])
            self.assertEqual(customer_lookup["baseline_score"], view_model["customer_ab_comparison"]["models"]["baseline"]["score"])
            self.assertEqual(customer_lookup["proposed_score"], view_model["customer_ab_comparison"]["models"]["proposed"]["score"])
            self.assertEqual(customer_lookup["proposed_detected"], view_model["customer_ab_comparison"]["models"]["proposed"]["detected"])
            self.assertEqual(customer_lookup["decision_changed"], view_model["customer_ab_comparison"]["difference"]["decision_changed"])

            self.assertTrue(ab_screen_path.exists())
            self.assertTrue(ab_data_path.exists())
            self.assertIn('id="customer-ab-comparison"', html)
            self.assertIn('data-ab-render-state="ready"', html)
            self.assertIn('data-ab-independent-of-llm-report="true"', html)
            self.assertIn("제안 모델 단독 포착", html)
            self.assertIn("핵심 점수, Agent 검증, 정책 탐색, A/B 비교는 로컬 산출물로 계속 표시됩니다.", html)

    def test_missing_llm_artifacts_return_safe_pending_ui_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bundle = load_dashboard_bundle(
                report_view_model_input=workspace / "missing_report.json",
                llm_auxiliary_input=workspace / "missing_auxiliary.json",
            )
            view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
            html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

            self.assertEqual(view_model["llm_report_service_status"]["report_mode"], "pending")
            self.assertFalse(view_model["llm_report_service_status"]["available"])
            self.assertFalse(view_model["llm_report_auxiliary_result"]["available"])
            self.assertEqual(view_model["customer"]["care_decision"], "예방 케어")
            self.assertTrue(view_model["approval_gate"]["passed"])
            self.assertIn('data-llm-report-mode="pending"', html)
            self.assertIn("Report Agent 산출물이 아직 없어", html)
            self.assertIn('id="customer-ab-comparison"', html)
            self.assertIn('id="llm-report-body-status"', html)
            self.assertIn('data-llm-report-body-rendered="false"', html)

    def test_agent_validation_and_ab_sections_render_when_llm_artifacts_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            report_path = workspace / "broken_report.json"
            auxiliary_path = workspace / "broken_auxiliary.json"
            report_path.write_text('{"schema_version": "broken-report"}', encoding="utf-8")
            auxiliary_path.write_text('{"schema_version": "broken-auxiliary"}', encoding="utf-8")

            bundle = load_dashboard_bundle(
                report_view_model_input=report_path,
                llm_auxiliary_input=auxiliary_path,
            )
            view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
            html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

            self.assertEqual(view_model["llm_report_service_status"]["report_mode"], "unavailable")
            self.assertFalse(view_model["llm_report_service_status"]["available"])
            self.assertTrue(view_model["llm_report_service_status"]["core_outputs_continue"])
            self.assertEqual(
                view_model["ui_render_state"]["schema_version"],
                "senior-safe-mileage-ui-render-state/v1",
            )
            self.assertEqual(view_model["ui_render_state"]["llm_report"]["render_state"], "unavailable")
            self.assertEqual(view_model["ui_render_state"]["score_panel"]["render_state"], "ready")
            self.assertTrue(view_model["ui_render_state"]["score_panel"]["independent_of_llm_report"])
            self.assertEqual(view_model["ui_render_state"]["agent_validation"]["render_state"], "ready")
            self.assertTrue(
                view_model["ui_render_state"]["agent_validation"]["independent_of_llm_report"]
            )
            self.assertEqual(view_model["ui_render_state"]["ab_comparison"]["render_state"], "ready")
            self.assertTrue(view_model["ui_render_state"]["ab_comparison"]["independent_of_llm_report"])
            self.assertTrue(view_model["ui_render_state"]["core_outputs_independent_of_llm_report"])
            self.assertEqual(view_model["agent_audit"]["check_count"], 8)
            self.assertEqual(
                view_model["customer_ab_comparison"]["models"]["proposed"]["decision"],
                "예방 케어",
            )
            self.assertIn('id="score-panel"', html)
            self.assertIn('data-score-render-state="ready"', html)
            self.assertIn('data-score-independent-of-llm-report="true"', html)
            self.assertIn('id="agent-audit-tab"', html)
            self.assertIn('data-agent-validation-render-state="ready"', html)
            self.assertIn('data-agent-validation-independent-of-llm-report="true"', html)
            self.assertIn('id="customer-ab-comparison"', html)
            self.assertIn('data-ab-render-state="ready"', html)
            self.assertIn('data-ab-independent-of-llm-report="true"', html)
            self.assertIn('data-llm-report-mode="unavailable"', html)
            self.assertIn('data-core-outputs-continue="true"', html)

    def test_validation_service_isolates_unavailable_report_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = load_validation_pipeline_result(report_view_model_input=Path(tmpdir) / "missing_report.json")
            report_check = get_validation_pipeline_check(pipeline, "report_agent")
            evaluation_check = get_validation_pipeline_check(pipeline, "evaluation_agent")

            self.assertFalse(report_check["passed"])
            self.assertEqual(report_check["validation"]["report_mode"], "unavailable")
            self.assertTrue(report_check["validation"]["fallback_available"])
            self.assertTrue(report_check["validation"]["core_outputs_continue"])
            self.assertTrue(report_check["warnings"])
            self.assertTrue(evaluation_check["passed"])
            self.assertTrue(evaluation_check["validation"]["approval_gate_passed"])

    def test_customer_decision_screen_exposes_proxy_label_result(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        proxy_label = view_model["proxy_label_auxiliary_result"]
        self.assertTrue(proxy_label["available"])
        self.assertEqual(proxy_label["customer_id"], "cust_011")
        self.assertEqual(proxy_label["rule_id"], "senior_safe_low_mileage_risk_change_proxy/v1")
        self.assertIs(proxy_label["is_target"], True)
        self.assertEqual(proxy_label["expected_care_decision"], "예방 케어")
        self.assertTrue(proxy_label["reason_codes"])
        self.assertTrue(proxy_label["thresholds"])
        self.assertIn('id="proxy-label-result"', html)
        self.assertIn("Proxy label 결과", html)
        self.assertIn('data-proxy-label-target="true"', html)
        self.assertIn(proxy_label["rule_id"], html)
        self.assertIn(proxy_label["summary"], html)
        for code in proxy_label["reason_codes"]:
            self.assertIn(code, html)

    def test_customer_decision_screen_exposes_hybrid_evaluation_pass_fail_rationale(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        hybrid = view_model["hybrid_evaluation_result"]
        self.assertTrue(hybrid["available"])
        self.assertEqual(hybrid["customer_id"], "cust_011")
        self.assertEqual(hybrid["proposed"]["verdict"], "pass")
        self.assertTrue(hybrid["proposed"]["passed"])
        self.assertEqual(hybrid["proposed"]["pass_threshold"], 80.0)
        self.assertIn("ground_truth=", hybrid["proposed"]["rationale"])
        self.assertIn("proxy_label=", hybrid["proposed"]["rationale"])
        self.assertIn('id="hybrid-evaluation-result"', html)
        self.assertIn("Hybrid 평가 결과 및 pass/fail 근거", html)
        self.assertIn('data-hybrid-proposed-verdict="pass"', html)
        self.assertIn('data-hybrid-proposed-passed="true"', html)
        self.assertIn(hybrid["proposed"]["pass_fail_rule_id"], html)
        self.assertIn(hybrid["proposed"]["rationale"], html)
        for code in hybrid["proposed"]["reason_codes"]:
            self.assertIn(code, html)

    def test_customer_decision_screen_exposes_six_hybrid_case_results(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")

        cases = view_model["hybrid_case_results"]
        self.assertEqual(len(cases), 6)
        self.assertEqual({case["customer_count"] for case in cases}, {5})
        self.assertEqual(
            {case["persona_type"] for case in cases},
            {customer["persona_type"] for customer in bundle["customers"]},
        )
        self.assertIn('id="hybrid-case-results"', html)
        self.assertIn("6개 케이스 Hybrid 평가 요약", html)
        self.assertIn('data-hybrid-case-count="6"', html)
        for case in cases:
            self.assertIn(case["case_id"], html)
            self.assertIn(case["persona_type"], html)
            self.assertIn(case["representative_customer_id"], html)
            self.assertIn(str(case["proposed"]["pass_count"]), html)

    def test_dashboard_case_detail_data_contains_proxy_labels_for_all_customers(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))

        self.assertEqual(len(bundle["customers"]), 30)
        self.assertTrue(all(customer["proxy_label"]["rule_id"] for customer in bundle["customers"]))
        self.assertEqual(
            sum(1 for customer in bundle["customers"] if customer["proxy_label"]["is_target"]),
            5,
        )

    def test_dashboard_bundle_exposes_ab_comparison_summary(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        summary = bundle["ab_comparison"]["comparison_summary"]

        self.assertEqual(summary["schema_version"], "senior-safe-mileage-ab-comparison-summary/v1")
        self.assertEqual(summary["customer_count"], 30)
        self.assertEqual(len(summary["persona_summaries"]), 6)
        self.assertGreater(summary["decision_differences"]["decision_changed_count"], 0)
        self.assertTrue(summary["customer_decision_differences"])

    def test_customer_decision_screen_exposes_non_target_false_positive_gate(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        gate = view_model["approval_gate"]

        self.assertEqual(gate["non_target_count"], 25)
        self.assertEqual(gate["non_target_false_positive_limit"], 3)
        self.assertLessEqual(gate["non_target_false_positive_count"], 3)
        self.assertTrue(gate["passes_non_target_false_positive_gate"])
        self.assertIn('id="false-positive-gate"', html)
        self.assertIn('data-false-positive-gate-passed="true"', html)
        self.assertIn("비위험군 25명 중 오탐", html)

    def test_customer_decision_screen_exposes_total_misclassification_check(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        gate = view_model["approval_gate"]
        check = gate["misclassification_check"]

        self.assertEqual(check["customer_count"], 30)
        self.assertEqual(check["limit"], 4)
        self.assertEqual(check["count"], gate["total_misclassification_count"])
        self.assertEqual(gate["total_misclassification_limit"], 4)
        self.assertLessEqual(gate["total_misclassification_count"], 4)
        self.assertTrue(gate["passes_misclassification_check"])
        self.assertTrue(check["passed"])
        self.assertIn('id="misclassification-check"', html)
        self.assertIn('data-misclassification-check-passed="true"', html)
        self.assertIn("30명 중 오분류", html)

    def test_customer_decision_screen_renders_side_by_side_ab_comparison_layout(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        comparison = view_model["customer_ab_comparison"]

        self.assertEqual(comparison["schema_version"], "senior-safe-mileage-customer-ab-layout/v1")
        self.assertTrue(comparison["same_customer_input"])
        self.assertEqual(comparison["models"]["baseline"]["label"], "기존 산식")
        self.assertEqual(comparison["models"]["proposed"]["label"], "제안 모델")
        self.assertEqual(comparison["models"]["baseline"]["decision"], "기존 저주행 할인")
        self.assertEqual(comparison["models"]["proposed"]["decision"], "예방 케어")
        self.assertFalse(comparison["models"]["baseline"]["detected"])
        self.assertTrue(comparison["models"]["proposed"]["detected"])
        self.assertTrue(comparison["difference"]["decision_changed"])
        self.assertTrue(comparison["difference"]["proposed_captures_risk_change_not_baseline"])
        self.assertIn('id="customer-ab-comparison"', html)
        self.assertIn('data-ab-layout="side-by-side"', html)
        self.assertIn('data-same-customer-input="true"', html)
        self.assertIn('data-ab-model="baseline"', html)
        self.assertIn('data-ab-model="proposed"', html)
        self.assertIn("기존 산식", html)
        self.assertIn("제안 모델", html)
        self.assertIn("기존 저주행 할인", html)
        self.assertIn("예방 케어", html)
        self.assertIn("제안 모델 단독 포착", html)
        self.assertIn(comparison["input_data_ref"], html)

    def test_customer_decision_screen_highlights_ab_score_grade_decision_reason_differences(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        comparison = view_model["customer_ab_comparison"]
        highlights = comparison["difference_highlights"]

        self.assertEqual([item["key"] for item in highlights], ["score", "grade", "decision", "reason_codes"])
        self.assertTrue(next(item for item in highlights if item["key"] == "score")["changed"])
        self.assertTrue(next(item for item in highlights if item["key"] == "grade")["changed"])
        self.assertTrue(next(item for item in highlights if item["key"] == "decision")["changed"])
        reason_highlight = next(item for item in highlights if item["key"] == "reason_codes")
        self.assertTrue(reason_highlight["changed"])
        self.assertIn("BASELINE_LOW_MILEAGE_DISCOUNT_ONLY", reason_highlight["baseline_value"])
        self.assertIn("PROPOSED_RISK_CHANGE_DETECTED", reason_highlight["proposed_value"])
        self.assertIn('id="ab-difference-highlights"', html)
        self.assertIn('data-ab-difference-highlight-count="4"', html)
        self.assertIn('data-ab-difference-field="score"', html)
        self.assertIn('data-ab-difference-field="grade"', html)
        self.assertIn('data-ab-difference-field="decision"', html)
        self.assertIn('data-ab-difference-field="reason_codes"', html)
        self.assertIn("주요 reason code", html)
        self.assertIn("BASELINE_LOW_MILEAGE_DISCOUNT_ONLY", html)
        self.assertIn("PROPOSED_RISK_CHANGE_DETECTED", html)

    def test_customer_decision_screen_explains_ab_business_impact_for_insurance_ops(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        impact = view_model["customer_ab_comparison"]["business_impact_explanation"]

        self.assertEqual(
            impact["schema_version"],
            "senior-safe-mileage-ab-business-impact/v1",
        )
        self.assertEqual(impact["audience"], "보험사 직원")
        self.assertTrue(impact["requires_staff_review"])
        self.assertEqual(impact["routing_queue"], "예방 케어 상담")
        self.assertIn("기존 산식은 저주행 할인", impact["summary"])
        self.assertTrue(impact["workflow_impacts"])
        self.assertTrue(impact["staff_actions"])
        self.assertTrue(impact["operational_controls"])
        self.assertIn("보험 업무 영향", html)
        self.assertIn('id="ab-business-impact"', html)
        self.assertIn('data-ab-business-impact-review-required="true"', html)
        self.assertIn('data-ab-business-impact-routing="예방 케어 상담"', html)
        self.assertIn(impact["summary"], html)
        self.assertIn("업무 처리 차이", html)
        self.assertIn("직원 조치", html)
        self.assertIn("운영 통제", html)
        for action in impact["staff_actions"]:
            self.assertIn(action, html)

    def test_ab_comparison_screen_renders_separated_summary_reason_and_impact_sections(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        explanation = view_model["customer_ab_comparison"]["change_explanation_sections"]

        self.assertEqual(
            explanation["schema_version"],
            "senior-safe-mileage-ab-change-explanation-sections/v1",
        )
        self.assertEqual(explanation["section_count"], 3)
        self.assertEqual(
            [section["key"] for section in explanation["sections"]],
            ["change-summary", "change-reasons", "impact-explanation"],
        )
        self.assertIn("예방 케어", explanation["sections"][0]["body"])
        self.assertTrue(explanation["sections"][1]["items"])
        self.assertTrue(explanation["sections"][2]["items"])
        self.assertIn('id="ab-change-explanation-sections"', html)
        self.assertIn('data-ab-change-explanation-section-count="3"', html)
        self.assertIn('data-ab-explanation-section="change-summary"', html)
        self.assertIn('data-ab-explanation-section="change-reasons"', html)
        self.assertIn('data-ab-explanation-section="impact-explanation"', html)
        self.assertIn("변경 요약", html)
        self.assertIn("변경 사유", html)
        self.assertIn("영향 설명", html)
        for section in explanation["sections"]:
            self.assertIn(section["body"], html)
            for item in section["items"]:
                self.assertIn(item, html)

    def test_policy_candidate_search_screen_compares_weights_and_thresholds(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        comparison = view_model["policy_candidate_comparison"]
        standalone = build_policy_candidate_comparison_view_model(
            selected_candidate_id=bundle["selected_policy"]["candidate_id"]
        )

        self.assertEqual(comparison["schema_version"], "senior-safe-mileage-policy-candidate-comparison/v1")
        self.assertEqual(comparison["candidate_count"], 114)
        self.assertEqual(standalone["candidate_count"], comparison["candidate_count"])
        self.assertEqual(comparison["selected_candidate_id"], bundle["selected_policy"]["candidate_id"])
        self.assertEqual(len(comparison["rows"]), 114)
        self.assertEqual(sum(1 for row in comparison["rows"] if row["is_selected"]), 1)
        selected = next(row for row in comparison["rows"] if row["is_selected"])
        self.assertEqual(selected["candidate_id"], "policy_30_30_20_20_p20_a75")
        self.assertEqual(selected["weights"]["w_mileage"], 0.3)
        self.assertEqual(selected["weights"]["w_in_zone"], 0.3)
        self.assertEqual(selected["weights"]["w_out_zone_safe"], 0.2)
        self.assertEqual(selected["weights"]["w_out_zone_change"], 0.2)
        self.assertEqual(selected["thresholds"]["care_threshold"], 41.14)
        self.assertEqual(selected["thresholds"]["tier_threshold"]["S"], 85)
        self.assertIn('id="policy-candidate-comparison"', html)
        self.assertIn('data-policy-candidate-count="114"', html)
        self.assertIn('data-policy-candidate-selected="true"', html)
        self.assertIn('aria-label="정책 탐색 근거 및 감사"', html)
        self.assertIn('data-policy-search-tab="evidence"', html)
        self.assertIn('data-policy-search-tab="audit"', html)
        self.assertIn('href="#selected-policy-candidate-rationale"', html)
        self.assertIn('href="#policy-candidate-audit-table"', html)
        self.assertIn('id="policy-candidate-audit-table"', html)
        self.assertIn("정책 후보 탐색 비교", html)
        self.assertIn("근거", html)
        self.assertIn("감사", html)
        self.assertIn("마일리지", html)
        self.assertIn("생활권 내", html)
        self.assertIn("생활권 밖 안전", html)
        self.assertIn("위험변화", html)
        self.assertIn("예방 기준", html)
        self.assertIn("S/A/B/C 기준", html)
        self.assertIn("policy_30_30_20_20_p20_a75", html)
        self.assertIn("41.1", html)
        self.assertIn("top 20%", html)

    def test_selected_policy_candidate_rationale_panel_is_rendered(self) -> None:
        bundle = build_ui_dashboard_bundle(evaluate_selected_policy(build_evaluation_input()))
        view_model = build_customer_decision_view_model(bundle, selected_customer_id="cust_011")
        html = render_customer_decision_page(bundle, selected_customer_id="cust_011")
        detail = view_model["policy_candidate_comparison"]["selected_candidate_detail"]

        self.assertEqual(detail["candidate_id"], "policy_30_30_20_20_p20_a75")
        self.assertEqual(detail["rank"], 1)
        self.assertTrue(detail["approval_gate_passed"])
        self.assertIn("ranked by synthetic 30-customer capture", detail["rationale"])
        self.assertIn("포착 5/5", detail["selection_summary"])
        self.assertIn("오탐", detail["selection_summary"])
        self.assertIn("APPROVAL_GATE_POLICY_CANDIDATE", detail["reason_codes"])
        self.assertTrue(detail["strengths"])
        self.assertTrue(detail["tradeoffs"])
        self.assertTrue(detail["fairness_notes"])
        self.assertTrue(detail["persona_detection_counts"])
        self.assertIn('id="selected-policy-candidate-rationale"', html)
        self.assertIn('data-selected-policy-rationale-candidate-id="policy_30_30_20_20_p20_a75"', html)
        self.assertIn("선택된 정책 후보 선택 근거", html)
        self.assertIn("선택 reason code", html)
        self.assertIn("강점", html)
        self.assertIn("Trade-off", html)
        self.assertIn("오분류 통제 메모", html)
        self.assertIn(detail["rationale"], html)
        self.assertIn(detail["selection_summary"], html)
        for code in detail["reason_codes"]:
            self.assertIn(code, html)


if __name__ == "__main__":
    unittest.main()

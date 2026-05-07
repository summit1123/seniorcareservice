from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import csv
from unittest.mock import patch

from src.agents.contracts import AgentInputPayload, AgentStatus, FORBIDDEN_EXTERNAL_API_FIELDS
from src.agents.critic_agent import CriticAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.report_agent import (
    ReportAgent,
    _load_openai_env_file,
    build_insurer_report,
    build_llm_report_auxiliary_results,
    load_report_inputs,
)
from src.llm import (
    OpenAIClientAPIError,
    OpenAIClientAuthenticationError,
    OpenAIClientTimeoutError,
    OpenAIReportResponse,
)
from src.webapp.validation_pipeline_service import (
    get_validation_pipeline_check,
    load_validation_pipeline_result,
)


class TestReportAgent(unittest.TestCase):
    def test_report_agent_writes_insurer_structured_report_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ab_output = workspace / "ab_test_results.csv"
            view_model_output = workspace / "evaluation_view_model.json"
            review_output = workspace / "rule_review.md"
            structured_review_output = workspace / "rule_review.json"
            report_output = workspace / "simulation_summary.md"
            structured_report_output = workspace / "simulation_summary.json"
            llm_auxiliary_output = workspace / "llm_report_auxiliary_results.json"

            evaluation_result = EvaluationAgent().run(
                AgentInputPayload(
                    run_id="report-evaluation-test",
                    agent_id="evaluation_agent",
                    parameters={
                        "output_path": str(ab_output),
                        "view_model_output_path": str(view_model_output),
                    },
                )
            )
            self.assertEqual(evaluation_result.status, AgentStatus.SUCCEEDED)
            critic_result = CriticAgent().run(
                AgentInputPayload(
                    run_id="report-critic-test",
                    agent_id="critic_agent",
                    parameters={
                        "ab_results_input": str(ab_output),
                        "view_model_input": str(view_model_output),
                        "review_output": str(review_output),
                        "structured_output": str(structured_review_output),
                    },
                )
            )
            self.assertEqual(critic_result.status, AgentStatus.SUCCEEDED)

            result = ReportAgent().run(
                AgentInputPayload(
                    run_id="report-agent-test",
                    agent_id="report_agent",
                    parameters={
                        "evaluation_view_model_input": str(view_model_output),
                        "critic_review_input": str(structured_review_output),
                        "report_output": str(report_output),
                        "structured_output": str(structured_report_output),
                        "llm_auxiliary_output": str(llm_auxiliary_output),
                    },
                )
            )

            result.validate()
            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            self.assertTrue(report_output.exists())
            self.assertTrue(structured_report_output.exists())
            assert result.output_payload is not None
            self.assertEqual(
                tuple(artifact.artifact_id for artifact in result.output_payload.output_artifacts),
                ("simulation_summary.md", "simulation_summary.json", "llm_report_auxiliary_results.json"),
            )
            self.assertEqual(result.output_payload.metrics["customer_count"], 30)
            self.assertTrue(result.output_payload.validation["privacy_checked"])
            self.assertIn("INSURER_REPORT_DATA_READY", result.output_payload.reason_codes)

            report = json.loads(structured_report_output.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "senior-report-agent/v1")
            self.assertTrue(report["approval"]["ready_for_insurer_review"])
            self.assertEqual(len(report["customer_reports"]), 30)
            self.assertTrue(llm_auxiliary_output.exists())
            auxiliary = json.loads(llm_auxiliary_output.read_text(encoding="utf-8"))
            self.assertEqual(auxiliary["schema_version"], "senior-llm-report-auxiliary-results/v1")
            self.assertEqual(len(auxiliary["customer_auxiliary_results"]), 30)
            self.assertTrue(auxiliary["validation"]["privacy_checked"])
            first = report["customer_reports"][0]
            self.assertEqual(first["llm_report"]["audience"], "insurer_staff")
            self.assertTrue(first["xai_reason_codes"])
            self.assertIn("hybrid_evaluation", first)
            self.assertIn("hybrid_pass_fail_rationale", first["llm_report"])
            self.assertTrue(first["llm_report"]["reason_code_narratives"])
            self.assertTrue(first["llm_report"]["reason_code_narratives"][0]["staff_sentence"])
            self.assertTrue(first["llm_report"]["reason_code_narratives"][0]["change_reason"])
            self.assertNotIn("customer_id", first["llm_report"]["request_features"])
            markdown = report_output.read_text(encoding="utf-8")
            self.assertIn("Senior Safe Mileage Simulation Summary", markdown)
            self.assertIn("Hybrid evaluation: proposed", markdown)
            self.assertIn("Hybrid rationale:", markdown)

    def test_report_agent_fallback_mode_keeps_core_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            result = ReportAgent().run(
                AgentInputPayload(
                    run_id="report-fallback-test",
                    agent_id="report_agent",
                    parameters={
                        "report_output": str(workspace / "simulation_summary.md"),
                        "structured_output": str(workspace / "simulation_summary.json"),
                        "llm_auxiliary_output": str(workspace / "llm_report_auxiliary_results.json"),
                        "force_llm_failure": True,
                    },
                )
            )

            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            assert result.output_payload is not None
            self.assertEqual(result.output_payload.metrics["customer_count"], 30)
            self.assertEqual(result.output_payload.metrics["risk_change_capture_count"], 5)
            self.assertEqual(result.output_payload.validation["fallback_report_count"], 30)

    def test_openai_api_failure_does_not_change_scores_or_customer_decisions(self) -> None:
        report_input = load_report_inputs()
        deterministic_report = build_insurer_report(report_input)
        failing_client = FailingOpenAIReportClient(OpenAIClientAPIError("simulated OpenAI outage"))

        fallback_report = build_insurer_report(report_input, openai_client=failing_client)

        self.assertEqual(fallback_report["report_mode"], "fallback_template")
        self.assertEqual(fallback_report["validation"]["fallback_report_count"], 30)
        self.assertEqual(deterministic_report["summary_metrics"], fallback_report["summary_metrics"])
        self.assertEqual(deterministic_report["selected_policy"], fallback_report["selected_policy"])
        self.assertEqual(len(fallback_report["customer_reports"]), 30)

        deterministic_by_customer = {
            row["customer_id"]: row for row in deterministic_report["customer_reports"]
        }
        for fallback_customer in fallback_report["customer_reports"]:
            deterministic_customer = deterministic_by_customer[fallback_customer["customer_id"]]
            with self.subTest(customer_id=fallback_customer["customer_id"]):
                self.assertEqual(fallback_customer["scores"], deterministic_customer["scores"])
                self.assertEqual(
                    fallback_customer["care_decision"],
                    deterministic_customer["care_decision"],
                )
                self.assertEqual(
                    fallback_customer["xai_reason_codes"],
                    deterministic_customer["xai_reason_codes"],
                )
                self.assertEqual(
                    fallback_customer["ab_comparison"],
                    deterministic_customer["ab_comparison"],
                )
                self.assertEqual(
                    fallback_customer["agent_validation"],
                    deterministic_customer["agent_validation"],
                )
                self.assertEqual(fallback_customer["llm_report"]["mode"], "fallback_template")
                self.assertEqual(fallback_customer["llm_report"]["llm_service_status"]["status"], "failed")
                self.assertFalse(fallback_customer["llm_report"]["llm_service_status"]["active"])
                self.assertTrue(fallback_customer["llm_report"]["llm_service_status"]["failure_detected"])
                self.assertEqual(
                    fallback_customer["llm_report"]["empty_report_result"]["status"],
                    "empty",
                )
                self.assertEqual(fallback_customer["llm_report"]["empty_report_result"]["text"], "")
                self.assertTrue(
                    fallback_customer["llm_report"]["empty_report_result"]["core_outputs_continue"]
                )

        self.assertEqual(len(failing_client.requests), 1)
        self.assertFalse(_flatten_keys(failing_client.requests[0].request_features) & FORBIDDEN_EXTERNAL_API_FIELDS)

    def test_shared_openai_client_failure_falls_back_without_failing_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            failing_client = FailingOpenAIReportClient()

            result = ReportAgent().run(
                AgentInputPayload(
                    run_id="report-openai-fallback-test",
                    agent_id="report_agent",
                    parameters={
                        "report_output": str(workspace / "simulation_summary.md"),
                        "structured_output": str(workspace / "simulation_summary.json"),
                        "llm_auxiliary_output": str(workspace / "llm_report_auxiliary_results.json"),
                        "openai_client": failing_client,
                    },
                )
            )

            self.assertEqual(result.status, AgentStatus.SUCCEEDED)
            assert result.output_payload is not None
            self.assertEqual(result.output_payload.metrics["customer_count"], 30)
            self.assertEqual(result.output_payload.metrics["risk_change_capture_count"], 5)
            self.assertEqual(result.output_payload.validation["fallback_report_count"], 30)
            self.assertIn("LLM_REPORT_FALLBACK_READY", result.output_payload.reason_codes)

            report = json.loads((workspace / "simulation_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(report["report_mode"], "fallback_template")
            self.assertEqual(report["portfolio_llm_report"]["mode"], "fallback_template")
            self.assertEqual(report["customer_reports"][0]["llm_report"]["mode"], "fallback_template")
            self.assertEqual(report["portfolio_llm_report"]["llm_service_status"]["status"], "failed")
            self.assertFalse(report["portfolio_llm_report"]["llm_service_status"]["active"])
            self.assertTrue(report["portfolio_llm_report"]["llm_service_status"]["failure_detected"])
            self.assertEqual(report["portfolio_llm_report"]["empty_report_result"]["text"], "")
            self.assertEqual(report["customer_reports"][0]["llm_report"]["empty_report_result"]["text"], "")
            self.assertEqual(
                report["customer_reports"][0]["llm_report"]["llm_client_error"]["handled_by"],
                "report_agent",
            )
            auxiliary = json.loads((workspace / "llm_report_auxiliary_results.json").read_text(encoding="utf-8"))
            self.assertEqual(auxiliary["portfolio_auxiliary_result"]["empty_report_result"]["text"], "")
            self.assertEqual(auxiliary["customer_auxiliary_results"][0]["empty_report_result"]["text"], "")
            self.assertEqual(len(failing_client.requests), 1)
            self.assertFalse(_flatten_keys(failing_client.requests[0].request_features) & FORBIDDEN_EXTERNAL_API_FIELDS)

    def test_mocked_openai_failure_still_generates_validation_and_ab_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ab_output = workspace / "ab_test_results.csv"
            view_model_output = workspace / "evaluation_view_model.json"
            review_output = workspace / "rule_review.md"
            structured_review_output = workspace / "rule_review.json"
            report_output = workspace / "simulation_summary.md"
            structured_report_output = workspace / "simulation_summary.json"
            llm_auxiliary_output = workspace / "llm_report_auxiliary_results.json"
            failing_client = FailingOpenAIReportClient(
                OpenAIClientAPIError("mocked OpenAI outage for validation scenario")
            )

            evaluation_result = EvaluationAgent().run(
                AgentInputPayload(
                    run_id="openai-failure-evaluation-test",
                    agent_id="evaluation_agent",
                    parameters={
                        "output_path": str(ab_output),
                        "view_model_output_path": str(view_model_output),
                    },
                )
            )
            self.assertEqual(evaluation_result.status, AgentStatus.SUCCEEDED)
            critic_result = CriticAgent().run(
                AgentInputPayload(
                    run_id="openai-failure-critic-test",
                    agent_id="critic_agent",
                    parameters={
                        "ab_results_input": str(ab_output),
                        "view_model_input": str(view_model_output),
                        "review_output": str(review_output),
                        "structured_output": str(structured_review_output),
                    },
                )
            )
            self.assertEqual(critic_result.status, AgentStatus.SUCCEEDED)

            report_result = ReportAgent().run(
                AgentInputPayload(
                    run_id="openai-failure-report-test",
                    agent_id="report_agent",
                    parameters={
                        "evaluation_view_model_input": str(view_model_output),
                        "critic_review_input": str(structured_review_output),
                        "report_output": str(report_output),
                        "structured_output": str(structured_report_output),
                        "llm_auxiliary_output": str(llm_auxiliary_output),
                        "openai_client": failing_client,
                    },
                )
            )

            self.assertEqual(report_result.status, AgentStatus.SUCCEEDED)
            self.assertFalse(report_result.errors)
            assert report_result.output_payload is not None
            self.assertTrue(report_result.output_payload.validation["passed"])
            self.assertTrue(report_result.output_payload.validation["approved_inputs"])
            self.assertEqual(report_result.output_payload.validation["fallback_report_count"], 30)
            self.assertEqual(report_result.output_payload.metrics["customer_count"], 30)
            self.assertEqual(report_result.output_payload.metrics["risk_change_capture_count"], 5)
            self.assertEqual(report_result.output_payload.decisions["approval_gate_passed"], True)
            self.assertEqual(report_result.output_payload.llm_report["mode"], "fallback_template")
            self.assertTrue(report_result.output_payload.llm_report["summary"])
            self.assertTrue(ab_output.exists())
            self.assertTrue(view_model_output.exists())
            self.assertTrue(report_output.exists())
            self.assertTrue(structured_report_output.exists())
            self.assertTrue(llm_auxiliary_output.exists())

            with ab_output.open(encoding="utf-8", newline="") as handle:
                ab_rows = list(csv.DictReader(handle))
            self.assertEqual(len(ab_rows), 30)
            self.assertIn("baseline_detected", ab_rows[0])
            self.assertIn("proposed_detected", ab_rows[0])
            self.assertEqual(
                sum(
                    1
                    for row in ab_rows
                    if int(row["risk_change_target"]) and int(row["proposed_detected"])
                ),
                5,
            )

            pipeline = load_validation_pipeline_result(
                run_id="openai-failure-local-validation-test",
                ab_results_input=ab_output,
                evaluation_view_model_input=view_model_output,
                critic_review_input=structured_review_output,
                report_view_model_input=structured_report_output,
            )
            evaluation_check = get_validation_pipeline_check(pipeline, "evaluation_agent")
            report_check = get_validation_pipeline_check(pipeline, "report_agent")

            self.assertTrue(evaluation_check["passed"])
            self.assertTrue(evaluation_check["validation"]["approval_gate_passed"])
            self.assertEqual(evaluation_check["metrics"]["customer_count"], 30)
            self.assertGreaterEqual(evaluation_check["metrics"]["agent_validation_pass_rate"], 0.95)
            self.assertTrue(report_check["passed"])
            self.assertEqual(report_check["validation"]["report_mode"], "fallback_template")
            self.assertEqual(report_check["validation"]["service_status"], "failed")
            self.assertFalse(report_check["validation"]["service_active"])
            self.assertTrue(report_check["validation"]["failure_detected"])
            self.assertTrue(report_check["validation"]["core_outputs_continue"])
            self.assertEqual(report_check["metrics"]["fallback_report_count"], 30)

            report = json.loads(structured_report_output.read_text(encoding="utf-8"))
            self.assertEqual(report["customer_reports"][0]["llm_report"]["empty_report_result"]["text"], "")
            self.assertTrue(
                report["customer_reports"][0]["llm_report"]["empty_report_result"]["core_outputs_continue"]
            )
            self.assertEqual(len(failing_client.requests), 1)
            self.assertFalse(_flatten_keys(failing_client.requests[0].request_features) & FORBIDDEN_EXTERNAL_API_FIELDS)

    def test_llm_timeout_auth_network_and_parsing_errors_do_not_stop_app_outputs(self) -> None:
        cases = (
            ("timeout", OpenAIClientTimeoutError("request timeout")),
            ("authentication", OpenAIClientAuthenticationError("401 invalid api key")),
            ("network", ConnectionError("network connection failed")),
            ("response_parsing", OpenAIClientAPIError("OpenAI response did not include text")),
        )
        for case_name, exc in cases:
            with self.subTest(case_name=case_name):
                with tempfile.TemporaryDirectory() as tmpdir:
                    workspace = Path(tmpdir)
                    failing_client = FailingOpenAIReportClient(exc)

                    result = ReportAgent().run(
                        AgentInputPayload(
                            run_id=f"report-{case_name}-fallback-test",
                            agent_id="report_agent",
                            parameters={
                                "report_output": str(workspace / "simulation_summary.md"),
                                "structured_output": str(workspace / "simulation_summary.json"),
                                "llm_auxiliary_output": str(workspace / "llm_report_auxiliary_results.json"),
                                "openai_client": failing_client,
                            },
                        )
                    )

                    self.assertEqual(result.status, AgentStatus.SUCCEEDED)
                    assert result.output_payload is not None
                    self.assertEqual(result.output_payload.metrics["customer_count"], 30)
                    self.assertEqual(result.output_payload.metrics["risk_change_capture_count"], 5)
                    self.assertTrue(result.output_payload.validation["passed"])
                    self.assertEqual(result.output_payload.validation["fallback_report_count"], 30)
                    self.assertIn("LLM_REPORT_FALLBACK_READY", result.output_payload.reason_codes)

                    report = json.loads((workspace / "simulation_summary.json").read_text(encoding="utf-8"))
                    auxiliary = json.loads(
                        (workspace / "llm_report_auxiliary_results.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(report["report_mode"], "fallback_template")
                    self.assertEqual(auxiliary["report_mode"], "fallback_template")
                    self.assertEqual(
                        report["portfolio_llm_report"]["llm_service_status"]["status"],
                        "failed",
                    )
                    self.assertFalse(report["portfolio_llm_report"]["llm_service_status"]["active"])
                    self.assertEqual(
                        report["customer_reports"][0]["llm_report"]["llm_client_error"]["error_type"],
                        exc.__class__.__name__,
                    )
                    self.assertEqual(
                        report["customer_reports"][0]["llm_report"]["empty_report_result"]["status"],
                        "empty",
                    )
                    self.assertEqual(
                        report["customer_reports"][0]["llm_report"]["empty_report_result"]["text"],
                        "",
                    )
                    self.assertTrue(
                        report["customer_reports"][0]["llm_report"]["empty_report_result"]["core_outputs_continue"]
                    )
                    self.assertEqual(
                        auxiliary["customer_auxiliary_results"][0]["empty_report_result"]["error_type"],
                        exc.__class__.__name__,
                    )
                    self.assertEqual(
                        auxiliary["customer_auxiliary_results"][0]["llm_service_status"]["status"],
                        "failed",
                    )
                    self.assertFalse(auxiliary["customer_auxiliary_results"][0]["llm_service_status"]["active"])
                    self.assertEqual(len(failing_client.requests), 1)
                    self.assertFalse(
                        _flatten_keys(failing_client.requests[0].request_features)
                        & FORBIDDEN_EXTERNAL_API_FIELDS
                    )

    def test_shared_openai_client_success_uses_privacy_filtered_features_only(self) -> None:
        client = SuccessfulOpenAIReportClient()
        report = build_insurer_report(load_report_inputs(), openai_client=client)

        self.assertEqual(report["report_mode"], "llm_generated")
        self.assertEqual(report["portfolio_llm_report"]["mode"], "llm_generated")
        self.assertEqual(report["customer_reports"][0]["llm_report"]["mode"], "llm_generated")
        self.assertEqual(report["portfolio_llm_report"]["llm_service_status"]["status"], "available")
        self.assertTrue(report["portfolio_llm_report"]["llm_service_status"]["active"])
        self.assertIn("LLM summary", report["customer_reports"][0]["llm_report"]["summary"])
        self.assertEqual(len(client.requests), 31)
        for request in client.requests:
            self.assertFalse(_flatten_keys(request.request_features) & FORBIDDEN_EXTERNAL_API_FIELDS)

    def test_report_cli_env_loader_accepts_lowercase_openai_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("openai_api_key=test-key\nopenai_model=test-model\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                _load_openai_env_file(env_file)

                self.assertEqual(os.environ["OPENAI_API_KEY"], "test-key")
                self.assertEqual(os.environ["OPENAI_MODEL"], "test-model")

    def test_llm_report_auxiliary_results_have_request_features_and_section_drafts(self) -> None:
        report = build_insurer_report(load_report_inputs(), force_llm_failure=True)
        auxiliary = build_llm_report_auxiliary_results(report)

        self.assertEqual(auxiliary["schema_version"], "senior-llm-report-auxiliary-results/v1")
        self.assertEqual(auxiliary["report_mode"], "fallback_template")
        self.assertEqual(auxiliary["validation"]["customer_auxiliary_result_count"], 30)
        self.assertEqual(auxiliary["validation"]["fallback_ready_count"], 30)
        first = auxiliary["customer_auxiliary_results"][0]
        self.assertIn("customer_id", first)
        self.assertIn("request_features", first)
        self.assertIn("staff_summary", first["section_drafts"])
        self.assertIn("decision_explanation", first["section_drafts"])
        self.assertIn("hybrid_pass_fail_rationale", first["section_drafts"])
        self.assertIn("recommended_action", first["section_drafts"])
        self.assertIn("caution_notice", first["section_drafts"])
        self.assertTrue(first["section_drafts"]["caution_notice"])
        self.assertTrue(first["evidence_cards"])
        self.assertIn("hybrid_evaluation", first)
        self.assertTrue(any(card["card_id"] == "hybrid_evaluation" for card in first["evidence_cards"]))
        self.assertTrue(first["reason_code_narratives"])
        self.assertTrue(first["reason_code_narratives"][0]["staff_sentence"])
        self.assertTrue(first["reason_code_narratives"][0]["change_reason"])
        self.assertIn("reason_code_narrative_summary", first["section_drafts"])
        self.assertEqual(first["privacy_contract"]["external_request_source"], "request_features")
        self.assertNotIn("customer_id", first["request_features"])

    def test_reason_codes_are_translated_to_insurer_staff_sentences_for_decision_change(self) -> None:
        report = build_insurer_report(load_report_inputs())
        preventive = next(
            row for row in report["customer_reports"]
            if row["customer_id"] == "cust_011"
        )

        narratives = preventive["llm_report"]["reason_code_narratives"]
        by_code = {row["code"]: row for row in narratives}
        self.assertIn("PROPOSED_MODEL_PREVENTIVE_CARE", by_code)
        self.assertEqual(by_code["PROPOSED_MODEL_PREVENTIVE_CARE"]["contribution_type"], "decision_change")
        self.assertIn("예방 케어 판정으로 전환", by_code["PROPOSED_MODEL_PREVENTIVE_CARE"]["staff_sentence"])
        self.assertIn("기존 산식은 연환산 거리 중심", by_code["PROPOSED_MODEL_PREVENTIVE_CARE"]["change_reason"])
        self.assertIn("생활권 밖 주행 패턴 변화", by_code["OUT_ZONE_PATTERN_CHANGE_RISK"]["staff_sentence"])
        self.assertIn("예방 케어 판정으로 전환", preventive["llm_report"]["decision_explanation"])

    def test_report_input_rejects_unapproved_critic_review(self) -> None:
        report_input = load_report_inputs()
        report_input["critic_review"] = {
            **report_input["critic_review"],
            "validation": {**report_input["critic_review"]["validation"], "passed": False},
        }

        with self.assertRaisesRegex(ValueError, "Critic Agent validation"):
            build_insurer_report(report_input)

    def test_llm_request_features_exclude_forbidden_identifiers(self) -> None:
        report = build_insurer_report(load_report_inputs())
        forbidden = set(FORBIDDEN_EXTERNAL_API_FIELDS)

        portfolio_keys = _flatten_keys(report["portfolio_llm_report"]["request_features"])
        self.assertFalse(portfolio_keys & forbidden)
        for row in report["customer_reports"]:
            request_keys = _flatten_keys(row["llm_report"]["request_features"])
            self.assertFalse(request_keys & forbidden)


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


class FailingOpenAIReportClient:
    def __init__(self, exc: BaseException | None = None) -> None:
        self.requests: list[object] = []
        self.exc = exc or OpenAIClientTimeoutError("request timeout")

    def generate_insurer_report(self, request: object) -> OpenAIReportResponse:
        self.requests.append(request)
        raise self.exc


class SuccessfulOpenAIReportClient:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def generate_insurer_report(self, request: object) -> OpenAIReportResponse:
        self.requests.append(request)
        return OpenAIReportResponse(
            text=f"LLM summary {len(self.requests)}",
            model="test-model",
            attempts=1,
        )


if __name__ == "__main__":
    unittest.main()

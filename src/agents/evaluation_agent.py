"""Evaluation Agent for Senior Safe Mileage A/B scoring outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents.contracts import (
    ABComparison,
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentStatus,
    AgentValidationSummary,
    ArtifactType,
    CustomerDecisionSnapshot,
    ObservationPeriod,
    PolicyCandidate,
    validate_customer_decision_snapshot,
    utc_now_iso,
)
from src.agents.policy_search_agent import (
    DEFAULT_SCENARIO_INPUT,
    DEFAULT_TRIP_INPUT,
    build_customer_features,
)
from src.agents.structured_outputs import validate_evaluation_view_model, write_structured_json
from src.features.build_model_features import write_csv
from src.features.zone_features import (
    DEFAULT_CUSTOMER_LIVING_ZONE_RECORD_STORE_PATH,
    living_zone_decision_summary,
    load_customer_living_zone_record_store,
)
from src.product.proxy_labels import (
    HYBRID_PASS_THRESHOLD,
    derive_risk_change_proxy_label,
    score_hybrid_evaluation_decision,
)
from src.product.ab_comparison import build_customer_ab_comparison_dataset


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_RULES_INPUT = ROOT / "data" / "fixtures" / "candidate_rules.json"
DEFAULT_OUTPUT = ROOT / "data" / "fixtures" / "ab_test_results.csv"
DEFAULT_VIEW_MODEL_OUTPUT = ROOT / "data" / "fixtures" / "evaluation_view_model.json"
SCHEMA_VERSION = "senior-evaluation-results/v1"


class EvaluationAgent:
    """Compare the distance-only baseline against the selected integrated policy."""

    metadata = AgentMetadata(
        agent_id="evaluation_agent",
        role=AgentRole.EVALUATION,
        display_name="Evaluation Agent",
        description="Produces customer and policy scoring outputs for UI consumption.",
        consumes=("candidate_rules.json", "decision_table.csv"),
        produces=("ab_test_results.csv", "evaluation_view_model.json"),
    )

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            candidate_rules_input = _resolve_artifact_path(
                payload,
                "candidate_rules.json",
                "candidate_rules_input",
                DEFAULT_CANDIDATE_RULES_INPUT,
            )
            trip_input = _resolve_artifact_path(payload, "senior_trip_logs.csv", "trip_input", DEFAULT_TRIP_INPUT)
            scenario_input = _resolve_artifact_path(payload, "scenario_config.json", "scenario_input", DEFAULT_SCENARIO_INPUT)
            output_path = Path(str(payload.parameters.get("output_path", DEFAULT_OUTPUT)))
            view_model_output_path = Path(
                str(payload.parameters.get("view_model_output_path", DEFAULT_VIEW_MODEL_OUTPUT))
            )

            evaluation_input = build_evaluation_input(
                candidate_rules_input=candidate_rules_input,
                trip_input=trip_input,
                scenario_input=scenario_input,
                selected_candidate_id=payload.parameters.get("selected_candidate_id"),
                selected_scenario_id=payload.parameters.get("selected_scenario_id"),
            )
            result = evaluate_selected_policy(evaluation_input)
            write_ab_results_csv(result, output_path)
            write_evaluation_view_model(result, view_model_output_path)

            metrics = result["summary_metrics"]
            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="ab_test_results.csv",
                        artifact_type=ArtifactType.CSV,
                        path=_relative_project_path(output_path),
                        rows=len(result["customer_rows"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "customer_count": metrics["customer_count"],
                            "passes_approval_gate": metrics["passes_approval_gate"],
                        },
                    ),
                    AgentArtifact(
                        artifact_id="evaluation_view_model.json",
                        artifact_type=ArtifactType.WEB_VIEW_MODEL,
                        path=_relative_project_path(view_model_output_path),
                        rows=len(result["customer_snapshots"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "selected_candidate_id": result["selected_policy"]["candidate_id"],
                        },
                    ),
                ),
                metrics={
                    "customer_count": metrics["customer_count"],
                    "risk_change_target_count": metrics["risk_change_target_count"],
                    "non_target_count": metrics["non_target_count"],
                    "baseline_capture_count": metrics["baseline_capture_count"],
                    "proposed_capture_count": metrics["proposed_capture_count"],
                    "non_target_false_positive_count": metrics["non_target_false_positive_count"],
                    "non_target_false_positive_limit": metrics["non_target_false_positive_limit"],
                    "passes_non_target_false_positive_gate": metrics["passes_non_target_false_positive_gate"],
                    "total_misclassification_count": metrics["total_misclassification_count"],
                    "total_misclassification_limit": metrics["total_misclassification_limit"],
                    "passes_misclassification_check": metrics["passes_misclassification_check"],
                    "agent_validation_pass_rate": metrics["agent_validation_pass_rate"],
                    "proposed_hybrid_pass_count": metrics["proposed_hybrid_pass_count"],
                    "proposed_hybrid_fail_count": metrics["proposed_hybrid_fail_count"],
                    "passes_approval_gate": metrics["passes_approval_gate"],
                },
                decisions={
                    "selected_candidate_id": result["selected_policy"]["candidate_id"],
                    "baseline_low_mileage_high_risk_capture": metrics["baseline_low_mileage_high_risk_capture"],
                    "proposed_low_mileage_high_risk_capture": metrics["proposed_low_mileage_high_risk_capture"],
                    "hybrid_pass_fail_threshold": metrics["hybrid_pass_fail_threshold"],
                    "customer_snapshot_count": len(result["customer_snapshots"]),
                },
                reason_codes=tuple(result["evaluation_reason_codes"]),
                validation={
                    "passed": bool(metrics["passes_approval_gate"]),
                    "schema_version": SCHEMA_VERSION,
                    "customer_snapshots_validated": len(result["customer_snapshots"]),
                    "privacy_checked": True,
                    "forbidden_external_api_fields_present": [],
                },
                messages=("evaluation results generated for A/B dashboard and customer detail views",),
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


def build_evaluation_input(
    *,
    candidate_rules_input: Path = DEFAULT_CANDIDATE_RULES_INPUT,
    trip_input: Path = DEFAULT_TRIP_INPUT,
    scenario_input: Path = DEFAULT_SCENARIO_INPUT,
    living_zone_store_input: Path = DEFAULT_CUSTOMER_LIVING_ZONE_RECORD_STORE_PATH,
    selected_candidate_id: str | None = None,
    selected_scenario_id: str | None = None,
) -> dict[str, Any]:
    candidate_rules = json.loads(candidate_rules_input.read_text(encoding="utf-8"))
    selected = _select_policy_candidate(candidate_rules, selected_candidate_id)
    scenario_config = json.loads(scenario_input.read_text(encoding="utf-8"))
    selected_scenario = _selected_scenario_state(
        scenario_config,
        scenario_input=scenario_input,
        selected_scenario_id=selected_scenario_id,
    )
    features = build_customer_features(trip_input, scenario_input)
    living_zone_store = (
        load_customer_living_zone_record_store(living_zone_store_input)
        if living_zone_store_input.exists()
        else None
    )
    return {
        "schema_version": f"{SCHEMA_VERSION}/input",
        "source_artifacts": {
            "candidate_rules_input": _relative_project_path(candidate_rules_input),
            "trip_input": _relative_project_path(trip_input),
            "scenario_input": _relative_project_path(scenario_input),
            "living_zone_store_input": _relative_project_path(living_zone_store_input)
            if living_zone_store
            else "",
        },
        "selected_policy": selected,
        "selected_scenario": selected_scenario,
        "customer_features": features,
        "living_zone_store": living_zone_store,
    }


def evaluate_selected_policy(evaluation_input: dict[str, Any]) -> dict[str, Any]:
    selected_policy = evaluation_input["selected_policy"]
    weights = {key: float(value) for key, value in selected_policy["weights"].items()}
    thresholds = dict(selected_policy["thresholds"])
    tier_threshold = thresholds["tier_threshold"]
    care_threshold = float(thresholds["care_threshold"])
    policy_candidate = PolicyCandidate(
        candidate_id=str(selected_policy["candidate_id"]),
        weights=weights,
        thresholds=thresholds,
        rationale="selected by Policy Search Agent and evaluated against the 30-customer fixture",
    )

    customer_rows: list[dict[str, Any]] = []
    customer_snapshots: list[dict[str, Any]] = []
    living_zone_store = evaluation_input.get("living_zone_store")
    proxy_labels_by_customer_id = {
        str(feature.customer_id): _proxy_label_summary(feature)
        for feature in evaluation_input["customer_features"]
    }
    comparison_dataset = build_customer_ab_comparison_dataset(
        evaluation_input["customer_features"],
        selected_policy_id=policy_candidate.candidate_id,
        weights=weights,
        care_threshold=care_threshold,
        tier_threshold=tier_threshold,
        proxy_label_by_customer_id={
            customer_id: bool(proxy_label["is_target"])
            for customer_id, proxy_label in proxy_labels_by_customer_id.items()
        },
    )
    comparison_dataset_payload = comparison_dataset.to_dict()
    for feature in evaluation_input["customer_features"]:
        proxy_label = proxy_labels_by_customer_id[str(feature.customer_id)]
        target_label = bool(feature.risk_change_target)
        proxy_target_label = bool(proxy_label["is_target"])
        model_comparison = comparison_dataset.get(str(feature.customer_id))
        senior_score = model_comparison.proposed_score
        baseline_detected = model_comparison.baseline_detected
        proposed_detected = model_comparison.proposed_detected
        baseline_hybrid_score = score_hybrid_evaluation_decision(
            decision_detected=baseline_detected,
            ground_truth_target=target_label,
            proxy_label_target=proxy_target_label,
        )
        proposed_hybrid_score = score_hybrid_evaluation_decision(
            decision_detected=proposed_detected,
            ground_truth_target=target_label,
            proxy_label_target=proxy_target_label,
        )
        tier = model_comparison.tier
        care_decision = model_comparison.care_decision
        living_zone = _living_zone_summary(feature, living_zone_store)
        reason_codes = tuple(_reason_codes(feature, proposed_detected, tier, living_zone))
        ab_core_metrics = model_comparison.core_metrics()
        ab_comparison = ABComparison(
            baseline_detected=baseline_detected,
            proposed_detected=proposed_detected,
            baseline_score=model_comparison.baseline_score,
            proposed_score=senior_score,
            metrics={
                **model_comparison.metrics(),
                "proxy_label_rule_id": proxy_label["rule_id"],
                "hybrid_evaluation_rule_id": proposed_hybrid_score.rule_id,
                "baseline_hybrid_evaluation_score": baseline_hybrid_score.score,
                "proposed_hybrid_evaluation_score": proposed_hybrid_score.score,
                "hybrid_evaluation_weights": proposed_hybrid_score.weights,
                "core_metrics": ab_core_metrics,
                "comparison_input": model_comparison.comparison_input.to_dict(),
                "baseline_model": model_comparison.baseline.to_dict(),
                "proposed_model": model_comparison.proposed.to_dict(),
            },
        )
        privacy_features = _privacy_filtered_features(feature, senior_score, care_decision, reason_codes)
        snapshot = CustomerDecisionSnapshot(
            customer_id=feature.customer_id,
            persona_type=feature.persona_type,
            observation_period=ObservationPeriod(),
            living_zone=living_zone,
            mileage_baseline_score=feature.mileage_baseline_score,
            senior_safe_mileage_score=senior_score,
            risk_change_score=feature.risk_change_score,
            policy_candidate=policy_candidate,
            care_decision=care_decision,
            reason_codes=reason_codes,
            ab_comparison=ab_comparison,
            agent_validation=AgentValidationSummary(passed=True, validation_pass_rate=1.0),
            llm_report={
                "mode": "pending_report_agent",
                "request_features": privacy_features,
                "fallback_available": True,
            },
            privacy_filtered_features=privacy_features,
        ).to_dict()
        snapshot["proxy_label"] = proxy_label
        snapshot["hybrid_evaluation"] = {
            "baseline": baseline_hybrid_score.to_dict(),
            "proposed": proposed_hybrid_score.to_dict(),
        }
        snapshot["model_comparison_record"] = model_comparison.to_record()
        validate_customer_decision_snapshot(snapshot)
        customer_snapshots.append(snapshot)
        customer_rows.append(
            {
                "customer_id": feature.customer_id,
                "persona_type": feature.persona_type,
                "risk_change_target": int(target_label),
                "expected_care_decision": feature.expected_care_decision,
                "proxy_label_rule_id": proxy_label["rule_id"],
                "proxy_label_is_target": int(proxy_target_label),
                "proxy_label_expected_care_decision": proxy_label["expected_care_decision"],
                "hybrid_evaluation_rule_id": proposed_hybrid_score.rule_id,
                "baseline_hybrid_evaluation_score": baseline_hybrid_score.score,
                "proposed_hybrid_evaluation_score": proposed_hybrid_score.score,
                "baseline_hybrid_evaluation_passed": int(baseline_hybrid_score.passed),
                "proposed_hybrid_evaluation_passed": int(proposed_hybrid_score.passed),
                "baseline_hybrid_evaluation_verdict": baseline_hybrid_score.verdict,
                "proposed_hybrid_evaluation_verdict": proposed_hybrid_score.verdict,
                "baseline_hybrid_exception_rule": baseline_hybrid_score.exception_rule or "",
                "proposed_hybrid_exception_rule": proposed_hybrid_score.exception_rule or "",
                "hybrid_evaluation_json": json.dumps(
                    {
                        "baseline": baseline_hybrid_score.to_dict(),
                        "proposed": proposed_hybrid_score.to_dict(),
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                "proxy_label_reason_codes_json": json.dumps(
                    proxy_label["reason_codes"],
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                "proxy_label_json": json.dumps(proxy_label, ensure_ascii=True, separators=(",", ":")),
                "mileage_baseline_score": feature.mileage_baseline_score,
                "in_zone_safe_score": feature.in_zone_safe_score,
                "recent_in_zone_km": feature.recent_in_zone_km,
                "recent_in_zone_trip_count": feature.recent_in_zone_trip_count,
                "recent_in_zone_risk_rate_per_100km": feature.recent_in_zone_risk_rate_per_100km,
                "out_zone_safe_score": feature.out_zone_safe_score,
                "recent_out_zone_km": feature.recent_out_zone_km,
                "recent_out_zone_trip_count": feature.recent_out_zone_trip_count,
                "recent_out_zone_risk_rate_per_100km": feature.recent_out_zone_risk_rate_per_100km,
                "risk_change_score": feature.risk_change_score,
                "senior_safe_mileage_score": senior_score,
                "baseline_detected": int(baseline_detected),
                "proposed_detected": int(proposed_detected),
                "non_target_false_positive": int((not target_label) and proposed_detected),
                "tier": tier,
                "care_decision": care_decision,
                "baseline_grade": ab_core_metrics["baseline"]["grade"],
                "proposed_grade": ab_core_metrics["proposed"]["grade"],
                "baseline_discount_rate_pct": ab_core_metrics["baseline"]["discount_rate_pct"],
                "baseline_surcharge_rate_pct": ab_core_metrics["baseline"]["surcharge_rate_pct"],
                "proposed_discount_rate_pct": ab_core_metrics["proposed"]["discount_rate_pct"],
                "proposed_surcharge_rate_pct": ab_core_metrics["proposed"]["surcharge_rate_pct"],
                "baseline_pricing_action": ab_core_metrics["baseline"]["pricing_action"],
                "proposed_pricing_action": ab_core_metrics["proposed"]["pricing_action"],
                "comparison_input_data_ref": model_comparison.comparison_input.input_data_ref,
                "comparison_lookup_key": model_comparison.to_record()["lookup_key"],
                "same_customer_input": int(model_comparison.same_customer_input),
                "ab_score_delta": ab_core_metrics["difference"]["score_delta"],
                "ab_decision_changed": int(ab_core_metrics["difference"]["decision_changed"]),
                "ab_premium_adjustment_delta_pct": ab_core_metrics["difference"]["premium_adjustment_delta_pct"],
                "reason_codes_json": json.dumps(list(reason_codes), ensure_ascii=True, separators=(",", ":")),
                "ab_core_metrics_json": json.dumps(ab_core_metrics, ensure_ascii=True, separators=(",", ":")),
                "comparison_input_json": json.dumps(
                    model_comparison.comparison_input.to_dict(),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                "ab_comparison_json": json.dumps(ab_comparison.to_dict(), ensure_ascii=True, separators=(",", ":")),
                "model_comparison_record_json": json.dumps(
                    model_comparison.to_record(),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                "privacy_filtered_features_json": json.dumps(privacy_features, ensure_ascii=True, separators=(",", ":")),
            }
        )

    summary_metrics = _summary_metrics(customer_rows)
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source_artifacts": evaluation_input["source_artifacts"],
        "selected_scenario": dict(evaluation_input.get("selected_scenario", {})),
        "selected_policy": {
            "candidate_id": policy_candidate.candidate_id,
            "weights": policy_candidate.weights,
            "thresholds": policy_candidate.thresholds,
            "source_rank": selected_policy.get("rank"),
        },
        "summary_metrics": summary_metrics,
        "evaluation_reason_codes": _evaluation_reason_codes(summary_metrics),
        "comparison_dataset": comparison_dataset_payload,
        "comparison_summary": comparison_dataset_payload["comparison_summary"],
        "hybrid_case_results": _hybrid_case_results(customer_snapshots),
        "customer_rows": customer_rows,
        "customer_snapshots": customer_snapshots,
    }
    validate_evaluation_result(result)
    return result


def write_ab_results_csv(result: dict[str, Any], output_path: str | Path = DEFAULT_OUTPUT) -> None:
    write_csv(Path(output_path), result["customer_rows"])


def write_evaluation_view_model(result: dict[str, Any], output_path: str | Path = DEFAULT_VIEW_MODEL_OUTPUT) -> None:
    write_structured_json(result, output_path)


def validate_evaluation_result(result: dict[str, Any]) -> None:
    validate_evaluation_view_model(result, expected_schema_version=SCHEMA_VERSION)


def _select_policy_candidate(candidate_rules: dict[str, Any], selected_candidate_id: str | None) -> dict[str, Any]:
    if not selected_candidate_id:
        return dict(candidate_rules["selected_candidate"])
    for candidate in candidate_rules.get("ranked_candidates", ()):
        if str(candidate.get("candidate_id")) == str(selected_candidate_id):
            return dict(candidate)
    raise ValueError(f"selected policy candidate not found: {selected_candidate_id}")


def _selected_scenario_state(
    scenario_config: dict[str, Any],
    *,
    scenario_input: Path,
    selected_scenario_id: str | None,
) -> dict[str, Any]:
    scenario_id = str(
        scenario_config.get("scenario_id")
        or f"scenario_seed_{scenario_config.get('simulation_seed', 'unknown')}_baseline60_recent30"
    )
    if selected_scenario_id and str(selected_scenario_id) != scenario_id:
        raise ValueError(f"selected scenario not found: {selected_scenario_id}")
    return {
        "schema_version": "senior-safe-mileage-selected-scenario-state/v1",
        "scenario_id": scenario_id,
        "source_artifact": _relative_project_path(scenario_input),
        "simulation_seed": scenario_config.get("simulation_seed"),
        "customer_count": int(scenario_config.get("customer_count", 0)),
        "customer_count_per_persona": int(scenario_config.get("customer_count_per_persona", 0)),
        "observation_period": dict(scenario_config.get("observation_period", {})),
    }


def _summary_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_rows = [row for row in rows if bool(row["risk_change_target"])]
    non_target_rows = [row for row in rows if not bool(row["risk_change_target"])]
    baseline_capture_count = sum(1 for row in target_rows if bool(row["baseline_detected"]))
    proposed_capture_count = sum(1 for row in target_rows if bool(row["proposed_detected"]))
    false_positive_rows = [row for row in non_target_rows if bool(row["proposed_detected"])]
    false_positive_count = len(false_positive_rows)
    false_positive_limit = 3
    false_negative_count = len(target_rows) - proposed_capture_count
    false_negative_rows = [row for row in target_rows if not bool(row["proposed_detected"])]
    misclassification_rows = false_positive_rows + false_negative_rows
    misclassification_count = len(misclassification_rows)
    misclassification_limit = 4
    proposed_hybrid_pass_count = sum(1 for row in rows if bool(row["proposed_hybrid_evaluation_passed"]))
    proposed_hybrid_fail_count = len(rows) - proposed_hybrid_pass_count
    pass_rate = round(proposed_hybrid_pass_count / max(1, len(rows)), 4)
    misclassification_check = {
        "schema_version": "senior-safe-mileage-misclassification-check/v1",
        "customer_count": len(rows),
        "limit": misclassification_limit,
        "count": misclassification_count,
        "passed": misclassification_count <= misclassification_limit,
        "false_positive_count": false_positive_count,
        "false_negative_count": false_negative_count,
        "misclassified_customer_ids": [
            str(row["customer_id"])
            for row in misclassification_rows
        ],
        "rule": "false positives among 25 non-targets plus false negatives among five targets must be <= 4",
    }
    return {
        "customer_count": len(rows),
        "risk_change_target_count": len(target_rows),
        "non_target_count": len(non_target_rows),
        "baseline_capture_count": baseline_capture_count,
        "proposed_capture_count": proposed_capture_count,
        "baseline_low_mileage_high_risk_capture": round(baseline_capture_count / max(1, len(target_rows)), 4),
        "proposed_low_mileage_high_risk_capture": round(proposed_capture_count / max(1, len(target_rows)), 4),
        "non_target_false_positive_count": false_positive_count,
        "non_target_false_positive_limit": false_positive_limit,
        "non_target_false_positive_customer_ids": [
            str(row["customer_id"])
            for row in false_positive_rows
        ],
        "passes_non_target_false_positive_gate": false_positive_count <= false_positive_limit,
        "false_negative_count": false_negative_count,
        "total_misclassification_count": misclassification_count,
        "total_misclassification_limit": misclassification_limit,
        "misclassified_customer_ids": list(misclassification_check["misclassified_customer_ids"]),
        "passes_misclassification_check": bool(misclassification_check["passed"]),
        "misclassification_check": misclassification_check,
        "hybrid_pass_fail_threshold": HYBRID_PASS_THRESHOLD,
        "proposed_hybrid_pass_count": proposed_hybrid_pass_count,
        "proposed_hybrid_fail_count": proposed_hybrid_fail_count,
        "proposed_hybrid_pass_rate": pass_rate,
        "agent_validation_pass_rate": pass_rate,
        "passes_approval_gate": (
            proposed_capture_count >= 4
            and false_positive_count <= false_positive_limit
            and bool(misclassification_check["passed"])
            and pass_rate >= 0.95
        ),
    }


def _hybrid_case_results(customer_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one display-ready hybrid evaluation case for each persona."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for snapshot in customer_snapshots:
        grouped.setdefault(str(snapshot["persona_type"]), []).append(snapshot)

    cases: list[dict[str, Any]] = []
    for index, persona_type in enumerate(sorted(grouped), start=1):
        rows = sorted(grouped[persona_type], key=lambda row: str(row["customer_id"]))
        representative = _representative_hybrid_case(rows)
        proposed_rows = [dict(row["hybrid_evaluation"]["proposed"]) for row in rows]
        baseline_rows = [dict(row["hybrid_evaluation"]["baseline"]) for row in rows]
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
                "rationale": _hybrid_case_rationale(representative),
            }
        )
    return cases


def _representative_hybrid_case(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [
        row for row in rows
        if not bool(row["hybrid_evaluation"]["proposed"]["passed"])
    ]
    if failed:
        return failed[0]
    targets = [
        row for row in rows
        if bool(row["ab_comparison"]["metrics"]["risk_change_target"])
    ]
    return (targets or rows)[0]


def _hybrid_case_model_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pass_count = sum(1 for row in rows if bool(row["passed"]))
    scores = [float(row["score"]) for row in rows]
    representative = rows[0]
    return {
        "pass_count": pass_count,
        "fail_count": len(rows) - pass_count,
        "pass_rate": round(pass_count / max(1, len(rows)), 4),
        "average_score": round(sum(scores) / max(1, len(scores)), 2),
        "verdict": "pass" if pass_count == len(rows) else "review",
        "pass_threshold": float(representative["pass_threshold"]),
        "pass_fail_rule_id": str(representative["pass_fail_rule_id"]),
    }


def _hybrid_case_rationale(representative: dict[str, Any]) -> str:
    proposed = dict(representative["hybrid_evaluation"]["proposed"])
    decision = "포착" if proposed["decision_detected"] else "미포착"
    ground_truth = "target" if proposed["ground_truth_target"] else "non-target"
    proxy_label = "target" if proposed["proxy_label_target"] else "non-target"
    return (
        f"representative={representative['customer_id']}, decision={decision}, "
        f"ground_truth={ground_truth}, proxy_label={proxy_label}, "
        f"score={float(proposed['score']):.1f}/{float(proposed['pass_threshold']):.1f}"
    )


def _senior_score(feature: Any, weights: dict[str, float]) -> float:
    score = (
        feature.mileage_baseline_score * weights["w_mileage"]
        + feature.in_zone_safe_score * weights["w_in_zone"]
        + feature.out_zone_safe_score * weights["w_out_zone_safe"]
        + (100.0 - feature.risk_change_score) * weights["w_out_zone_change"]
    )
    return round(_clamp(score), 2)


def _care_decision(proposed_detected: bool, tier: str, risk_change_score: float) -> str:
    if proposed_detected:
        return "예방 케어"
    if tier in {"S", "A"} and risk_change_score < 35:
        return "우대"
    return "기본"


def _reason_codes(
    feature: Any,
    proposed_detected: bool,
    tier: str,
    living_zone: dict[str, Any] | None = None,
) -> list[str]:
    codes = ["LOW_MILEAGE_BASELINE_ELIGIBLE"]

    living_zone = living_zone or {}
    zone_mix = living_zone.get("recent_zone_mix") if isinstance(living_zone.get("recent_zone_mix"), dict) else {}
    recent_in_zone_ratio = float(zone_mix.get("in_zone_ratio", feature.recent_in_zone_ratio))
    recent_out_zone_ratio = float(zone_mix.get("out_zone_ratio", feature.recent_out_zone_ratio))
    zone_stability_score = living_zone.get("zone_stability_score")
    route_repeat_ratio = living_zone.get("route_repeat_ratio")
    new_destination_count = living_zone.get("new_destination_count")

    if living_zone.get("source") == "saved_customer_living_zone_record":
        codes.append("LIVING_ZONE_DBSCAN_P90_INPUT_USED")
    if recent_in_zone_ratio >= 0.7:
        codes.append("LIVING_ZONE_STABLE_DRIVING")
    if zone_stability_score is not None and float(zone_stability_score) >= 70.0:
        codes.append("LIVING_ZONE_HIGH_STABILITY")
    if route_repeat_ratio is not None and float(route_repeat_ratio) >= 0.6:
        codes.append("REPEATED_ROUTE_PATTERN")
    if new_destination_count is not None and int(new_destination_count) >= 2 and recent_out_zone_ratio >= 0.25:
        codes.append("NEW_DESTINATION_OUT_ZONE_SIGNAL")

    if feature.risk_change_score >= 60:
        codes.append("OUT_ZONE_PATTERN_CHANGE_RISK")
    elif feature.risk_change_score >= 35:
        codes.append("BORDERLINE_PATTERN_CHANGE_MONITORED")
    else:
        codes.append("NO_STRONG_RISK_CHANGE")
    if feature.recent_night_ratio > feature.baseline_night_ratio + 0.1:
        codes.append("RECENT_NIGHT_DRIVING_INCREASE")
    if feature.risk_rate_delta_per_100km > 2.0:
        codes.append("RISK_EVENT_RATE_INCREASE")
    if proposed_detected:
        codes.append("PROPOSED_MODEL_PREVENTIVE_CARE")
    elif tier in {"S", "A"}:
        codes.append("PROPOSED_MODEL_FAVORABLE_OR_STANDARD")
    return codes


def _living_zone_summary(feature: Any, living_zone_store: dict[str, Any] | None = None) -> dict[str, Any]:
    if living_zone_store:
        summary = living_zone_decision_summary(feature.customer_id, store=living_zone_store)
        summary["baseline_out_zone_ratio"] = feature.baseline_out_zone_ratio
        summary["out_zone_ratio_delta"] = feature.out_zone_ratio_delta
        return summary
    return {
        "source": "derived_customer_policy_feature",
        "method": "synthetic_dbscan_p90_summary",
        "baseline_out_zone_ratio": feature.baseline_out_zone_ratio,
        "recent_out_zone_ratio": feature.recent_out_zone_ratio,
        "recent_in_zone_ratio": feature.recent_in_zone_ratio,
        "out_zone_ratio_delta": feature.out_zone_ratio_delta,
        "zone_labels": ["core", "buffer", "outer"],
    }


def _privacy_filtered_features(feature: Any, senior_score: float, care_decision: str, reason_codes: tuple[str, ...]) -> dict[str, Any]:
    return {
        "persona_type": feature.persona_type,
        "baseline_total_km": feature.baseline_total_km,
        "recent_total_km": feature.recent_total_km,
        "annualized_recent_km": feature.annualized_recent_km,
        "recent_trip_count": feature.recent_trip_count,
        "recent_in_zone_ratio": feature.recent_in_zone_ratio,
        "recent_out_zone_ratio": feature.recent_out_zone_ratio,
        "out_zone_ratio_delta": feature.out_zone_ratio_delta,
        "night_ratio_delta": feature.night_ratio_delta,
        "risk_rate_delta_per_100km": feature.risk_rate_delta_per_100km,
        "recent_in_zone_km": feature.recent_in_zone_km,
        "recent_in_zone_trip_count": feature.recent_in_zone_trip_count,
        "recent_in_zone_night_ratio": feature.recent_in_zone_night_ratio,
        "recent_in_zone_risk_rate_per_100km": feature.recent_in_zone_risk_rate_per_100km,
        "recent_out_zone_km": feature.recent_out_zone_km,
        "recent_out_zone_trip_count": feature.recent_out_zone_trip_count,
        "recent_out_zone_night_ratio": feature.recent_out_zone_night_ratio,
        "recent_out_zone_risk_rate_per_100km": feature.recent_out_zone_risk_rate_per_100km,
        "out_zone_safe_score": feature.out_zone_safe_score,
        "mileage_baseline_score": feature.mileage_baseline_score,
        "risk_change_score": feature.risk_change_score,
        "senior_safe_mileage_score": senior_score,
        "care_decision": care_decision,
        "reason_codes": list(reason_codes),
    }


def _proxy_label_summary(feature: Any) -> dict[str, Any]:
    label = derive_risk_change_proxy_label(feature)
    return label.to_dict()


def _evaluation_reason_codes(metrics: dict[str, Any]) -> list[str]:
    codes = ["AB_EVALUATION_COMPLETED", "CUSTOMER_SNAPSHOTS_READY_FOR_UI"]
    if metrics["proposed_low_mileage_high_risk_capture"] > metrics["baseline_low_mileage_high_risk_capture"]:
        codes.append("PROPOSED_MODEL_OUTPERFORMS_DISTANCE_BASELINE")
    if metrics["passes_approval_gate"]:
        codes.append("APPROVAL_GATE_EVALUATION_PASSED")
    return codes


def _tier(score: float, tier_threshold: dict[str, int | float]) -> str:
    if score >= float(tier_threshold["S"]):
        return "S"
    if score >= float(tier_threshold["A"]):
        return "A"
    if score >= float(tier_threshold["B"]):
        return "B"
    return "C"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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
    parser = argparse.ArgumentParser(description="Evaluate Senior Safe Mileage policy A/B results.")
    parser.add_argument("--candidate-rules", default=str(DEFAULT_CANDIDATE_RULES_INPUT), help="Candidate rules JSON input path")
    parser.add_argument("--trips", default=str(DEFAULT_TRIP_INPUT), help="Synthetic trip CSV input path")
    parser.add_argument("--scenario", default=str(DEFAULT_SCENARIO_INPUT), help="Scenario config JSON input path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="A/B CSV output path")
    parser.add_argument("--view-model-output", default=str(DEFAULT_VIEW_MODEL_OUTPUT), help="UI JSON output path")
    args = parser.parse_args(argv)

    result = EvaluationAgent().run(
        AgentInputPayload(
            run_id="evaluation-cli",
            agent_id="evaluation_agent",
            parameters={
                "candidate_rules_input": args.candidate_rules,
                "trip_input": args.trips,
                "scenario_input": args.scenario,
                "output_path": args.output,
                "view_model_output_path": args.view_model_output,
            },
        )
    )
    if result.status != AgentStatus.SUCCEEDED:
        for error in result.errors:
            print(error)
        return 1
    assert result.output_payload is not None
    print(f"ab results: {args.output}")
    print(f"evaluation view model: {args.view_model_output}")
    print(result.output_payload.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

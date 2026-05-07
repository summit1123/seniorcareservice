"""Policy Search Agent for Senior Safe Mileage candidate rules."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, replace
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
    PolicyCandidate,
    utc_now_iso,
)
from src.product.ab_comparison import compare_customer_models
from src.product.proxy_labels import derive_risk_change_proxy_label, load_ground_truth_labels
from src.product.scoring_engine import (
    SeniorSafeMileageScoreInput,
    calculate_in_zone_safe_score,
    calculate_mileage_baseline_score,
    calculate_out_zone_safe_score,
    calculate_risk_change_score,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRIP_INPUT = ROOT / "data" / "fixtures" / "senior_trip_logs.csv"
DEFAULT_SCENARIO_INPUT = ROOT / "data" / "fixtures" / "scenario_config.json"
DEFAULT_VALIDATION_REPORT_INPUT = ROOT / "data" / "fixtures" / "validation_report.md"
DEFAULT_OUTPUT = ROOT / "data" / "fixtures" / "candidate_rules.json"
DEFAULT_CANDIDATE_SCORES_OUTPUT = ROOT / "data" / "fixtures" / "policy_candidate_scores.csv"
SCHEMA_VERSION = "senior-policy-candidate-rules/v1"
POLICY_CANDIDATE_SCHEMA_VERSION = f"{SCHEMA_VERSION}/candidate"
WEIGHT_KEYS = ("w_mileage", "w_in_zone", "w_out_zone_safe", "w_out_zone_change")

DEFAULT_WEIGHT_GRID = {
    "w_mileage": (0.30, 0.35, 0.40),
    "w_in_zone": (0.30, 0.35, 0.40),
    "w_out_zone_safe": (0.10, 0.15, 0.20),
    "w_out_zone_change": (0.10, 0.15, 0.20),
}
DEFAULT_CARE_PERCENTILES = (0.20, 0.15, 0.10)
DEFAULT_TIER_THRESHOLDS = (
    {"S": 85, "A": 75, "B": 65, "C": 0},
    {"S": 88, "A": 78, "B": 68, "C": 0},
)
DEFAULT_OBJECTIVE_CONSTRAINTS = {
    "risk_change_target_min_capture": 4,
    "non_target_false_positive_max": 3,
    "total_misclassification_max": 4,
    "agent_validation_pass_rate_minimum": 0.95,
}


@dataclass(frozen=True)
class CustomerPolicyFeature:
    customer_id: str
    persona_type: str
    expected_care_decision: str
    risk_change_target: bool
    baseline_total_km: float
    recent_total_km: float
    annualized_recent_km: float
    recent_trip_count: int
    recent_in_zone_ratio: float
    recent_out_zone_ratio: float
    baseline_out_zone_ratio: float
    out_zone_ratio_delta: float
    baseline_night_ratio: float
    recent_night_ratio: float
    night_ratio_delta: float
    baseline_risk_rate_per_100km: float
    recent_risk_rate_per_100km: float
    risk_rate_delta_per_100km: float
    recent_risk_signal_count: int
    recent_in_zone_km: float
    recent_in_zone_trip_count: int
    recent_in_zone_night_ratio: float
    recent_in_zone_risk_rate_per_100km: float
    recent_out_zone_km: float
    recent_out_zone_trip_count: int
    recent_out_zone_night_ratio: float
    recent_out_zone_risk_rate_per_100km: float
    proxy_label_rule_id: str = ""
    proxy_label_reason_codes: tuple[str, ...] = ()
    proxy_label_thresholds: dict[str, float | int] | None = None

    @property
    def mileage_baseline_score(self) -> float:
        return calculate_mileage_baseline_score(self.annualized_recent_km)

    @property
    def in_zone_safe_score(self) -> float:
        return calculate_in_zone_safe_score(self._score_input())

    @property
    def out_zone_safe_score(self) -> float:
        return calculate_out_zone_safe_score(self._score_input())

    @property
    def risk_change_score(self) -> float:
        return calculate_risk_change_score(self._score_input())

    def _score_input(self) -> SeniorSafeMileageScoreInput:
        return SeniorSafeMileageScoreInput(
            annualized_recent_km=self.annualized_recent_km,
            recent_trip_count=self.recent_trip_count,
            recent_in_zone_ratio=self.recent_in_zone_ratio,
            recent_out_zone_ratio=self.recent_out_zone_ratio,
            out_zone_ratio_delta=self.out_zone_ratio_delta,
            baseline_night_ratio=self.baseline_night_ratio,
            recent_night_ratio=self.recent_night_ratio,
            night_ratio_delta=self.night_ratio_delta,
            baseline_risk_rate_per_100km=self.baseline_risk_rate_per_100km,
            recent_risk_rate_per_100km=self.recent_risk_rate_per_100km,
            risk_rate_delta_per_100km=self.risk_rate_delta_per_100km,
            recent_risk_signal_count=self.recent_risk_signal_count,
            recent_in_zone_km=self.recent_in_zone_km,
            recent_in_zone_night_ratio=self.recent_in_zone_night_ratio,
            recent_in_zone_risk_rate_per_100km=self.recent_in_zone_risk_rate_per_100km,
            recent_out_zone_km=self.recent_out_zone_km,
            recent_out_zone_night_ratio=self.recent_out_zone_night_ratio,
            recent_out_zone_risk_rate_per_100km=self.recent_out_zone_risk_rate_per_100km,
        )

    def public_summary(self) -> dict[str, Any]:
        return {
            "persona_type": self.persona_type,
            "expected_care_decision": self.expected_care_decision,
            "risk_change_target": self.risk_change_target,
            "annualized_recent_km": round(self.annualized_recent_km, 2),
            "recent_trip_count": self.recent_trip_count,
            "recent_in_zone_ratio": round(self.recent_in_zone_ratio, 4),
            "recent_out_zone_ratio": round(self.recent_out_zone_ratio, 4),
            "out_zone_ratio_delta": round(self.out_zone_ratio_delta, 4),
            "night_ratio_delta": round(self.night_ratio_delta, 4),
            "risk_rate_delta_per_100km": round(self.risk_rate_delta_per_100km, 4),
            "recent_in_zone_km": round(self.recent_in_zone_km, 2),
            "recent_in_zone_trip_count": self.recent_in_zone_trip_count,
            "recent_in_zone_night_ratio": round(self.recent_in_zone_night_ratio, 4),
            "recent_in_zone_risk_rate_per_100km": round(self.recent_in_zone_risk_rate_per_100km, 4),
            "recent_out_zone_km": round(self.recent_out_zone_km, 2),
            "recent_out_zone_trip_count": self.recent_out_zone_trip_count,
            "recent_out_zone_night_ratio": round(self.recent_out_zone_night_ratio, 4),
            "recent_out_zone_risk_rate_per_100km": round(self.recent_out_zone_risk_rate_per_100km, 4),
            "mileage_baseline_score": self.mileage_baseline_score,
            "in_zone_safe_score": self.in_zone_safe_score,
            "out_zone_safe_score": self.out_zone_safe_score,
            "risk_change_score": self.risk_change_score,
            "proxy_label": {
                "rule_id": self.proxy_label_rule_id,
                "risk_change_target": self.risk_change_target,
                "reason_codes": list(self.proxy_label_reason_codes),
                "thresholds": self.proxy_label_thresholds or {},
            },
        }


class PolicySearchAgent:
    """Search Senior Safe Mileage rule candidates over a structured local grid."""

    metadata = AgentMetadata(
        agent_id="policy_search_agent",
        role=AgentRole.POLICY_SEARCH,
        display_name="Policy Search Agent",
        description="Proposes Senior Safe Mileage Score weights and thresholds.",
        consumes=("validation_report.md", "model_feature_table.csv"),
        produces=("candidate_rules.json", "policy_candidate_scores.csv"),
    )

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            trip_input = _resolve_artifact_path(payload, "senior_trip_logs.csv", "trip_input", DEFAULT_TRIP_INPUT)
            scenario_input = _resolve_artifact_path(payload, "scenario_config.json", "scenario_input", DEFAULT_SCENARIO_INPUT)
            validation_report_input = _resolve_artifact_path(
                payload,
                "validation_report.md",
                "validation_report_input",
                DEFAULT_VALIDATION_REPORT_INPUT,
            )
            output_path = Path(str(payload.parameters.get("output_path", DEFAULT_OUTPUT)))
            candidate_scores_output_path = Path(
                str(payload.parameters.get("candidate_scores_output_path", DEFAULT_CANDIDATE_SCORES_OUTPUT))
            )

            search_input = build_search_input(
                payload.parameters,
                trip_input=trip_input,
                scenario_input=scenario_input,
                validation_report_input=validation_report_input,
            )
            result = self.search(search_input)
            self.write_candidate_rules(result, output_path)
            self.write_candidate_scores(result, candidate_scores_output_path)

            selected = result["selected_candidate"]
            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="candidate_rules.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_project_path(output_path),
                        rows=len(result["ranked_candidates"]),
                        summary={
                            "schema_version": SCHEMA_VERSION,
                            "candidate_count": len(result["ranked_candidates"]),
                            "selected_candidate_id": selected["candidate_id"],
                            "selected_rank": selected["rank"],
                            "structured_candidate_fields": ["candidate_id", "weights", "thresholds", "scores", "metadata"],
                            "passes_approval_gate": selected["metrics"]["passes_approval_gate"],
                        },
                    ),
                    AgentArtifact(
                        artifact_id="policy_candidate_scores.csv",
                        artifact_type=ArtifactType.CSV,
                        path=_relative_project_path(candidate_scores_output_path),
                        rows=result["candidate_score_summary"]["score_row_count"],
                        summary={
                            "schema_version": f"{SCHEMA_VERSION}/candidate-scores",
                            "candidate_count": len(result["ranked_candidates"]),
                            "customers_per_candidate": result["candidate_score_summary"]["customers_per_candidate"],
                        },
                    ),
                ),
                metrics={
                    "weight_candidate_count": result["search_input"]["weight_candidate_summary"]["generated_candidate_count"],
                    "candidate_count": len(result["ranked_candidates"]),
                    "passing_candidate_count": sum(
                        1 for candidate in result["ranked_candidates"] if candidate["metrics"]["passes_approval_gate"]
                    ),
                    "selected_capture_count": selected["metrics"]["risk_change_target_capture_count"],
                    "selected_false_positive_count": selected["metrics"]["non_target_false_positive_count"],
                    "selected_misclassification_count": selected["metrics"]["total_misclassification_count"],
                    "passes_approval_gate": selected["metrics"]["passes_approval_gate"],
                },
                decisions={
                    "selected_candidate_id": selected["candidate_id"],
                    "selected_weights": selected["weights"],
                    "selected_thresholds": selected["thresholds"],
                    "selected_scores": selected["scores"],
                    "selected_metadata": selected["metadata"],
                    "ranked_candidate_ids": [candidate["candidate_id"] for candidate in result["ranked_candidates"]],
                    "ranked_candidate_summaries": [
                        structured_policy_candidate_summary(candidate)
                        for candidate in result["ranked_candidates"]
                    ],
                },
                reason_codes=tuple(selected["reason_metadata"]["selected_reason_codes"]),
                validation={
                    "passed": bool(selected["metrics"]["passes_approval_gate"]),
                    "schema_version": SCHEMA_VERSION,
                    "privacy_checked": True,
                    "forbidden_external_api_fields_present": [],
                    "objective_constraints": result["search_input"]["objective_constraints"],
                },
                messages=("policy candidates generated, ranked, and validated",),
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

    def search(self, search_input: dict[str, Any]) -> dict[str, Any]:
        features = build_customer_features(
            _project_path(search_input["source_artifacts"]["trip_input"]),
            _project_path(search_input["source_artifacts"]["scenario_input"]),
        )
        threshold_candidates = generate_threshold_candidates(
            features,
            search_input["care_threshold_percentiles"],
            search_input["tier_thresholds"],
        )
        search_input = {
            **search_input,
            "threshold_candidates": threshold_candidates,
            "threshold_candidate_summary": summarize_threshold_candidates(threshold_candidates),
        }
        candidates = []
        for weights in iter_weight_candidates(search_input["weight_grid"]):
            for threshold_candidate in threshold_candidates:
                candidates.append(evaluate_candidate(features, weights, threshold_candidate))

        ranked_candidates = sorted(
            candidates,
            key=lambda candidate: (
                not candidate["metrics"]["passes_approval_gate"],
                -candidate["metrics"]["ranking_score"],
                candidate["metrics"]["non_target_false_positive_count"],
                candidate["thresholds"]["care_threshold_percentile"],
                candidate["candidate_id"],
            ),
        )
        for rank, candidate in enumerate(ranked_candidates, start=1):
            candidate["rank"] = rank
            candidate["metadata"]["rank"] = rank

        selected = ranked_candidates[0]
        result = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now_iso(),
            "search_input": search_input,
            "selected_candidate_id": selected["candidate_id"],
            "selected_candidate": selected,
            "ranked_candidates": ranked_candidates,
            "candidate_score_summary": summarize_policy_candidate_scores(ranked_candidates),
            "customer_feature_summaries": [feature.public_summary() for feature in features],
        }
        validate_policy_result(result)
        return result

    def write_candidate_rules(self, result: dict[str, Any], output_path: str | Path = DEFAULT_OUTPUT) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def write_candidate_scores(
        self,
        result: dict[str, Any],
        output_path: str | Path = DEFAULT_CANDIDATE_SCORES_OUTPUT,
    ) -> None:
        write_candidate_scores_csv(result, output_path)


def build_search_input(
    parameters: dict[str, Any] | None = None,
    *,
    trip_input: Path = DEFAULT_TRIP_INPUT,
    scenario_input: Path = DEFAULT_SCENARIO_INPUT,
    validation_report_input: Path = DEFAULT_VALIDATION_REPORT_INPUT,
) -> dict[str, Any]:
    parameters = parameters or {}
    weight_grid = parameters.get("weight_grid", DEFAULT_WEIGHT_GRID)
    care_threshold_percentiles = parameters.get("care_threshold_percentiles", DEFAULT_CARE_PERCENTILES)
    tier_thresholds = parameters.get("tier_thresholds", DEFAULT_TIER_THRESHOLDS)
    objective_constraints = {**DEFAULT_OBJECTIVE_CONSTRAINTS, **parameters.get("objective_constraints", {})}
    weight_grid = {key: [float(value) for value in values] for key, values in weight_grid.items()}
    weight_candidates = iter_weight_candidates(weight_grid)
    search_input = {
        "schema_version": f"{SCHEMA_VERSION}/search-input",
        "source_artifacts": {
            "trip_input": _relative_project_path(trip_input),
            "scenario_input": _relative_project_path(scenario_input),
            "validation_report_input": _relative_project_path(validation_report_input),
        },
        "weight_grid": weight_grid,
        "weight_candidate_summary": {
            "generated_candidate_count": len(weight_candidates),
            "weight_keys": list(WEIGHT_KEYS),
            "constraints": {
                "sum_equals": 1.0,
                "sum_tolerance": 0.0001,
                "source": "FINAL_PRODUCT_DIRECTION.md#10",
            },
        },
        "care_threshold_percentiles": [float(value) for value in care_threshold_percentiles],
        "tier_thresholds": tier_thresholds,
        "objective_constraints": objective_constraints,
        "ranking_objective": (
            "maximize recent_outer_risk_change capture, minimize non-target false positives, "
            "and keep stable low-mileage drivers favorable"
        ),
    }
    validate_search_input(search_input)
    return search_input


def generate_threshold_candidates(
    features: list[CustomerPolicyFeature],
    care_threshold_percentiles: list[float] | tuple[float, ...],
    tier_thresholds: list[dict[str, int | float]] | tuple[dict[str, int | float], ...],
) -> list[dict[str, Any]]:
    """Build explicit threshold candidates before policy scoring/ranking."""
    if not features:
        raise ValueError("threshold candidate generation requires customer features")
    risk_scores = sorted((feature.risk_change_score for feature in features), reverse=True)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for care_percentile in care_threshold_percentiles:
        percentile = float(care_percentile)
        cutoff_index = max(0, min(len(risk_scores) - 1, int(len(risk_scores) * percentile) - 1))
        care_threshold_score = round(risk_scores[cutoff_index], 2)
        expected_top_n = cutoff_index + 1
        for tier_threshold in tier_thresholds:
            normalized_tier = _normalize_tier_threshold(tier_threshold)
            threshold_id = _threshold_candidate_id(percentile, normalized_tier)
            if threshold_id in seen:
                continue
            seen.add(threshold_id)
            candidates.append(
                {
                    "threshold_candidate_id": threshold_id,
                    "care_threshold": care_threshold_score,
                    "care_threshold_percentile": percentile,
                    "care_threshold_source": "risk_change_score_top_percentile",
                    "care_threshold_expected_top_n": expected_top_n,
                    "tier_threshold": normalized_tier,
                    "rationale": (
                        "care threshold is generated from the synthetic 30-customer risk-change score "
                        "distribution; tier thresholds come from FINAL_PRODUCT_DIRECTION.md#10 S/A/B/C bands"
                    ),
                }
            )
    if not candidates:
        raise ValueError("threshold grids produced no threshold candidates")
    return candidates


def summarize_threshold_candidates(threshold_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    percentiles = sorted({float(candidate["care_threshold_percentile"]) for candidate in threshold_candidates})
    care_thresholds = sorted({float(candidate["care_threshold"]) for candidate in threshold_candidates}, reverse=True)
    tier_threshold_count = len(
        {
            json.dumps(candidate["tier_threshold"], sort_keys=True, separators=(",", ":"))
            for candidate in threshold_candidates
        }
    )
    return {
        "generated_candidate_count": len(threshold_candidates),
        "care_threshold_percentiles": percentiles,
        "care_threshold_values": care_thresholds,
        "tier_threshold_candidate_count": tier_threshold_count,
        "constraints": {
            "care_threshold_source": "risk_change_score_top_percentile",
            "tier_threshold_source": "FINAL_PRODUCT_DIRECTION.md#10",
        },
    }


def build_customer_features(trip_input: Path, scenario_input: Path) -> list[CustomerPolicyFeature]:
    rows = _read_csv(trip_input)
    scenario_by_customer = _load_scenario_by_customer(scenario_input)
    ground_truth_by_customer = load_ground_truth_labels(scenario_input)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["customer_id"], []).append(row)

    features = []
    for customer_id, customer_rows in sorted(grouped.items()):
        scenario = scenario_by_customer[customer_id]
        ground_truth = ground_truth_by_customer[customer_id]
        baseline = [row for row in customer_rows if row["observation_period"] == "baseline"]
        recent = [row for row in customer_rows if row["observation_period"] == "recent"]
        if not baseline or not recent:
            raise ValueError(f"{customer_id} must have both baseline and recent trips")

        baseline_total_km = _sum_float(baseline, "trip_distance_km")
        recent_total_km = _sum_float(recent, "trip_distance_km")
        baseline_risk_rate = _risk_event_rate_per_100km(baseline, baseline_total_km)
        recent_risk_rate = _risk_event_rate_per_100km(recent, recent_total_km)
        baseline_out_zone_ratio = _distance_ratio(baseline, "zone_label", {"outer"})
        recent_out_zone_ratio = _distance_ratio(recent, "zone_label", {"outer"})
        baseline_night_ratio = _distance_ratio(baseline, "night_drive_flag", {"1"})
        recent_night_ratio = _distance_ratio(recent, "night_drive_flag", {"1"})
        recent_in_zone = [row for row in recent if _is_in_zone_row(row)]
        recent_in_zone_km = _sum_float(recent_in_zone, "trip_distance_km") if recent_in_zone else 0.0
        recent_in_zone_night_ratio = _distance_ratio(recent_in_zone, "night_drive_flag", {"1"})
        recent_in_zone_risk_rate = _risk_event_rate_per_100km(recent_in_zone, recent_in_zone_km)
        recent_out_zone = [row for row in recent if _is_out_zone_row(row)]
        recent_out_zone_km = _sum_float(recent_out_zone, "trip_distance_km") if recent_out_zone else 0.0
        recent_out_zone_night_ratio = _distance_ratio(recent_out_zone, "night_drive_flag", {"1"})
        recent_out_zone_risk_rate = _risk_event_rate_per_100km(recent_out_zone, recent_out_zone_km)

        feature = CustomerPolicyFeature(
            customer_id=customer_id,
            persona_type=str(scenario["persona_type"]),
            expected_care_decision=ground_truth.expected_care_decision,
            risk_change_target=ground_truth.risk_change_target,
            baseline_total_km=round(baseline_total_km, 2),
            recent_total_km=round(recent_total_km, 2),
            annualized_recent_km=round(recent_total_km * 12.0, 2),
            recent_trip_count=len(recent),
            recent_in_zone_ratio=round(1.0 - recent_out_zone_ratio, 4),
            recent_out_zone_ratio=round(recent_out_zone_ratio, 4),
            baseline_out_zone_ratio=round(baseline_out_zone_ratio, 4),
            out_zone_ratio_delta=round(recent_out_zone_ratio - baseline_out_zone_ratio, 4),
            baseline_night_ratio=round(baseline_night_ratio, 4),
            recent_night_ratio=round(recent_night_ratio, 4),
            night_ratio_delta=round(recent_night_ratio - baseline_night_ratio, 4),
            baseline_risk_rate_per_100km=round(baseline_risk_rate, 4),
            recent_risk_rate_per_100km=round(recent_risk_rate, 4),
            risk_rate_delta_per_100km=round(recent_risk_rate - baseline_risk_rate, 4),
            recent_risk_signal_count=sum(_risk_signal_count(row) for row in recent),
            recent_in_zone_km=round(recent_in_zone_km, 2),
            recent_in_zone_trip_count=len(recent_in_zone),
            recent_in_zone_night_ratio=round(recent_in_zone_night_ratio, 4),
            recent_in_zone_risk_rate_per_100km=round(recent_in_zone_risk_rate, 4),
            recent_out_zone_km=round(recent_out_zone_km, 2),
            recent_out_zone_trip_count=len(recent_out_zone),
            recent_out_zone_night_ratio=round(recent_out_zone_night_ratio, 4),
            recent_out_zone_risk_rate_per_100km=round(recent_out_zone_risk_rate, 4),
        )
        proxy_label = derive_risk_change_proxy_label(feature)
        features.append(
            replace(
                feature,
                expected_care_decision=proxy_label.expected_care_decision
                if ground_truth.risk_change_target
                else ground_truth.expected_care_decision,
                risk_change_target=ground_truth.risk_change_target,
                proxy_label_rule_id=proxy_label.rule_id,
                proxy_label_reason_codes=proxy_label.reason_codes,
                proxy_label_thresholds=proxy_label.thresholds,
            )
        )
    if len(features) != 30:
        raise ValueError(f"policy search expects 30 customer summaries, got {len(features)}")
    return features


def iter_weight_candidates(weight_grid: dict[str, list[float]]) -> list[dict[str, float]]:
    missing = [key for key in WEIGHT_KEYS if key not in weight_grid]
    if missing:
        raise ValueError(f"weight_grid missing keys: {missing}")
    rows: list[dict[str, float]] = []
    for w_mileage in weight_grid["w_mileage"]:
        for w_in_zone in weight_grid["w_in_zone"]:
            for w_out_zone_safe in weight_grid["w_out_zone_safe"]:
                for w_out_zone_change in weight_grid["w_out_zone_change"]:
                    weights = {
                        "w_mileage": float(w_mileage),
                        "w_in_zone": float(w_in_zone),
                        "w_out_zone_safe": float(w_out_zone_safe),
                        "w_out_zone_change": float(w_out_zone_change),
                    }
                    if abs(sum(weights.values()) - 1.0) <= 0.0001:
                        rows.append(weights)
    if not rows:
        raise ValueError("weight_grid produced no candidates with weights summing to 1.0")
    return rows


def evaluate_candidate(
    features: list[CustomerPolicyFeature],
    weights: dict[str, float],
    threshold_candidate: dict[str, Any],
) -> dict[str, Any]:
    care_percentile = float(threshold_candidate["care_threshold_percentile"])
    care_threshold_score = float(threshold_candidate["care_threshold"])
    tier_threshold = dict(threshold_candidate["tier_threshold"])
    candidate_id = _candidate_id(weights, care_percentile, tier_threshold)

    scored_rows = []
    for feature in features:
        proxy_label = derive_risk_change_proxy_label(feature)
        model_comparison = compare_customer_models(
            feature,
            weights=weights,
            care_threshold=care_threshold_score,
            tier_threshold=tier_threshold,
            target_label=bool(feature.risk_change_target),
            proxy_target_label=bool(proxy_label.is_target),
        )
        scored_rows.append(
            {
                "customer_id": feature.customer_id,
                "persona_type": feature.persona_type,
                "risk_change_target": feature.risk_change_target,
                "expected_care_decision": feature.expected_care_decision,
                "proxy_label_is_target": bool(proxy_label.is_target),
                "mileage_baseline_score": model_comparison.baseline_score,
                "in_zone_safe_score": feature.in_zone_safe_score,
                "out_zone_safe_score": feature.out_zone_safe_score,
                "risk_change_score": feature.risk_change_score,
                "senior_safe_mileage_score": model_comparison.proposed_score,
                "baseline_detected": model_comparison.baseline_detected,
                "proposed_detected": model_comparison.proposed_detected,
                "tier": model_comparison.tier,
                "care_decision": model_comparison.care_decision,
            }
        )

    target_rows = [row for row in scored_rows if row["risk_change_target"]]
    non_target_rows = [row for row in scored_rows if not row["risk_change_target"]]
    false_positive_rows = [row for row in non_target_rows if row["proposed_detected"]]
    false_negative_rows = [row for row in target_rows if not row["proposed_detected"]]
    stable_low_rows = [row for row in scored_rows if row["persona_type"] == "stable_local_low_mileage"]
    favorable_rows = [row for row in scored_rows if row["tier"] in {"S", "A"} and not row["proposed_detected"]]
    persona_detection_counts = _persona_detection_counts(scored_rows)
    capture_count = len(target_rows) - len(false_negative_rows)
    false_positive_count = len(false_positive_rows)
    misclassification_count = false_positive_count + len(false_negative_rows)
    stable_driver_capture_rate = (
        sum(1 for row in stable_low_rows if row["tier"] in {"S", "A"} and not row["proposed_detected"]) / len(stable_low_rows)
        if stable_low_rows
        else 0.0
    )
    low_mileage_high_risk_capture = capture_count / len(target_rows) if target_rows else 0.0
    baseline_capture = sum(1 for row in target_rows if row["baseline_detected"]) / len(target_rows) if target_rows else 0.0
    care_target_rate = sum(1 for row in scored_rows if row["proposed_detected"]) / len(scored_rows)
    priority_or_favorable_rate = len(favorable_rows) / len(scored_rows)
    insurer_efficiency_score = _clamp(
        low_mileage_high_risk_capture * 65.0
        + stable_driver_capture_rate * 20.0
        + max(0.0, 1.0 - false_positive_count / max(1, len(non_target_rows))) * 15.0
    )
    passes_gate = capture_count >= 4 and false_positive_count <= 3 and misclassification_count <= 4
    ranking_score = round(
        insurer_efficiency_score
        + low_mileage_high_risk_capture * 25.0
        - false_positive_count * 3.0
        - abs(care_target_rate - 0.15) * 20.0,
        4,
    )

    score_summary = summarize_candidate_customer_scores(scored_rows)
    metrics = {
        "low_mileage_high_risk_capture": round(low_mileage_high_risk_capture, 4),
        "baseline_low_mileage_high_risk_capture": round(baseline_capture, 4),
        "risk_change_target_capture_count": capture_count,
        "non_target_false_positive_count": false_positive_count,
        "total_misclassification_count": misclassification_count,
        "stable_driver_capture_rate": round(stable_driver_capture_rate, 4),
        "care_target_rate": round(care_target_rate, 4),
        "priority_or_favorable_rate": round(priority_or_favorable_rate, 4),
        "insurer_efficiency_score": round(insurer_efficiency_score, 2),
        "ranking_score": ranking_score,
        "passes_approval_gate": passes_gate,
    }
    reason_metadata = {
        "selected_reason_codes": _candidate_reason_codes(passes_gate, low_mileage_high_risk_capture, false_positive_count),
        "strengths": _candidate_strengths(low_mileage_high_risk_capture, stable_driver_capture_rate, false_positive_count),
        "tradeoffs": _candidate_tradeoffs(care_target_rate, false_positive_count),
        "fairness_notes": [
            "stable_outer_safe drivers are evaluated by risk-change deltas, not outer-zone exposure alone",
            "stable low-mileage drivers are protected from preventive-care false positives",
        ],
        "persona_detection_counts": persona_detection_counts,
    }
    candidate = {
        "candidate_id": candidate_id,
        "rank": 0,
        "weights": weights,
        "thresholds": {
            "care_threshold": round(care_threshold_score, 2),
            "care_threshold_percentile": care_percentile,
            "threshold_candidate_id": threshold_candidate["threshold_candidate_id"],
            "care_threshold_source": threshold_candidate["care_threshold_source"],
            "care_threshold_expected_top_n": threshold_candidate["care_threshold_expected_top_n"],
            "tier_threshold": tier_threshold,
        },
        "scores": {
            "ranking_score": ranking_score,
            "insurer_efficiency_score": round(insurer_efficiency_score, 2),
            "low_mileage_high_risk_capture": round(low_mileage_high_risk_capture, 4),
            "baseline_low_mileage_high_risk_capture": round(baseline_capture, 4),
            "stable_driver_capture_rate": round(stable_driver_capture_rate, 4),
            "care_target_rate": round(care_target_rate, 4),
            "priority_or_favorable_rate": round(priority_or_favorable_rate, 4),
            "customer_score_summary": score_summary,
        },
        "metrics": metrics,
        "score_summary": score_summary,
        "customer_scores": scored_rows,
        "metadata": {
            "schema_version": POLICY_CANDIDATE_SCHEMA_VERSION,
            "rank": 0,
            "candidate_id": candidate_id,
            "threshold_candidate_id": threshold_candidate["threshold_candidate_id"],
            "weight_keys": list(WEIGHT_KEYS),
            "weight_sum": round(sum(float(value) for value in weights.values()), 4),
            "customer_count": len(scored_rows),
            "source": "Policy Search Agent structured candidate grid",
            "input_fixture_scope": "synthetic_30_customers_90_day_trip_logs",
            "privacy_scope": "local_fixture_customer_ids_only_no_external_api_payload",
            "rationale": "ranked by synthetic 30-customer capture, false-positive, and stability metrics",
        },
        "reason_metadata": reason_metadata,
    }
    PolicyCandidate(
        candidate_id=candidate["candidate_id"],
        weights=candidate["weights"],
        thresholds=candidate["thresholds"],
        rationale="ranked by synthetic 30-customer capture, false-positive, and stability metrics",
    ).validate()
    return candidate


def summarize_candidate_customer_scores(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not scored_rows:
        raise ValueError("candidate scoring requires at least one customer row")
    senior_scores = [float(row["senior_safe_mileage_score"]) for row in scored_rows]
    baseline_scores = [float(row["mileage_baseline_score"]) for row in scored_rows]
    return {
        "customer_count": len(scored_rows),
        "average_senior_safe_mileage_score": round(sum(senior_scores) / len(senior_scores), 2),
        "min_senior_safe_mileage_score": round(min(senior_scores), 2),
        "max_senior_safe_mileage_score": round(max(senior_scores), 2),
        "average_mileage_baseline_score": round(sum(baseline_scores) / len(baseline_scores), 2),
        "preventive_care_count": sum(1 for row in scored_rows if row["care_decision"] == "예방 케어"),
        "favorable_count": sum(1 for row in scored_rows if row["care_decision"] == "우대"),
        "standard_count": sum(1 for row in scored_rows if row["care_decision"] == "기본"),
        "tier_counts": {
            tier: sum(1 for row in scored_rows if row["tier"] == tier)
            for tier in ("S", "A", "B", "C")
        },
    }


def summarize_policy_candidate_scores(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("policy candidate score summary requires candidates")
    customers_per_candidate = len(candidates[0].get("customer_scores", []))
    score_row_count = sum(len(candidate.get("customer_scores", [])) for candidate in candidates)
    if customers_per_candidate <= 0:
        raise ValueError("each policy candidate must include customer_scores")
    incomplete = [
        candidate["candidate_id"]
        for candidate in candidates
        if len(candidate.get("customer_scores", [])) != customers_per_candidate
    ]
    if incomplete:
        raise ValueError(f"policy candidates have incomplete customer_scores: {incomplete[:3]}")
    return {
        "schema_version": f"{SCHEMA_VERSION}/candidate-scores",
        "candidate_count": len(candidates),
        "customers_per_candidate": customers_per_candidate,
        "score_row_count": score_row_count,
        "score_formula": (
            "senior_safe_mileage_score = mileage_baseline_score*w_mileage + "
            "in_zone_safe_score*w_in_zone + out_zone_safe_score*w_out_zone_safe + "
            "(100-risk_change_score)*w_out_zone_change"
        ),
    }


def structured_policy_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    validate_structured_policy_candidate(candidate)
    return {
        "candidate_id": candidate["candidate_id"],
        "rank": candidate["rank"],
        "weights": candidate["weights"],
        "thresholds": candidate["thresholds"],
        "scores": candidate["scores"],
        "metadata": candidate["metadata"],
    }


def iter_policy_candidate_score_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in result["ranked_candidates"]:
        thresholds = dict(candidate["thresholds"])
        weights = dict(candidate["weights"])
        for customer_score in candidate["customer_scores"]:
            rows.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "rank": candidate["rank"],
                    "threshold_candidate_id": thresholds["threshold_candidate_id"],
                    "care_threshold": thresholds["care_threshold"],
                    "care_threshold_percentile": thresholds["care_threshold_percentile"],
                    "tier_threshold_json": json.dumps(
                        thresholds["tier_threshold"],
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "w_mileage": weights["w_mileage"],
                    "w_in_zone": weights["w_in_zone"],
                    "w_out_zone_safe": weights["w_out_zone_safe"],
                    "w_out_zone_change": weights["w_out_zone_change"],
                    **customer_score,
                }
            )
    return rows


def write_candidate_scores_csv(result: dict[str, Any], output_path: str | Path) -> None:
    rows = iter_policy_candidate_score_rows(result)
    if not rows:
        raise ValueError("candidate score CSV requires at least one row")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validate_search_input(search_input: dict[str, Any]) -> None:
    for key in ("weight_grid", "care_threshold_percentiles", "tier_thresholds", "objective_constraints"):
        if key not in search_input:
            raise ValueError(f"search_input missing {key}")
    for percentile in search_input["care_threshold_percentiles"]:
        if percentile not in {0.20, 0.15, 0.10}:
            raise ValueError(f"unsupported care_threshold_percentile: {percentile}")
    iter_weight_candidates(search_input["weight_grid"])


def validate_policy_result(result: dict[str, Any]) -> None:
    candidates = result.get("ranked_candidates", [])
    if not candidates:
        raise ValueError("policy result must include ranked_candidates")
    for candidate in candidates:
        validate_structured_policy_candidate(candidate)
    if result["selected_candidate_id"] != candidates[0]["candidate_id"]:
        raise ValueError("selected_candidate_id must match top ranked candidate")
    summary = summarize_policy_candidate_scores(candidates)
    if result.get("candidate_score_summary", {}).get("score_row_count") != summary["score_row_count"]:
        raise ValueError("candidate_score_summary must match ranked candidate customer score rows")
    serialized = json.dumps(result, ensure_ascii=False).lower()
    forbidden_present = [field for field in FORBIDDEN_EXTERNAL_API_FIELDS if f'"{field.lower()}"' in serialized]
    allowed_local_fields = {"customer_id"}
    forbidden_present = [field for field in forbidden_present if field not in allowed_local_fields]
    if forbidden_present:
        raise ValueError(f"candidate rules include forbidden external API fields: {forbidden_present}")


def validate_structured_policy_candidate(candidate: dict[str, Any]) -> None:
    required = {"candidate_id", "rank", "weights", "thresholds", "scores", "metadata"}
    missing = sorted(required - set(candidate))
    if missing:
        raise ValueError(f"policy candidate missing structured fields: {missing}")
    PolicyCandidate(
        candidate_id=str(candidate["candidate_id"]),
        weights={key: float(value) for key, value in candidate["weights"].items()},
        thresholds=dict(candidate["thresholds"]),
        rationale=str(candidate.get("metadata", {}).get("rationale", "")),
    ).validate()
    scores = dict(candidate["scores"])
    for key in (
        "ranking_score",
        "insurer_efficiency_score",
        "low_mileage_high_risk_capture",
        "baseline_low_mileage_high_risk_capture",
        "stable_driver_capture_rate",
        "care_target_rate",
        "priority_or_favorable_rate",
        "customer_score_summary",
    ):
        if key not in scores:
            raise ValueError(f"policy candidate scores missing {key}")
    metadata = dict(candidate["metadata"])
    if metadata.get("schema_version") != POLICY_CANDIDATE_SCHEMA_VERSION:
        raise ValueError("policy candidate metadata schema_version mismatch")
    if metadata.get("candidate_id") != candidate["candidate_id"]:
        raise ValueError("policy candidate metadata candidate_id mismatch")
    if int(metadata.get("rank", 0)) != int(candidate["rank"]):
        raise ValueError("policy candidate metadata rank mismatch")
    if metadata.get("threshold_candidate_id") != candidate["thresholds"].get("threshold_candidate_id"):
        raise ValueError("policy candidate metadata threshold_candidate_id mismatch")
    if round(float(metadata.get("weight_sum", 0.0)), 4) != 1.0:
        raise ValueError("policy candidate metadata weight_sum must be 1.0")
    if int(metadata.get("customer_count", 0)) != int(candidate["score_summary"]["customer_count"]):
        raise ValueError("policy candidate metadata customer_count mismatch")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def _load_scenario_by_customer(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        config = json.load(file)
    return {rule["customer_id"]: rule for rule in config["customer_scenario_rules"]}


def _sum_float(rows: list[dict[str, str]], field: str) -> float:
    return sum(float(row[field]) for row in rows)


def _distance_ratio(rows: list[dict[str, str]], field: str, matching_values: set[str]) -> float:
    total_km = _sum_float(rows, "trip_distance_km")
    if total_km <= 0:
        return 0.0
    matched_km = sum(float(row["trip_distance_km"]) for row in rows if str(row[field]) in matching_values)
    return matched_km / total_km


def _is_in_zone_row(row: dict[str, str]) -> bool:
    return str(row.get("zone_label", "")) in {"core", "buffer"}


def _is_out_zone_row(row: dict[str, str]) -> bool:
    return str(row.get("zone_label", "")) == "outer"


def _risk_event_rate_per_100km(rows: list[dict[str, str]], total_km: float) -> float:
    if total_km <= 0:
        return 0.0
    event_count = sum(
        int(row["speeding_count"]) + int(row["harsh_accel_count"]) + int(row["harsh_brake_count"]) + int(row["sharp_turn_count"])
        for row in rows
    )
    return event_count / total_km * 100.0


def _risk_signal_count(row: dict[str, str]) -> int:
    return sum(
        int(row[field])
        for field in (
            "night_driving_signal",
            "sudden_braking_signal",
            "route_deviation_signal",
            "reduced_activity_signal",
            "fatigue_indicator",
        )
    )


def _candidate_id(weights: dict[str, float], care_percentile: float, tier_threshold: dict[str, int | float]) -> str:
    weight_part = "_".join(str(int(weights[key] * 100)) for key in ("w_mileage", "w_in_zone", "w_out_zone_safe", "w_out_zone_change"))
    threshold_part = f"p{int(care_percentile * 100)}_a{int(tier_threshold['A'])}"
    return f"policy_{weight_part}_{threshold_part}"


def _threshold_candidate_id(care_percentile: float, tier_threshold: dict[str, int | float]) -> str:
    return f"threshold_p{int(care_percentile * 100)}_s{int(tier_threshold['S'])}_a{int(tier_threshold['A'])}_b{int(tier_threshold['B'])}"


def _normalize_tier_threshold(tier_threshold: dict[str, int | float]) -> dict[str, int | float]:
    required = ("S", "A", "B", "C")
    missing = [key for key in required if key not in tier_threshold]
    if missing:
        raise ValueError(f"tier_threshold missing keys: {missing}")
    normalized = {key: float(tier_threshold[key]) for key in required}
    if not (normalized["S"] > normalized["A"] > normalized["B"] >= normalized["C"]):
        raise ValueError(f"tier_threshold must satisfy S > A > B >= C: {tier_threshold}")
    return {key: int(value) if value.is_integer() else value for key, value in normalized.items()}


def _tier(score: float, tier_threshold: dict[str, int | float]) -> str:
    if score >= float(tier_threshold["S"]):
        return "S"
    if score >= float(tier_threshold["A"]):
        return "A"
    if score >= float(tier_threshold["B"]):
        return "B"
    return "C"


def _persona_detection_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        persona = str(row["persona_type"])
        counts.setdefault(persona, {"customer_count": 0, "proposed_detected": 0, "baseline_detected": 0})
        counts[persona]["customer_count"] += 1
        counts[persona]["proposed_detected"] += int(bool(row["proposed_detected"]))
        counts[persona]["baseline_detected"] += int(bool(row["baseline_detected"]))
    return dict(sorted(counts.items()))


def _candidate_reason_codes(passes_gate: bool, capture_rate: float, false_positive_count: int) -> list[str]:
    codes = ["POLICY_GRID_STRUCTURED_SEARCH_COMPLETED", "WEIGHT_SUM_CONSTRAINT_SATISFIED"]
    if capture_rate >= 0.8:
        codes.append("LOW_MILEAGE_RISK_CHANGE_CAPTURED")
    if false_positive_count <= 3:
        codes.append("NON_TARGET_FALSE_POSITIVE_LIMIT_SATISFIED")
    if passes_gate:
        codes.append("APPROVAL_GATE_POLICY_CANDIDATE")
    return codes


def _candidate_strengths(capture_rate: float, stable_rate: float, false_positive_count: int) -> list[str]:
    strengths = []
    if capture_rate >= 0.8:
        strengths.append("captures at least four of five recent outer risk-change customers")
    if stable_rate >= 0.8:
        strengths.append("keeps stable local low-mileage customers out of preventive care")
    if false_positive_count <= 3:
        strengths.append("keeps non-target preventive-care false positives within the gate")
    return strengths or ["balanced candidate without a dominant strength"]


def _candidate_tradeoffs(care_target_rate: float, false_positive_count: int) -> list[str]:
    tradeoffs = []
    if care_target_rate > 0.20:
        tradeoffs.append("care target rate may be operationally heavy")
    if care_target_rate < 0.10:
        tradeoffs.append("care target rate is narrow and may miss borderline cases")
    if false_positive_count:
        tradeoffs.append(f"{false_positive_count} non-target customers are still routed to preventive care")
    return tradeoffs or ["no material tradeoff observed in the synthetic fixture"]


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
    parser = argparse.ArgumentParser(description="Search Senior Safe Mileage policy candidates.")
    parser.add_argument("--trips", default=str(DEFAULT_TRIP_INPUT), help="Synthetic trip CSV input path")
    parser.add_argument("--scenario", default=str(DEFAULT_SCENARIO_INPUT), help="Scenario config JSON input path")
    parser.add_argument("--validation-report", default=str(DEFAULT_VALIDATION_REPORT_INPUT), help="Validation report input path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Candidate rules JSON output path")
    parser.add_argument(
        "--candidate-scores-output",
        default=str(DEFAULT_CANDIDATE_SCORES_OUTPUT),
        help="Per-candidate customer score CSV output path",
    )
    args = parser.parse_args(argv)

    agent = PolicySearchAgent()
    payload = AgentInputPayload(
        run_id="policy-search-cli",
        agent_id="policy_search_agent",
        parameters={
            "trip_input": args.trips,
            "scenario_input": args.scenario,
            "validation_report_input": args.validation_report,
            "output_path": args.output,
            "candidate_scores_output_path": args.candidate_scores_output,
        },
    )
    result = agent.run(payload)
    if result.status != AgentStatus.SUCCEEDED:
        for error in result.errors:
            print(error)
        return 1
    assert result.output_payload is not None
    print(f"candidate rules: {args.output}")
    print(f"candidate scores: {args.candidate_scores_output}")
    print(result.output_payload.decisions["selected_candidate_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""A/B comparison logic for mileage baseline and Senior Safe Mileage models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from src.product.scoring_engine import (
    LOCAL_SCORING_ENGINE_ID,
    build_score_input_from_feature,
    calculate_local_score_result,
    calculate_mileage_baseline_score,
    calculate_senior_safe_mileage_score,
)


BASELINE_ANNUAL_MILEAGE_LIMIT_KM = 12_000.0
BASELINE_DISCOUNT_TIERS = (
    (3_000.0, "S", 10.0),
    (5_000.0, "A", 7.0),
    (7_000.0, "B", 5.0),
    (BASELINE_ANNUAL_MILEAGE_LIMIT_KM, "C", 3.0),
)
PROPOSED_TIER_ADJUSTMENTS = {
    "S": ("discount", 8.0, 0.0),
    "A": ("discount", 5.0, 0.0),
    "B": ("none", 0.0, 0.0),
    "C": ("surcharge", 0.0, 3.0),
}


@dataclass(frozen=True)
class ModelDecision:
    model_id: str
    score: float
    detected: bool
    threshold: float
    reason_codes: tuple[str, ...]
    input_summary: dict[str, float | int | str | bool]
    input_data_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "score": self.score,
            "detected": self.detected,
            "threshold": self.threshold,
            "reason_codes": list(self.reason_codes),
            "input_summary": dict(self.input_summary),
            "input_data_ref": self.input_data_ref,
        }


@dataclass(frozen=True)
class CustomerComparisonInput:
    """Stable local input envelope shared by the baseline and proposed model."""

    customer_id: str
    persona_type: str
    observation_period: dict[str, int]
    feature_summary: dict[str, float | int | str | bool]
    input_data_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "senior-safe-mileage-comparison-input/v1",
            "customer_id": self.customer_id,
            "persona_type": self.persona_type,
            "observation_period": dict(self.observation_period),
            "feature_summary": dict(self.feature_summary),
            "input_data_ref": self.input_data_ref,
        }


@dataclass(frozen=True)
class CustomerABComparisonResult:
    customer_id: str
    persona_type: str
    baseline: ModelDecision
    proposed: ModelDecision
    tier: str
    care_decision: str
    target_label: bool
    proxy_target_label: bool
    comparison_input: CustomerComparisonInput

    @property
    def baseline_detected(self) -> bool:
        return self.baseline.detected

    @property
    def proposed_detected(self) -> bool:
        return self.proposed.detected

    @property
    def baseline_score(self) -> float:
        return self.baseline.score

    @property
    def proposed_score(self) -> float:
        return self.proposed.score

    def metrics(self) -> dict[str, Any]:
        return {
            "comparison_rule_id": "same_customer_scenario_ab_comparison/v1",
            "same_customer_input": self.same_customer_input,
            "input_data_ref": self.comparison_input.input_data_ref,
            "baseline_model_id": self.baseline.model_id,
            "proposed_model_id": self.proposed.model_id,
            "baseline_threshold_annualized_km": self.baseline.threshold,
            "proposed_care_threshold": self.proposed.threshold,
            "annualized_recent_km": self.baseline.input_summary["annualized_recent_km"],
            "risk_change_score": self.proposed.input_summary["risk_change_score"],
            "risk_change_target": self.target_label,
            "proxy_label_target": self.proxy_target_label,
            "baseline_correct": self.baseline_detected == self.target_label,
            "proposed_correct": self.proposed_detected == self.target_label,
            "risk_change_capture": self.proposed_detected and self.target_label,
            "tier": self.tier,
            "core_metrics": self.core_metrics(),
        }

    @property
    def same_customer_input(self) -> bool:
        return (
            self.baseline.input_data_ref == self.proposed.input_data_ref
            and self.baseline.input_data_ref == self.comparison_input.input_data_ref
        )

    def core_metrics(self) -> dict[str, Any]:
        """Return UI/API-ready A/B fields: score, premium impact, grade, and decision delta."""

        baseline = baseline_pricing_outcome(self.baseline)
        proposed = proposed_pricing_outcome(
            self.proposed,
            tier=self.tier,
            care_decision=self.care_decision,
        )
        return {
            "schema_version": "senior-safe-mileage-ab-core-metrics/v1",
            "baseline": baseline,
            "proposed": proposed,
            "difference": {
                "score_delta": round(proposed["score"] - baseline["score"], 2),
                "grade_changed": baseline["grade"] != proposed["grade"],
                "decision_changed": baseline["decision"] != proposed["decision"],
                "baseline_decision": baseline["decision"],
                "proposed_decision": proposed["decision"],
                "premium_adjustment_delta_pct": round(
                    proposed["net_premium_adjustment_pct"] - baseline["net_premium_adjustment_pct"],
                    2,
                ),
                "proposed_captures_risk_change_not_baseline": (
                    self.proposed_detected and not self.baseline_detected
                ),
            },
        }

    def to_record(self) -> dict[str, Any]:
        """Return a lookup-ready comparison record for one local customer."""

        return {
            "schema_version": "senior-safe-mileage-customer-ab-comparison/v1",
            "customer_id": self.customer_id,
            "persona_type": self.persona_type,
            "lookup_key": customer_comparison_lookup_key(self.customer_id),
            "comparison_input": self.comparison_input.to_dict(),
            "baseline_model": self.baseline.to_dict(),
            "proposed_model": self.proposed.to_dict(),
            "baseline_detected": self.baseline_detected,
            "proposed_detected": self.proposed_detected,
            "baseline_score": self.baseline_score,
            "proposed_score": self.proposed_score,
            "tier": self.tier,
            "care_decision": self.care_decision,
            "target_label": self.target_label,
            "proxy_target_label": self.proxy_target_label,
            "same_customer_input": self.same_customer_input,
            "core_metrics": self.core_metrics(),
            "metrics": self.metrics(),
        }


@dataclass(frozen=True)
class CustomerABComparisonDataset:
    """Collection that supports customer-level A/B result lookup."""

    selected_policy_id: str
    records: tuple[CustomerABComparisonResult, ...]

    def get(self, customer_id: str) -> CustomerABComparisonResult:
        for record in self.records:
            if record.customer_id == customer_id:
                return record
        raise KeyError(f"unknown customer_id: {customer_id}")

    def to_dict(self) -> dict[str, Any]:
        records = [record.to_record() for record in self.records]
        comparison_summary = build_ab_comparison_summary(records)
        return {
            "schema_version": "senior-safe-mileage-ab-comparison-dataset/v1",
            "selected_policy_id": self.selected_policy_id,
            "customer_count": len(records),
            "record_lookup_key": "customer_id",
            "same_input_contract": {
                "baseline_and_proposed_share_input_data_ref": all(
                    bool(record["same_customer_input"]) for record in records
                ),
                "observation_period": {
                    "baseline_days": 60,
                    "recent_days": 30,
                    "total_days": 90,
                },
            },
            "comparison_summary": comparison_summary,
            "records": records,
            "by_customer_id": {
                record["customer_id"]: {
                    "lookup_key": record["lookup_key"],
                    "input_data_ref": record["comparison_input"]["input_data_ref"],
                    "baseline_score": record["baseline_score"],
                    "proposed_score": record["proposed_score"],
                    "baseline_detected": record["baseline_detected"],
                    "proposed_detected": record["proposed_detected"],
                    "care_decision": record["care_decision"],
                    "decision_changed": record["core_metrics"]["difference"]["decision_changed"],
                    "score_delta": record["core_metrics"]["difference"]["score_delta"],
                }
                for record in records
            },
        }


def build_ab_comparison_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize key outputs and customer decision deltas across both models."""

    baseline_outputs = [dict(record["core_metrics"]["baseline"]) for record in records]
    proposed_outputs = [dict(record["core_metrics"]["proposed"]) for record in records]
    differences = [dict(record["core_metrics"]["difference"]) for record in records]
    score_deltas = [float(diff["score_delta"]) for diff in differences]
    decision_changed_records = [
        _customer_decision_difference_record(record)
        for record in records
        if bool(record["core_metrics"]["difference"]["decision_changed"])
    ]
    proposed_only_capture_records = [
        _customer_decision_difference_record(record)
        for record in records
        if bool(record["target_label"])
        and bool(record["core_metrics"]["difference"]["proposed_captures_risk_change_not_baseline"])
    ]
    return {
        "schema_version": "senior-safe-mileage-ab-comparison-summary/v1",
        "customer_count": len(records),
        "model_outputs": {
            "baseline": _model_output_summary(baseline_outputs),
            "proposed": _model_output_summary(proposed_outputs),
        },
        "decision_differences": {
            "decision_changed_count": len(decision_changed_records),
            "grade_changed_count": sum(1 for diff in differences if bool(diff["grade_changed"])),
            "proposed_only_risk_change_capture_count": len(proposed_only_capture_records),
            "score_delta_average": _average(score_deltas),
            "score_delta_min": round(min(score_deltas), 2) if score_deltas else 0.0,
            "score_delta_max": round(max(score_deltas), 2) if score_deltas else 0.0,
            "premium_adjustment_delta_average_pct": _average(
                [float(diff["premium_adjustment_delta_pct"]) for diff in differences]
            ),
            "changed_customer_ids": [record["customer_id"] for record in decision_changed_records],
            "proposed_only_capture_customer_ids": [
                record["customer_id"]
                for record in proposed_only_capture_records
            ],
        },
        "persona_summaries": _persona_comparison_summaries(records),
        "customer_decision_differences": decision_changed_records,
    }


def build_customer_ab_comparison_dataset(
    features: list[Any],
    *,
    selected_policy_id: str,
    weights: dict[str, float],
    care_threshold: float,
    tier_threshold: dict[str, int | float],
    proxy_label_by_customer_id: dict[str, bool] | None = None,
) -> CustomerABComparisonDataset:
    """Run and index both models for every customer feature row."""

    proxy_lookup = proxy_label_by_customer_id or {}
    records = tuple(
        compare_customer_models(
            feature,
            weights=weights,
            care_threshold=care_threshold,
            tier_threshold=tier_threshold,
            target_label=bool(feature.risk_change_target),
            proxy_target_label=bool(proxy_lookup.get(str(feature.customer_id), feature.risk_change_target)),
        )
        for feature in features
    )
    return CustomerABComparisonDataset(selected_policy_id=selected_policy_id, records=records)


def run_mileage_baseline_model(feature: Any) -> ModelDecision:
    """Run the existing annual-mileage rule on one customer feature row."""

    annualized_recent_km = float(feature.annualized_recent_km)
    score = calculate_mileage_baseline_score(
        annualized_recent_km,
        annual_mileage_limit_km=BASELINE_ANNUAL_MILEAGE_LIMIT_KM,
    )
    detected = annualized_recent_km > BASELINE_ANNUAL_MILEAGE_LIMIT_KM
    reason_codes = ["BASELINE_ANNUAL_MILEAGE_RULE_EXECUTED"]
    reason_codes.append("BASELINE_OVER_MILEAGE_LIMIT" if detected else "BASELINE_LOW_MILEAGE_DISCOUNT_ONLY")
    return ModelDecision(
        model_id="existing_annual_mileage_baseline/v1",
        score=score,
        detected=detected,
        threshold=BASELINE_ANNUAL_MILEAGE_LIMIT_KM,
        reason_codes=tuple(reason_codes),
        input_summary={
            "annualized_recent_km": round(annualized_recent_km, 2),
            "recent_total_km": round(float(feature.recent_total_km), 2),
            "recent_trip_count": int(feature.recent_trip_count),
        },
    )


def baseline_pricing_outcome(decision: ModelDecision) -> dict[str, Any]:
    annualized_recent_km = float(decision.input_summary["annualized_recent_km"])
    if decision.detected:
        grade = "D"
        pricing_action = "surcharge"
        discount_rate_pct = 0.0
        surcharge_rate_pct = 5.0
        label = "기존 거리 기준 할증 검토"
    else:
        grade, discount_rate_pct = _baseline_discount_grade(annualized_recent_km)
        pricing_action = "discount"
        surcharge_rate_pct = 0.0
        label = "기존 저주행 할인"
    return _pricing_outcome(
        model_id=decision.model_id,
        score=decision.score,
        grade=grade,
        decision=label,
        detected=decision.detected,
        pricing_action=pricing_action,
        discount_rate_pct=discount_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
    )


def run_senior_safe_mileage_model(
    feature: Any,
    *,
    weights: dict[str, float],
    care_threshold: float,
    tier_threshold: dict[str, int | float],
) -> ModelDecision:
    """Run the proposed integrated Senior Safe Mileage model on the same row."""

    local_score = calculate_local_score_result(build_score_input_from_feature(feature), weights)
    score = local_score.senior_safe_mileage_score
    tier = calculate_tier(score, tier_threshold)
    detected = float(feature.risk_change_score) >= care_threshold and score < float(tier_threshold["A"])
    reason_codes = ["PROPOSED_SENIOR_SAFE_MILEAGE_RULE_EXECUTED"]
    reason_codes.append("LOCAL_RULE_SCORING_ENGINE_USED")
    reason_codes.append("PROPOSED_RISK_CHANGE_DETECTED" if detected else "PROPOSED_NO_PREVENTIVE_SIGNAL")
    return ModelDecision(
        model_id="senior_safe_mileage_integrated/v1",
        score=score,
        detected=detected,
        threshold=round(float(care_threshold), 2),
        reason_codes=tuple(reason_codes),
        input_summary={
            "annualized_recent_km": round(float(feature.annualized_recent_km), 2),
            "scoring_engine_id": LOCAL_SCORING_ENGINE_ID,
            "mileage_baseline_score": round(float(feature.mileage_baseline_score), 2),
            "in_zone_safe_score": round(float(feature.in_zone_safe_score), 2),
            "out_zone_safe_score": round(float(feature.out_zone_safe_score), 2),
            "risk_change_score": round(float(feature.risk_change_score), 2),
            "recent_in_zone_ratio": round(float(feature.recent_in_zone_ratio), 4),
            "recent_out_zone_ratio": round(float(feature.recent_out_zone_ratio), 4),
        },
    )


def proposed_pricing_outcome(
    decision: ModelDecision,
    *,
    tier: str,
    care_decision: str,
) -> dict[str, Any]:
    pricing_action, discount_rate_pct, surcharge_rate_pct = PROPOSED_TIER_ADJUSTMENTS[tier]
    if care_decision == "예방 케어":
        pricing_action = "care_review"
        discount_rate_pct = 0.0
        surcharge_rate_pct = 0.0
    return _pricing_outcome(
        model_id=decision.model_id,
        score=decision.score,
        grade=tier,
        decision=care_decision,
        detected=decision.detected,
        pricing_action=pricing_action,
        discount_rate_pct=discount_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
    )


def compare_customer_models(
    feature: Any,
    *,
    weights: dict[str, float],
    care_threshold: float,
    tier_threshold: dict[str, int | float],
    target_label: bool,
    proxy_target_label: bool,
) -> CustomerABComparisonResult:
    """Run both models against the same customer/scenario feature input."""

    comparison_input = build_customer_comparison_input(feature)
    baseline = replace(run_mileage_baseline_model(feature), input_data_ref=comparison_input.input_data_ref)
    proposed = replace(run_senior_safe_mileage_model(
        feature,
        weights=weights,
        care_threshold=care_threshold,
        tier_threshold=tier_threshold,
    ), input_data_ref=comparison_input.input_data_ref)
    tier = calculate_tier(proposed.score, tier_threshold)
    return CustomerABComparisonResult(
        customer_id=str(feature.customer_id),
        persona_type=str(feature.persona_type),
        baseline=baseline,
        proposed=proposed,
        tier=tier,
        care_decision=care_decision(proposed.detected, tier, float(feature.risk_change_score)),
        target_label=bool(target_label),
        proxy_target_label=bool(proxy_target_label),
        comparison_input=comparison_input,
    )


def build_customer_comparison_input(feature: Any) -> CustomerComparisonInput:
    feature_summary = customer_comparison_feature_summary(feature)
    payload = {
        "customer_id": str(feature.customer_id),
        "persona_type": str(feature.persona_type),
        "observation_period": {"baseline_days": 60, "recent_days": 30, "total_days": 90},
        "feature_summary": feature_summary,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    input_data_ref = "same-customer-input:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return CustomerComparisonInput(
        customer_id=str(feature.customer_id),
        persona_type=str(feature.persona_type),
        observation_period={"baseline_days": 60, "recent_days": 30, "total_days": 90},
        feature_summary=feature_summary,
        input_data_ref=input_data_ref,
    )


def customer_comparison_feature_summary(feature: Any) -> dict[str, float | int | str | bool]:
    """Return the shared local feature row both A/B models are calculated from."""

    return {
        "expected_care_decision": str(feature.expected_care_decision),
        "risk_change_target": bool(feature.risk_change_target),
        "baseline_total_km": round(float(feature.baseline_total_km), 2),
        "recent_total_km": round(float(feature.recent_total_km), 2),
        "annualized_recent_km": round(float(feature.annualized_recent_km), 2),
        "recent_trip_count": int(feature.recent_trip_count),
        "recent_in_zone_ratio": round(float(feature.recent_in_zone_ratio), 4),
        "recent_out_zone_ratio": round(float(feature.recent_out_zone_ratio), 4),
        "baseline_out_zone_ratio": round(float(feature.baseline_out_zone_ratio), 4),
        "out_zone_ratio_delta": round(float(feature.out_zone_ratio_delta), 4),
        "baseline_night_ratio": round(float(feature.baseline_night_ratio), 4),
        "recent_night_ratio": round(float(feature.recent_night_ratio), 4),
        "night_ratio_delta": round(float(feature.night_ratio_delta), 4),
        "baseline_risk_rate_per_100km": round(float(feature.baseline_risk_rate_per_100km), 4),
        "recent_risk_rate_per_100km": round(float(feature.recent_risk_rate_per_100km), 4),
        "risk_rate_delta_per_100km": round(float(feature.risk_rate_delta_per_100km), 4),
        "recent_risk_signal_count": int(feature.recent_risk_signal_count),
        "recent_in_zone_km": round(float(feature.recent_in_zone_km), 2),
        "recent_in_zone_trip_count": int(feature.recent_in_zone_trip_count),
        "recent_in_zone_night_ratio": round(float(feature.recent_in_zone_night_ratio), 4),
        "recent_in_zone_risk_rate_per_100km": round(float(feature.recent_in_zone_risk_rate_per_100km), 4),
        "recent_out_zone_km": round(float(feature.recent_out_zone_km), 2),
        "recent_out_zone_trip_count": int(feature.recent_out_zone_trip_count),
        "recent_out_zone_night_ratio": round(float(feature.recent_out_zone_night_ratio), 4),
        "recent_out_zone_risk_rate_per_100km": round(float(feature.recent_out_zone_risk_rate_per_100km), 4),
        "mileage_baseline_score": round(float(feature.mileage_baseline_score), 2),
        "in_zone_safe_score": round(float(feature.in_zone_safe_score), 2),
        "out_zone_safe_score": round(float(feature.out_zone_safe_score), 2),
        "risk_change_score": round(float(feature.risk_change_score), 2),
    }


def customer_comparison_lookup_key(customer_id: str) -> str:
    return f"customer_id:{customer_id}"


def calculate_senior_safe_mileage_score_from_feature(feature: Any, weights: dict[str, float]) -> float:
    return calculate_senior_safe_mileage_score(
        mileage_baseline_score=float(feature.mileage_baseline_score),
        in_zone_safe_score=float(feature.in_zone_safe_score),
        out_zone_safe_score=float(feature.out_zone_safe_score),
        risk_change_score=float(feature.risk_change_score),
        weights=weights,
    )


def calculate_tier(score: float, tier_threshold: dict[str, int | float]) -> str:
    if score >= float(tier_threshold["S"]):
        return "S"
    if score >= float(tier_threshold["A"]):
        return "A"
    if score >= float(tier_threshold["B"]):
        return "B"
    return "C"


def care_decision(proposed_detected: bool, tier: str, risk_change_score: float) -> str:
    if proposed_detected:
        return "예방 케어"
    if tier in {"S", "A"} and risk_change_score < 35:
        return "우대"
    return "기본"


def _baseline_discount_grade(annualized_recent_km: float) -> tuple[str, float]:
    for limit, grade, discount_rate_pct in BASELINE_DISCOUNT_TIERS:
        if annualized_recent_km <= limit:
            return grade, discount_rate_pct
    return "D", 0.0


def _pricing_outcome(
    *,
    model_id: str,
    score: float,
    grade: str,
    decision: str,
    detected: bool,
    pricing_action: str,
    discount_rate_pct: float,
    surcharge_rate_pct: float,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "score": round(float(score), 2),
        "grade": grade,
        "decision": decision,
        "detected": bool(detected),
        "pricing_action": pricing_action,
        "discount_rate_pct": round(float(discount_rate_pct), 2),
        "surcharge_rate_pct": round(float(surcharge_rate_pct), 2),
        "net_premium_adjustment_pct": round(float(surcharge_rate_pct) - float(discount_rate_pct), 2),
    }


def _model_output_summary(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(output["score"]) for output in outputs]
    return {
        "score_average": _average(scores),
        "score_min": round(min(scores), 2) if scores else 0.0,
        "score_max": round(max(scores), 2) if scores else 0.0,
        "detected_count": sum(1 for output in outputs if bool(output["detected"])),
        "grade_counts": _count_values(str(output["grade"]) for output in outputs),
        "decision_counts": _count_values(str(output["decision"]) for output in outputs),
        "pricing_action_counts": _count_values(str(output["pricing_action"]) for output in outputs),
        "average_net_premium_adjustment_pct": _average(
            [float(output["net_premium_adjustment_pct"]) for output in outputs]
        ),
    }


def _persona_comparison_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["persona_type"]), []).append(record)

    summaries: list[dict[str, Any]] = []
    for persona_type in sorted(grouped):
        persona_records = grouped[persona_type]
        differences = [dict(record["core_metrics"]["difference"]) for record in persona_records]
        summaries.append(
            {
                "persona_type": persona_type,
                "customer_count": len(persona_records),
                "baseline_detected_count": sum(1 for record in persona_records if bool(record["baseline_detected"])),
                "proposed_detected_count": sum(1 for record in persona_records if bool(record["proposed_detected"])),
                "decision_changed_count": sum(1 for diff in differences if bool(diff["decision_changed"])),
                "grade_changed_count": sum(1 for diff in differences if bool(diff["grade_changed"])),
                "average_score_delta": _average([float(diff["score_delta"]) for diff in differences]),
                "care_decision_counts": _count_values(str(record["care_decision"]) for record in persona_records),
                "proposed_only_capture_count": sum(
                    1
                    for diff in differences
                    if bool(diff["proposed_captures_risk_change_not_baseline"])
                ),
            }
        )
    return summaries


def _customer_decision_difference_record(record: dict[str, Any]) -> dict[str, Any]:
    core_metrics = dict(record["core_metrics"])
    baseline = dict(core_metrics["baseline"])
    proposed = dict(core_metrics["proposed"])
    difference = dict(core_metrics["difference"])
    return {
        "customer_id": str(record["customer_id"]),
        "persona_type": str(record["persona_type"]),
        "baseline_score": float(baseline["score"]),
        "proposed_score": float(proposed["score"]),
        "score_delta": float(difference["score_delta"]),
        "baseline_grade": str(baseline["grade"]),
        "proposed_grade": str(proposed["grade"]),
        "baseline_decision": str(baseline["decision"]),
        "proposed_decision": str(proposed["decision"]),
        "decision_changed": bool(difference["decision_changed"]),
        "grade_changed": bool(difference["grade_changed"]),
        "baseline_detected": bool(record["baseline_detected"]),
        "proposed_detected": bool(record["proposed_detected"]),
        "proposed_captures_risk_change_not_baseline": bool(
            difference["proposed_captures_risk_change_not_baseline"]
        ),
        "premium_adjustment_delta_pct": float(difference["premium_adjustment_delta_pct"]),
    }


def _count_values(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _average(values: list[float]) -> float:
    return round(sum(values) / max(1, len(values)), 2)

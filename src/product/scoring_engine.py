"""Local Senior Safe Mileage scoring engine.

This module is intentionally deterministic and has no LLM or report-agent
dependency.  It is the single local rules boundary used by policy search,
evaluation, and A/B comparison before any insurer-facing LLM report is built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LOCAL_SCORING_ENGINE_ID = "senior_safe_mileage_local_rules/v1"
DEFAULT_BASELINE_ANNUAL_MILEAGE_LIMIT_KM = 12_000.0


@dataclass(frozen=True)
class SeniorSafeMileageScoreInput:
    annualized_recent_km: float
    recent_trip_count: int
    recent_in_zone_ratio: float
    recent_out_zone_ratio: float
    out_zone_ratio_delta: float
    baseline_night_ratio: float
    recent_night_ratio: float
    night_ratio_delta: float
    baseline_risk_rate_per_100km: float
    recent_risk_rate_per_100km: float
    risk_rate_delta_per_100km: float
    recent_risk_signal_count: int
    recent_in_zone_km: float
    recent_in_zone_night_ratio: float
    recent_in_zone_risk_rate_per_100km: float
    recent_out_zone_km: float
    recent_out_zone_night_ratio: float
    recent_out_zone_risk_rate_per_100km: float


@dataclass(frozen=True)
class SeniorSafeMileageScoreResult:
    engine_id: str
    mileage_baseline_score: float
    in_zone_safe_score: float
    out_zone_safe_score: float
    risk_change_score: float
    senior_safe_mileage_score: float
    components: dict[str, float | int | str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "mileage_baseline_score": self.mileage_baseline_score,
            "in_zone_safe_score": self.in_zone_safe_score,
            "out_zone_safe_score": self.out_zone_safe_score,
            "risk_change_score": self.risk_change_score,
            "senior_safe_mileage_score": self.senior_safe_mileage_score,
            "components": dict(self.components),
        }


def build_score_input_from_feature(feature: Any) -> SeniorSafeMileageScoreInput:
    """Build a local scoring input from a customer feature object."""

    return SeniorSafeMileageScoreInput(
        annualized_recent_km=float(feature.annualized_recent_km),
        recent_trip_count=int(feature.recent_trip_count),
        recent_in_zone_ratio=float(feature.recent_in_zone_ratio),
        recent_out_zone_ratio=float(feature.recent_out_zone_ratio),
        out_zone_ratio_delta=float(feature.out_zone_ratio_delta),
        baseline_night_ratio=float(feature.baseline_night_ratio),
        recent_night_ratio=float(feature.recent_night_ratio),
        night_ratio_delta=float(feature.night_ratio_delta),
        baseline_risk_rate_per_100km=float(feature.baseline_risk_rate_per_100km),
        recent_risk_rate_per_100km=float(feature.recent_risk_rate_per_100km),
        risk_rate_delta_per_100km=float(feature.risk_rate_delta_per_100km),
        recent_risk_signal_count=int(feature.recent_risk_signal_count),
        recent_in_zone_km=float(feature.recent_in_zone_km),
        recent_in_zone_night_ratio=float(feature.recent_in_zone_night_ratio),
        recent_in_zone_risk_rate_per_100km=float(feature.recent_in_zone_risk_rate_per_100km),
        recent_out_zone_km=float(feature.recent_out_zone_km),
        recent_out_zone_night_ratio=float(feature.recent_out_zone_night_ratio),
        recent_out_zone_risk_rate_per_100km=float(feature.recent_out_zone_risk_rate_per_100km),
    )


def calculate_local_score_result(
    score_input: SeniorSafeMileageScoreInput,
    weights: dict[str, float],
) -> SeniorSafeMileageScoreResult:
    """Calculate all core scores from local summary features and rules only."""

    mileage_baseline_score = calculate_mileage_baseline_score(score_input.annualized_recent_km)
    in_zone_safe_score = calculate_in_zone_safe_score(score_input)
    out_zone_safe_score = calculate_out_zone_safe_score(score_input)
    risk_change_score = calculate_risk_change_score(score_input)
    senior_score = calculate_senior_safe_mileage_score(
        mileage_baseline_score=mileage_baseline_score,
        in_zone_safe_score=in_zone_safe_score,
        out_zone_safe_score=out_zone_safe_score,
        risk_change_score=risk_change_score,
        weights=weights,
    )
    return SeniorSafeMileageScoreResult(
        engine_id=LOCAL_SCORING_ENGINE_ID,
        mileage_baseline_score=mileage_baseline_score,
        in_zone_safe_score=in_zone_safe_score,
        out_zone_safe_score=out_zone_safe_score,
        risk_change_score=risk_change_score,
        senior_safe_mileage_score=senior_score,
        components={
            "annualized_recent_km": round(float(score_input.annualized_recent_km), 2),
            "recent_trip_count": int(score_input.recent_trip_count),
            "recent_in_zone_ratio": round(float(score_input.recent_in_zone_ratio), 4),
            "recent_out_zone_ratio": round(float(score_input.recent_out_zone_ratio), 4),
            "out_zone_ratio_delta": round(float(score_input.out_zone_ratio_delta), 4),
            "night_ratio_delta": round(float(score_input.night_ratio_delta), 4),
            "risk_rate_delta_per_100km": round(float(score_input.risk_rate_delta_per_100km), 4),
            "recent_risk_signal_count": int(score_input.recent_risk_signal_count),
        },
    )


def calculate_mileage_baseline_score(
    annualized_recent_km: float,
    *,
    annual_mileage_limit_km: float = DEFAULT_BASELINE_ANNUAL_MILEAGE_LIMIT_KM,
) -> float:
    return round(_clamp(100.0 - (float(annualized_recent_km) / annual_mileage_limit_km * 100.0)), 2)


def calculate_in_zone_safe_score(score_input: SeniorSafeMileageScoreInput) -> float:
    risk_rate = score_input.recent_in_zone_risk_rate_per_100km
    night_ratio = score_input.recent_in_zone_night_ratio
    if score_input.recent_in_zone_km <= 0:
        risk_rate = score_input.recent_risk_rate_per_100km
        night_ratio = score_input.recent_night_ratio
    risk_penalty = risk_rate * 6.0 + night_ratio * 12.0
    exposure_penalty = max(0.0, 0.50 - score_input.recent_in_zone_ratio) * 12.0
    return round(_clamp(100.0 - risk_penalty - exposure_penalty), 2)


def calculate_out_zone_safe_score(score_input: SeniorSafeMileageScoreInput) -> float:
    risk_rate = score_input.recent_out_zone_risk_rate_per_100km
    night_ratio = score_input.recent_out_zone_night_ratio
    if score_input.recent_out_zone_km <= 0:
        risk_rate = 0.0
        night_ratio = 0.0
    risk_penalty = risk_rate * 5.5 + night_ratio * 15.0
    exposure_penalty = max(0.0, score_input.recent_out_zone_ratio - 0.35) * 20.0
    return round(_clamp(100.0 - risk_penalty - exposure_penalty), 2)


def calculate_risk_change_score(score_input: SeniorSafeMileageScoreInput) -> float:
    outer_component = min(max(0.0, score_input.out_zone_ratio_delta) / 0.30, 1.0) * 35.0
    night_component = min(max(0.0, score_input.night_ratio_delta) / 0.25, 1.0) * 25.0
    risk_delta_component = min(max(0.0, score_input.risk_rate_delta_per_100km) / 5.0, 1.0) * 25.0
    signal_component = (
        min(score_input.recent_risk_signal_count / max(1, score_input.recent_trip_count), 1.0) * 15.0
    )
    return round(_clamp(outer_component + night_component + risk_delta_component + signal_component), 2)


def calculate_senior_safe_mileage_score(
    *,
    mileage_baseline_score: float,
    in_zone_safe_score: float,
    out_zone_safe_score: float,
    risk_change_score: float,
    weights: dict[str, float],
) -> float:
    score = (
        float(mileage_baseline_score) * weights["w_mileage"]
        + float(in_zone_safe_score) * weights["w_in_zone"]
        + float(out_zone_safe_score) * weights["w_out_zone_safe"]
        + (100.0 - float(risk_change_score)) * weights["w_out_zone_change"]
    )
    return round(_clamp(score), 2)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))

"""Ground-truth and rule-based proxy labels for synthetic evaluation."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


PROXY_LABEL_RULE_ID = "senior_safe_low_mileage_risk_change_proxy/v1"
HYBRID_EVALUATION_RULE_ID = "senior_safe_hybrid_ground_truth_proxy/v1"
HYBRID_PASS_FAIL_RULE_ID = "senior_safe_hybrid_pass_fail_threshold/v1"
HYBRID_PASS_THRESHOLD = 80.0
LABEL_INPUT_SCHEMA_VERSION = "senior-safe-mileage-label-input/v1"

CARE_DECISION_ALIASES = {
    "favorable": "우대",
    "preferred": "우대",
    "priority": "우대",
    "우대": "우대",
    "standard": "기본",
    "basic": "기본",
    "default": "기본",
    "기본": "기본",
    "preventive_care": "예방 케어",
    "preventive-care": "예방 케어",
    "care": "예방 케어",
    "예방케어": "예방 케어",
    "예방 케어": "예방 케어",
}


@dataclass(frozen=True)
class RiskChangeProxyThresholds:
    """Thresholds used to derive evaluation labels without claims or accident data."""

    low_mileage_annualized_km_max: float = 12_000.0
    risk_change_score_min: float = 60.0
    out_zone_ratio_delta_min: float = 0.25
    night_ratio_delta_min: float = 0.15
    risk_rate_delta_per_100km_min: float = 3.0
    recent_out_zone_risk_rate_per_100km_min: float = 3.0
    recent_out_zone_trip_count_min: int = 3

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


DEFAULT_RISK_CHANGE_PROXY_THRESHOLDS = RiskChangeProxyThresholds()


@dataclass(frozen=True)
class HybridEvaluationWeights:
    """Weights for scoring a model decision against synthetic evaluation truth."""

    ground_truth_priority: float = 0.80
    proxy_label_correction: float = 0.20

    def __post_init__(self) -> None:
        if self.ground_truth_priority < 0 or self.proxy_label_correction < 0:
            raise ValueError("hybrid evaluation weights must be non-negative")
        total = self.ground_truth_priority + self.proxy_label_correction
        if abs(total - 1.0) > 0.0001:
            raise ValueError("hybrid evaluation weights must sum to 1.0")

    def to_dict(self) -> dict[str, float]:
        return {
            "ground_truth_priority": self.ground_truth_priority,
            "proxy_label_correction": self.proxy_label_correction,
        }


DEFAULT_HYBRID_EVALUATION_WEIGHTS = HybridEvaluationWeights()


@dataclass(frozen=True)
class RiskChangeProxyLabel:
    """Computed proxy target label and auditable rule evidence."""

    is_target: bool
    expected_care_decision: str
    rule_id: str
    reason_codes: tuple[str, ...]
    thresholds: dict[str, float | int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_target": self.is_target,
            "expected_care_decision": self.expected_care_decision,
            "rule_id": self.rule_id,
            "reason_codes": list(self.reason_codes),
            "thresholds": self.thresholds,
        }


@dataclass(frozen=True)
class GroundTruthLabelInput:
    """Human-authored persona/scenario expectation used as synthetic truth."""

    customer_id: str
    persona_type: str
    risk_change_target: bool
    expected_care_decision: str
    expected_reason_codes: tuple[str, ...]
    source_artifact: str
    schema_version: str = LABEL_INPUT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "customer_id": self.customer_id,
            "persona_type": self.persona_type,
            "risk_change_target": self.risk_change_target,
            "expected_care_decision": self.expected_care_decision,
            "expected_reason_codes": list(self.expected_reason_codes),
            "source_artifact": self.source_artifact,
        }


@dataclass(frozen=True)
class ProxyLabelFeatureInput:
    """Non-identifying aggregate feature row allowed for proxy label derivation."""

    customer_id: str
    persona_type: str
    annualized_recent_km: float
    risk_change_score: float
    out_zone_ratio_delta: float
    night_ratio_delta: float
    risk_rate_delta_per_100km: float
    recent_out_zone_risk_rate_per_100km: float
    recent_out_zone_trip_count: int
    source_artifact: str
    schema_version: str = LABEL_INPUT_SCHEMA_VERSION

    def to_proxy_feature(self) -> dict[str, float | int]:
        return {
            "annualized_recent_km": self.annualized_recent_km,
            "risk_change_score": self.risk_change_score,
            "out_zone_ratio_delta": self.out_zone_ratio_delta,
            "night_ratio_delta": self.night_ratio_delta,
            "risk_rate_delta_per_100km": self.risk_rate_delta_per_100km,
            "recent_out_zone_risk_rate_per_100km": self.recent_out_zone_risk_rate_per_100km,
            "recent_out_zone_trip_count": self.recent_out_zone_trip_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "customer_id": self.customer_id,
            "persona_type": self.persona_type,
            "annualized_recent_km": self.annualized_recent_km,
            "risk_change_score": self.risk_change_score,
            "out_zone_ratio_delta": self.out_zone_ratio_delta,
            "night_ratio_delta": self.night_ratio_delta,
            "risk_rate_delta_per_100km": self.risk_rate_delta_per_100km,
            "recent_out_zone_risk_rate_per_100km": self.recent_out_zone_risk_rate_per_100km,
            "recent_out_zone_trip_count": self.recent_out_zone_trip_count,
            "source_artifact": self.source_artifact,
        }


@dataclass(frozen=True)
class HybridLabelInput:
    """Aligned ground-truth and proxy inputs for one synthetic customer."""

    customer_id: str
    persona_type: str
    ground_truth: GroundTruthLabelInput
    proxy_feature_input: ProxyLabelFeatureInput
    schema_version: str = LABEL_INPUT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "customer_id": self.customer_id,
            "persona_type": self.persona_type,
            "ground_truth": self.ground_truth.to_dict(),
            "proxy_feature_input": self.proxy_feature_input.to_dict(),
        }


@dataclass(frozen=True)
class HybridEvaluationScore:
    """Decision-level evaluation score with ground truth priority and proxy correction."""

    hybrid_target: bool
    ground_truth_target: bool
    proxy_label_target: bool
    decision_detected: bool
    score: float
    rule_id: str
    weights: dict[str, float]
    reason_codes: tuple[str, ...]
    passed: bool
    verdict: str
    pass_threshold: float
    pass_fail_rule_id: str
    exception_rule: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hybrid_target": self.hybrid_target,
            "ground_truth_target": self.ground_truth_target,
            "proxy_label_target": self.proxy_label_target,
            "decision_detected": self.decision_detected,
            "score": self.score,
            "rule_id": self.rule_id,
            "weights": self.weights,
            "reason_codes": list(self.reason_codes),
            "passed": self.passed,
            "verdict": self.verdict,
            "pass_threshold": self.pass_threshold,
            "pass_fail_rule_id": self.pass_fail_rule_id,
            "exception_rule": self.exception_rule,
        }


def normalize_care_decision(value: Any) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("expected_care_decision is required")
    key = normalized.lower().replace(" ", "_")
    if normalized in CARE_DECISION_ALIASES:
        return CARE_DECISION_ALIASES[normalized]
    if key in CARE_DECISION_ALIASES:
        return CARE_DECISION_ALIASES[key]
    raise ValueError(f"unsupported expected_care_decision: {value!r}")


def load_ground_truth_labels(path: str | Path) -> dict[str, GroundTruthLabelInput]:
    """Load and normalize synthetic ground-truth labels from JSON or CSV fixtures."""

    artifact_path = Path(path)
    if artifact_path.suffix.lower() == ".json":
        rows = _ground_truth_rows_from_json(artifact_path)
    elif artifact_path.suffix.lower() == ".csv":
        rows = _read_csv(artifact_path)
    else:
        raise ValueError(f"unsupported ground-truth label input: {artifact_path}")

    labels: dict[str, GroundTruthLabelInput] = {}
    for row in rows:
        label = normalize_ground_truth_label(row, source_artifact=str(artifact_path))
        if label.customer_id in labels:
            raise ValueError(f"duplicate ground-truth customer_id: {label.customer_id}")
        labels[label.customer_id] = label
    return labels


def normalize_ground_truth_label(row: Mapping[str, Any], *, source_artifact: str = "") -> GroundTruthLabelInput:
    customer_id = str(_required(row, "customer_id")).strip()
    persona_type = str(_required(row, "persona_type")).strip()
    if not customer_id:
        raise ValueError("ground-truth customer_id is required")
    if not persona_type:
        raise ValueError(f"{customer_id} ground-truth persona_type is required")
    ground_truth = row.get("ground_truth") if isinstance(row.get("ground_truth"), Mapping) else row
    expected_reason_codes = _reason_code_tuple(
        ground_truth.get("expected_reason_codes")
        if isinstance(ground_truth, Mapping)
        else row.get("expected_reason_codes")
    )
    return GroundTruthLabelInput(
        customer_id=customer_id,
        persona_type=persona_type,
        risk_change_target=_bool_value(_required(ground_truth, "risk_change_target")),
        expected_care_decision=normalize_care_decision(_required(ground_truth, "expected_care_decision")),
        expected_reason_codes=expected_reason_codes,
        source_artifact=source_artifact,
    )


def load_proxy_label_inputs(path: str | Path) -> list[ProxyLabelFeatureInput]:
    """Load proxy-label feature inputs from a CSV or JSON feature fixture."""

    artifact_path = Path(path)
    if artifact_path.suffix.lower() == ".json":
        loaded = json.loads(artifact_path.read_text(encoding="utf-8"))
        rows = loaded.get("customer_feature_summaries", loaded if isinstance(loaded, list) else [])
        if not isinstance(rows, list):
            raise ValueError(f"{artifact_path} does not contain proxy feature rows")
    elif artifact_path.suffix.lower() == ".csv":
        rows = _read_csv(artifact_path)
    else:
        raise ValueError(f"unsupported proxy label input: {artifact_path}")
    return [normalize_proxy_label_input(row, source_artifact=str(artifact_path)) for row in rows]


def normalize_proxy_label_input(row: Mapping[str, Any] | Any, *, source_artifact: str = "") -> ProxyLabelFeatureInput:
    return ProxyLabelFeatureInput(
        customer_id=str(_field_value(row, "customer_id", default="")).strip(),
        persona_type=str(_field_value(row, "persona_type", default="")).strip(),
        annualized_recent_km=_float_field(row, "annualized_recent_km"),
        risk_change_score=_float_field(row, "risk_change_score"),
        out_zone_ratio_delta=_float_field(row, "out_zone_ratio_delta"),
        night_ratio_delta=_float_field(row, "night_ratio_delta"),
        risk_rate_delta_per_100km=_float_field(row, "risk_rate_delta_per_100km"),
        recent_out_zone_risk_rate_per_100km=_float_field(row, "recent_out_zone_risk_rate_per_100km"),
        recent_out_zone_trip_count=_int_field(row, "recent_out_zone_trip_count"),
        source_artifact=source_artifact,
    )


def build_hybrid_label_inputs(
    proxy_inputs: list[ProxyLabelFeatureInput],
    ground_truth_by_customer: Mapping[str, GroundTruthLabelInput],
) -> list[HybridLabelInput]:
    hybrid_inputs = []
    for proxy_input in proxy_inputs:
        ground_truth = ground_truth_by_customer.get(proxy_input.customer_id)
        if ground_truth is None:
            raise ValueError(f"missing ground-truth label for {proxy_input.customer_id}")
        if ground_truth.persona_type != proxy_input.persona_type:
            raise ValueError(
                f"{proxy_input.customer_id} persona mismatch: "
                f"{ground_truth.persona_type} != {proxy_input.persona_type}"
            )
        hybrid_inputs.append(
            HybridLabelInput(
                customer_id=proxy_input.customer_id,
                persona_type=proxy_input.persona_type,
                ground_truth=ground_truth,
                proxy_feature_input=proxy_input,
            )
        )
    return hybrid_inputs


def score_hybrid_evaluation_decision(
    *,
    decision_detected: bool,
    ground_truth_target: bool,
    proxy_label_target: bool,
    weights: HybridEvaluationWeights = DEFAULT_HYBRID_EVALUATION_WEIGHTS,
) -> HybridEvaluationScore:
    """Score one model decision against ground truth first, with proxy correction.

    The final target label follows the human-authored synthetic ground truth.
    The proxy label only contributes the configured correction weight so a
    disagreement can reduce confidence without overriding the fixture truth.
    """

    ground_truth_correct = bool(decision_detected) == bool(ground_truth_target)
    proxy_correct = bool(decision_detected) == bool(proxy_label_target)
    score = (
        float(ground_truth_correct) * weights.ground_truth_priority
        + float(proxy_correct) * weights.proxy_label_correction
    ) * 100.0
    rounded_score = round(score, 2)
    passed = rounded_score >= HYBRID_PASS_THRESHOLD
    exception_rule = _hybrid_exception_rule(
        ground_truth_correct=ground_truth_correct,
        proxy_correct=proxy_correct,
        ground_truth_target=ground_truth_target,
        proxy_label_target=proxy_label_target,
    )
    reason_codes = ["HYBRID_EVALUATION_GROUND_TRUTH_PRIORITY"]
    if ground_truth_target == proxy_label_target:
        reason_codes.append("HYBRID_GROUND_TRUTH_PROXY_ALIGNED")
    else:
        reason_codes.append("HYBRID_PROXY_CORRECTION_APPLIED")
    reason_codes.append("HYBRID_DECISION_MATCHES_GROUND_TRUTH" if ground_truth_correct else "HYBRID_DECISION_MISSES_GROUND_TRUTH")
    reason_codes.append("HYBRID_DECISION_MATCHES_PROXY" if proxy_correct else "HYBRID_DECISION_MISSES_PROXY")
    reason_codes.append("HYBRID_PASS_FAIL_PASSED" if passed else "HYBRID_PASS_FAIL_FAILED")
    if exception_rule:
        reason_codes.append(exception_rule)
    return HybridEvaluationScore(
        hybrid_target=bool(ground_truth_target),
        ground_truth_target=bool(ground_truth_target),
        proxy_label_target=bool(proxy_label_target),
        decision_detected=bool(decision_detected),
        score=rounded_score,
        rule_id=HYBRID_EVALUATION_RULE_ID,
        weights=weights.to_dict(),
        reason_codes=tuple(reason_codes),
        passed=passed,
        verdict="pass" if passed else "fail",
        pass_threshold=HYBRID_PASS_THRESHOLD,
        pass_fail_rule_id=HYBRID_PASS_FAIL_RULE_ID,
        exception_rule=exception_rule,
    )


def _hybrid_exception_rule(
    *,
    ground_truth_correct: bool,
    proxy_correct: bool,
    ground_truth_target: bool,
    proxy_label_target: bool,
) -> str | None:
    if ground_truth_target == proxy_label_target:
        return None
    if ground_truth_correct and not proxy_correct:
        return "HYBRID_EXCEPTION_PROXY_DISAGREEMENT_ALLOWED_WHEN_GROUND_TRUTH_MATCHES"
    if proxy_correct and not ground_truth_correct:
        return "HYBRID_EXCEPTION_PROXY_ONLY_MATCH_DOES_NOT_OVERRIDE_GROUND_TRUTH"
    return None


def derive_risk_change_proxy_label(
    feature: Mapping[str, Any] | Any,
    thresholds: RiskChangeProxyThresholds = DEFAULT_RISK_CHANGE_PROXY_THRESHOLDS,
) -> RiskChangeProxyLabel:
    """Derive the low-mileage risk-change proxy label from summary features.

    The proxy intentionally uses only non-identifying aggregate behavior:
    recent annualized mileage, living-zone departure change, night-driving
    change, risk-event deltas, and recent outside-zone exposure.
    """

    annualized_recent_km = _value(feature, "annualized_recent_km")
    risk_change_score = _value(feature, "risk_change_score")
    out_zone_ratio_delta = _value(feature, "out_zone_ratio_delta")
    night_ratio_delta = _value(feature, "night_ratio_delta")
    risk_rate_delta = _value(feature, "risk_rate_delta_per_100km")
    recent_out_zone_risk_rate = _value(feature, "recent_out_zone_risk_rate_per_100km")
    recent_out_zone_trip_count = int(_value(feature, "recent_out_zone_trip_count"))

    low_mileage = annualized_recent_km <= thresholds.low_mileage_annualized_km_max
    behavior_change = risk_change_score >= thresholds.risk_change_score_min
    outside_zone_shift = out_zone_ratio_delta >= thresholds.out_zone_ratio_delta_min
    night_shift = night_ratio_delta >= thresholds.night_ratio_delta_min
    risk_rate_shift = risk_rate_delta >= thresholds.risk_rate_delta_per_100km_min
    outside_zone_risk = (
        recent_out_zone_risk_rate >= thresholds.recent_out_zone_risk_rate_per_100km_min
        and recent_out_zone_trip_count >= thresholds.recent_out_zone_trip_count_min
    )

    is_target = bool(
        low_mileage
        and behavior_change
        and outside_zone_shift
        and (night_shift or risk_rate_shift)
        and outside_zone_risk
    )
    reason_codes = _reason_codes(
        low_mileage=low_mileage,
        behavior_change=behavior_change,
        outside_zone_shift=outside_zone_shift,
        night_shift=night_shift,
        risk_rate_shift=risk_rate_shift,
        outside_zone_risk=outside_zone_risk,
        is_target=is_target,
    )
    return RiskChangeProxyLabel(
        is_target=is_target,
        expected_care_decision="예방 케어" if is_target else "기본",
        rule_id=PROXY_LABEL_RULE_ID,
        reason_codes=reason_codes,
        thresholds=thresholds.to_dict(),
    )


def derive_proxy_labels(
    features: list[Mapping[str, Any] | Any],
    thresholds: RiskChangeProxyThresholds = DEFAULT_RISK_CHANGE_PROXY_THRESHOLDS,
) -> list[RiskChangeProxyLabel]:
    return [derive_risk_change_proxy_label(feature, thresholds) for feature in features]


def _reason_codes(
    *,
    low_mileage: bool,
    behavior_change: bool,
    outside_zone_shift: bool,
    night_shift: bool,
    risk_rate_shift: bool,
    outside_zone_risk: bool,
    is_target: bool,
) -> tuple[str, ...]:
    codes = ["PROXY_LABEL_RULE_BASED"]
    codes.append("PROXY_LOW_MILEAGE_Y" if low_mileage else "PROXY_LOW_MILEAGE_N")
    if behavior_change:
        codes.append("PROXY_RISK_CHANGE_SCORE_HIGH")
    if outside_zone_shift:
        codes.append("PROXY_OUT_ZONE_RATIO_DELTA_HIGH")
    if night_shift:
        codes.append("PROXY_NIGHT_RATIO_DELTA_HIGH")
    if risk_rate_shift:
        codes.append("PROXY_RISK_RATE_DELTA_HIGH")
    if outside_zone_risk:
        codes.append("PROXY_OUT_ZONE_RISK_CONFIRMED")
    codes.append("PROXY_RISK_CHANGE_TARGET_Y" if is_target else "PROXY_RISK_CHANGE_TARGET_N")
    return tuple(codes)


def _value(feature: Mapping[str, Any] | Any, field: str) -> float:
    if isinstance(feature, Mapping):
        value = feature[field]
    else:
        value = getattr(feature, field)
    return float(value)


def _ground_truth_rows_from_json(path: Path) -> list[Mapping[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        return loaded
    for key in ("customer_scenario_rules", "customers"):
        rows = loaded.get(key)
        if isinstance(rows, list):
            return rows
    raise ValueError(f"{path} does not contain customer ground-truth rows")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def _required(row: Mapping[str, Any], field: str) -> Any:
    value = row.get(field)
    if value is None or value == "":
        raise ValueError(f"label input missing required field: {field}")
    return value


def _field_value(row: Mapping[str, Any] | Any, field: str, *, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        if field in row:
            return row[field]
        return default
    return getattr(row, field, default)


def _float_field(row: Mapping[str, Any] | Any, field: str) -> float:
    value = _field_value(row, field)
    if value is None or value == "":
        raise ValueError(f"proxy label input missing numeric field: {field}")
    return float(value)


def _int_field(row: Mapping[str, Any] | Any, field: str) -> int:
    return int(_float_field(row, field))


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"cannot normalize boolean label value: {value!r}")


def _reason_code_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            return tuple(str(item) for item in parsed)
        return tuple(part.strip() for part in stripped.split("|") if part.strip())
    return tuple(str(item) for item in value)

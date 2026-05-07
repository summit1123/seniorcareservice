"""Final reward and care decision rules."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.features.build_model_features import write_csv
from src.models.score_rules import OUTSIDE_LIVING_ZONE_SEGMENT_FIELDS, P90_THRESHOLD_FIELDS


ROOT = Path(__file__).resolve().parents[2]
SCORE_TABLE_PATH = ROOT / "data" / "processed" / "score_table.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "decision_table.csv"

SCORE_FIELDS = (
    "mileage_baseline_score",
    "senior_safe_mileage_score",
    "risk_change_score",
)

CARE_DECISIONS = frozenset({"우대", "기본", "예방 케어"})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def coerce_threshold_value(field: str, value: str) -> float | int | str:
    if value == "":
        return ""
    if field.endswith("_sample_count"):
        return int(float(value))
    return round(float(value), 4)


def extract_p90_thresholds(row: dict[str, str]) -> dict[str, float | int | str]:
    """Expose calculated P90 thresholds as a stable customer decision sub-structure."""
    return {
        field: coerce_threshold_value(field, row.get(field, ""))
        for field in P90_THRESHOLD_FIELDS
        if field in row
    }


def extract_outside_living_zone_segments(row: dict[str, str]) -> dict[str, float | int | str]:
    """Expose outside living-zone segment criteria and flags for customer decisions."""
    payload: dict[str, float | int | str] = {}
    for field in OUTSIDE_LIVING_ZONE_SEGMENT_FIELDS:
        if field not in row:
            continue
        value = row.get(field, "")
        if value == "":
            payload[field] = ""
        elif field.endswith("_count"):
            payload[field] = int(float(value))
        elif field.endswith("_criteria"):
            payload[field] = value
        else:
            payload[field] = round(float(value), 4)
    return payload


def extract_score_fields(row: dict[str, str]) -> dict[str, float]:
    return {
        field: round(float(row[field]), 2)
        for field in SCORE_FIELDS
        if field in row
    }


def decide(row: dict[str, str]) -> dict[str, Any]:
    safe = float(row["safe_driving_score"])
    familiar = float(row["familiar_zone_score"])
    pattern = float(row["pattern_change_score"])
    out_zone_risk = float(row["out_zone_behavior_risk"])
    care = float(row["care_trigger_score"])
    senior_score = float(row["senior_safe_mileage_score"])
    risk_change = float(row.get("risk_change_score", out_zone_risk))
    score_fields = extract_score_fields(row)
    p90_thresholds = extract_p90_thresholds(row)
    outside_living_zone_segments = extract_outside_living_zone_segments(row)

    if risk_change >= 60 and out_zone_risk >= 60:
        decision = "예방 케어"
        reasons = [
            "최근 운전패턴이 평소와 크게 달라짐",
            "생활권 밖 주행과 위험행동이 함께 증가함",
            "차량 점검 또는 안전운전 리포트 안내 필요",
        ]
        trigger = 1
    elif pattern >= 60 and out_zone_risk >= 60:
        decision = "예방 케어"
        reasons = [
            "최근 운전패턴이 평소와 크게 달라짐",
            "생활권 밖 주행과 위험행동이 함께 증가함",
            "차량 점검 또는 안전운전 리포트 안내 필요",
        ]
        trigger = 1
    elif senior_score >= 80 and risk_change < 35 and care < 35:
        decision = "우대"
        reasons = [
            "Senior Safe Mileage Score가 우대 구간에 있음",
            "생활권 내외 위험변화가 낮음",
            "최근 운전패턴이 평소와 유사함",
        ]
        trigger = 0
    else:
        decision = "기본"
        reasons = [
            "일부 생활권 밖 주행은 있으나 고위험 변화는 제한적",
            "기존 마일리지/안전운전 혜택 판단은 유지 가능",
            "추가 데이터 확보 후 재평가 가능",
        ]
        trigger = 0

    if decision not in CARE_DECISIONS:
        raise ValueError(f"invalid care decision: {decision}")

    return {
        "customer_id": row.get("customer_id", row["driver_id"]),
        "driver_id": row["driver_id"],
        "persona_type": row.get("persona_type", ""),
        "safe_driving_score": safe,
        **score_fields,
        "familiar_zone_score": familiar,
        "pattern_change_score": pattern,
        "out_zone_behavior_risk": out_zone_risk,
        "care_trigger_score": care,
        **p90_thresholds,
        **outside_living_zone_segments,
        "p90_thresholds_json": json.dumps(p90_thresholds, ensure_ascii=True, separators=(",", ":")),
        "outside_living_zone_segments_json": json.dumps(
            outside_living_zone_segments,
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        "care_trigger": trigger,
        "care_decision": decision,
        "decision": decision,
        "reason_1": reasons[0],
        "reason_2": reasons[1],
        "reason_3": reasons[2],
    }


def build_decision_table(score_table_path: Path = SCORE_TABLE_PATH, output_path: Path = OUTPUT_PATH) -> list[dict[str, Any]]:
    rows = [decide(row) for row in read_csv(score_table_path)]
    write_csv(output_path, rows)
    return rows


def main() -> int:
    rows = build_decision_table()
    print(f"decision table: {OUTPUT_PATH}")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

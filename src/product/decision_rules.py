"""Final reward and care decision rules."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.features.build_model_features import write_csv


ROOT = Path(__file__).resolve().parents[2]
SCORE_TABLE_PATH = ROOT / "data" / "processed" / "score_table.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "decision_table.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def decide(row: dict[str, str]) -> dict[str, Any]:
    safe = float(row["safe_driving_score"])
    familiar = float(row["familiar_zone_score"])
    pattern = float(row["pattern_change_score"])
    out_zone_risk = float(row["out_zone_behavior_risk"])
    care = float(row["care_trigger_score"])

    if safe >= 80 and familiar >= 70 and pattern < 35:
        decision = "추가 리워드"
        reasons = [
            "생활권 중심 주행 비율이 높음",
            "과속·급감속 등 위험행동이 낮음",
            "최근 운전패턴이 평소와 유사함",
        ]
        trigger = 0
    elif pattern >= 60 and out_zone_risk >= 60:
        decision = "예방 케어"
        reasons = [
            "최근 운전패턴이 평소와 크게 달라짐",
            "생활권 밖 주행과 위험행동이 함께 증가함",
            "차량 점검 또는 안전운전 리포트 안내 필요",
        ]
        trigger = 1
    else:
        decision = "기본 유지"
        reasons = [
            "일부 생활권 밖 주행은 있으나 고위험 변화는 제한적",
            "기존 마일리지/안전운전 혜택 판단은 유지 가능",
            "추가 데이터 확보 후 재평가 가능",
        ]
        trigger = 0

    return {
        "driver_id": row["driver_id"],
        "safe_driving_score": safe,
        "familiar_zone_score": familiar,
        "pattern_change_score": pattern,
        "out_zone_behavior_risk": out_zone_risk,
        "care_trigger_score": care,
        "care_trigger": trigger,
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

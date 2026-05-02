"""Build TAAS behavior-weight features from municipal accident statistics."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_TAAS_PATH = ROOT / "data" / "raw" / "taas_stt_2010_2024.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "taas_weight_table.csv"

TOTAL_CATEGORY = "전체"
NIGHT_CATEGORY = "야간사고"
ELDERLY_DRIVER_CATEGORY = "고령운전사고"
ELDERLY_ACCIDENT_CATEGORY = "노인사고"

LAW_COLUMNS = {
    "speeding_weight": "과속",
    "centerline_violation_weight": "중앙선 침범",
    "signal_violation_weight": "신호위반",
    "safety_distance_weight": "안전거리 미확보",
    "safe_driving_violation_weight": "안전운전 의무 불이행",
    "pedestrian_protection_weight": "보행자 보호의무 위반",
    "single_vehicle_weight": "차량단독",
}


def number(value: str) -> float:
    value = (value or "").strip().replace(",", "")
    return float(value) if value else 0.0


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as csvfile:
        return list(csv.DictReader(csvfile))


def is_sido_total(row: dict[str, str]) -> bool:
    code = row["법정동코드"].strip()
    return len(code) == 4 and code.endswith("00")


def weighted_fatality_rate(rows: list[dict[str, str]]) -> float:
    accident_count = sum(number(row["사고건수"]) for row in rows)
    if accident_count <= 0:
        return 0.0
    return sum(number(row["사고건수"]) * number(row["치사율"]) for row in rows) / accident_count


def rows_for(rows: list[dict[str, str]], year: str, category: str) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["연도"] == year and row["대상사고 구분명"] == category and is_sido_total(row)
    ]


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def build_year_weight(rows: list[dict[str, str]], year: str) -> dict[str, Any]:
    total_rows = rows_for(rows, year, TOTAL_CATEGORY)
    night_rows = rows_for(rows, year, NIGHT_CATEGORY)
    elderly_driver_rows = rows_for(rows, year, ELDERLY_DRIVER_CATEGORY)
    elderly_accident_rows = rows_for(rows, year, ELDERLY_ACCIDENT_CATEGORY)

    total_accidents = sum(number(row["사고건수"]) for row in total_rows)
    total_deaths = sum(number(row["사망자수"]) for row in total_rows)
    night_accidents = sum(number(row["사고건수"]) for row in night_rows)
    night_deaths = sum(number(row["사망자수"]) for row in night_rows)
    elderly_driver_accidents = sum(number(row["사고건수"]) for row in elderly_driver_rows)
    elderly_driver_deaths = sum(number(row["사망자수"]) for row in elderly_driver_rows)
    elderly_accidents = sum(number(row["사고건수"]) for row in elderly_accident_rows)
    elderly_deaths = sum(number(row["사망자수"]) for row in elderly_accident_rows)
    total_fatality = weighted_fatality_rate(total_rows)
    night_fatality = weighted_fatality_rate(night_rows)
    elderly_driver_fatality = weighted_fatality_rate(elderly_driver_rows)
    elderly_accident_fatality = weighted_fatality_rate(elderly_accident_rows)

    result: dict[str, Any] = {
        "year": year,
        "aggregation_scope": "sido_total_rows_only",
        "region_count": len(total_rows),
        "total_acc_cnt": int(total_accidents),
        "total_dth_cnt": int(total_deaths),
        "night_acc_cnt": int(night_accidents),
        "night_dth_cnt": int(night_deaths),
        "elderly_driver_acc_cnt": int(elderly_driver_accidents),
        "elderly_driver_dth_cnt": int(elderly_driver_deaths),
        "elderly_accident_acc_cnt": int(elderly_accidents),
        "elderly_accident_dth_cnt": int(elderly_deaths),
        "night_accident_share": round(ratio(night_accidents, total_accidents), 4),
        "night_death_share": round(ratio(night_deaths, total_deaths), 4),
        "elderly_driver_accident_share": round(ratio(elderly_driver_accidents, total_accidents), 4),
        "elderly_driver_death_share": round(ratio(elderly_driver_deaths, total_deaths), 4),
        "elderly_accident_share": round(ratio(elderly_accidents, total_accidents), 4),
        "elderly_accident_death_share": round(ratio(elderly_deaths, total_deaths), 4),
        "total_fatality_rate": round(total_fatality, 4),
        "night_fatality_rate": round(night_fatality, 4),
        "elderly_driver_fatality_rate": round(elderly_driver_fatality, 4),
        "elderly_accident_fatality_rate": round(elderly_accident_fatality, 4),
        "night_fatality_weight": round(ratio(night_fatality, total_fatality), 4),
        "elderly_driver_fatality_weight": round(ratio(elderly_driver_fatality, total_fatality), 4),
        "elderly_accident_fatality_weight": round(ratio(elderly_accident_fatality, total_fatality), 4),
    }

    for output_column, source_column in LAW_COLUMNS.items():
        count = sum(number(row[source_column]) for row in total_rows)
        result[output_column] = round(ratio(count, total_accidents), 6)

    return result


def build_taas_weight_table(input_path: Path = RAW_TAAS_PATH, output_path: Path = OUTPUT_PATH) -> list[dict[str, Any]]:
    rows = read_rows(input_path)
    years = sorted({row["연도"] for row in rows})
    output_rows = [build_year_weight(rows, year) for year in years]
    speeding_reference_values = [
        row["speeding_weight"]
        for row in output_rows
        if int(row["year"]) <= 2020 and row["speeding_weight"] > 0
    ]
    speeding_reference = (
        sum(speeding_reference_values) / len(speeding_reference_values)
        if speeding_reference_values
        else 0.0
    )
    for row in output_rows:
        raw_speeding_available = int(not (int(row["year"]) >= 2021 and row["speeding_weight"] == 0))
        row["speeding_weight_available"] = raw_speeding_available
        row["speeding_weight_reference_2010_2020"] = round(speeding_reference, 6)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)
    return output_rows


def main() -> int:
    rows = build_taas_weight_table()
    print(f"taas weight table: {OUTPUT_PATH}")
    print(f"years: {rows[0]['year']}~{rows[-1]['year']}, rows={len(rows)}")
    print(f"latest: {rows[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

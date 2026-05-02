"""Column mapping helpers for public trip CSV files.

The model pipeline uses a fixed English schema. Public business-vehicle CSVs
often arrive with Korean source headers, so this module detects whether a file
can be normalized before it reaches the feature pipeline.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


STANDARD_COLUMNS = [
    "driver_id",
    "trip_id",
    "trip_start_time",
    "trip_end_time",
    "start_gps_x",
    "start_gps_y",
    "end_gps_x",
    "end_gps_y",
    "trip_distance_km",
    "trip_duration_min",
    "avg_speed",
    "max_speed",
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
    "stop_count",
]

DIRECT_CANDIDATES: dict[str, list[str]] = {
    "driver_id": [
        "driver_id",
        "운전자ID",
        "운전자아이디",
        "차량ID",
        "자동차등록번호",
        "차량번호",
        "운수회사코드",
    ],
    "trip_id": [
        "trip_id",
        "운행ID",
        "운행아이디",
        "운행일련번호",
        "trip_no",
    ],
    "trip_start_time": [
        "trip_start_time",
        "시동ON일시",
        "시동ON 일시",
        "운행시작일시",
        "운행 시작 일시",
        "출발일시",
        "시작일시",
    ],
    "trip_end_time": [
        "trip_end_time",
        "시동OFF일시",
        "시동OFF 일시",
        "운행종료일시",
        "운행 종료 일시",
        "도착일시",
        "종료일시",
    ],
    "start_gps_x": ["start_gps_x", "시작 GPS X좌표", "시작GPSX좌표", "출발 GPS X좌표", "출발경도", "시작경도"],
    "start_gps_y": ["start_gps_y", "시작 GPS Y좌표", "시작GPSY좌표", "출발 GPS Y좌표", "출발위도", "시작위도"],
    "end_gps_x": ["end_gps_x", "종료 GPS X좌표", "종료GPSX좌표", "도착 GPS X좌표", "도착경도", "종료경도"],
    "end_gps_y": ["end_gps_y", "종료 GPS Y좌표", "종료GPSY좌표", "도착 GPS Y좌표", "도착위도", "종료위도"],
    "trip_distance_km": ["trip_distance_km", "TRIP 운행거리", "운행거리", "주행거리", "trip_distance"],
    "trip_duration_min": ["trip_duration_min", "TRIP 운행시간", "운행시간", "주행시간", "trip_duration"],
    "avg_speed": ["avg_speed", "평균운행속도", "평균 운행 속도", "평균속도"],
    "max_speed": ["max_speed", "최고속도", "최고 속도", "최대속도"],
    "speeding_count": ["speeding_count", "과속건수", "과속 건수", "과속횟수"],
    "harsh_accel_count": ["harsh_accel_count", "급가속건수", "급가속 건수", "급가속횟수"],
    "harsh_brake_count": ["harsh_brake_count", "급감속건수", "급감속 건수", "급감속횟수", "급제동건수"],
    "sharp_turn_count": ["sharp_turn_count", "급회전건수", "급회전 건수", "급좌우회전건수"],
    "stop_count": ["stop_count", "운행중정지건수", "운행중 정지건수", "정지건수"],
}

LEFT_TURN_CANDIDATES = ["급좌회전건수", "급좌회전 건수", "급좌회전횟수"]
RIGHT_TURN_CANDIDATES = ["급우회전건수", "급우회전 건수", "급우회전횟수"]
COMPANY_CANDIDATES = ["운수회사코드", "회사코드", "업체코드"]
VEHICLE_CANDIDATES = ["자동차등록번호", "차량번호", "차량등록번호"]
TRIP_DATE_CANDIDATES = ["운행일자", "운행 일자", "운행일"]

EVENT_COUNT_COLUMNS = {
    "speeding_count",
    "harsh_accel_count",
    "harsh_brake_count",
    "sharp_turn_count",
    "stop_count",
}


@dataclass(frozen=True)
class CsvPayload:
    fieldnames: list[str]
    rows: list[dict[str, str]]
    encoding: str
    delimiter: str


@dataclass(frozen=True)
class MappingResult:
    source_path: Path
    encoding: str
    delimiter: str
    row_count: int
    field_count: int
    mapping: dict[str, str]
    missing: list[str]
    derived: dict[str, str]
    notes: list[str]

    @property
    def can_normalize(self) -> bool:
        return not self.missing


def normalize_header(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch.isalnum())


def read_csv_payload(path: Path) -> CsvPayload:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        return CsvPayload(
            fieldnames=list(reader.fieldnames or []),
            rows=[{key: value for key, value in row.items() if key is not None} for row in reader],
            encoding=encoding,
            delimiter=dialect.delimiter,
        )
    if last_error:
        raise last_error
    raise ValueError(f"Unable to read CSV file: {path}")


def match_header(fieldnames: list[str], candidates: list[str]) -> str | None:
    normalized = {normalize_header(field): field for field in fieldnames}
    for candidate in candidates:
        hit = normalized.get(normalize_header(candidate))
        if hit:
            return hit
    return None


def analyze_mapping(path: Path) -> MappingResult:
    payload = read_csv_payload(path)
    mapping: dict[str, str] = {}
    missing: list[str] = []
    derived: dict[str, str] = {}
    notes: list[str] = []

    for standard_column in STANDARD_COLUMNS:
        hit = match_header(payload.fieldnames, DIRECT_CANDIDATES[standard_column])
        if hit:
            mapping[standard_column] = hit
            continue

        if standard_column == "driver_id":
            company = match_header(payload.fieldnames, COMPANY_CANDIDATES)
            vehicle = match_header(payload.fieldnames, VEHICLE_CANDIDATES)
            if vehicle:
                mapping[standard_column] = vehicle
                derived[standard_column] = "원본 식별자를 deterministic anonymous driver_id로 변환"
                if company:
                    notes.append("driver_id는 운수회사코드와 자동차등록번호 조합을 익명화할 수 있습니다.")
                continue

        if standard_column == "trip_id":
            start_time = match_header(payload.fieldnames, DIRECT_CANDIDATES["trip_start_time"])
            vehicle = match_header(payload.fieldnames, VEHICLE_CANDIDATES)
            if start_time and vehicle:
                mapping[standard_column] = f"derived:{vehicle}+{start_time}"
                derived[standard_column] = "차량 식별자, 운행 시작 시각, 행 번호로 trip_id 생성"
                continue

        if standard_column == "trip_duration_min":
            start_time = match_header(payload.fieldnames, DIRECT_CANDIDATES["trip_start_time"])
            end_time = match_header(payload.fieldnames, DIRECT_CANDIDATES["trip_end_time"])
            if start_time and end_time:
                mapping[standard_column] = f"derived:{start_time}->{end_time}"
                derived[standard_column] = "시작/종료 시각 차이로 분 단위 운행시간 생성"
                continue

        if standard_column == "avg_speed":
            distance = match_header(payload.fieldnames, DIRECT_CANDIDATES["trip_distance_km"])
            duration = match_header(payload.fieldnames, DIRECT_CANDIDATES["trip_duration_min"])
            if distance and duration:
                mapping[standard_column] = f"derived:{distance}/{duration}"
                derived[standard_column] = "운행거리와 운행시간으로 평균속도 생성"
                continue

        if standard_column == "sharp_turn_count":
            left_turn = match_header(payload.fieldnames, LEFT_TURN_CANDIDATES)
            right_turn = match_header(payload.fieldnames, RIGHT_TURN_CANDIDATES)
            if left_turn and right_turn:
                mapping[standard_column] = f"derived:{left_turn}+{right_turn}"
                derived[standard_column] = "급좌회전건수와 급우회전건수를 합산"
                continue

        missing.append(standard_column)

    if not payload.rows:
        notes.append("CSV에 데이터 행이 없습니다. 헤더 매핑은 가능해도 파이프라인은 실행하지 않습니다.")

    return MappingResult(
        source_path=path,
        encoding=payload.encoding,
        delimiter=payload.delimiter,
        row_count=len(payload.rows),
        field_count=len(payload.fieldnames),
        mapping=mapping,
        missing=missing,
        derived=derived,
        notes=notes,
    )


def value(row: dict[str, str], header: str | None, default: str = "") -> str:
    if not header:
        return default
    return (row.get(header) or "").strip()


def numeric_value(raw_value: str, default: float = 0.0) -> float:
    cleaned = raw_value.strip().replace(",", "")
    cleaned = cleaned.replace("km", "").replace("KM", "").replace("분", "").strip()
    if cleaned == "":
        return default
    return float(cleaned)


def integer_string(raw_value: str, default: int = 0) -> str:
    return str(int(round(numeric_value(raw_value, float(default)))))


def normalize_time(raw_value: str) -> str:
    cleaned = raw_value.strip()
    if not cleaned:
        raise ValueError("empty datetime value")
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"unsupported datetime value: {raw_value}") from exc


def parse_standard_time(value_: str) -> datetime:
    return datetime.strptime(normalize_time(value_), "%Y-%m-%d %H:%M:%S")


def anonymize_driver(raw_key: str, index_by_key: dict[str, int]) -> str:
    key = raw_key.strip()
    if not key:
        key = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:8]
    if key.startswith("driver_"):
        return key
    if key not in index_by_key:
        index_by_key[key] = len(index_by_key) + 1
    return f"driver_{index_by_key[key]:03d}"


def build_driver_key(row: dict[str, str], mapping: dict[str, str]) -> str:
    mapped = mapping["driver_id"]
    if mapped.startswith("derived:"):
        return mapped
    vehicle = value(row, mapped)
    company = match_header(list(row), COMPANY_CANDIDATES)
    company_value = value(row, company)
    return f"{company_value}:{vehicle}" if company_value else vehicle


def normalize_rows(path: Path, result: MappingResult) -> list[dict[str, str]]:
    if result.missing:
        raise ValueError(f"Cannot normalize CSV. Missing required columns: {', '.join(result.missing)}")

    payload = read_csv_payload(path)
    driver_index: dict[str, int] = {}
    normalized: list[dict[str, str]] = []

    for index, row in enumerate(payload.rows, start=1):
        output: dict[str, str] = {}
        driver_key = build_driver_key(row, result.mapping)
        output["driver_id"] = anonymize_driver(driver_key, driver_index)

        start_time = normalize_time(value(row, result.mapping["trip_start_time"]))
        end_time = normalize_time(value(row, result.mapping["trip_end_time"]))
        output["trip_start_time"] = start_time
        output["trip_end_time"] = end_time

        trip_mapping = result.mapping["trip_id"]
        if trip_mapping.startswith("derived:"):
            output["trip_id"] = f"{output['driver_id']}_trip_{index:06d}"
        else:
            output["trip_id"] = value(row, trip_mapping) or f"{output['driver_id']}_trip_{index:06d}"

        for column in ["start_gps_x", "start_gps_y", "end_gps_x", "end_gps_y", "trip_distance_km", "max_speed"]:
            output[column] = str(numeric_value(value(row, result.mapping[column])))

        duration_mapping = result.mapping["trip_duration_min"]
        if duration_mapping.startswith("derived:"):
            minutes = (parse_standard_time(end_time) - parse_standard_time(start_time)).total_seconds() / 60
            output["trip_duration_min"] = str(int(round(minutes)))
        else:
            output["trip_duration_min"] = integer_string(value(row, duration_mapping))

        avg_speed_mapping = result.mapping["avg_speed"]
        if avg_speed_mapping.startswith("derived:"):
            distance = numeric_value(output["trip_distance_km"])
            duration = max(numeric_value(output["trip_duration_min"]), 1.0)
            output["avg_speed"] = f"{distance / (duration / 60):.1f}"
        else:
            output["avg_speed"] = str(numeric_value(value(row, avg_speed_mapping)))

        for column in EVENT_COUNT_COLUMNS - {"sharp_turn_count"}:
            output[column] = integer_string(value(row, result.mapping[column]))

        sharp_turn_mapping = result.mapping["sharp_turn_count"]
        if sharp_turn_mapping.startswith("derived:"):
            left = match_header(list(row), LEFT_TURN_CANDIDATES)
            right = match_header(list(row), RIGHT_TURN_CANDIDATES)
            sharp_turns = numeric_value(value(row, left)) + numeric_value(value(row, right))
            output["sharp_turn_count"] = str(int(round(sharp_turns)))
        else:
            output["sharp_turn_count"] = integer_string(value(row, sharp_turn_mapping))

        normalized.append({column: output[column] for column in STANDARD_COLUMNS})

    return normalized


def write_standard_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=STANDARD_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

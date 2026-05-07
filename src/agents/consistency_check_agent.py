"""Consistency Check Agent for synthetic senior-driver trip fixtures."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents.ai_simulation_agent import EVENT_COUNT_FIELDS, RISK_SIGNAL_FIELDS, TRIP_FIELDS
from src.agents.contracts import (
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentStatus,
    ArtifactType,
    utc_now_iso,
)
from src.agents.persona_agent import EXPECTED_PERSONA_TYPES


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRIP_INPUT = ROOT / "data" / "fixtures" / "senior_trip_logs.csv"
DEFAULT_MANIFEST_INPUT = ROOT / "data" / "fixtures" / "simulation_manifest.json"
DEFAULT_REPORT_OUTPUT = ROOT / "data" / "fixtures" / "validation_report.md"
REPORT_SCHEMA_VERSION = "senior-trip-consistency-validation/v1"


@dataclass(frozen=True)
class ConsistencyValidationReport:
    passed: bool
    checks: dict[str, dict[str, Any]]
    metrics: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class ConsistencyCheckAgent:
    """Checks coordinate, distance, time, risk-signal, and manifest consistency."""

    metadata = AgentMetadata(
        agent_id="consistency_check_agent",
        role=AgentRole.CONSISTENCY_CHECK,
        display_name="Consistency Check Agent",
        description="Checks trip coordinate, distance, time, and risk-event consistency.",
        consumes=("senior_trip_logs.csv", "simulation_manifest.json"),
        produces=("validation_report.md",),
    )

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            trip_input = _resolve_artifact_path(
                payload,
                artifact_id="senior_trip_logs.csv",
                parameter_name="trip_input",
                default_path=DEFAULT_TRIP_INPUT,
            )
            manifest_input = _resolve_artifact_path(
                payload,
                artifact_id="simulation_manifest.json",
                parameter_name="manifest_input",
                default_path=DEFAULT_MANIFEST_INPUT,
            )
            report_output = Path(str(payload.parameters.get("report_output", DEFAULT_REPORT_OUTPUT)))
            report = self.validate_fixture(trip_input, manifest_input)
            self.write_report(report, report_output)

            if not report.passed:
                raise ValueError("; ".join(report.errors[:5]) or "fixture consistency validation failed")

            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="validation_report.md",
                        artifact_type=ArtifactType.MARKDOWN,
                        path=_relative_fixture_path(report_output),
                        rows=int(report.metrics["trip_count"]),
                        summary={
                            "passed": report.passed,
                            "check_count": len(report.checks),
                            "customer_count": report.metrics["customer_count"],
                            "trip_count": report.metrics["trip_count"],
                            "warning_count": len(report.warnings),
                        },
                    ),
                ),
                metrics={
                    "customer_count": report.metrics["customer_count"],
                    "trip_count": report.metrics["trip_count"],
                    "persona_count": report.metrics["persona_count"],
                    "check_count": len(report.checks),
                    "failed_check_count": sum(1 for check in report.checks.values() if not check["passed"]),
                    "warning_count": len(report.warnings),
                },
                validation={
                    "passed": report.passed,
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "checks": report.checks,
                    "warnings": list(report.warnings),
                },
                reason_codes=(
                    "TRIP_COORDINATE_DISTANCE_TIME_CONSISTENCY_PASSED",
                    "RISK_SIGNAL_CODE_CONSISTENCY_PASSED",
                    "SIMULATION_MANIFEST_CONSISTENCY_PASSED",
                ),
                messages=("trip fixture consistency validation passed",),
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
                warnings=report.warnings,
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

    def validate_fixture(
        self,
        trip_input: str | Path = DEFAULT_TRIP_INPUT,
        manifest_input: str | Path = DEFAULT_MANIFEST_INPUT,
    ) -> ConsistencyValidationReport:
        rows = self.load_rows(trip_input)
        manifest = self.load_manifest(manifest_input)
        errors: list[str] = []
        warnings: list[str] = []

        checks = {
            "schema": self._check_schema(rows),
            "population": self._check_population(rows),
            "observation_period": self._check_observation_period(rows, manifest),
            "coordinate_distance_time": self._check_coordinate_distance_time(rows),
            "risk_signal_codes": self._check_risk_signal_codes(rows),
            "manifest": self._check_manifest(rows, manifest),
        }
        for check_name, check in checks.items():
            errors.extend(f"{check_name}: {message}" for message in check["errors"])
            warnings.extend(f"{check_name}: {message}" for message in check["warnings"])

        metrics = self._build_metrics(rows)
        return ConsistencyValidationReport(
            passed=not errors,
            checks=checks,
            metrics=metrics,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def load_rows(self, trip_input: str | Path) -> list[dict[str, str]]:
        path = Path(trip_input)
        with path.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            if reader.fieldnames != TRIP_FIELDS:
                raise ValueError(f"trip CSV schema mismatch: {reader.fieldnames}")
        if not rows:
            raise ValueError("trip CSV has no rows")
        return rows

    def load_manifest(self, manifest_input: str | Path) -> dict[str, Any]:
        with Path(manifest_input).open(encoding="utf-8") as file:
            return json.load(file)

    def write_report(self, report: ConsistencyValidationReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Senior Trip Fixture Consistency Validation",
            "",
            f"- schema_version: `{REPORT_SCHEMA_VERSION}`",
            f"- passed: `{str(report.passed).lower()}`",
            f"- customer_count: `{report.metrics['customer_count']}`",
            f"- trip_count: `{report.metrics['trip_count']}`",
            f"- persona_count: `{report.metrics['persona_count']}`",
            "",
            "## Checks",
            "",
        ]
        for check_name, check in report.checks.items():
            lines.append(f"- `{check_name}`: {'passed' if check['passed'] else 'failed'}")
            lines.append(f"  - rows_checked: `{check['rows_checked']}`")
            if check["errors"]:
                lines.append(f"  - errors: `{len(check['errors'])}`")
            if check["warnings"]:
                lines.append(f"  - warnings: `{len(check['warnings'])}`")
        if report.errors:
            lines.extend(["", "## Errors", ""])
            lines.extend(f"- {error}" for error in report.errors)
        if report.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in report.warnings)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _check_schema(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        errors: list[str] = []
        for row_number, row in enumerate(rows, start=2):
            missing = [field for field in TRIP_FIELDS if field not in row]
            if missing:
                errors.append(f"row {row_number} missing fields: {missing}")
        return _check_result(rows, errors)

    def _check_population(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        errors: list[str] = []
        by_persona: dict[str, set[str]] = {}
        by_customer: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_persona.setdefault(row["persona_type"], set()).add(row["customer_id"])
            by_customer.setdefault(row["customer_id"], []).append(row)
        if len(by_customer) != 30:
            errors.append(f"expected 30 customers, got {len(by_customer)}")
        if set(by_persona) != EXPECTED_PERSONA_TYPES:
            errors.append(f"persona set mismatch: {sorted(by_persona)}")
        invalid_counts = {
            persona_type: len(customer_ids)
            for persona_type, customer_ids in by_persona.items()
            if len(customer_ids) != 5
        }
        if invalid_counts:
            errors.append(f"each persona must have five customers: {invalid_counts}")
        for customer_id, customer_rows in by_customer.items():
            baseline_count = sum(1 for row in customer_rows if row["observation_period"] == "baseline")
            recent_count = sum(1 for row in customer_rows if row["observation_period"] == "recent")
            if baseline_count < 20 or recent_count < 8:
                errors.append(f"{customer_id} has insufficient baseline/recent trips: {baseline_count}/{recent_count}")
        return _check_result(rows, errors)

    def _check_observation_period(self, rows: list[dict[str, str]], manifest: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        start_date = date.fromisoformat(str(manifest.get("start_date", "2026-01-01")))
        expected_dates = {
            1: start_date,
            60: start_date + timedelta(days=59),
            61: start_date + timedelta(days=60),
            90: start_date + timedelta(days=89),
        }
        by_customer: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_customer.setdefault(row["customer_id"], []).append(row)
            day_index = int(row["observation_day_index"])
            service_date = date.fromisoformat(row["service_date"])
            if service_date != start_date + timedelta(days=day_index - 1):
                errors.append(f"{row['trip_id']} service_date does not match observation_day_index")
            if row["observation_period"] == "baseline" and not 1 <= day_index <= 60:
                errors.append(f"{row['trip_id']} baseline day index outside 1..60")
            if row["observation_period"] == "recent" and not 61 <= day_index <= 90:
                errors.append(f"{row['trip_id']} recent day index outside 61..90")

        for customer_id, customer_rows in by_customer.items():
            days = {int(row["observation_day_index"]) for row in customer_rows}
            missing = sorted(set(expected_dates) - days)
            if missing:
                errors.append(f"{customer_id} missing observation boundary days: {missing}")
            period_days = {
                period: {int(row["observation_day_index"]) for row in customer_rows if row["observation_period"] == period}
                for period in ("baseline", "recent")
            }
            if period_days["baseline"] & period_days["recent"]:
                errors.append(f"{customer_id} has overlapping baseline/recent day indices")
        return _check_result(rows, errors)

    def _check_coordinate_distance_time(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        for row in rows:
            trip_id = row["trip_id"]
            start = (float(row["start_gps_x"]), float(row["start_gps_y"]))
            end = (float(row["end_gps_x"]), float(row["end_gps_y"]))
            if not _in_range(start) or not _in_range(end):
                errors.append(f"{trip_id} coordinates outside synthetic operating range")
            distance_km = float(row["trip_distance_km"])
            duration_min = float(row["trip_duration_min"])
            avg_speed = float(row["avg_speed"])
            max_speed = float(row["max_speed"])
            start_dt = datetime.strptime(row["trip_start_time"], "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(row["trip_end_time"], "%Y-%m-%d %H:%M:%S")
            duration_from_time = (end_dt - start_dt).total_seconds() / 60
            if duration_from_time <= 0:
                errors.append(f"{trip_id} trip_end_time must be after trip_start_time")
            if abs(duration_from_time - duration_min) > 1.0:
                errors.append(f"{trip_id} duration mismatch: time={duration_from_time:.1f}, field={duration_min:.1f}")
            expected_avg_speed = distance_km / duration_min * 60
            if abs(expected_avg_speed - avg_speed) > 1.0:
                errors.append(f"{trip_id} avg_speed mismatch")
            if max_speed < avg_speed:
                errors.append(f"{trip_id} max_speed lower than avg_speed")
            straight_line_km = _haversine_km(start, end)
            if straight_line_km > distance_km * 1.35 + 0.5:
                errors.append(
                    f"{trip_id} straight-line coordinate distance exceeds trip distance: "
                    f"{straight_line_km:.2f}km > {distance_km:.2f}km"
                )
            if avg_speed > 95 or max_speed > 120:
                warnings.append(f"{trip_id} has high but bounded synthetic speed")
        return _check_result(rows, errors, warnings)

    def _check_risk_signal_codes(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        errors: list[str] = []
        code_by_field = {
            "night_driving_signal": "NIGHT_DRIVING",
            "sudden_braking_signal": "SUDDEN_BRAKING",
            "route_deviation_signal": "ROUTE_DEVIATION",
            "reduced_activity_signal": "REDUCED_ACTIVITY",
            "fatigue_indicator": "FATIGUE_INDICATOR",
        }
        for row in rows:
            trip_id = row["trip_id"]
            for field in (*RISK_SIGNAL_FIELDS, *EVENT_COUNT_FIELDS, "stop_count"):
                if int(row[field]) < 0:
                    errors.append(f"{trip_id} {field} must be non-negative")
            if int(row["night_driving_signal"]) != int(row["night_drive_flag"]):
                errors.append(f"{trip_id} night_driving_signal must mirror night_drive_flag")
            if int(row["sudden_braking_signal"]) != int(int(row["harsh_brake_count"]) > 0):
                errors.append(f"{trip_id} sudden_braking_signal must follow harsh_brake_count")
            codes = set() if row["risk_signal_codes"] == "none" else set(row["risk_signal_codes"].split("|"))
            expected_codes = {code for field, code in code_by_field.items() if int(row[field]) == 1}
            if codes != expected_codes:
                errors.append(f"{trip_id} risk_signal_codes mismatch: expected={sorted(expected_codes)}, actual={sorted(codes)}")
            if not row["persona_risk_annotation"] or not row["synthetic_risk_tag"]:
                errors.append(f"{trip_id} missing persona annotation or synthetic risk tag")
        return _check_result(rows, errors)

    def _check_manifest(self, rows: list[dict[str, str]], manifest: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        metrics = self._build_metrics(rows)
        if manifest.get("trip_count") != metrics["trip_count"]:
            errors.append(f"manifest trip_count mismatch: {manifest.get('trip_count')} != {metrics['trip_count']}")
        if manifest.get("customer_count") != metrics["customer_count"]:
            errors.append(f"manifest customer_count mismatch: {manifest.get('customer_count')} != {metrics['customer_count']}")
        if manifest.get("persona_customer_counts") != metrics["persona_customer_counts"]:
            errors.append("manifest persona_customer_counts mismatch")
        for key in (
            "customer_90_day_coverage_validation",
            "baseline_coverage_validation",
            "recent_coverage_validation",
        ):
            if not manifest.get(key, {}).get("passed"):
                errors.append(f"manifest {key} is not passed")
        return _check_result(rows, errors)

    def _build_metrics(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        by_persona: dict[str, set[str]] = {}
        customer_ids: set[str] = set()
        for row in rows:
            customer_ids.add(row["customer_id"])
            by_persona.setdefault(row["persona_type"], set()).add(row["customer_id"])
        return {
            "customer_count": len(customer_ids),
            "trip_count": len(rows),
            "persona_count": len(by_persona),
            "persona_customer_counts": {
                persona_type: len(customer_ids)
                for persona_type, customer_ids in sorted(by_persona.items())
            },
        }


def _check_result(
    rows: list[dict[str, str]],
    errors: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "passed": not errors,
        "rows_checked": len(rows),
        "errors": errors,
        "warnings": warnings or [],
    }


def _resolve_artifact_path(
    payload: AgentInputPayload,
    *,
    artifact_id: str,
    parameter_name: str,
    default_path: Path,
) -> Path:
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


def _relative_fixture_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _in_range(point: tuple[float, float]) -> bool:
    lon, lat = point
    return 126.70 <= lon <= 127.30 and 37.35 <= lat <= 37.75


def _haversine_km(start: tuple[float, float], end: tuple[float, float]) -> float:
    lon1, lat1 = start
    lon2, lat2 = end
    radius_km = 6371.0088
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    hav = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(hav))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate senior synthetic trip fixture consistency.")
    parser.add_argument("--trips", default=str(DEFAULT_TRIP_INPUT), help="Trip CSV input path")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_INPUT), help="Simulation manifest input path")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_OUTPUT), help="Validation report Markdown output path")
    args = parser.parse_args(argv)

    agent = ConsistencyCheckAgent()
    report = agent.validate_fixture(args.trips, args.manifest)
    agent.write_report(report, args.report)
    print(f"validation {'passed' if report.passed else 'failed'}; wrote {args.report}")
    if not report.passed:
        for error in report.errors[:10]:
            print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

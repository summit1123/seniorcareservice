#!/usr/bin/env python3
"""Validate and optionally normalize a public trip CSV for the model pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.column_mapping import STANDARD_COLUMNS, analyze_mapping, normalize_rows, write_standard_csv
from src.features.build_model_features import build_model_features
from src.models.pattern_model import build_pattern_scores
from src.models.score_rules import build_score_table
from src.product.decision_rules import build_decision_table
from src.reporting.analysis_visuals import generate_analysis_outputs


DEFAULT_REPORT_DIR = ROOT / ".codex-loop" / "artifacts" / "csv-mapping"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def default_normalized_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}_standardized.csv")


def default_report_path(source_path: Path) -> Path:
    return DEFAULT_REPORT_DIR / f"{source_path.stem}-mapping-report.md"


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 실제 CSV 컬럼 매핑 검증 리포트",
        "",
        f"- 생성 시각: {payload['generatedAt']}",
        f"- 원본 파일: `{payload['source']}`",
        f"- 인코딩: {payload['encoding']}",
        f"- 구분자: `{payload['delimiter']}`",
        f"- 행 수: {payload['rowCount']}",
        f"- 원본 컬럼 수: {payload['fieldCount']}",
        f"- 검증 결과: {payload['status']}",
        "",
        "## 표준 컬럼 매핑",
        "",
        "| 표준 컬럼 | 원본 컬럼 또는 생성 규칙 | 상태 |",
        "|---|---|---|",
    ]
    for column in STANDARD_COLUMNS:
        source = payload["mapping"].get(column, "")
        if column in payload["missing"]:
            status = "누락"
        elif column in payload["derived"]:
            status = "생성"
        else:
            status = "직접 매핑"
        lines.append(f"| `{column}` | `{source or '-'}` | {status} |")

    lines.extend(["", "## 누락 컬럼"])
    if payload["missing"]:
        lines.extend(f"- `{column}`" for column in payload["missing"])
    else:
        lines.append("- 없음")

    lines.extend(["", "## 생성 규칙"])
    if payload["derived"]:
        lines.extend(f"- `{column}`: {rule}" for column, rule in payload["derived"].items())
    else:
        lines.append("- 없음")

    lines.extend(["", "## 파이프라인 실행"])
    pipeline = payload["pipeline"]
    lines.append(f"- 상태: {pipeline['status']}")
    if pipeline.get("input"):
        lines.append(f"- 입력 파일: `{pipeline['input']}`")
    if pipeline.get("reason"):
        lines.append(f"- 사유: {pipeline['reason']}")
    for item in pipeline.get("outputs", []):
        lines.append(f"- 산출물: `{item}`")

    lines.extend(
        [
            "",
            "## 개인정보 및 한계",
            "- 원본 차량번호 또는 회사코드는 모델 입력에서 `driver_###` 형식으로 익명화합니다.",
            "- 원본 좌표는 생활권 feature 생성에만 쓰며, 최종 `model_feature_table.csv`에는 직접 남기지 않습니다.",
            "- 공공 사업용차량 CSV는 시니어 개인 승용차를 대표하지 않으므로 프로토타입 연결성 검증 자료로만 사용합니다.",
        ]
    )
    if payload["notes"]:
        lines.extend(["", "## 메모", *[f"- {note}" for note in payload["notes"]]])
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_pipeline_for_input(input_path: Path, generate_visuals: bool) -> dict[str, Any]:
    feature_outputs = build_model_features(input_path=input_path)
    pattern_scores = build_pattern_scores()
    score_rows = build_score_table()
    decision_rows = build_decision_table()
    outputs = [relative(path) for path in feature_outputs.values()]
    outputs.extend(
        [
            "data/processed/pattern_change_score.csv",
            "data/processed/score_table.csv",
            "data/processed/decision_table.csv",
        ]
    )
    if generate_visuals:
        visual_outputs = generate_analysis_outputs()
        outputs.extend(relative(path) for path in visual_outputs.values())
    return {
        "status": "실행 완료",
        "input": relative(input_path),
        "rows": {
            "pattern": len(pattern_scores),
            "score": len(score_rows),
            "decision": len(decision_rows),
        },
        "outputs": outputs,
    }


def build_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source_path = (ROOT / args.source).resolve() if not Path(args.source).is_absolute() else Path(args.source)
    result = analyze_mapping(source_path)
    normalized_path = (ROOT / args.normalized_output).resolve() if args.normalized_output else default_normalized_path(source_path)
    pipeline: dict[str, Any] = {
        "status": "미실행",
        "reason": "검증만 요청되어 파이프라인을 실행하지 않았습니다.",
        "outputs": [],
    }
    exit_code = 0

    if result.missing:
        pipeline = {
            "status": "실행 불가",
            "reason": f"필수 컬럼 누락: {', '.join(result.missing)}",
            "outputs": [],
        }
        exit_code = 2
    else:
        pipeline_input = source_path
        if args.normalize or args.run_pipeline:
            rows = normalize_rows(source_path, result)
            if any(result.mapping[column] != column for column in STANDARD_COLUMNS):
                write_standard_csv(normalized_path, rows)
                pipeline_input = normalized_path
            elif args.normalize:
                write_standard_csv(normalized_path, rows)
                pipeline_input = normalized_path

        if args.run_pipeline:
            pipeline = run_pipeline_for_input(pipeline_input, args.generate_visuals)

    payload = {
        "generatedAt": now_iso(),
        "source": relative(source_path),
        "encoding": result.encoding,
        "delimiter": result.delimiter,
        "rowCount": result.row_count,
        "fieldCount": result.field_count,
        "status": "통과" if not result.missing else "실패",
        "mapping": result.mapping,
        "missing": result.missing,
        "derived": result.derived,
        "notes": result.notes,
        "pipeline": pipeline,
    }
    return payload, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a raw trip CSV against the model input schema.")
    parser.add_argument("source", nargs="?", default="data/raw/trip_sample.csv", help="CSV file to validate")
    parser.add_argument("--normalize", action="store_true", help="Write a standardized CSV even when the pipeline is not run")
    parser.add_argument("--normalized-output", help="Output path for a standardized CSV")
    parser.add_argument("--run-pipeline", action="store_true", help="Run the model pipeline when mapping validation passes")
    parser.add_argument("--generate-visuals", action="store_true", help="Regenerate reports/figures after pipeline execution")
    parser.add_argument("--report", help="Markdown report path")
    parser.add_argument("--json", dest="json_path", help="JSON report path")
    args = parser.parse_args()

    payload, exit_code = build_payload(args)
    report_path = (ROOT / args.report).resolve() if args.report else default_report_path(Path(payload["source"]))
    json_path = (ROOT / args.json_path).resolve() if args.json_path else report_path.with_suffix(".json")

    report_text = render_report(payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    write_json(json_path, payload)

    print(f"mapping report: {relative(report_path)}")
    print(f"mapping json: {relative(json_path)}")
    print(f"status: {payload['status']}")
    if payload["missing"]:
        print(f"missing required columns: {', '.join(payload['missing'])}")
    if payload["pipeline"]["status"] != "미실행":
        print(f"pipeline: {payload['pipeline']['status']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

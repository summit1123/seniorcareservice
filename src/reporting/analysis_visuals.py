"""Generate analysis-result visuals from model outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCORE_TABLE = ROOT / "data" / "processed" / "score_table.csv"
DECISION_TABLE = ROOT / "data" / "processed" / "decision_table.csv"
PATTERN_TABLE = ROOT / "data" / "processed" / "pattern_change_score.csv"
FIGURE_DIR = ROOT / "reports" / "figures"
REPORT_PATH = ROOT / "reports" / "model_demo_summary.md"

FONT = "Apple SD Gothic Neo, Noto Sans KR, Noto Sans CJK KR, Arial, sans-serif"
BLACK = "#111111"
TEXT = "#222222"
MUTED = "#666666"
LINE = "#BBBBBB"
FILL = "#F7F7F7"
WHITE = "#FFFFFF"

SIGNAL_LABELS = {
    "trip_distance_increase": "주행거리 증가",
    "out_zone_increase": "생활권 밖 주행 증가",
    "night_driving_increase": "야간 주행 증가",
    "speeding_increase": "과속 증가",
    "harsh_brake_increase": "급감속 증가",
    "sharp_turn_increase": "급회전 증가",
    "no_recent_trip": "최근 주행 없음",
    "no_baseline_trip": "평소 기준 주행 부족",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def text(x: int, y: int, value: str, size: int = 18, weight: int = 400, color: str = TEXT) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{value}</text>'
    )


def rect(x: int, y: int, w: float, h: int, fill: str = FILL, stroke: str = LINE) -> str:
    return f'<rect x="{x}" y="{y}" width="{w:.2f}" height="{h}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'


def base_svg(width: int, height: int, title: str, subtitle: str, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="{WHITE}"/>
  {text(48, 58, title, size=30, weight=800, color=BLACK)}
  {text(48, 92, subtitle, size=17, color=MUTED)}
  {body}
</svg>
'''


def write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def signal_label(signal: str) -> str:
    label = SIGNAL_LABELS.get(signal, signal)
    return f"{label} (`{signal}`)"


def score_comparison_svg(score_rows: list[dict[str, str]]) -> str:
    metrics = [
        ("safe_driving_score", "안전운전"),
        ("familiar_zone_score", "생활권 안정성"),
        ("pattern_change_score", "패턴 변화"),
        ("out_zone_behavior_risk", "생활권 밖 위험"),
    ]
    fills = {
        "safe_driving_score": "#DADADA",
        "familiar_zone_score": "#CFCFCF",
        "pattern_change_score": "#777777",
        "out_zone_behavior_risk": "#444444",
    }
    body: list[str] = []
    y = 142
    scale = 4.8
    for row in score_rows:
        body.append(text(58, y + 24, row["driver_id"], size=18, weight=800, color=BLACK))
        for idx, (key, label) in enumerate(metrics):
            bar_y = y + idx * 34
            value = float(row[key])
            body.append(text(188, bar_y + 21, label, size=15, color=MUTED))
            body.append(rect(330, bar_y + 5, 480, 18, fill="#F2F2F2", stroke="#E0E0E0"))
            body.append(rect(330, bar_y + 5, value * scale, 18, fill=fills[key], stroke=fills[key]))
            body.append(text(828, bar_y + 21, f"{value:.1f}", size=15, weight=700, color=BLACK))
        y += 154

    if score_rows:
        top_pattern = max(score_rows, key=lambda row: float(row["pattern_change_score"]))
        body.append(text(58, 620, "해석", size=18, weight=800, color=BLACK))
        body.append(
            text(
                118,
                620,
                f"{top_pattern['driver_id']}은 패턴 변화 점수가 가장 높아 직원용 리포트에서 우선 확인한다.",
                size=17,
            )
        )
    return base_svg(
        1100,
        680,
        "고객별 점수 비교",
        "모델이 생성한 점수를 고객별로 비교해 추가 리워드/케어 판단의 근거를 확인한다.",
        "\n".join(body),
    )


def decision_summary_svg(decision_rows: list[dict[str, str]]) -> str:
    body: list[str] = []
    y = 140
    headers = ["고객", "판단", "Care", "주요 사유"]
    widths = [150, 170, 90, 690]
    x = 48
    for header, width in zip(headers, widths):
        body.append(rect(x, y, width, 42, fill="#EFEFEF"))
        body.append(text(x + 14, y + 27, header, size=16, weight=800, color=BLACK))
        x += width
    y += 42

    for row in decision_rows:
        x = 48
        height = 96
        values = [
            row["driver_id"],
            row["decision"],
            "예" if row["care_trigger"] == "1" else "아니오",
            f"{row['reason_1']} / {row['reason_2']}",
        ]
        for idx, (value, width) in enumerate(zip(values, widths)):
            body.append(rect(x, y, width, height, fill=WHITE))
            size = 15 if idx == 3 else 16
            weight = 800 if idx in (0, 1) else 400
            body.append(text(x + 14, y + 32, value, size=size, weight=weight, color=BLACK if idx != 3 else TEXT))
            x += width
        y += height

    body.append(text(58, 510, "핵심", size=18, weight=800, color=BLACK))
    body.append(text(110, 510, "위험 고객을 보험료 패널티가 아니라 예방 케어 대상으로 전환한다.", size=17))
    return base_svg(
        1160,
        570,
        "최종 판단 결과",
        "score table을 decision table로 바꾼 결과이며, 고객별 안내 또는 직원용 리포트에 연결된다.",
        "\n".join(body),
    )


def write_summary_report(
    score_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    pattern_rows: list[dict[str, str]],
) -> None:
    decision_by_driver = {row["driver_id"]: row for row in decision_rows}
    pattern_by_driver = {row["driver_id"]: row for row in pattern_rows}
    decision_counts: dict[str, int] = {}
    for row in decision_rows:
        decision_counts[row["decision"]] = decision_counts.get(row["decision"], 0) + 1
    summary_text = ", ".join(f"{name} {count}명" for name, count in sorted(decision_counts.items())) or "판단 대상 없음"
    lines = [
        "# 모델 견본 결과 요약",
        "",
        "## 심사위원 질문 대응",
        "",
        "| 질문 | 제출 패키지의 답변 | 확인 산출물 |",
        "|---|---|---|",
        "| AI가 무엇을 했는가 | DBSCAN 방식 밀도 기반 클러스터링으로 고객별 생활권 중심을 만들고, 최근 trip vector가 baseline보다 얼마나 달라졌는지 이상탐지 점수로 계산했다 | `zone_feature_table.csv`, `pattern_change_score.csv` |",
        "| 왜 사고 예측이 아닌가 | 개인 사고 라벨 없이 과장된 예측을 하지 않고, 평소패턴 변화와 위험행동 증가를 분리해 예방 케어 후보만 찾는다 | `score_table.csv`, `decision_table.csv` |",
        "| 결과를 어떻게 설명하는가 | 고객별 score, care trigger, reason code, top change signal을 함께 남겨 직원용 리포트와 고객 안내 문구로 전환할 수 있게 했다 | `decision_table.csv`, `reports/model_demo_summary.md` |",
        "",
        "## 실행 결과",
        "",
        "| 고객 | Safe Driving | Familiar Zone | Pattern Change | Out-Zone Risk | 최종 판단 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in score_rows:
        decision = decision_by_driver[row["driver_id"]]["decision"]
        lines.append(
            f"| {row['driver_id']} | {float(row['safe_driving_score']):.1f} | "
            f"{float(row['familiar_zone_score']):.1f} | {float(row['pattern_change_score']):.1f} | "
            f"{float(row['out_zone_behavior_risk']):.1f} | {decision} |"
        )

    lines.extend(
        [
            "",
            "## 이상탐지 설명 신호",
            "",
            "| 고객 | 변화 점수 | 이상 여부 | 주요 변화 신호 | 모델 백엔드 |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in score_rows:
        pattern = pattern_by_driver[row["driver_id"]]
        lines.append(
            f"| {row['driver_id']} | {float(pattern['pattern_change_score']):.1f} | "
            f"{pattern['anomaly_flag']} | {signal_label(pattern['top_change_signal'])} | {pattern['pattern_model_backend']} |"
        )

    lines.extend(
        [
            "",
            "## 데이터 기준",
            "",
            "- 입력 CSV는 `docs/data-contract.md`의 표준 Trip schema를 기준으로 검증한다.",
            "- 팀원이 받은 공공 사업용차량 CSV는 `scripts/validate_trip_csv_mapping.py`로 원본 컬럼 매핑, 필수 컬럼 누락, 파이프라인 실행 가능 여부를 먼저 확인한다.",
            "- 원본 차량 식별자는 `driver_###` 형식으로 익명화하고, 원본 좌표는 생활권 feature 생성 뒤 최종 모델 feature table에 직접 남기지 않는다.",
            "- 현재 수치는 실제 보험료 산정값이 아니라 생활권 생성, 평소패턴 변화 감지, 예방 케어 판단 구조의 구현 견본이다.",
            "",
            "## 해석",
            "",
            f"- 이번 실행에서는 총 {len(decision_rows)}명의 판단 결과가 생성되었고, 결과 분포는 {summary_text}입니다.",
            "- 같은 운전자에 대해 baseline과 recent trip이 모두 있는 경우에만 생활권 안정성과 평소패턴 변화 해석이 유효합니다.",
            "- 단일 trip만 있는 운전자는 생활권 학습과 평소 대비 변화 감지에 필요한 기준 데이터가 부족하므로 최종 판단표에서 제외됩니다.",
            "",
            "## 발표에 사용할 문장",
            "",
            "기존 마일리지·착한운전 특약이 거리와 일반 안전점수 중심이라면, 이 모델은 DBSCAN 생활권과 평소패턴 이상탐지를 결합해 익숙한 생활권 안에서의 안정 운전은 추가 리워드로, 평소와 다른 위험 변화는 예방 케어로 분리합니다.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_analysis_outputs() -> dict[str, Path]:
    score_rows = read_csv(SCORE_TABLE)
    decision_rows = read_csv(DECISION_TABLE)
    pattern_rows = read_csv(PATTERN_TABLE)
    outputs = {
        "score_comparison": FIGURE_DIR / "04_driver_score_comparison.svg",
        "decision_summary": FIGURE_DIR / "05_decision_result_summary.svg",
        "summary_report": REPORT_PATH,
    }
    write_svg(outputs["score_comparison"], score_comparison_svg(score_rows))
    write_svg(outputs["decision_summary"], decision_summary_svg(decision_rows))
    write_summary_report(score_rows, decision_rows, pattern_rows)
    return outputs


def main() -> int:
    outputs = generate_analysis_outputs()
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate analysis-result visuals from model outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCORE_TABLE = ROOT / "data" / "processed" / "score_table.csv"
DECISION_TABLE = ROOT / "data" / "processed" / "decision_table.csv"
FIGURE_DIR = ROOT / "reports" / "figures"
REPORT_PATH = ROOT / "reports" / "model_demo_summary.md"

FONT = "Apple SD Gothic Neo, Noto Sans KR, Noto Sans CJK KR, Arial, sans-serif"
BLACK = "#111111"
TEXT = "#222222"
MUTED = "#666666"
LINE = "#BBBBBB"
FILL = "#F7F7F7"
WHITE = "#FFFFFF"


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

    body.append(text(58, 620, "해석", size=18, weight=800, color=BLACK))
    body.append(text(118, 620, "driver_003은 패턴 변화와 생활권 밖 위험이 동시에 높아 예방 케어 대상으로 분리된다.", size=17))
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


def write_summary_report(score_rows: list[dict[str, str]], decision_rows: list[dict[str, str]]) -> None:
    decision_by_driver = {row["driver_id"]: row for row in decision_rows}
    lines = [
        "# 모델 견본 결과 요약",
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
            "## 해석",
            "",
            "- `driver_001`은 생활권 중심 주행과 낮은 위험행동으로 추가 리워드 대상이다.",
            "- `driver_002`는 생활권 밖 주행이 일부 있지만 위험행동 변화가 크지 않아 기본 유지 대상이다.",
            "- `driver_003`은 생활권 밖 주행, 위험행동, 평소패턴 변화가 동시에 높아 예방 케어 대상이다.",
            "",
            "## 발표에 사용할 문장",
            "",
            "이 모델은 사고 발생을 직접 예측하기보다, 고객의 평소 생활권과 운전패턴을 기준으로 최근 변화가 커진 고객을 찾아 추가 리워드 또는 예방 케어로 연결합니다.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_analysis_outputs() -> dict[str, Path]:
    score_rows = read_csv(SCORE_TABLE)
    decision_rows = read_csv(DECISION_TABLE)
    outputs = {
        "score_comparison": FIGURE_DIR / "04_driver_score_comparison.svg",
        "decision_summary": FIGURE_DIR / "05_decision_result_summary.svg",
        "summary_report": REPORT_PATH,
    }
    write_svg(outputs["score_comparison"], score_comparison_svg(score_rows))
    write_svg(outputs["decision_summary"], decision_summary_svg(decision_rows))
    write_summary_report(score_rows, decision_rows)
    return outputs


def main() -> int:
    outputs = generate_analysis_outputs()
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

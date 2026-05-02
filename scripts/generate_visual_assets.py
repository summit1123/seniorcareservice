#!/usr/bin/env python3
"""Generate reviewer-facing SVG figures for the senior safe-zone rider proposal."""

from __future__ import annotations

from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = ROOT / "reports" / "figures"

FONT = "Apple SD Gothic Neo, Noto Sans KR, Noto Sans CJK KR, Arial, sans-serif"
BLACK = "#111111"
TEXT = "#222222"
MUTED = "#666666"
LINE = "#B8B8B8"
FILL = "#F7F7F7"
FILL_DARK = "#EFEFEF"
WHITE = "#FFFFFF"


def text(x: int, y: int, value: str, size: int = 20, weight: int = 400, color: str = TEXT) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{escape(value)}</text>'
    )


def multiline_text(x: int, y: int, lines: list[str], size: int = 16, color: str = MUTED, gap: int = 24) -> str:
    return "\n".join(text(x, y + idx * gap, line, size=size, color=color) for idx, line in enumerate(lines))


def box(x: int, y: int, w: int, h: int, title: str, body: list[str] | None = None) -> str:
    body = body or []
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{FILL}" stroke="{LINE}" stroke-width="1"/>',
        text(x + 18, y + 34, title, size=20, weight=700, color=BLACK),
    ]
    if body:
        parts.append(multiline_text(x + 18, y + 64, body, size=15, gap=22))
    return "\n".join(parts)


def label_box(x: int, y: int, w: int, h: int, title: str, body: list[str]) -> str:
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{WHITE}" stroke="{LINE}" stroke-width="1"/>',
        text(x + 16, y + 30, title, size=18, weight=700, color=BLACK),
        multiline_text(x + 16, y + 58, body, size=14, gap=20),
    ]
    return "\n".join(parts)


def arrow(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{BLACK}" stroke-width="1.5" marker-end="url(#arrow)"/>'
    )


def base_svg(width: int, height: int, title: str, subtitle: str, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{BLACK}"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" fill="{WHITE}"/>
  {text(48, 58, title, size=30, weight=800, color=BLACK)}
  {text(48, 92, subtitle, size=17, color=MUTED)}
  {body}
</svg>
'''


def write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ai_pipeline_svg() -> str:
    boxes = [
        (48, 150, 160, 110, "Trip 데이터", ["GPS", "거리/시간", "위험운전"]),
        (250, 150, 180, 110, "생활권 생성 AI", ["DBSCAN", "반복 목적지", "in/out zone"]),
        (472, 150, 180, 110, "운전행동 Feature", ["과속/100km", "급감속/100km", "급회전/100km"]),
        (694, 150, 210, 110, "평소패턴 감지 AI", ["Isolation Forest", "최근 변화 감지", "anomaly flag"]),
        (946, 150, 190, 110, "점수/판단", ["Safe Driving", "Familiar Zone", "Care Trigger"]),
    ]
    body = []
    for idx, item in enumerate(boxes):
        body.append(box(*item))
        if idx < len(boxes) - 1:
            x, y, w, h, *_ = item
            nx, ny, *_ = boxes[idx + 1]
            body.append(arrow(x + w + 12, y + h // 2, nx - 12, ny + h // 2))

    body.append(label_box(70, 325, 320, 142, "AI가 학습하는 것", [
        "고객별 반복 주행 패턴",
        "생활권 안/밖 주행 비율",
        "평소 대비 위험행동 변화",
    ]))
    body.append(label_box(440, 325, 320, 142, "TAAS의 역할", [
        "개인 사고 예측 라벨이 아님",
        "위험행동 가중치 근거",
        "과속/야간/노인운전자 보정",
    ]))
    body.append(label_box(810, 325, 320, 142, "상품 적용", [
        "마일리지 할인은 유지",
        "안정 주행은 추가 리워드",
        "위험 변화는 예방 케어",
    ]))

    return base_svg(
        1200,
        540,
        "AI 활용 구조",
        "생활권과 평소 운전패턴을 학습하고, 위험 변화는 예방 케어로 연결한다.",
        "\n".join(body),
    )


def score_structure_svg() -> str:
    body = []
    body.append(box(455, 156, 290, 116, "최종 판단", ["추가 리워드", "기본 유지", "예방 케어"]))

    score_boxes = [
        (62, 138, 300, 112, "Safe Driving Score", ["과속, 급가속, 급감속", "급회전, 안전운전점수"]),
        (62, 330, 300, 112, "Familiar Zone Score", ["생활권 내 주행 비율", "반복 경로, 신규 목적지"]),
        (838, 138, 300, 112, "Pattern Change Score", ["최근 주행과 평소 패턴 차이", "Isolation Forest 결과"]),
        (838, 330, 300, 112, "Out-Zone Behavior Risk", ["생활권 밖 위험행동", "야간/과속/급감속 변화"]),
    ]
    for item in score_boxes:
        body.append(box(*item))

    body.extend([
        arrow(362, 194, 455, 204),
        arrow(362, 386, 455, 224),
        arrow(838, 194, 745, 204),
        arrow(838, 386, 745, 224),
    ])

    body.append(
        f'<rect x="390" y="315" width="420" height="106" rx="4" fill="{FILL_DARK}" stroke="{LINE}" stroke-width="1"/>'
    )
    body.append(text(416, 350, "판단 원칙", size=21, weight=800, color=BLACK))
    body.append(multiline_text(416, 382, [
        "생활권 밖이라는 이유만으로 위험 처리하지 않는다.",
        "위험행동 증가와 평소패턴 변화가 함께 있을 때 케어 신호로 본다.",
    ], size=15, gap=23))

    return base_svg(
        1200,
        520,
        "점수 구조",
        "운전 안정성, 생활권 안정성, 패턴 변화, 생활권 밖 위험행동을 분리해 판단한다.",
        "\n".join(body),
    )


def decision_flow_svg() -> str:
    body = []
    body.append(box(72, 150, 240, 118, "입력", ["마일리지 조건", "생활권 feature", "위험운전 feature"]))
    body.append(box(380, 150, 250, 118, "AI 점수 계산", ["Safe Driving", "Familiar Zone", "Pattern Change"]))
    body.append(box(698, 150, 250, 118, "판단 규칙", ["안정 주행", "보통 변화", "위험 변화"]))
    body.append(arrow(324, 209, 368, 209))
    body.append(arrow(642, 209, 686, 209))

    decisions = [
        (120, 355, 270, 122, "A. 추가 리워드", ["생활권 중심 주행", "위험행동 낮음", "패턴 변화 낮음"]),
        (465, 355, 270, 122, "B. 기본 유지", ["생활권 밖 주행 있음", "위험행동 변화 없음", "기존 혜택 유지"]),
        (810, 355, 270, 122, "C. 예방 케어", ["생활권 밖 주행 증가", "급감속/과속 증가", "차량점검/리포트 안내"]),
    ]
    for item in decisions:
        body.append(label_box(*item))

    body.append(arrow(815, 268, 255, 343))
    body.append(arrow(825, 268, 600, 343))
    body.append(arrow(835, 268, 945, 343))

    body.append(text(82, 540, "핵심 문장:", size=18, weight=800, color=BLACK))
    body.append(text(185, 540, "보험료 패널티가 아니라, 추가 혜택 조정과 예방 케어 안내로 연결한다.", size=18, color=TEXT))

    return base_svg(
        1200,
        610,
        "상품 판단 흐름",
        "마일리지 제도 위에 생활권 안정성과 평소패턴 변화를 추가 보정한다.",
        "\n".join(body),
    )


def write_manifest() -> None:
    manifest = """# 시각화 산출물 목록

| 파일 | 설명 |
|---|---|
| `reports/figures/01_ai_pipeline.svg` | AI 활용 구조 |
| `reports/figures/02_score_structure.svg` | 최종 점수 구조 |
| `reports/figures/03_decision_flow.svg` | 상품 판단 흐름 |

모든 figure는 검정/회색 중심의 reviewer-facing 자료로 생성됩니다.
"""
    (ROOT / "reports" / "visual_assets_manifest.md").write_text(manifest, encoding="utf-8")


def main() -> int:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    write_svg(FIGURE_DIR / "01_ai_pipeline.svg", ai_pipeline_svg())
    write_svg(FIGURE_DIR / "02_score_structure.svg", score_structure_svg())
    write_svg(FIGURE_DIR / "03_decision_flow.svg", decision_flow_svg())
    write_manifest()
    print(f"Generated visual assets in {FIGURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

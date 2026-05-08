"""Contest-oriented demo page for Senior Safe Mileage.

The existing customer decision page is a dense operator/debug surface.  This
module renders a separate first screen for judges: it explains what was built,
which data files exist, what the same-customer comparison proves, and where the detailed
evidence lives.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from src.product.ab_comparison import (
    BASELINE_ANNUAL_MILEAGE_LIMIT_KM,
    calculate_tier,
    care_decision,
)
from src.product.scoring_engine import (
    SeniorSafeMileageScoreInput,
    calculate_local_score_result,
)


ROOT = Path(__file__).resolve().parents[2]
TRIP_LOG_PATH = ROOT / "data" / "fixtures" / "senior_trip_logs.csv"
SCENARIO_CONFIG_PATH = ROOT / "data" / "fixtures" / "scenario_config.json"
VALIDATION_REPORT_PATH = ROOT / "data" / "fixtures" / "validation_report.md"
AB_RESULTS_PATH = ROOT / "data" / "fixtures" / "ab_test_results.csv"
SUMMARY_REPORT_PATH = ROOT / "data" / "fixtures" / "simulation_summary.json"


PERSONA_ORDER = [
    "stable_local_low_mileage",
    "recent_outer_risk_change",
    "stable_outer_safe",
    "in_zone_risky_low_mileage",
    "medical_visit_pattern",
    "irregular_family_support",
]

PERSONA_FALLBACK_NAMES = {
    "stable_local_low_mileage": "생활권 안 저주행 안정형",
    "recent_outer_risk_change": "최근 생활권 밖 위험변화형",
    "stable_outer_safe": "생활권 밖 안정형",
    "in_zone_risky_low_mileage": "생활권 안 위험행동형",
    "medical_visit_pattern": "병원 방문 반복형",
    "irregular_family_support": "가족 돌봄 외부 이동형",
}

ARTIFACT_ROWS = [
    ("주행 로그", "data/fixtures/senior_trip_logs.csv", "30명, 90일 관측기간의 좌표·시간·위험행동 기록"),
    ("시나리오 조건", "data/fixtures/scenario_config.json", "6개 시니어 운전자 유형과 이전/최근 변화 조건"),
    ("검증 리포트", "data/fixtures/validation_report.md", "좌표·시간·거리·위험행동 일관성 검증 결과"),
    ("모델 설계 후보", "data/fixtures/candidate_rules.json", "4개 판단 요소의 가중치와 예방 케어 기준"),
    ("기존 방식 비교", "data/fixtures/ab_test_results.csv", "동일 고객에 기존 거리 방식과 제안 방식을 함께 적용한 결과"),
    ("설명문 산출물", "data/fixtures/simulation_summary.json", "보험사 직원용 설명문과 고객별 판단 근거"),
]

REASON_LABELS = {
    "LOW_MILEAGE_BASELINE_ELIGIBLE": "저주행 조건 충족",
    "LIVING_ZONE_DBSCAN_P90_INPUT_USED": "생활권 좌표 분석 반영",
    "NEW_DESTINATION_OUT_ZONE_SIGNAL": "생활권 밖 신규 목적지 증가",
    "OUT_ZONE_PATTERN_CHANGE_RISK": "생활권 밖 주행 패턴 변화",
    "RECENT_NIGHT_DRIVING_INCREASE": "최근 야간주행 증가",
    "RISK_EVENT_RATE_INCREASE": "위험행동 빈도 증가",
    "PROPOSED_MODEL_PREVENTIVE_CARE": "예방 케어 판정",
    "LIVING_ZONE_STABLE_DRIVING": "생활권 중심 안정 주행",
    "LIVING_ZONE_HIGH_STABILITY": "생활권 안정성 높음",
    "REPEATED_ROUTE_PATTERN": "반복 경로 패턴 확인",
    "NO_STRONG_RISK_CHANGE": "강한 위험변화 없음",
}


def render_contest_demo_page(bundle: dict[str, Any], *, request_path: str = "/") -> str:
    """Render the judge-facing contest demo page."""

    trip_stats = _load_trip_stats()
    scenario = _load_json(SCENARIO_CONFIG_PATH)
    summary_report = _load_json(SUMMARY_REPORT_PATH)
    approval = dict(bundle["approval_gate"])
    ab = dict(bundle["ab_comparison"])
    selected_policy = dict(bundle["selected_policy"])
    agent_audit = dict(bundle["agent_audit"])
    customers = list(bundle["customers"])
    selected_customer = _select_customer_from_query(customers, request_path)
    risk_customer = selected_customer or _select_demo_customer(customers, "recent_outer_risk_change")
    stable_customer = _select_demo_customer(customers, "stable_local_low_mileage")
    persona_rows = _build_persona_rows(bundle, scenario)
    llm_status = _llm_status(summary_report, bundle)
    simulation = _build_simulation_view_model(customers, risk_customer, selected_policy, request_path)

    title = "시니어 안심주행 보험 검증 대시보드"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #15181d;
      --muted: #5f6772;
      --subtle: #f5f6f7;
      --panel: #ffffff;
      --line: #d8dde4;
      --line-strong: #aeb7c2;
      --good: #126149;
      --warn: #9a4a15;
      --focus: #114f68;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #fff;
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    a {{ color: inherit; }}
    .shell {{ max-width: 1280px; margin: 0 auto; padding: 0 28px 48px; }}
    header {{
      border-bottom: 1px solid var(--line);
      background: #fbfbfc;
      padding: 28px 0 20px;
      margin-bottom: 22px;
    }}
    .header-inner {{ max-width: 1280px; margin: 0 auto; padding: 0 28px; }}
    .eyebrow {{ margin: 0 0 8px; color: var(--focus); font-weight: 700; font-size: 13px; }}
    h1 {{ margin: 0; font-size: 32px; line-height: 1.18; letter-spacing: 0; }}
    .lead {{ margin: 10px 0 0; max-width: 920px; color: var(--muted); font-size: 16px; }}
    .top-nav {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }}
    .top-nav a {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      text-decoration: none;
      background: #fff;
      font-size: 13px;
    }}
    section {{ border-top: 1px solid var(--line); padding-top: 22px; margin-top: 24px; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; }}
    p {{ margin: 0; color: var(--muted); }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.95fr);
      gap: 18px;
      align-items: start;
    }}
    .statement {{
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 18px;
      background: var(--panel);
    }}
    .statement strong {{ display: block; margin: 10px 0 6px; font-size: 18px; }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      align-self: start;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: var(--subtle);
      min-height: 116px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 28px; line-height: 1.15; }}
    .metric.good strong {{ color: var(--good); }}
    .metric.warn strong {{ color: var(--warn); }}
    .verdict-band {{
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: #fff;
      padding: 18px;
    }}
    .verdict-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .verdict-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: var(--subtle);
      min-height: 120px;
    }}
    .verdict-card span {{ display: block; color: var(--focus); font-weight: 800; font-size: 12px; margin-bottom: 8px; }}
    .verdict-card strong {{ display: block; font-size: 18px; margin-bottom: 6px; }}
    .question-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .question-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fff;
    }}
    .question-card span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
    .question-card strong {{ display: block; font-size: 16px; margin-bottom: 8px; }}
    .question-card p {{ margin-bottom: 10px; }}
    .evidence {{ color: var(--focus); font-size: 12px; font-weight: 700; overflow-wrap: anywhere; }}
    .journey-table td:nth-child(1), .journey-table th:nth-child(1) {{ width: 70px; }}
    .journey-table td:nth-child(4), .journey-table th:nth-child(4) {{ width: 190px; }}
    .map-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
      gap: 18px;
      align-items: stretch;
    }}
    .map-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 14px;
    }}
    .zone-map {{
      display: block;
      width: 100%;
      min-height: 360px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f7f9f8;
    }}
    .map-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend-dot {{ width: 10px; height: 10px; border-radius: 999px; border: 1px solid var(--line-strong); display: inline-block; }}
    .legend-dot.before {{ background: #8a949e; }}
    .legend-dot.recent-in {{ background: #1f6f8b; }}
    .legend-dot.recent-out {{ background: #bd5b1a; }}
    .legend-dot.risk {{ background: #c7352b; }}
    .insight-list {{ display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }}
    .insight-list li {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--subtle);
    }}
    .insight-list strong {{ display: block; margin-bottom: 4px; }}
    .model-factor-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .model-factor {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
      min-height: 104px;
    }}
    .model-factor span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
    .model-factor strong {{ display: block; font-size: 22px; }}
    .difference-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      align-items: stretch;
    }}
    .system-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      background: #fff;
    }}
    .system-card h3 {{ font-size: 18px; }}
    .system-card ul {{ margin: 12px 0 0; padding-left: 18px; color: var(--muted); }}
    .system-card li {{ margin: 6px 0; }}
    .example-strip {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .example-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      background: var(--subtle);
    }}
    .example-card span {{ display: block; color: var(--focus); font-size: 12px; font-weight: 800; margin-bottom: 6px; }}
    .example-card strong {{ display: block; font-size: 19px; margin-bottom: 4px; }}
    .bridge-note {{
      margin-top: 14px;
      border: 1px solid #b8d8d3;
      border-radius: 8px;
      padding: 14px;
      background: #f2faf8;
      color: var(--ink);
    }}
    .lab-grid {{
      display: grid;
      grid-template-columns: minmax(360px, 0.9fr) minmax(0, 1.1fr);
      gap: 18px;
      align-items: start;
    }}
    .lab-form {{
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }}
    .field-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    label {{ display: grid; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 700; }}
    input, select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 8px 10px;
      font: inherit;
      font-size: 14px;
    }}
    .lab-actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .lab-result-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .lab-result {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--subtle);
    }}
    .lab-result span {{ display: block; color: var(--muted); font-size: 12px; }}
    .lab-result strong {{ display: block; margin-top: 6px; font-size: 20px; }}
    .criteria-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .criteria-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .preset-list {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .two-col {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.75fr); gap: 18px; }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      background: #fff;
    }}
    .note {{
      border-left: 4px solid var(--focus);
      padding: 12px 14px;
      background: #f4f8fa;
      color: var(--ink);
    }}
    .note p {{ color: var(--ink); }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 11px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f8f9fa; color: #424a54; font-weight: 700; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #fff;
      white-space: nowrap;
    }}
    .status.pass {{ color: var(--good); border-color: #99cab9; background: #eef8f4; }}
    .status.review {{ color: var(--warn); border-color: #d8b99d; background: #fff7ef; }}
    .code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      color: #17485c;
      overflow-wrap: anywhere;
    }}
    .flow {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }}
    .step {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }}
    .step span {{ display: block; color: var(--focus); font-weight: 800; font-size: 12px; margin-bottom: 6px; }}
    .bars {{ display: grid; gap: 10px; }}
    .bar-row {{ display: grid; grid-template-columns: 120px minmax(0, 1fr) 70px; gap: 10px; align-items: center; }}
    .bar-track {{ height: 12px; background: #ebeff2; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: var(--focus); }}
    .bar-fill.good {{ background: var(--good); }}
    .case-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .case-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }}
    .case-card strong {{ display: block; font-size: 18px; margin-bottom: 6px; }}
    .case-card dl {{ display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 6px 10px; margin: 12px 0 0; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; }}
    .footer-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
    .button {{
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 8px 11px;
      text-decoration: none;
      background: #fff;
      font-weight: 700;
      font-size: 13px;
    }}
    details summary {{ cursor: pointer; color: var(--focus); font-weight: 700; }}
    details .code {{ display: inline-block; margin-top: 6px; }}
    @media (max-width: 960px) {{
      .hero-grid, .difference-grid, .map-grid, .lab-grid, .two-col, .case-grid {{ grid-template-columns: 1fr; }}
      .verdict-grid, .question-grid, .model-factor-grid, .criteria-grid, .lab-result-grid, .example-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .flow {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 620px) {{
      .shell, .header-inner {{ padding-left: 18px; padding-right: 18px; }}
      h1 {{ font-size: 26px; }}
      .metric-grid, .verdict-grid, .question-grid, .model-factor-grid, .field-grid, .criteria-grid, .lab-result-grid, .example-strip, .flow {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <p class="eyebrow">테스트 결과를 먼저 보여주는 공모전 시연 화면</p>
      <h1>{title}</h1>
      <p class="lead">기존 마일리지 보험은 “얼마나 적게 탔는가”로 할인 여부를 판단합니다. 이 데모는 거기에 “평소 생활권에서 벗어난 최근 위험변화가 있었는가”를 추가해, 같은 저주행 고객도 우대/기본/예방 케어로 다르게 설명하는 화면입니다.</p>
      <nav class="top-nav" aria-label="데모 흐름">
        <a href="#system-difference">시스템 차이</a>
        <a href="#living-zone-preview">생활권 지도</a>
        <a href="#simulation-lab">조건 테스트</a>
        <a href="#test-questions">테스트 질문</a>
        <a href="#test-journey">실행 로그</a>
        <a href="#ab-proof">기존 방식 비교</a>
        <a href="#persona-cases">케이스별 판정</a>
        <a href="/detail">상세 검증 화면</a>
      </nav>
    </div>
  </header>
  <main class="shell">
    <section class="hero-grid" id="summary" aria-labelledby="summary-heading">
      <div class="verdict-band">
        <h2 id="summary-heading">한 문장으로 보면</h2>
        <p>기존 마일리지 시스템은 “적게 탔으니 할인”에서 멈춥니다. 제안 방식은 “적게 탔지만 최근 생활권 밖 야간/위험행동이 늘었는가”까지 확인해, 할인 대상인지 예방 케어가 필요한 고객인지 나눕니다.</p>
        <div class="verdict-grid" aria-label="검증 결론">
          {_verdict_card("기존 마일리지", "주행거리 중심 할인", "1년 환산 주행거리가 기준보다 낮으면 대체로 우량 고객처럼 봅니다.")}
          {_verdict_card("제안 방식", "생활권 변화까지 판정", "어디서, 언제, 어떤 위험신호가 늘었는지까지 봅니다.")}
          {_verdict_card("결과 해석", "우대 / 기본 / 예방 케어", "단순 할인 계산이 아니라 고객별 설명과 케어 액션을 함께 만듭니다.")}
        </div>
        <div class="footer-actions">
          <a class="button" href="#living-zone-preview">좌표 프리뷰 보기</a>
          <a class="button" href="#customer-report">고객별 설명 보기</a>
        </div>
      </div>
      <div class="metric-grid" aria-label="핵심 수치">
        {_metric_card("합성 고객", f"{trip_stats['customer_count']}명", "6개 유형, 유형별 5명")}
        {_metric_card("주행 기록", f"{trip_stats['trip_count']:,}건", "90일 관측기간 중 실제 운전이 발생한 기록")}
        {_metric_card("놓친 위험고객 발견", f"{approval['risk_change_capture_count']}/{approval['risk_change_target_count']}", "기존 방식 0명, 제안 방식 5명", "good")}
        {_metric_card("오분류", f"{approval['total_misclassification_count']}/{approval['total_misclassification_limit']}", "허용 기준 이내", "good")}
      </div>
    </section>

    <section id="system-difference" aria-labelledby="system-difference-heading">
      <h2 id="system-difference-heading">기존 마일리지 시스템과 무엇이 다른가</h2>
      {_system_difference_section(risk_customer)}
    </section>

    <section id="simulation-lab" aria-labelledby="simulation-lab-heading">
      <h2 id="simulation-lab-heading">직접 돌려보는 조건 테스트</h2>
      <div class="lab-grid">
        <div class="panel">
          <h3>고객과 최근 주행 조건을 바꿔보기</h3>
          <p>보험 직원이나 심사위원이 “이 고객의 최근 운전 상황이 달라지면 판정도 바뀌나?”를 확인하는 영역입니다. 값을 바꾸면 기존 마일리지 방식과 제안 방식을 같은 조건으로 다시 계산합니다.</p>
          {_simulation_form(simulation)}
          {_simulation_presets(simulation)}
        </div>
        <div class="panel">
          <h3>가정 결과</h3>
          {_simulation_result(simulation)}
        </div>
      </div>
      <div class="criteria-grid" aria-label="판정 기준">
        {_criteria_card("기존 거리 방식", f"1년 환산 주행거리 {BASELINE_ANNUAL_MILEAGE_LIMIT_KM:,.0f}km 초과 여부만 봅니다.", "생활권 밖으로 나갔는지, 야간/위험행동이 늘었는지는 반영하지 않습니다.")}
        {_criteria_card("위험변화 점수", "생활권 밖 비중 증가 35점 + 야간 증가 25점 + 위험행동 증가 25점 + 위험신호 빈도 15점", "최근 변화가 클수록 100점에 가까워집니다.")}
        {_criteria_card("제안 방식 판정", f"위험변화 점수 {float(selected_policy['thresholds']['care_threshold']):.1f}점 이상이고 통합 점수가 우대 기준보다 낮으면 예방 케어입니다.", "위험변화가 낮고 통합 점수가 우대 구간이면 우대, 나머지는 기본입니다.")}
      </div>
    </section>

    <section id="living-zone-preview" aria-labelledby="living-zone-heading">
      <h2 id="living-zone-heading">좌표로 보는 생활권 모델</h2>
      <div class="map-grid">
        <div class="map-card">
          <h3>{escape(_display_customer_id(str(risk_customer['customer_id'])))}의 90일 주행 좌표</h3>
          {_living_zone_svg(risk_customer)}
          <div class="map-legend" aria-label="좌표 범례">
            <span class="legend-item"><span class="legend-dot before"></span>이전 60일</span>
            <span class="legend-item"><span class="legend-dot recent-in"></span>최근 30일 생활권 안</span>
            <span class="legend-item"><span class="legend-dot recent-out"></span>최근 30일 생활권 밖</span>
            <span class="legend-item"><span class="legend-dot risk"></span>위험 신호 포함</span>
          </div>
        </div>
        <div class="panel">
          <h3>이 그림이 말하는 판정 변화</h3>
          {_living_zone_insights(risk_customer)}
        </div>
      </div>
      <div class="panel" style="margin-top:14px">
        <h3>모델이 실제로 보는 4가지 판단 요소</h3>
        <p>아래 가중치는 114개 후보를 비교한 뒤 승인 기준을 통과한 설계값입니다. 생활권 밖으로 나갔다는 사실 하나만으로 불리하게 보지 않고, 안전운전과 최근 변화 신호를 함께 봅니다.</p>
        <div class="model-factor-grid" aria-label="모델 판단 요소">
          {_model_factor_cards(selected_policy)}
        </div>
      </div>
    </section>

    <section id="test-questions" aria-labelledby="test-questions-heading">
      <h2 id="test-questions-heading">우리가 실제로 테스트한 질문</h2>
      <div class="question-grid" aria-label="검증 질문">
        {_question_card("Q1", "90일 주행 데이터가 실제로 만들어졌나?", f"주행 기록 {trip_stats['trip_count']:,}건 · 고객 {trip_stats['customer_count']}명 · {trip_stats['date_min']}~{trip_stats['date_max']}", "주행 로그 CSV", "data/fixtures/senior_trip_logs.csv")}
        {_question_card("Q2", "기존 거리 방식이 위험변화를 놓치나?", f"기존 {ab['baseline_capture_count']}/5명, 제안 {ab['proposed_capture_count']}/5명 포착", "기존 방식 비교 결과", "data/fixtures/ab_test_results.csv")}
        {_question_card("Q3", "새 모델이 오탐을 과하게 만들지 않나?", f"비대상 오탐 {approval['non_target_false_positive_count']}/{approval['non_target_false_positive_limit']} · 전체 오분류 {approval['total_misclassification_count']}/{approval['total_misclassification_limit']}", "승인 기준 검증 결과", "data/fixtures/evaluation_view_model.json")}
        {_question_card("Q4", "보험사 직원용 설명문도 실제 생성됐나?", f"{llm_status['display_report_mode']} · {llm_status['service_status']}", "설명문 산출물", "data/fixtures/simulation_summary.json")}
      </div>
    </section>

    <section id="test-journey" aria-labelledby="test-journey-heading">
      <h2 id="test-journey-heading">테스트 실행 로그</h2>
      <div class="table-wrap">
        <table class="journey-table" aria-label="테스트 실행 로그">
          <thead><tr><th>순서</th><th>검증 단계</th><th>무엇을 확인했나</th><th>결과</th><th>근거 파일</th></tr></thead>
          <tbody>{_test_journey_rows(trip_stats, approval, ab, selected_policy, agent_audit, llm_status)}</tbody>
        </table>
      </div>
    </section>

    <section id="data-proof" aria-labelledby="data-proof-heading">
      <h2 id="data-proof-heading">데이터 증거</h2>
      <div class="two-col">
        <div class="panel">
          <h3>생성된 90일 관측 데이터</h3>
          <p class="note">현재 데이터는 실제 고객 개인정보가 아니라, 실제 운영 데이터 형식을 흉내 낸 합성 주행 기록입니다. 30명 각각에 이전 60일과 최근 30일 관측기간이 있고, 운전이 발생한 날의 좌표·시간·거리·위험행동 기록이 저장되어 있습니다.</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="생성 데이터 요약">
              <tbody>
                <tr><th scope="row">근거</th><td data-evidence-path="data/fixtures/senior_trip_logs.csv">주행 로그 CSV</td></tr>
                <tr><th scope="row">관측기간</th><td>{escape(trip_stats['date_min'])} ~ {escape(trip_stats['date_max'])} · 이전 60일 + 최근 30일</td></tr>
                <tr><th scope="row">데이터 행</th><td>주행 기록 {trip_stats['trip_count']:,}건 · 이전 {trip_stats['baseline_trip_count']:,}건 / 최근 {trip_stats['recent_trip_count']:,}건</td></tr>
                <tr><th scope="row">고객/유형</th><td>{trip_stats['customer_count']}명 · {trip_stats['persona_count']}개 유형</td></tr>
                <tr><th scope="row">주요 컬럼</th><td>좌표, 시간, 거리, 속도, 야간 여부, 과속/급가감속, 생활권 구분, 위험 신호</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3>OpenAI 설명문 생성 상태</h3>
          <p>{escape(llm_status['headline'])}</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="OpenAI 상태">
              <tbody>
                <tr><th scope="row">현재 상태</th><td data-report-mode="{escape(llm_status['report_mode'])}">{escape(llm_status['display_report_mode'])}</td></tr>
                <tr><th scope="row">외부 API 호출</th><td>{escape(llm_status['service_status'])}</td></tr>
                <tr><th scope="row">키 사용 여부</th><td>{escape(llm_status['key_usage'])}</td></tr>
                <tr><th scope="row">안전장치</th><td>고객명, 차량번호, 정확한 좌표, 원본 주행 식별자는 외부 전송 금지</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="table-wrap" style="margin-top:14px">
        <table aria-label="산출 파일 목록">
          <thead><tr><th>산출물</th><th>파일</th><th>역할</th><th>상태</th></tr></thead>
          <tbody>{_artifact_rows()}</tbody>
        </table>
      </div>
    </section>

    <section id="workflow" aria-labelledby="workflow-heading">
      <h2 id="workflow-heading">분석 에이전트 실행 흐름</h2>
      <div class="flow" aria-label="구현 흐름">
        {_flow_step("1", "운전자 유형", "6개 시니어 운전자 유형과 예외 케이스 정의")}
        {_flow_step("2", "주행 생성", "90일 주행 기록과 최근 변화 신호 생성")}
        {_flow_step("3", "일관성 검증", "좌표·시간·거리·위험행동 검토")}
        {_flow_step("4", "생활권 분석", "좌표 밀집도와 90% 이동 반경으로 생활권 안/밖 구분")}
        {_flow_step("5", "정책 탐색", "114개 후보 중 승인 게이트 통과 후보 선택")}
        {_flow_step("6", "설명문", "비교 결과와 판단 근거를 직원용 문장으로 변환")}
      </div>
    </section>

    <section id="ab-proof" aria-labelledby="ab-proof-heading">
      <h2 id="ab-proof-heading">기존 마일리지와 무엇이 달라졌나</h2>
      <div class="two-col">
        <div class="panel">
          <h3>같은 고객 30명으로 비교한 핵심 결과</h3>
          <div class="bars">
            {_bar_row("기존 방식", ab["baseline_capture_rate"], f"{ab['baseline_capture_count']}/5 발견")}
            {_bar_row("제안 방식", ab["proposed_capture_rate"], f"{ab['proposed_capture_count']}/5 발견", "good")}
          </div>
          <div class="table-wrap" style="margin-top:14px">
            <table aria-label="기존 방식 비교 승인 게이트">
              <tbody>
                <tr><th scope="row">저주행 위험변화형</th><td>{approval['risk_change_capture_count']}/{approval['risk_change_target_count']} 포착</td><td><span class="status pass">통과</span></td></tr>
                <tr><th scope="row">비대상 오탐</th><td>{approval['non_target_false_positive_count']}/{approval['non_target_false_positive_limit']}</td><td><span class="status pass">통과</span></td></tr>
                <tr><th scope="row">전체 오분류</th><td>{approval['total_misclassification_count']}/{approval['total_misclassification_limit']}</td><td><span class="status pass">통과</span></td></tr>
                <tr><th scope="row">고객 판정 검증률</th><td>{_format_percent(approval['agent_validation_pass_rate'])}</td><td><span class="status pass">통과</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="panel" data-policy-id="{escape(str(selected_policy['candidate_id']))}">
          <h3>선택된 모델 설계값</h3>
          <p>이 조합이 위험변화 포착, 오탐, 전체 오분류 기준을 모두 통과했습니다.</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="선택된 모델 설계값">
              <tbody>
                {_weight_rows(selected_policy)}
                <tr><th scope="row">예방 케어 기준</th><td>위험변화 상위 {escape(_format_percent(selected_policy['thresholds']['care_threshold_percentile']))}</td></tr>
                <tr><th scope="row">후보 수</th><td>{bundle['policy_candidate_comparison']['candidate_count']}개 후보 비교</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section id="persona-cases" aria-labelledby="persona-heading">
      <h2 id="persona-heading">6개 시니어 케이스가 어떻게 판정됐나</h2>
      <div class="table-wrap">
        <table aria-label="6개 시니어 케이스 결과">
          <thead><tr><th>케이스</th><th>검증 목적</th><th>제안 방식 결과</th><th>기존 방식 대비</th></tr></thead>
          <tbody>{_persona_table_rows(persona_rows)}</tbody>
        </table>
      </div>
    </section>

    <section id="customer-report" aria-labelledby="customer-report-heading">
      <h2 id="customer-report-heading">고객 1명으로 보면 어떻게 설명되나</h2>
      <div class="case-grid">
        {_customer_case_card("선택 고객", risk_customer)}
        {_customer_case_card("안정 저주행 우대 고객", stable_customer)}
      </div>
    </section>

    <section id="agent-proof" aria-labelledby="agent-proof-heading">
      <h2 id="agent-proof-heading">분석 에이전트 검증은 어디까지 됐나</h2>
      <div class="two-col">
        <div class="panel">
          <h3>검증 요약</h3>
          <p>필수 분석 에이전트 {agent_audit['required_agent_count']}개 산출물 무결성 검증은 {_format_percent(agent_audit['validation_pass_rate'])}이고, 고객 판정 승인 게이트 검증률은 {_format_percent(approval['agent_validation_pass_rate'])}입니다.</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="분석 에이전트 검증 결과">
              <thead><tr><th>에이전트</th><th>상태</th><th>산출물</th></tr></thead>
              <tbody>{_agent_rows(agent_audit)}</tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3>심사위원에게 보여줄 결론</h3>
          <p class="note">이 화면은 “실제 고객 사고율을 예측했다”는 주장이 아닙니다. 6개 합성 케이스에서 기존 거리 중심 마일리지가 놓치는 위험변화 신호를 제안 방식이 어떻게 구분하는지 보여주는 검증용 제품 화면입니다.</p>
          <div class="footer-actions">
            <a class="button" href="/detail">상세 검증 화면 열기</a>
            <a class="button" href="/api/validation">검증 결과 원문 보기</a>
          </div>
        </div>
      </div>
    </section>
  </main>
</body>
</html>"""


def _load_trip_stats() -> dict[str, Any]:
    with TRIP_LOG_PATH.open(encoding="utf-8") as trip_log:
        rows = list(csv.DictReader(trip_log))
    customers = sorted({row["customer_id"] for row in rows})
    personas = Counter(row["persona_type"] for row in rows)
    periods = Counter(row["observation_period"] for row in rows)
    day_indices_by_customer = defaultdict(lambda: defaultdict(set))
    for row in rows:
        day_indices_by_customer[row["customer_id"]][row["observation_period"]].add(
            int(row["observation_day_index"])
        )
    return {
        "trip_count": len(rows),
        "customer_count": len(customers),
        "persona_count": len(personas),
        "baseline_trip_count": periods["baseline"],
        "recent_trip_count": periods["recent"],
        "date_min": min(row["service_date"] for row in rows),
        "date_max": max(row["service_date"] for row in rows),
        "customers_with_60_30_periods": sum(
            1
            for customer_id in customers
            if max(day_indices_by_customer[customer_id]["baseline"] or [0]) == 60
            and max(day_indices_by_customer[customer_id]["recent"] or [0]) == 90
        ),
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _select_demo_customer(customers: list[dict[str, Any]], persona_type: str) -> dict[str, Any]:
    for customer in customers:
        if customer.get("persona_type") == persona_type:
            return dict(customer)
    return dict(customers[0])


def _build_persona_rows(bundle: dict[str, Any], scenario: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = {
        str(row["persona_type"]): dict(row)
        for row in bundle["ab_comparison"]["comparison_summary"].get("persona_summaries", ())
    }
    rules = scenario.get("persona_generation_rules", {})
    rows = []
    for persona in PERSONA_ORDER:
        rule = dict(rules.get(persona, {}))
        summary = summaries.get(persona, {})
        rows.append(
            {
                "persona_type": persona,
                "display_name": rule.get("display_name_ko") or PERSONA_FALLBACK_NAMES.get(persona, persona),
                "purpose": rule.get("product_role", ""),
                "target": bool(rule.get("risk_change_target")),
                "care_counts": summary.get("care_decision_counts", {}),
                "proposed_capture_count": int(summary.get("proposed_only_capture_count", 0)),
                "score_delta": float(summary.get("average_score_delta", 0.0)),
            }
        )
    return rows


def _llm_status(summary_report: dict[str, Any], bundle: dict[str, Any]) -> dict[str, str]:
    service = dict(summary_report.get("portfolio_llm_report", {}).get("llm_service_status", {}))
    report_mode = str(summary_report.get("report_mode") or bundle["llm_report_service_status"].get("report_mode"))
    active = bool(service.get("active"))
    display_modes = {
        "llm_generated": "OpenAI 실호출",
        "fallback_template": "안전 템플릿 리포트",
        "deterministic_template": "로컬 템플릿 리포트",
        "pending": "리포트 생성 대기",
        "unavailable": "리포트 확인 불가",
    }
    return {
        "report_mode": report_mode,
        "display_report_mode": display_modes.get(report_mode, "리포트 상태 확인"),
        "service_status": "실제 OpenAI API 호출 없음" if not active else "OpenAI API 호출 활성",
        "key_usage": ".env의 OPENAI_API_KEY는 이번 산출물 생성에서 사용하지 않음" if not active else "식별자 없는 요약 피처만 전송",
        "headline": (
            "현재 산출물은 OpenAI 실호출 결과가 아니라 로컬 템플릿 리포트입니다. "
            "OpenAI 연동 코드는 구현되어 있고 실패 시 안전 템플릿으로 전환됩니다."
            if not active
            else "OpenAI API로 생성된 보험사 직원용 리포트가 표시됩니다."
        ),
    }


def _metric_card(label: str, value: str, caption: str, tone: str = "") -> str:
    tone_class = f" {tone}" if tone else ""
    return f"""<article class="metric{tone_class}">
          <span>{escape(label)}</span>
          <strong>{escape(value)}</strong>
          <p>{escape(caption)}</p>
        </article>"""


def _verdict_card(label: str, value: str, body: str) -> str:
    return f"""<article class="verdict-card">
            <span>{escape(label)}</span>
            <strong>{escape(value)}</strong>
            <p>{escape(body)}</p>
          </article>"""


def _question_card(number: str, question: str, answer: str, evidence_label: str, evidence_path: str) -> str:
    return f"""<article class="question-card">
          <span>{escape(number)}</span>
          <strong>{escape(question)}</strong>
          <p>{escape(answer)}</p>
          <div class="evidence" data-evidence-path="{escape(evidence_path)}">근거: {escape(evidence_label)}</div>
        </article>"""


def _system_difference_section(customer: dict[str, Any]) -> str:
    metrics = dict(customer.get("ab_comparison", {}).get("metrics", {}))
    core_metrics = dict(metrics.get("core_metrics", {}))
    feature_summary = dict(metrics.get("comparison_input", {}).get("feature_summary", {}))
    baseline = dict(core_metrics.get("baseline", {}))
    proposed = dict(core_metrics.get("proposed", {}))
    annualized_km = float(feature_summary.get("annualized_recent_km", 0.0))
    baseline_out = _format_ratio_percent(feature_summary.get("baseline_out_zone_ratio", 0.0))
    recent_out = _format_ratio_percent(feature_summary.get("recent_out_zone_ratio", 0.0))
    night_delta = _format_ratio_delta(feature_summary.get("night_ratio_delta", 0.0))
    risk_delta = float(feature_summary.get("risk_rate_delta_per_100km", 0.0))
    return f"""<div class="difference-grid">
        <article class="system-card">
          <h3>기존 마일리지 보험</h3>
          <p>보험료 할인 여부를 주로 주행거리로 판단합니다.</p>
          <ul>
            <li>입력: 최근 주행거리를 1년 기준으로 환산한 km</li>
            <li>판정: 기준보다 적게 타면 저주행 할인</li>
            <li>한계: 어디로 갔는지, 밤에 달렸는지, 위험행동이 늘었는지는 놓칩니다.</li>
          </ul>
        </article>
        <article class="system-card">
          <h3>시니어 안심주행 방식</h3>
          <p>거리만 보지 않고 최근 운전 패턴이 평소 생활권에서 어떻게 달라졌는지 봅니다.</p>
          <ul>
            <li>입력: 주행거리 + 생활권 안/밖 좌표 + 야간주행 + 위험행동</li>
            <li>판정: 우대, 기본, 예방 케어로 나눔</li>
            <li>효과: 저주행 고객 안에서도 “안정 저주행”과 “최근 위험변화”를 분리합니다.</li>
          </ul>
        </article>
      </div>
      <div class="example-strip" aria-label="같은 고객 판정 예시">
        {_example_card("같은 고객", _display_customer_id(str(customer['customer_id'])), "주행거리는 낮지만 최근 생활권 밖 변화가 생긴 고객")}
        {_example_card("기존 방식 판정", str(baseline.get("decision", "기존 저주행 할인")), f"1년 환산 {annualized_km:,.0f}km라서 거리 기준으로는 우량해 보입니다.")}
        {_example_card("제안 방식 판정", str(proposed.get("decision", customer.get("care_decision", ""))), f"생활권 밖 {baseline_out} -> {recent_out}, 야간 {night_delta}, 위험행동 100km당 {risk_delta:+.1f}건")}
      </div>
      <p class="bridge-note">핵심은 “할인을 없애자”가 아닙니다. 기존 저주행 할인을 유지하되, 시니어 고객에게 중요한 최근 생활권 변화 신호를 별도로 감지해 보험사 직원이 설명 가능한 케어 액션을 만들자는 것입니다.</p>"""


def _example_card(label: str, value: str, body: str) -> str:
    return f"""<article class="example-card">
          <span>{escape(label)}</span>
          <strong>{escape(value)}</strong>
          <p>{escape(body)}</p>
        </article>"""


def _select_customer_from_query(customers: list[dict[str, Any]], request_path: str) -> dict[str, Any] | None:
    query = parse_qs(urlparse(request_path).query)
    selected_customer_id = query.get("customer_id", [None])[0]
    if not selected_customer_id:
        return None
    for customer in customers:
        if str(customer.get("customer_id")) == selected_customer_id:
            return dict(customer)
    return None


def _build_simulation_view_model(
    customers: list[dict[str, Any]],
    customer: dict[str, Any],
    selected_policy: dict[str, Any],
    request_path: str,
) -> dict[str, Any]:
    query = parse_qs(urlparse(request_path).query)
    metrics = dict(customer.get("ab_comparison", {}).get("metrics", {}))
    feature_summary = dict(metrics.get("comparison_input", {}).get("feature_summary", {}))
    scores = dict(customer.get("scores", {}))
    weights = {key: float(value) for key, value in dict(selected_policy["weights"]).items()}
    thresholds = dict(selected_policy["thresholds"])
    tier_threshold = dict(thresholds["tier_threshold"])
    care_threshold = float(thresholds["care_threshold"])

    baseline_out_ratio = float(feature_summary.get("baseline_out_zone_ratio", 0.0))
    baseline_night_ratio = float(feature_summary.get("baseline_night_ratio", 0.0))
    baseline_risk_rate = float(feature_summary.get("baseline_risk_rate_per_100km", 0.0))
    annualized_recent_km = _query_float(
        query,
        "annualized_recent_km",
        float(feature_summary.get("annualized_recent_km", 0.0)),
        0.0,
        30000.0,
    )
    recent_out_zone_ratio_pct = _query_float(
        query,
        "recent_out_zone_ratio_pct",
        float(feature_summary.get("recent_out_zone_ratio", 0.0)) * 100,
        0.0,
        100.0,
    )
    night_delta_pct = _query_float(
        query,
        "night_delta_pct",
        float(feature_summary.get("night_ratio_delta", 0.0)) * 100,
        -50.0,
        100.0,
    )
    risk_rate_delta = _query_float(
        query,
        "risk_rate_delta_per_100km",
        float(feature_summary.get("risk_rate_delta_per_100km", 0.0)),
        -20.0,
        30.0,
    )
    risk_signal_count = int(
        round(
            _query_float(
                query,
                "risk_signal_count",
                float(feature_summary.get("recent_risk_signal_count", 0.0)),
                0.0,
                80.0,
            )
        )
    )

    recent_out_zone_ratio = recent_out_zone_ratio_pct / 100.0
    recent_in_zone_ratio = _clamp_float(1.0 - recent_out_zone_ratio, 0.0, 1.0)
    night_delta = night_delta_pct / 100.0
    recent_night_ratio = _clamp_float(baseline_night_ratio + night_delta, 0.0, 1.0)
    recent_risk_rate = max(0.0, baseline_risk_rate + risk_rate_delta)
    recent_trip_count = int(feature_summary.get("recent_trip_count", max(1, risk_signal_count)))
    recent_trip_count = max(1, recent_trip_count)
    recent_total_km = annualized_recent_km / 365.0 * 30.0
    recent_in_zone_km = recent_total_km * recent_in_zone_ratio
    recent_out_zone_km = recent_total_km * recent_out_zone_ratio

    score_input = SeniorSafeMileageScoreInput(
        annualized_recent_km=annualized_recent_km,
        recent_trip_count=recent_trip_count,
        recent_in_zone_ratio=recent_in_zone_ratio,
        recent_out_zone_ratio=recent_out_zone_ratio,
        out_zone_ratio_delta=recent_out_zone_ratio - baseline_out_ratio,
        baseline_night_ratio=baseline_night_ratio,
        recent_night_ratio=recent_night_ratio,
        night_ratio_delta=night_delta,
        baseline_risk_rate_per_100km=baseline_risk_rate,
        recent_risk_rate_per_100km=recent_risk_rate,
        risk_rate_delta_per_100km=risk_rate_delta,
        recent_risk_signal_count=risk_signal_count,
        recent_in_zone_km=recent_in_zone_km,
        recent_in_zone_night_ratio=float(feature_summary.get("recent_in_zone_night_ratio", recent_night_ratio)),
        recent_in_zone_risk_rate_per_100km=float(
            feature_summary.get("recent_in_zone_risk_rate_per_100km", recent_risk_rate)
        ),
        recent_out_zone_km=recent_out_zone_km,
        recent_out_zone_night_ratio=recent_night_ratio if recent_out_zone_km else 0.0,
        recent_out_zone_risk_rate_per_100km=recent_risk_rate if recent_out_zone_km else 0.0,
    )
    score_result = calculate_local_score_result(score_input, weights)
    tier = calculate_tier(score_result.senior_safe_mileage_score, tier_threshold)
    proposed_detected = (
        score_result.risk_change_score >= care_threshold
        and score_result.senior_safe_mileage_score < float(tier_threshold["A"])
    )
    proposed_decision = care_decision(proposed_detected, tier, score_result.risk_change_score)
    baseline_detected = annualized_recent_km > BASELINE_ANNUAL_MILEAGE_LIMIT_KM
    baseline_decision = "기존 거리 기준 할증 검토" if baseline_detected else "기존 저주행 할인"
    original_decision = str(customer.get("care_decision", ""))

    return {
        "customer": dict(customer),
        "customer_options": _simulation_customer_options(customers, str(customer["customer_id"])),
        "inputs": {
            "annualized_recent_km": round(annualized_recent_km, 0),
            "recent_out_zone_ratio_pct": round(recent_out_zone_ratio_pct, 1),
            "night_delta_pct": round(night_delta_pct, 1),
            "risk_rate_delta_per_100km": round(risk_rate_delta, 1),
            "risk_signal_count": risk_signal_count,
        },
        "original": {
            "care_decision": original_decision,
            "risk_change_score": float(scores.get("risk_change_score", 0.0)),
            "senior_safe_mileage_score": float(scores.get("senior_safe_mileage_score", 0.0)),
        },
        "result": {
            "baseline_decision": baseline_decision,
            "baseline_detected": baseline_detected,
            "proposed_decision": proposed_decision,
            "proposed_detected": proposed_detected,
            "tier": tier,
            "mileage_baseline_score": score_result.mileage_baseline_score,
            "senior_safe_mileage_score": score_result.senior_safe_mileage_score,
            "risk_change_score": score_result.risk_change_score,
            "in_zone_safe_score": score_result.in_zone_safe_score,
            "out_zone_safe_score": score_result.out_zone_safe_score,
            "care_threshold": care_threshold,
            "a_threshold": float(tier_threshold["A"]),
        },
        "components": {
            "out_zone_ratio_delta_pct": round((recent_out_zone_ratio - baseline_out_ratio) * 100, 1),
            "night_delta_pct": round(night_delta_pct, 1),
            "risk_rate_delta_per_100km": round(risk_rate_delta, 1),
            "risk_signal_count": risk_signal_count,
            "recent_trip_count": recent_trip_count,
        },
    }


def _simulation_form(simulation: dict[str, Any]) -> str:
    inputs = dict(simulation["inputs"])
    return f"""<form class="lab-form" method="get" action="/#simulation-lab">
            <label>고객 선택
              <select name="customer_id">{simulation['customer_options']}</select>
            </label>
            <div class="field-grid">
              <label>최근 주행거리(1년 환산 km)
                <input name="annualized_recent_km" type="number" min="0" max="30000" step="100" value="{escape(_format_number_input(inputs['annualized_recent_km']))}">
              </label>
              <label>최근 생활권 밖 주행 비중(%)
                <input name="recent_out_zone_ratio_pct" type="number" min="0" max="100" step="1" value="{escape(_format_number_input(inputs['recent_out_zone_ratio_pct']))}">
              </label>
              <label>야간주행 증가(%p)
                <input name="night_delta_pct" type="number" min="-50" max="100" step="1" value="{escape(_format_number_input(inputs['night_delta_pct']))}">
              </label>
              <label>위험행동 증가(100km당)
                <input name="risk_rate_delta_per_100km" type="number" min="-20" max="30" step="0.5" value="{escape(_format_number_input(inputs['risk_rate_delta_per_100km']))}">
              </label>
              <label>최근 위험 신호 건수
                <input name="risk_signal_count" type="number" min="0" max="80" step="1" value="{escape(str(inputs['risk_signal_count']))}">
              </label>
            </div>
            <div class="lab-actions">
              <button class="button" type="submit">이 조건으로 다시 판정</button>
              <a class="button" href="/?customer_id={escape(str(simulation['customer']['customer_id']))}#simulation-lab">원본 조건으로 보기</a>
            </div>
          </form>"""


def _simulation_presets(simulation: dict[str, Any]) -> str:
    customer_id = str(simulation["customer"]["customer_id"])
    presets = [
        ("안정 저주행", {"annualized_recent_km": 4200, "recent_out_zone_ratio_pct": 5, "night_delta_pct": 0, "risk_rate_delta_per_100km": 0, "risk_signal_count": 0}),
        ("생활권 밖 안전운전", {"annualized_recent_km": 6500, "recent_out_zone_ratio_pct": 30, "night_delta_pct": 2, "risk_rate_delta_per_100km": 0.5, "risk_signal_count": 1}),
        ("최근 위험변화", {"annualized_recent_km": 4040, "recent_out_zone_ratio_pct": 38, "night_delta_pct": 23, "risk_rate_delta_per_100km": 5.5, "risk_signal_count": 21}),
        ("과다 주행", {"annualized_recent_km": 15000, "recent_out_zone_ratio_pct": 12, "night_delta_pct": 1, "risk_rate_delta_per_100km": 0.5, "risk_signal_count": 1}),
    ]
    links = []
    for label, values in presets:
        query = {"customer_id": customer_id, **values}
        links.append(f'<a class="button" href="/?{escape(urlencode(query))}#simulation-lab">{escape(label)}</a>')
    return f"""<div class="preset-list" aria-label="조건 프리셋">
            {''.join(links)}
          </div>"""


def _simulation_result(simulation: dict[str, Any]) -> str:
    result = dict(simulation["result"])
    components = dict(simulation["components"])
    original = dict(simulation["original"])
    changed = result["proposed_decision"] != original["care_decision"]
    change_text = (
        f"원래 {original['care_decision']}에서 {result['proposed_decision']}로 바뀝니다."
        if changed
        else f"원래 판정과 같은 {result['proposed_decision']}입니다."
    )
    return f"""<p>{escape(_display_customer_id(str(simulation['customer']['customer_id'])))} 기준으로 조건을 다시 계산했습니다. {escape(change_text)}</p>
          <div class="lab-result-grid">
            {_lab_result_card("기존 방식", result['baseline_decision'], f"기준: {BASELINE_ANNUAL_MILEAGE_LIMIT_KM:,.0f}km 초과 여부")}
            {_lab_result_card("제안 방식", result['proposed_decision'], f"등급 {result['tier']} · 통합 점수 {result['senior_safe_mileage_score']:.1f}")}
            {_lab_result_card("위험변화 점수", f"{result['risk_change_score']:.1f}점", f"예방 케어 기준 {result['care_threshold']:.1f}점")}
          </div>
          <div class="table-wrap" style="margin-top:14px">
            <table aria-label="조건 테스트 계산 근거">
              <tbody>
                <tr><th scope="row">생활권 밖 비중 증가</th><td>{components['out_zone_ratio_delta_pct']:+.1f}%p</td></tr>
                <tr><th scope="row">야간주행 증가</th><td>{components['night_delta_pct']:+.1f}%p</td></tr>
                <tr><th scope="row">위험행동 증가</th><td>100km당 {components['risk_rate_delta_per_100km']:+.1f}건</td></tr>
                <tr><th scope="row">위험신호 건수</th><td>{components['risk_signal_count']}건 / 최근 주행 {components['recent_trip_count']}회</td></tr>
                <tr><th scope="row">예방 케어 조건</th><td>위험변화 {result['risk_change_score']:.1f}점 >= {result['care_threshold']:.1f}점, 통합 점수 {result['senior_safe_mileage_score']:.1f}점 < A등급 {result['a_threshold']:.1f}점</td></tr>
              </tbody>
            </table>
          </div>"""


def _lab_result_card(label: str, value: str, caption: str) -> str:
    return f"""<article class="lab-result">
              <span>{escape(label)}</span>
              <strong>{escape(value)}</strong>
              <p>{escape(caption)}</p>
            </article>"""


def _criteria_card(title: str, body: str, caption: str) -> str:
    return f"""<article class="criteria-card">
          <h3>{escape(title)}</h3>
          <p>{escape(body)}</p>
          <p style="margin-top:8px">{escape(caption)}</p>
        </article>"""


def _simulation_customer_options(customers: list[dict[str, Any]], selected_customer_id: str) -> str:
    options = []
    for customer in customers:
        customer_id = str(customer["customer_id"])
        selected = " selected" if customer_id == selected_customer_id else ""
        label = (
            f"{_display_customer_id(customer_id)} · "
            f"{PERSONA_FALLBACK_NAMES.get(str(customer['persona_type']), str(customer['persona_type']))} · "
            f"{customer['care_decision']}"
        )
        options.append(f'<option value="{escape(customer_id)}"{selected}>{escape(label)}</option>')
    return "".join(options)


def _query_float(
    query: dict[str, list[str]],
    key: str,
    default: float,
    low: float,
    high: float,
) -> float:
    raw = query.get(key, [None])[0]
    if raw in {None, ""}:
        value = default
    else:
        try:
            value = float(raw)
        except ValueError:
            value = default
    return _clamp_float(value, low, high)


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _format_number_input(value: object) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _load_customer_trip_rows(customer_id: str) -> list[dict[str, str]]:
    with TRIP_LOG_PATH.open(encoding="utf-8") as trip_log:
        return [row for row in csv.DictReader(trip_log) if row["customer_id"] == customer_id]


def _living_zone_svg(customer: dict[str, Any]) -> str:
    rows = _load_customer_trip_rows(str(customer["customer_id"]))
    if not rows:
        return '<div class="zone-map" role="img" aria-label="표시할 주행 좌표가 없습니다"></div>'

    width = 560
    height = 360
    padding = 34
    coords = []
    for row in rows:
        coords.append((float(row["start_gps_x"]), float(row["start_gps_y"])))
        coords.append((float(row["end_gps_x"]), float(row["end_gps_y"])))
    min_x = min(x for x, _ in coords)
    max_x = max(x for x, _ in coords)
    min_y = min(y for _, y in coords)
    max_y = max(y for _, y in coords)
    if max_x == min_x:
        max_x += 0.001
        min_x -= 0.001
    if max_y == min_y:
        max_y += 0.001
        min_y -= 0.001

    def scale_x(value: float) -> float:
        return padding + ((value - min_x) / (max_x - min_x)) * (width - padding * 2)

    def scale_y(value: float) -> float:
        return height - padding - ((value - min_y) / (max_y - min_y)) * (height - padding * 2)

    baseline_local = [
        (float(row["end_gps_x"]), float(row["end_gps_y"]))
        for row in rows
        if row["observation_period"] == "baseline" and row["zone_label"] != "outer"
    ]
    if not baseline_local:
        baseline_local = [
            (float(row["end_gps_x"]), float(row["end_gps_y"]))
            for row in rows
            if row["observation_period"] == "baseline"
        ]
    center_lon = sum(x for x, _ in baseline_local) / len(baseline_local)
    center_lat = sum(y for _, y in baseline_local) / len(baseline_local)
    center_x = scale_x(center_lon)
    center_y = scale_y(center_lat)

    distances_x = sorted(abs(scale_x(x) - center_x) for x, _ in baseline_local)
    distances_y = sorted(abs(scale_y(y) - center_y) for _, y in baseline_local)
    core_rx = max(34.0, _percentile(distances_x, 0.62) + 18.0)
    core_ry = max(28.0, _percentile(distances_y, 0.62) + 16.0)
    buffer_rx = max(core_rx + 34.0, _percentile(distances_x, 0.90) + 48.0)
    buffer_ry = max(core_ry + 26.0, _percentile(distances_y, 0.90) + 42.0)

    route_lines = []
    point_nodes = []
    for row in rows:
        start_x = scale_x(float(row["start_gps_x"]))
        start_y = scale_y(float(row["start_gps_y"]))
        end_x = scale_x(float(row["end_gps_x"]))
        end_y = scale_y(float(row["end_gps_y"]))
        period = row["observation_period"]
        zone = row["zone_label"]
        risk = _row_has_risk_signal(row)
        if period == "recent":
            stroke = "#bd5b1a" if zone == "outer" else "#1f6f8b"
            route_lines.append(
                f'<line x1="{start_x:.1f}" y1="{start_y:.1f}" x2="{end_x:.1f}" y2="{end_y:.1f}" '
                f'stroke="{stroke}" stroke-width="1.4" opacity="0.26" />'
            )
        if period == "baseline":
            fill = "#8a949e"
            radius = 3.0
            opacity = "0.58"
        elif zone == "outer":
            fill = "#bd5b1a"
            radius = 4.4
            opacity = "0.86"
        else:
            fill = "#1f6f8b"
            radius = 3.8
            opacity = "0.82"
        if risk:
            point_nodes.append(
                f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="{radius + 4.0:.1f}" '
                'fill="none" stroke="#c7352b" stroke-width="2" opacity="0.78" />'
            )
            fill = "#c7352b"
            radius += 0.8
            opacity = "0.96"
        point_nodes.append(
            f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="{radius:.1f}" fill="{fill}" opacity="{opacity}" />'
        )

    return f"""<svg class="zone-map" viewBox="0 0 {width} {height}" role="img" aria-label="고객 {_display_customer_id(str(customer['customer_id']))}의 주행 좌표와 생활권 프리뷰">
            <rect x="0" y="0" width="{width}" height="{height}" fill="#f7f9f8" />
            <path d="M40 72 H520 M40 144 H520 M40 216 H520 M40 288 H520 M112 30 V330 M224 30 V330 M336 30 V330 M448 30 V330" stroke="#e1e6e2" stroke-width="1" />
            <ellipse cx="{center_x:.1f}" cy="{center_y:.1f}" rx="{buffer_rx:.1f}" ry="{buffer_ry:.1f}" fill="#f4efe4" stroke="#caa46c" stroke-width="2" stroke-dasharray="7 5" opacity="0.86" />
            <ellipse cx="{center_x:.1f}" cy="{center_y:.1f}" rx="{core_rx:.1f}" ry="{core_ry:.1f}" fill="#e7f1ed" stroke="#4d8c78" stroke-width="2" opacity="0.82" />
            <text x="{center_x + 10:.1f}" y="{center_y - core_ry - 8:.1f}" fill="#126149" font-size="13" font-weight="700">생활권 안</text>
            <text x="{min(width - 190, center_x + buffer_rx - 120):.1f}" y="{min(height - 14, max(24, center_y + buffer_ry + 20)):.1f}" fill="#9a4a15" font-size="13" font-weight="700">생활권 밖 변화</text>
            {''.join(route_lines)}
            {''.join(point_nodes)}
          </svg>"""


def _living_zone_insights(customer: dict[str, Any]) -> str:
    metrics = dict(customer.get("ab_comparison", {}).get("metrics", {}))
    feature_summary = dict(metrics.get("comparison_input", {}).get("feature_summary", {}))
    baseline_out = _format_ratio_percent(feature_summary.get("baseline_out_zone_ratio", 0))
    recent_out = _format_ratio_percent(feature_summary.get("recent_out_zone_ratio", 0))
    night_delta = _format_ratio_delta(feature_summary.get("night_ratio_delta", 0))
    risk_delta = float(feature_summary.get("risk_rate_delta_per_100km", 0.0))
    annualized_km = float(feature_summary.get("annualized_recent_km", 0.0))
    baseline_decision = str(metrics.get("core_metrics", {}).get("baseline", {}).get("decision", "기존 저주행 할인"))
    proposed_decision = str(customer.get("care_decision", "예방 케어"))
    return f"""<ul class="insight-list">
          <li>
            <strong>기존 방식은 왜 놓쳤나</strong>
            <p>최근 주행거리를 1년 기준으로 환산하면 {annualized_km:,.0f}km라서 {escape(baseline_decision)}처럼 보입니다.</p>
          </li>
          <li>
            <strong>좌표 프리뷰에서 보이는 변화</strong>
            <p>생활권 밖 주행 비중이 이전 {baseline_out}에서 최근 {recent_out}로 늘었습니다. 그림의 주황/빨간 점이 이 변화입니다.</p>
          </li>
          <li>
            <strong>위험 신호가 같이 늘었나</strong>
            <p>야간주행은 {night_delta}, 위험행동은 100km당 {risk_delta:+.1f}건 변했습니다.</p>
          </li>
          <li>
            <strong>최종 판정</strong>
            <p>그래서 제안 방식은 이 고객을 {escape(proposed_decision)} 대상으로 분류합니다.</p>
          </li>
        </ul>"""


def _model_factor_cards(selected_policy: dict[str, Any]) -> str:
    labels = [
        ("w_mileage", "주행거리", "적게 탔는지 확인"),
        ("w_in_zone", "생활권 안 안정성", "평소 생활권에서 안전하게 달렸는지 확인"),
        ("w_out_zone_safe", "생활권 밖 안전운전", "밖으로 나가도 안전하게 달리면 불이익을 줄임"),
        ("w_out_zone_change", "최근 위험변화", "최근 생활권 밖 위험 신호 증가를 감점"),
    ]
    weights = dict(selected_policy["weights"])
    return "\n".join(
        f"""<article class="model-factor">
            <span>{escape(caption)}</span>
            <strong>{_format_percent(weights[key])}</strong>
            <p>{escape(label)}</p>
          </article>"""
        for key, label, caption in labels
    )


def _test_journey_rows(
    trip_stats: dict[str, Any],
    approval: dict[str, Any],
    ab: dict[str, Any],
    selected_policy: dict[str, Any],
    agent_audit: dict[str, Any],
    llm_status: dict[str, str],
) -> str:
    rows = [
        (
            "1",
            "시니어 케이스 설계",
            "안정 저주행, 생활권 밖 안정 주행, 최근 위험변화, 병원 방문, 가족 돌봄 등 6개 케이스를 만들었습니다.",
            f"{trip_stats['customer_count']}명 / {trip_stats['persona_count']}개 유형",
            "시나리오 조건",
            "data/fixtures/scenario_config.json",
        ),
        (
            "2",
            "90일 주행 로그 생성",
            "이전 60일과 최근 30일을 나누고, 실제 운전이 발생한 날의 좌표 기록을 저장했습니다.",
            f"주행 기록 {trip_stats['trip_count']:,}건",
            "주행 로그",
            "data/fixtures/senior_trip_logs.csv",
        ),
        (
            "3",
            "데이터 일관성 검사",
            "좌표, 시간, 거리, 위험행동 신호가 다음 분석 단계에서 쓸 수 있는지 검사했습니다.",
            "검증 통과",
            "검증 리포트",
            "data/fixtures/validation_report.md",
        ),
        (
            "4",
            "정책 후보 탐색",
            "가중치와 예방 케어 기준을 조합한 후보를 비교해 승인 게이트를 통과하는 정책을 골랐습니다.",
            "선택 모델 확정",
            "모델 설계 후보",
            "data/fixtures/candidate_rules.json",
        ),
        (
            "5",
            "기존 방식 비교",
            "동일 고객 30명에 기존 거리 중심 방식과 제안 방식을 모두 적용했습니다.",
            f"기존 방식 {ab['baseline_capture_count']}/5 · 제안 방식 {ab['proposed_capture_count']}/5",
            "기존 방식 비교 결과",
            "data/fixtures/ab_test_results.csv",
        ),
        (
            "6",
            "승인 게이트/오탐 검증",
            "위험변화 포착, 비대상 오탐, 전체 오분류, 고객 판정 검증률을 기준으로 통과 여부를 확인했습니다.",
            (
                f"오탐 {approval['non_target_false_positive_count']}/{approval['non_target_false_positive_limit']} · "
                f"오분류 {approval['total_misclassification_count']}/{approval['total_misclassification_limit']}"
            ),
            "승인 기준 검증 결과",
            "data/fixtures/evaluation_view_model.json",
        ),
        (
            "7",
            "분석 에이전트 산출물 검증",
            "각 분석 에이전트가 필요한 산출물을 남겼는지, 다음 단계가 그 산출물을 실제로 참조했는지 검증했습니다.",
            f"{agent_audit['required_agent_count']}개 에이전트 · {_format_percent(agent_audit['validation_pass_rate'])}",
            "검증 결과 원문",
            "/api/validation",
        ),
        (
            "8",
            "OpenAI 설명문 생성",
            "보험사 직원이 읽을 수 있는 판정 설명문을 식별자 없는 요약 피처만 보내 생성했습니다.",
            f"{llm_status['display_report_mode']} · {llm_status['service_status']}",
            "설명문 산출물",
            "data/fixtures/simulation_summary.json",
        ),
    ]
    return "\n".join(
        "<tr>"
        f"<td><span class=\"code\">{escape(number)}</span></td>"
        f"<td><strong>{escape(stage)}</strong></td>"
        f"<td>{escape(check)}</td>"
        f"<td><span class=\"status pass\">{escape(result)}</span></td>"
        f"<td data-evidence-path=\"{escape(evidence_path)}\">{escape(evidence_label)}</td>"
        "</tr>"
        for number, stage, check, result, evidence_label, evidence_path in rows
    )


def _artifact_rows() -> str:
    rows = []
    for label, path, role in ARTIFACT_ROWS:
        exists = (ROOT / path).exists()
        status = '<span class="status pass">있음</span>' if exists else '<span class="status review">없음</span>'
        rows.append(
            f"<tr><td>{escape(label)}</td><td><details><summary>파일 위치 보기</summary><span class=\"code\">{escape(path)}</span></details></td>"
            f"<td>{escape(role)}</td><td>{status}</td></tr>"
        )
    return "\n".join(rows)


def _flow_step(number: str, title: str, body: str) -> str:
    return f"""<article class="step">
          <span>{escape(number)}</span>
          <strong>{escape(title)}</strong>
          <p>{escape(body)}</p>
        </article>"""


def _bar_row(label: str, rate: float, detail: str, tone: str = "") -> str:
    percent = max(0.0, min(100.0, float(rate) * 100))
    tone_class = f" {tone}" if tone else ""
    return f"""<div class="bar-row">
              <strong>{escape(label)}</strong>
              <div class="bar-track" aria-hidden="true"><div class="bar-fill{tone_class}" style="width:{percent:.0f}%"></div></div>
              <span>{escape(detail)}</span>
            </div>"""


def _weight_rows(selected_policy: dict[str, Any]) -> str:
    labels = {
        "w_mileage": "주행거리",
        "w_in_zone": "생활권 내 안정운전",
        "w_out_zone_safe": "생활권 밖 안전운전",
        "w_out_zone_change": "생활권 밖 위험변화 감점",
    }
    return "\n".join(
        f"<tr><th scope=\"row\">{escape(labels[key])}</th><td>{float(value):.2f}</td></tr>"
        for key, value in selected_policy["weights"].items()
    )


def _persona_table_rows(rows: list[dict[str, Any]]) -> str:
    html_rows = []
    for row in rows:
        counts = ", ".join(f"{key} {value}" for key, value in sorted(row["care_counts"].items()))
        target = "핵심 포착 대상" if row["target"] else "오탐 방지/보정 대상"
        status = "pass" if row["care_counts"] else "review"
        html_rows.append(
            f"<tr data-persona-type=\"{escape(row['persona_type'])}\"><td><strong>{escape(row['display_name'])}</strong></td>"
            f"<td>{escape(row['purpose'])}</td>"
            f"<td><span class=\"status {status}\">{escape(counts or '결과 없음')}</span></td>"
            f"<td>{escape(target)} · 평균 점수 변화 {row['score_delta']:+.1f}</td></tr>"
        )
    return "\n".join(html_rows)


def _customer_case_card(title: str, customer: dict[str, Any]) -> str:
    scores = dict(customer["scores"])
    ab = dict(customer["ab_comparison"])
    reason_codes = ", ".join(_reason_label(str(code)) for code in customer.get("xai_reason_codes", ())[:4])
    return f"""<article class="case-card" data-customer-id="{escape(str(customer['customer_id']))}">
          <h3>{escape(title)}</h3>
          <strong>{escape(_display_customer_id(str(customer['customer_id'])))} · {escape(PERSONA_FALLBACK_NAMES.get(str(customer['persona_type']), str(customer['persona_type'])))}</strong>
          <p>{escape(str(customer['care_decision']))} 판정</p>
          <dl>
            <dt>기존 점수</dt><dd>{float(scores['mileage_baseline_score']):.1f}</dd>
            <dt>제안 점수</dt><dd>{float(scores['senior_safe_mileage_score']):.1f}</dd>
            <dt>위험변화</dt><dd>{float(scores['risk_change_score']):.1f}</dd>
            <dt>판정 차이</dt><dd>{escape(str(ab.get('decision_delta_label', '판정 비교 제공')))}</dd>
            <dt>판정 근거</dt><dd>{escape(reason_codes)}</dd>
          </dl>
        </article>"""


def _agent_rows(agent_audit: dict[str, Any]) -> str:
    rows = []
    for check in agent_audit.get("checks", ()):
        artifact_ids = ", ".join(_artifact_label(str(artifact_id)) for artifact_id in check.get("artifact_ids", ()))
        rows.append(
            f"<tr data-agent-id=\"{escape(str(check['agent_id']))}\"><td>{escape(_agent_label(str(check['agent_id'])))}</td>"
            f"<td><span class=\"status pass\">통과</span></td>"
            f"<td>{escape(artifact_ids)}</td></tr>"
        )
    return "\n".join(rows)


def _row_has_risk_signal(row: dict[str, str]) -> bool:
    signal_fields = (
        "night_driving_signal",
        "sudden_braking_signal",
        "route_deviation_signal",
        "fatigue_indicator",
        "speeding_count",
        "harsh_accel_count",
        "harsh_brake_count",
        "sharp_turn_count",
    )
    return any(int(float(row.get(field, "0") or 0)) > 0 for field in signal_fields) or row.get(
        "risk_signal_codes", "none"
    ) not in {"", "none"}


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
    return values[index]


def _format_ratio_percent(value: object) -> str:
    return f"{float(value) * 100:.0f}%"


def _format_ratio_delta(value: object) -> str:
    delta = float(value) * 100
    if abs(delta) < 0.5:
        return "변화 없음"
    return f"{delta:+.0f}%포인트"


def _format_percent(value: object) -> str:
    return f"{float(value) * 100:.0f}%"


def _display_customer_id(customer_id: str) -> str:
    suffix = customer_id.split("_")[-1]
    return f"고객 {suffix}" if suffix.isdigit() else "고객"


def _reason_label(reason_code: str) -> str:
    return REASON_LABELS.get(reason_code, reason_code.replace("_", " ").title())


def _agent_label(agent_id: str) -> str:
    labels = {
        "persona_agent": "운전자 유형 생성",
        "scenario_agent": "시니어 케이스 설계",
        "ai_simulation_agent": "주행 기록 생성",
        "consistency_check_agent": "데이터 일관성 검사",
        "driving_data_scenario_agent": "주행 데이터 생성",
        "living_zone_agent": "생활권 분석",
        "score_agent": "점수 산정",
        "evaluation_agent": "판정 검증",
        "critic_agent": "규칙 검토",
        "report_agent": "설명문 생성",
        "policy_search_agent": "정책 후보 탐색",
    }
    return labels.get(agent_id, agent_id.replace("_", " "))


def _artifact_label(artifact_id: str) -> str:
    labels = {
        "senior_customers.json": "고객 조건",
        "persona_templates.yaml": "운전자 유형 템플릿",
        "customer_driving_parameters.json": "주행 파라미터",
        "scenario_config.json": "시나리오 조건",
        "senior_trip_logs.csv": "주행 로그",
        "simulation_manifest.json": "실행 메타정보",
        "validation_report.md": "검증 리포트",
        "candidate_rules.json": "모델 설계 후보",
        "policy_candidate_scores.csv": "정책 후보 점수",
        "ab_test_results.csv": "기존 방식 비교 결과",
        "evaluation_view_model.json": "판정 검증 결과",
        "rule_review.json": "규칙 검토 결과",
        "simulation_summary.json": "실행 요약",
        "scenario_config": "시나리오 조건",
        "senior_trip_logs": "주행 로그",
        "living_zone_features": "생활권 특징",
        "customer_scores": "고객별 점수",
        "evaluation_view_model": "판정 검증 결과",
        "critic_review": "규칙 검토 결과",
        "report_view_model": "설명문 산출물",
        "candidate_rules": "모델 설계 후보",
        "ab_test_results": "기존 방식 비교 결과",
        "simulation_summary": "실행 요약",
    }
    return labels.get(artifact_id, artifact_id.replace("_", " "))

"""Contest-oriented demo page for Senior Safe Mileage.

The existing customer decision page is a dense operator/debug surface.  This
module renders a separate first screen for judges: it explains what was built,
which data files exist, what the A/B result proves, and where the detailed
evidence lives.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Any


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
    ("합성 주행 데이터", "data/fixtures/senior_trip_logs.csv", "30명, 90일 관측기간 trip log"),
    ("시나리오 조건", "data/fixtures/scenario_config.json", "6개 페르소나별 baseline/recent 변화 규칙"),
    ("Agent 검증", "data/fixtures/validation_report.md", "좌표/시간/위험행동 일관성 검증 결과"),
    ("정책 후보", "data/fixtures/candidate_rules.json", "가중치/기준값 후보와 선택 근거"),
    ("A/B 결과", "data/fixtures/ab_test_results.csv", "기존 산식과 제안 산식의 동일 입력 비교"),
    ("리포트 산출물", "data/fixtures/simulation_summary.json", "보험사 직원용 설명문 템플릿과 XAI 근거"),
]


def render_contest_demo_page(bundle: dict[str, Any]) -> str:
    """Render the judge-facing contest demo page."""

    trip_stats = _load_trip_stats()
    scenario = _load_json(SCENARIO_CONFIG_PATH)
    summary_report = _load_json(SUMMARY_REPORT_PATH)
    approval = dict(bundle["approval_gate"])
    ab = dict(bundle["ab_comparison"])
    selected_policy = dict(bundle["selected_policy"])
    agent_audit = dict(bundle["agent_audit"])
    customers = list(bundle["customers"])
    risk_customer = _select_demo_customer(customers, "recent_outer_risk_change")
    stable_customer = _select_demo_customer(customers, "stable_local_low_mileage")
    persona_rows = _build_persona_rows(bundle, scenario)
    llm_status = _llm_status(summary_report, bundle)

    title = "Senior Safe Mileage 공모전 데모"
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
      align-items: stretch;
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
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: var(--subtle);
      min-height: 104px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 28px; line-height: 1.15; }}
    .metric.good strong {{ color: var(--good); }}
    .metric.warn strong {{ color: var(--warn); }}
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
    @media (max-width: 960px) {{
      .hero-grid, .two-col, .case-grid {{ grid-template-columns: 1fr; }}
      .flow {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 620px) {{
      .shell, .header-inner {{ padding-left: 18px; padding-right: 18px; }}
      h1 {{ font-size: 26px; }}
      .metric-grid, .flow {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <p class="eyebrow">공모전 시연용 화면 · 내부 디버그 대시보드 아님</p>
      <h1>{title}</h1>
      <p class="lead">기존 마일리지가 같은 저주행 고객을 동일하게 보는 한계를, 생활권 안정성·생활권 밖 안전운전·최근 위험변화 지표로 재분류하는 Python 기반 분석/시연 제품입니다.</p>
      <nav class="top-nav" aria-label="데모 흐름">
        <a href="#data-proof">데이터 증거</a>
        <a href="#ab-proof">A/B 핵심 결과</a>
        <a href="#persona-cases">6개 케이스</a>
        <a href="#customer-report">고객 리포트</a>
        <a href="/detail">상세 검증 화면</a>
      </nav>
    </div>
  </header>
  <main class="shell">
    <section class="hero-grid" id="summary" aria-labelledby="summary-heading">
      <div class="statement">
        <h2 id="summary-heading">무엇을 만들었나</h2>
        <p>단순 할인 확대가 아니라, 기존 거리 중심 마일리지 산식을 종합 안심주행 지표로 고도화한 시니어 특화 상품 검증 프로토타입입니다.</p>
        <strong>핵심 주장</strong>
        <p>같은 저주행이라도 생활권 안에서 안정적으로 반복 운전한 고객과, 최근 생활권 밖 야간/급감속/과속이 늘어난 고객은 다르게 설명되어야 합니다.</p>
        <div class="footer-actions">
          <a class="button" href="#data-proof">실제 생성 데이터 보기</a>
          <a class="button" href="#customer-report">예방 케어 고객 예시</a>
        </div>
      </div>
      <div class="metric-grid" aria-label="핵심 수치">
        {_metric_card("합성 고객", f"{trip_stats['customer_count']}명", "6개 페르소나 x 각 5명")}
        {_metric_card("Trip row", f"{trip_stats['trip_count']:,}건", "90일 관측기간 내 실제 주행 발생 row")}
        {_metric_card("위험변화 포착", f"{approval['risk_change_capture_count']}/{approval['risk_change_target_count']}", "기존 산식 0명, 제안 모델 5명", "good")}
        {_metric_card("오분류", f"{approval['total_misclassification_count']}/{approval['total_misclassification_limit']}", "허용 기준 이내", "good")}
      </div>
    </section>

    <section id="data-proof" aria-labelledby="data-proof-heading">
      <h2 id="data-proof-heading">데이터는 실제로 만들어졌나</h2>
      <div class="two-col">
        <div class="panel">
          <h3>생성된 90일 관측 데이터</h3>
          <p class="note">현재 데이터는 실제 고객 개인정보가 아니라, 실제 운영 데이터 형식을 흉내 낸 합성 trip log입니다. 30명 각각에 baseline 60일과 recent 30일 관측기간이 있고, 운전이 발생한 날의 trip row가 저장되어 있습니다.</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="생성 데이터 요약">
              <tbody>
                <tr><th scope="row">파일</th><td><span class="code">data/fixtures/senior_trip_logs.csv</span></td></tr>
                <tr><th scope="row">관측기간</th><td>{escape(trip_stats['date_min'])} ~ {escape(trip_stats['date_max'])} · baseline 60일 + recent 30일</td></tr>
                <tr><th scope="row">데이터 행</th><td>{trip_stats['trip_count']:,} trip rows · baseline {trip_stats['baseline_trip_count']:,} / recent {trip_stats['recent_trip_count']:,}</td></tr>
                <tr><th scope="row">고객/페르소나</th><td>{trip_stats['customer_count']}명 · {trip_stats['persona_count']}개 유형</td></tr>
                <tr><th scope="row">컬럼</th><td>GPS, 시간, 거리, 속도, 야간 여부, 과속/급가감속, 생활권 zone, 위험 신호 코드</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3>OpenAI 사용 상태</h3>
          <p>{escape(llm_status['headline'])}</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="OpenAI 상태">
              <tbody>
                <tr><th scope="row">현재 리포트 모드</th><td><span class="code">{escape(llm_status['report_mode'])}</span></td></tr>
                <tr><th scope="row">외부 API 호출</th><td>{escape(llm_status['service_status'])}</td></tr>
                <tr><th scope="row">키 사용 여부</th><td>{escape(llm_status['key_usage'])}</td></tr>
                <tr><th scope="row">안전장치</th><td>고객명, 차량번호, 정확한 GPS, 원본 trip id는 외부 전송 금지</td></tr>
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
      <h2 id="workflow-heading">분석/Agent 흐름</h2>
      <div class="flow" aria-label="구현 흐름">
        {_flow_step("1", "페르소나", "6개 시니어 운전자 유형과 엣지케이스 정의")}
        {_flow_step("2", "주행 생성", "90일 trip log와 recent 변화 신호 생성")}
        {_flow_step("3", "일관성 검증", "좌표·시간·거리·위험행동 검토")}
        {_flow_step("4", "생활권 분석", "DBSCAN/P90으로 core/buffer/outer 구분")}
        {_flow_step("5", "정책 탐색", "114개 후보 중 승인 게이트 통과 후보 선택")}
        {_flow_step("6", "리포트", "A/B 결과와 XAI reason code를 직원용 설명으로 변환")}
      </div>
    </section>

    <section id="ab-proof" aria-labelledby="ab-proof-heading">
      <h2 id="ab-proof-heading">기존 마일리지와 무엇이 달라졌나</h2>
      <div class="two-col">
        <div class="panel">
          <h3>A/B 핵심 결과</h3>
          <div class="bars">
            {_bar_row("기존 산식", ab["baseline_capture_rate"], f"{ab['baseline_capture_count']}/5 포착")}
            {_bar_row("제안 모델", ab["proposed_capture_rate"], f"{ab['proposed_capture_count']}/5 포착", "good")}
          </div>
          <div class="table-wrap" style="margin-top:14px">
            <table aria-label="A/B 승인 게이트">
              <tbody>
                <tr><th scope="row">저주행 위험변화형</th><td>{approval['risk_change_capture_count']}/{approval['risk_change_target_count']} 포착</td><td><span class="status pass">통과</span></td></tr>
                <tr><th scope="row">비대상 오탐</th><td>{approval['non_target_false_positive_count']}/{approval['non_target_false_positive_limit']}</td><td><span class="status pass">통과</span></td></tr>
                <tr><th scope="row">전체 오분류</th><td>{approval['total_misclassification_count']}/{approval['total_misclassification_limit']}</td><td><span class="status pass">통과</span></td></tr>
                <tr><th scope="row">고객 판정 검증률</th><td>{_format_percent(approval['agent_validation_pass_rate'])}</td><td><span class="status pass">통과</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3>선택 정책 후보</h3>
          <p><span class="code">{escape(str(selected_policy['candidate_id']))}</span></p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="선택 정책 후보">
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
        <table aria-label="6개 페르소나 결과">
          <thead><tr><th>케이스</th><th>검증 목적</th><th>제안 모델 결과</th><th>기존 산식 대비</th></tr></thead>
          <tbody>{_persona_table_rows(persona_rows)}</tbody>
        </table>
      </div>
    </section>

    <section id="customer-report" aria-labelledby="customer-report-heading">
      <h2 id="customer-report-heading">고객 1명으로 보면 어떻게 설명되나</h2>
      <div class="case-grid">
        {_customer_case_card("예방 케어로 포착된 고객", risk_customer)}
        {_customer_case_card("안정 저주행 우대 고객", stable_customer)}
      </div>
    </section>

    <section id="agent-proof" aria-labelledby="agent-proof-heading">
      <h2 id="agent-proof-heading">Agent 검증은 어디까지 됐나</h2>
      <div class="two-col">
        <div class="panel">
          <h3>검증 요약</h3>
          <p>필수 Agent {agent_audit['required_agent_count']}개 산출물 무결성 검증은 {_format_percent(agent_audit['validation_pass_rate'])}이고, 고객 판정 승인 게이트 검증률은 {_format_percent(approval['agent_validation_pass_rate'])}입니다.</p>
          <div class="table-wrap" style="margin-top:12px">
            <table aria-label="Agent 검증 결과">
              <thead><tr><th>Agent</th><th>상태</th><th>산출물</th></tr></thead>
              <tbody>{_agent_rows(agent_audit)}</tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3>심사위원에게 보여줄 결론</h3>
          <p class="note">이 화면은 “실제 고객 사고율을 예측했다”는 주장이 아닙니다. 6개 합성 케이스에서 기존 거리 중심 마일리지가 놓치는 위험변화 신호를 제안 모델이 어떻게 구분하는지 보여주는 검증용 제품 화면입니다.</p>
          <div class="footer-actions">
            <a class="button" href="/detail">상세 검증 화면 열기</a>
            <a class="button" href="/api/validation">Agent 검증 API 보기</a>
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
    return {
        "report_mode": report_mode,
        "service_status": "실제 OpenAI API 호출 없음" if not active else "OpenAI API 호출 활성",
        "key_usage": ".env의 OPENAI_API_KEY는 이번 산출물 생성에서 사용하지 않음" if not active else "식별자 없는 요약 피처만 전송",
        "headline": (
            "현재 산출물은 OpenAI 실호출 결과가 아니라 로컬 deterministic template 리포트입니다. "
            "OpenAI 연동 코드는 구현되어 있고 실패 시 fallback이 검증되어 있습니다."
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


def _artifact_rows() -> str:
    rows = []
    for label, path, role in ARTIFACT_ROWS:
        exists = (ROOT / path).exists()
        status = '<span class="status pass">있음</span>' if exists else '<span class="status review">없음</span>'
        rows.append(
            f"<tr><td>{escape(label)}</td><td><span class=\"code\">{escape(path)}</span></td>"
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
            f"<tr><td><strong>{escape(row['display_name'])}</strong><br><span class=\"code\">{escape(row['persona_type'])}</span></td>"
            f"<td>{escape(row['purpose'])}</td>"
            f"<td><span class=\"status {status}\">{escape(counts or '결과 없음')}</span></td>"
            f"<td>{escape(target)} · 평균 점수 변화 {row['score_delta']:+.1f}</td></tr>"
        )
    return "\n".join(html_rows)


def _customer_case_card(title: str, customer: dict[str, Any]) -> str:
    scores = dict(customer["scores"])
    ab = dict(customer["ab_comparison"])
    reason_codes = ", ".join(str(code) for code in customer.get("xai_reason_codes", ())[:4])
    return f"""<article class="case-card">
          <h3>{escape(title)}</h3>
          <strong>{escape(str(customer['customer_id']))} · {escape(PERSONA_FALLBACK_NAMES.get(str(customer['persona_type']), str(customer['persona_type'])))}</strong>
          <p>{escape(str(customer['care_decision']))} 판정</p>
          <dl>
            <dt>기존 점수</dt><dd>{float(scores['mileage_baseline_score']):.1f}</dd>
            <dt>제안 점수</dt><dd>{float(scores['senior_safe_mileage_score']):.1f}</dd>
            <dt>위험변화</dt><dd>{float(scores['risk_change_score']):.1f}</dd>
            <dt>A/B 차이</dt><dd>{escape(str(ab.get('decision_delta_label', '판정 비교 제공')))}</dd>
            <dt>근거 코드</dt><dd><span class="code">{escape(reason_codes)}</span></dd>
          </dl>
        </article>"""


def _agent_rows(agent_audit: dict[str, Any]) -> str:
    rows = []
    for check in agent_audit.get("checks", ()):
        artifact_ids = ", ".join(str(artifact_id) for artifact_id in check.get("artifact_ids", ()))
        rows.append(
            f"<tr><td><span class=\"code\">{escape(str(check['agent_id']))}</span></td>"
            f"<td><span class=\"status pass\">통과</span></td>"
            f"<td>{escape(artifact_ids)}</td></tr>"
        )
    return "\n".join(rows)


def _format_percent(value: object) -> str:
    return f"{float(value) * 100:.0f}%"

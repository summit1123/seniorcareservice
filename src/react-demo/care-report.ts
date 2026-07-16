/**
 * 케어 리포트 v1 — 구조화(JSON) 직원 검수 리포트 + 고객 재해석 메시지.
 *
 * 설계 원칙:
 * - 숫자(점수·지수·거리·기여)는 전부 엔진/어댑터 값 그대로 — LLM은 재계산 금지.
 * - LLM은 서사 필드(headline/summary/사유/고객 메시지)와 사후지원 "선택"만 담당.
 *   사후지원 항목 자체는 선언된 카탈로그(aftercare_catalog.json)에서만 고른다.
 * - 이 파일의 buildLocalCareReport()는 완전 결정론 — 키가 없거나 서버 호출이
 *   실패해도 동일 스키마로 데모가 계속된다(오프라인 안전).
 */
import catalogJson from "./aftercare-catalog.json";
import { normalizeProductWeights } from "./gaip-decision";
import type { DriverAnnualSummary, MonthlyEvidence } from "./types";
import type { ProductRules } from "./gaip-types";

export type AftercareCatalogItem = {
  id: string;
  title_ko: string;
  description_ko: string;
  trigger_signals: string[];
  partner_type: string;
  urgency: "high" | "medium" | "low" | string;
  customer_benefit_ko: string;
};

export const AFTERCARE_CATALOG: AftercareCatalogItem[] =
  (catalogJson as { items: AftercareCatalogItem[] }).items;

export type CareSignal =
  | "care_gate"
  | "risky_change_high"
  | "in_zone_risky"
  | "night_outer"
  | "mobility_change_only"
  | "coverage_low";

export type CareReport = {
  schema_version: "masil-care-report/v1";
  generated_by: "local_deterministic" | "openai_structured";
  report_month: string;
  driver: {
    id: string;
    name_ko: string;
    age_label: string;
    environment_ko: string;
  };
  verdict: {
    favorable_axis: string;
    care_axis: string;
    integrated_score: number | null;
    headline_ko: string;
    summary_ko: string;
  };
  metrics: {
    mileage_score: number;
    in_zone_safe_score: number | null;
    out_zone_safe_score: number | null;
    pattern_stability_score: number;
    mobility_change_pct: number;
    risky_change_pct: number;
    data_coverage_pct: number;
    monthly_distance_km: number;
  };
  pattern_timeline: Array<{
    month: string;
    change_pct: number;
    care: boolean;
    baseline: boolean;
    selected: boolean;
  }>;
  weight_contributions: Array<{
    key: string;
    label_ko: string;
    score: number | null;
    weight_pct: number;
    contribution: number | null;
  }>;
  xai_reasons: Array<{
    label_ko: string;
    direction: "positive" | "attention" | "neutral";
    note_ko: string;
  }>;
  aftercare: Array<{
    id: string;
    title_ko: string;
    description_ko: string;
    customer_benefit_ko: string;
    urgency: string;
    reason_ko: string;
  }>;
  staff_review: {
    recommendation: "confirm" | "request_more" | "hold";
    rationale_ko: string;
  };
  customer_message: {
    title_ko: string;
    body_ko: string;
    closing_ko: string;
  };
  data_status: string;
};

/** 선택 월의 신호를 선언 규칙으로 도출 — 카탈로그 trigger_signals와 1:1. */
export function deriveCareSignals(row: MonthlyEvidence, rules: ProductRules): CareSignal[] {
  const signals: CareSignal[] = [];
  const mob = row.mobility_change_index_pct ?? 0;
  const risk = row.risky_behavior_change_index_pct ?? 0;
  const careGate = mob >= rules.care_mobility_change_threshold && risk >= rules.care_risky_behavior_threshold;
  if (careGate) signals.push("care_gate");
  if (risk >= rules.care_risky_behavior_threshold) signals.push("risky_change_high");
  // 생활권 안 위험: 안쪽 안전점수가 낮은데 이동 변화는 크지 않은 패턴
  if ((row.in_zone_safe_driving_score ?? 100) < 60 && mob < rules.care_mobility_change_threshold) {
    signals.push("in_zone_risky");
  }
  // 야간 외곽: 케어 게이트가 열린 달의 외곽 이동(합성 데이터는 야간 플래그가 없어
  // 케어 게이트+이동 변화 조합을 프록시로 사용 — 선언된 근사)
  if (careGate && mob >= 40) signals.push("night_outer");
  if (mob >= rules.care_mobility_change_threshold && risk < rules.care_risky_behavior_threshold) {
    signals.push("mobility_change_only");
  }
  if ((row.data_coverage_pct ?? 100) < rules.minimum_data_coverage_pct) signals.push("coverage_low");
  return signals;
}

/** 신호에 맞는 사후지원을 카탈로그에서 결정론적으로 선택(urgency 순, 최대 3개). */
export function selectAftercare(signals: CareSignal[]): AftercareCatalogItem[] {
  const order = { high: 0, medium: 1, low: 2 } as Record<string, number>;
  const picked = AFTERCARE_CATALOG.filter((item) =>
    item.trigger_signals.some((trigger) => (signals as string[]).includes(trigger))
  );
  picked.sort((a, b) => (order[a.urgency] ?? 9) - (order[b.urgency] ?? 9));
  return picked.slice(0, 3);
}

function stateKo(value: string | undefined, fallback: string): string {
  return value && value.length ? value : fallback;
}

/** 완전 결정론 로컬 빌더 — LLM 없이 동일 스키마를 채운다. */
export function buildLocalCareReport(
  driver: DriverAnnualSummary,
  rows: MonthlyEvidence[],
  selected: MonthlyEvidence,
  rules: ProductRules,
  driverNameKo: string
): CareReport {
  const weights = normalizeProductWeights(rules.weights);
  const signals = deriveCareSignals(selected, rules);
  const aftercareItems = selectAftercare(signals);
  const careGate = signals.includes("care_gate");
  const mob = selected.mobility_change_index_pct ?? 0;
  const risk = selected.risky_behavior_change_index_pct ?? 0;
  const integrated = selected.monthly_integrated_evidence_score ?? null;

  const contributions = [
    { key: "mileage", label_ko: "주행거리", score: selected.mileage_score as number | null, weight_pct: weights.mileage },
    { key: "in_zone_safe", label_ko: "생활권 안 안전", score: selected.in_zone_safe_driving_score, weight_pct: weights.in_zone_safe },
    { key: "out_zone_safe", label_ko: "생활권 밖 안전", score: selected.out_zone_safe_driving_score, weight_pct: weights.out_zone_safe },
    { key: "pattern_stability", label_ko: "패턴 안정성", score: (selected.pattern_stability_score ?? null) as number | null, weight_pct: weights.pattern_stability }
  ].map((entry) => ({
    ...entry,
    contribution: entry.score === null ? null : Math.round(entry.score * entry.weight_pct) / 100
  }));

  const headline = careGate
    ? "이동 맥락과 위험행동의 동시변화 — 사람 검토 제안"
    : selected.care_state === "Hold" || selected.reward_state === "Hold"
      ? "근거 부족 — 판단 보류(불이익 없음)"
      : (selected.reward_state ?? "").toLowerCase() === "reward"
        ? "익숙한 생활권 안 안정 주행 — 우대 근거 충족"
        : "기준 범위 내 주행 — 기본 유지";

  const summary = careGate
    ? `${selected.service_month}에 이동 변화 ${mob.toFixed(1)}%p와 위험행동 변화 ${risk.toFixed(1)}%p가 같은 달에 함께 관찰됐습니다. 자동 조치 없이 담당자 검토와 예방 지원 연결을 제안합니다.`
    : `${selected.service_month} 주행 ${selected.monthly_total_distance_km}km, 데이터 사용률 ${selected.data_coverage_pct ?? 0}% 기준으로 평가했습니다. 위치만으로 감점하지 않으며, 아래 지표가 판단의 전부입니다.`;

  const xai: CareReport["xai_reasons"] = [
    {
      label_ko: "이동 맥락 변화",
      direction: mob >= rules.care_mobility_change_threshold ? "attention" : "neutral",
      note_ko: mob >= rules.care_mobility_change_threshold
        ? `기준선 대비 생활권 밖 비중이 ${mob.toFixed(1)}%p 상승 — 케어 임계(${rules.care_mobility_change_threshold}%p) 초과`
        : `기준선 대비 ${mob.toFixed(1)}%p — 임계 이내의 자연스러운 변동`
    },
    {
      label_ko: "생활권 안 안전",
      direction: (selected.in_zone_safe_driving_score ?? 100) >= 75 ? "positive" : "attention",
      note_ko: selected.in_zone_safe_driving_score === null
        ? "해당 월 생활권 안 관측 없음(감점 아님)"
        : `${selected.in_zone_safe_driving_score}점 — 익숙한 반경 안 급감속·과속 빈도 반영`
    },
    {
      label_ko: "생활권 밖 안전",
      direction: (selected.out_zone_safe_driving_score ?? 100) >= 75 ? "positive" : "attention",
      note_ko: selected.out_zone_safe_driving_score === null
        ? "해당 월 외부 이동 없음(중립)"
        : `${selected.out_zone_safe_driving_score}점 — 외부 이동 자체는 중립, 행동만 평가`
    },
    {
      label_ko: "위험행동 변화",
      direction: risk >= rules.care_risky_behavior_threshold ? "attention" : "positive",
      note_ko: risk >= rules.care_risky_behavior_threshold
        ? `기준선 대비 ${risk.toFixed(1)}%p 상승 — 이동 변화와 함께 나타나 케어 게이트 충족`
        : `기준선 대비 ${risk.toFixed(1)}%p — 급증 신호 없음`
    }
  ];

  const recommendation: CareReport["staff_review"]["recommendation"] = careGate
    ? "confirm"
    : (selected.data_coverage_pct ?? 100) < rules.minimum_data_coverage_pct
      ? "hold"
      : "confirm";

  const shortName = driverNameKo.replace(/\s*\(.*\)\s*$/, "");
  const customerTitle = careGate
    ? `${shortName}님, 이번 달 새로운 길을 많이 다니셨네요`
    : `${shortName}님, 이번 달도 안전 운전 감사합니다`;
  const customerBody = careGate
    ? `${selected.service_month}에는 평소보다 먼 곳을 자주 다니셨고, 새 경로에서 급제동이 조금 늘었습니다. 벌점이나 보험료 불이익이 아니라, 안전하게 계속 운전하시도록 아래 지원을 준비했습니다.`
    : `${selected.service_month}에는 익숙한 생활권 안에서 안정적으로 운전하셨습니다. 이 기록은 우대 혜택 산정에 그대로 반영됩니다.`;

  return {
    schema_version: "masil-care-report/v1",
    generated_by: "local_deterministic",
    report_month: selected.service_month,
    driver: {
      id: driver.customer_id,
      name_ko: driverNameKo,
      age_label: driver.persona_display_name_ko,
      environment_ko: driver.environment_display_name_ko ?? driver.environment_id ?? ""
    },
    verdict: {
      favorable_axis: stateKo(driver.reward_state, "Neutral"),
      care_axis: stateKo(selected.care_state, "None"),
      integrated_score: integrated,
      headline_ko: headline,
      summary_ko: summary
    },
    metrics: {
      mileage_score: selected.mileage_score,
      in_zone_safe_score: selected.in_zone_safe_driving_score,
      out_zone_safe_score: selected.out_zone_safe_driving_score,
      pattern_stability_score: selected.pattern_stability_score ?? Math.max(0, 100 - selected.out_zone_pattern_change_risk),
      mobility_change_pct: mob,
      risky_change_pct: risk,
      data_coverage_pct: selected.data_coverage_pct ?? 0,
      monthly_distance_km: selected.monthly_total_distance_km
    },
    pattern_timeline: rows.map((row) => ({
      month: row.service_month,
      change_pct: Math.min(100, row.mobility_change_index_pct ?? row.out_zone_pattern_change_risk),
      care: row.care_state === "Care Review",
      baseline: row.period_role === "baseline",
      selected: row.month === selected.month
    })),
    weight_contributions: contributions,
    xai_reasons: xai,
    aftercare: aftercareItems.map((item) => ({
      id: item.id,
      title_ko: item.title_ko,
      description_ko: item.description_ko,
      customer_benefit_ko: item.customer_benefit_ko,
      urgency: item.urgency,
      reason_ko: careGate
        ? "같은 달 동시변화 신호에 대응하는 선언 규칙 매칭"
        : "선택 월 신호에 대응하는 선언 규칙 매칭"
    })),
    staff_review: {
      recommendation,
      rationale_ko: careGate
        ? "동시변화 게이트 충족 — 자동 감액이 아니라 예방 지원 연결이 목적이므로, 지원 항목 확정 후 고객 발송을 권합니다."
        : recommendation === "hold"
          ? "데이터 사용률이 최소 기준 미만 — 불이익 없이 보류하고 수집 점검을 권합니다."
          : "지표가 기준 범위 내 — 리포트 승인 후 고객 발송을 권합니다."
    },
    customer_message: {
      title_ko: customerTitle,
      body_ko: customerBody,
      closing_ko: "지원이 필요하시면 아래에서 신청해 주세요. 이 리포트는 안내용이며, 보험료·인수 결정을 확정하지 않습니다."
    },
    data_status: "합성 시뮬레이션 — 실제 고객 데이터가 아니며, 담당자 검수 후 고객에게 전달되는 흐름의 데모입니다."
  };
}

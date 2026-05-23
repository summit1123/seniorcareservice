import { existsSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import type { ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";
import { defineConfig, type ViteDevServer } from "vite";

const viewModelPath = fileURLToPath(new URL("./data/fixtures/judge_demo_view_model.json", import.meta.url));
const zoneSnapshotPath = fileURLToPath(new URL("./data/processed/monthly_zone_snapshots.json", import.meta.url));
const localEnvPath = fileURLToPath(new URL("./.env", import.meta.url));
const openAIResponsesUrl = "https://api.openai.com/v1/responses";

type JsonObject = Record<string, unknown>;
type ReportFeatures = ReturnType<typeof buildReportFeatures>;

let cachedLocalEnv: Record<string, string> | null = null;

function readLocalEnv() {
  if (cachedLocalEnv) return cachedLocalEnv;
  cachedLocalEnv = {};
  if (!existsSync(localEnvPath)) return cachedLocalEnv;

  const lines = readFileSync(localEnvPath, "utf-8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) continue;
    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    cachedLocalEnv[key] = value;
  }
  return cachedLocalEnv;
}

function envValue(name: string) {
  return process.env[name] || readLocalEnv()[name] || "";
}

async function readJson(path: string): Promise<JsonObject> {
  return JSON.parse(await readFile(path, "utf-8")) as JsonObject;
}

function sendJson(res: ServerResponse, statusCode: number, payload: unknown) {
  const body = JSON.stringify(payload);
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(body);
}

function toRecord(value: unknown): JsonObject {
  return value && typeof value === "object" ? (value as JsonObject) : {};
}

function toArray(value: unknown): JsonObject[] {
  return Array.isArray(value) ? (value as JsonObject[]) : [];
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" ? value : Number(value ?? fallback) || fallback;
}

function krw(value: unknown): string {
  return `${Math.round(num(value)).toLocaleString("ko-KR")}원`;
}

function pct(value: unknown): string {
  return `${num(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}

function normalizedPremium(value: unknown, fallback: number) {
  const candidate = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(candidate)) return fallback;
  return Math.max(100000, Math.min(5000000, Math.round(candidate)));
}

function projectedPremium(comparison: JsonObject, basePremiumInput?: number) {
  const basePremium = normalizedPremium(basePremiumInput, num(comparison.base_premium_krw));
  const existingRate = num(comparison.existing_discount_rate_pct);
  const proposedRate = num(comparison.proposed_discount_rate_pct);
  const existingDiscount = Math.round(basePremium * (existingRate / 100));
  const proposedDiscount = Math.round(basePremium * (proposedRate / 100));
  return {
    basePremium,
    existingRate,
    proposedRate,
    existingDiscount,
    proposedDiscount,
    existingNet: basePremium - existingDiscount,
    proposedNet: basePremium - proposedDiscount,
    discountDelta: proposedDiscount - existingDiscount,
    premiumDelta: (basePremium - proposedDiscount) - (basePremium - existingDiscount)
  };
}

function reasonLabel(code: string): string {
  const labels: Record<string, string> = {
    CANDIDATE_LIVING_ZONE: "후보 생활권 관찰",
    HARSH_BRAKE_INCREASE: "급감속 증가",
    LOW_MILEAGE: "저주행 조건",
    LOW_NIGHT_DRIVING: "야간 주행 낮음",
    LOW_RISK_EVENTS: "위험행동 낮음",
    NIGHT_DRIVING_INCREASE: "야간 주행 증가",
    NO_RECENT_OUT_ZONE_SPIKE: "최근 생활권 밖 급증 없음",
    NO_STRONG_RISK_CHANGE: "강한 위험변화 없음",
    OUT_ZONE_PATTERN_CHANGE_RISK: "생활권 밖 위험변화",
    OUT_ZONE_RATIO_INCREASE: "생활권 밖 비중 증가",
    OUT_ZONE_SAFE: "생활권 밖 안정",
    OUT_ZONE_SAFE_DRIVING: "생활권 밖 안전주행",
    PREVENTIVE_CARE_REVIEW: "예방 케어 검토",
    RISK_EVENT_INCREASE: "위험행동 증가",
    STABLE_IN_ZONE_DRIVING: "생활권 안 안정주행"
  };
  return labels[code] ?? code;
}

const personaNames = [
  "김영호",
  "박순자",
  "이정식",
  "최명희",
  "정기철",
  "윤복순",
  "한상일",
  "오미자",
  "강문수",
  "서정례",
  "조한기",
  "문영희",
  "배상국",
  "신옥자",
  "유만호",
  "임경자",
  "노성식",
  "홍금자",
  "권태식",
  "장순덕",
  "고재훈",
  "백영도",
  "남기철",
  "송화자",
  "양춘호",
  "차미경",
  "주병일",
  "민정례",
  "하석준",
  "도영자"
];

const CARE_REVIEW_RISK_THRESHOLD = 70;

function personaIndex(customerId: unknown) {
  const matched = text(customerId).match(/(\d+)$/);
  return matched ? Math.max(0, Number(matched[1]) - 1) : 0;
}

function personaName(customerId: unknown) {
  return `${personaNames[personaIndex(customerId)] ?? "시니어 운전자"} 어르신`;
}

function basisLabel(value: unknown) {
  if (value === "pre_policy_60_day_dbscan") return "가입 전 60일 기준";
  if (value === "rolling_60_day_dbscan") return "직전 60일 갱신";
  return text(value);
}

function distanceScopeLabel(value: unknown) {
  if (value === "evaluation_period_only") return "평가기간만 반영";
  return text(value, "12개월 평가");
}

function findDriver(viewModel: JsonObject, driverId: string): JsonObject | undefined {
  const drivers = viewModel.drivers as JsonObject[] | undefined;
  return drivers?.find((driver) => driver.customer_id === driverId || driver.driver_id === driverId);
}

function findZoneSnapshot(zones: JsonObject, customerId: unknown, month: number): JsonObject | undefined {
  return toArray(zones.snapshots).find((row) => row.customer_id === customerId && row.month === month);
}

function interpretationLabel(value: unknown): string {
  const labels: Record<string, string> = {
    candidate_living_zone: "반복 외부 후보",
    existing_living_zone: "기준 생활권 안",
    out_zone_pattern_change_risk: "생활권 밖 위험변화",
    out_zone_safe_driving: "생활권 밖 안정"
  };
  return labels[text(value)] ?? text(value, "미분류");
}

function destinationLabel(value: unknown): string {
  const labels: Record<string, string> = {
    clinic: "병원",
    family: "자녀 집",
    family_home: "자녀 집",
    home: "자택",
    leisure: "근교 외출지",
    market: "마트",
    pharmacy: "약국",
    unknown_outer: "신규 외부 목적지"
  };
  return labels[text(value)] ?? text(value, "알 수 없는 목적지");
}

function personaTypeLabel(value: unknown): string {
  const labels: Record<string, string> = {
    stable_local_low_mileage: "생활권 안 저주행 안정형",
    stable_outer_safe: "생활권 밖 안정 주행형",
    recent_outer_risk_change: "최근 생활권 밖 위험변화형",
    in_zone_risky_low_mileage: "생활권 안 저주행 위험행동형",
    medical_visit_pattern: "병원 방문 반복 외부 목적지형",
    irregular_family_support: "가족 돌봄 불규칙 외부 이동형"
  };
  return labels[text(value)] ?? text(value, "시니어 운전자");
}

function decisionLabel(value: unknown): string {
  const labels: Record<string, string> = {
    우대: "우대",
    기본: "기본",
    "예방 케어": "예방 케어",
    Favorable: "우대",
    Preferred: "우대",
    Standard: "기본",
    "Preventive Care": "예방 케어"
  };
  return labels[text(value)] ?? text(value, "기본");
}

function translateKnownText(value: unknown): string {
  const labels: Record<string, string> = {
    "Under 3,000 km": "3천km 이하",
    "Under 4,000 km": "4천km 이하",
    "Under 5,000 km": "5천km 이하",
    "Under 6,000 km": "6천km 이하",
    "Under 7,000 km": "7천km 이하",
    "Under 8,000 km": "8천km 이하",
    "Under 9,000 km": "9천km 이하",
    "About 2 trips/week": "주 2회 내외",
    "3-4 trips/week": "주 3~4회",
    "Mostly In-Zone": "생활권 안 중심",
    "Low risk events": "위험행동 낮음",
    "Repeated external destinations with stable behavior": "반복 외부 목적지 안정",
    "Increase in external destinations in the second half": "하반기 외부 목적지 증가",
    "Increase in night driving and harsh braking in the second half": "하반기 야간/급제동 증가",
    "Repeated In-Zone speeding and harsh braking": "생활권 안 과속/급감속 반복",
    "Repeated external hospital trips": "반복 병원 목적 외부 이동",
    "Mostly daytime hospital trips with low risk events": "주간 병원 이동 중심, 위험행동 낮음",
    "Variable external travel for family care": "가족 돌봄 외부 이동 변동",
    "External travel varies, but risk events remain limited": "외부 이동은 변동하나 위험행동 제한적"
  };
  return labels[text(value)] ?? text(value);
}

function englishLivingPattern(value: unknown): JsonObject {
  const pattern = toRecord(value);
  return {
    home_anchor: text(pattern.home_anchor),
    weekly_outing_frequency: translateKnownText(pattern.weekly_outing_frequency_ko),
    primary_destinations: toArray(pattern.primary_destinations).map((item) => destinationLabel(item)),
    outer_trip_tendency: translateKnownText(pattern.outer_trip_tendency),
    risk_behavior_tendency: translateKnownText(pattern.risk_behavior_tendency)
  };
}

function englishCareContext(value: unknown): JsonObject {
  const context = toRecord(value);
  return {
    product_role: translateKnownText(context.product_role),
    message_focus: translateKnownText(context.message_focus),
    false_positive_or_negative_risk: translateKnownText(context.false_positive_or_negative_risk)
  };
}

function translateDecisionCounts(value: unknown): Record<string, number> {
  const counts = toRecord(value);
  return Object.fromEntries(Object.entries(counts).map(([key, count]) => [decisionLabel(key), num(count)]));
}

function englishPersonaSummary(value: JsonObject): JsonObject {
  return {
    ...value,
    persona_display_name_ko: personaTypeLabel(value.persona_type),
    decision_counts: translateDecisionCounts(value.decision_counts)
  };
}

function englishTierSegment(value: JsonObject): JsonObject {
  return {
    ...value,
    existing_matched_tier_label: translateKnownText(value.existing_matched_tier_label),
    proposed_decision_signal_counts: translateDecisionCounts(value.proposed_decision_signal_counts)
  };
}

function englishDriverOption(value: JsonObject): JsonObject {
  const driverId = text(value.driver_id);
  const personaType = text(value.persona_type);
  return {
    ...value,
    label: `${driverId} · ${personaTypeLabel(personaType)}`,
    annual_decision_signal: decisionLabel(value.annual_decision_signal),
    existing_matched_tier_label: translateKnownText(value.existing_matched_tier_label)
  };
}

function englishProductFrame(): JsonObject {
  return {
    product_name_ko: "안심반경 시니어 마일리지",
    existing_formula_ko: "연간 주행거리 + 차종 → 기존 마일리지 할인율",
    proposed_formula_ko: "연간 주행거리 + 12개월 생활권 안정성 + 생활권 밖 안전성 + 위험변화 → 통합점수 기반 할인 보정",
    llm_boundary_ko: "LLM은 보험료를 계산하지 않고, 이미 계산된 근거를 직원용 설명문으로 변환합니다."
  };
}

function englishDestinations(value: unknown): JsonObject {
  return Object.fromEntries(
    Object.entries(toRecord(value)).map(([key, destination]) => {
      const record = toRecord(destination);
      return [key, { ...record, label_ko: destinationLabel(key) }];
    })
  );
}

function englishDriverSummary(value: JsonObject): JsonObject {
  const annualScore = toRecord(value.annual_score);
  const comparison = toRecord(value.ab_comparison);
  return {
    ...value,
    persona_display_name_ko: personaTypeLabel(value.persona_type),
    living_pattern: {
      ...toRecord(value.living_pattern),
      weekly_outing_frequency_ko: translateKnownText(toRecord(value.living_pattern).weekly_outing_frequency_ko),
      outer_trip_tendency: translateKnownText(toRecord(value.living_pattern).outer_trip_tendency),
      risk_behavior_tendency: translateKnownText(toRecord(value.living_pattern).risk_behavior_tendency)
    },
    care_context: englishCareContext(value.care_context),
    living_destinations: englishDestinations(value.living_destinations),
    annual_score: {
      ...annualScore,
      annual_decision_signal: decisionLabel(annualScore.annual_decision_signal)
    },
    ab_comparison: {
      ...comparison,
      existing_matched_tier_label: translateKnownText(comparison.existing_matched_tier_label),
      annual_decision_signal: decisionLabel(comparison.annual_decision_signal)
    }
  };
}

function englishZoneSnapshot(value: JsonObject): JsonObject {
  return {
    ...value,
    trip_interpretations: toArray(value.trip_interpretations).map((trip) => ({
      ...trip,
      destination_label_ko: destinationLabel(trip.destination_type)
    })),
    source_event: {
      ...toRecord(value.source_event),
      event_label_ko: translateKnownText(toRecord(value.source_event).event_label_ko),
      living_zone_interpretation_ko: translateKnownText(toRecord(value.source_event).living_zone_interpretation_ko)
    }
  };
}

function groupedTripEvidence(snapshot: JsonObject) {
  const trips = toArray(snapshot.trip_interpretations);
  const grouped = new Map<
    string,
    {
      key: string;
      label: string;
      count: number;
      distanceKm: number;
      riskEvents: number;
      nightTrips: number;
      repeatTrips: number;
      newDestinationTrips: number;
      interpretations: Record<string, number>;
    }
  >();

  for (const trip of trips) {
    const key = text(trip.destination_type, "unknown");
    const current =
      grouped.get(key) ??
      {
        key,
        label: destinationLabel(key),
        count: 0,
        distanceKm: 0,
        riskEvents: 0,
        nightTrips: 0,
        repeatTrips: 0,
        newDestinationTrips: 0,
        interpretations: {}
      };

    current.count += 1;
    current.distanceKm += num(trip.distance_km);
    current.riskEvents += num(trip.risk_event_count);
    current.nightTrips += num(trip.night_drive_flag);
    current.repeatTrips += num(trip.route_repeat_flag);
    current.newDestinationTrips += num(trip.new_destination_flag);
    const interpretation = text(trip.interpretation, "unknown");
    current.interpretations[interpretation] = (current.interpretations[interpretation] ?? 0) + 1;
    grouped.set(key, current);
  }

  return [...grouped.values()].sort((a, b) => b.count - a.count || b.distanceKm - a.distanceKm);
}

function dominantInterpretation(item: ReturnType<typeof groupedTripEvidence>[number]) {
  return Object.entries(item.interpretations).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "unknown";
}

function reportEvidence(snapshot: JsonObject) {
  const grouped = groupedTripEvidence(snapshot);
  const trips = toArray(snapshot.trip_interpretations);
  const monthlyEvidence = toRecord(snapshot.monthly_evidence);
  const scores = toRecord(snapshot.scores);
  const tripCount = trips.length;
  const riskEvents = grouped.reduce((sum, item) => sum + item.riskEvents, 0);
  const nightTrips = grouped.reduce((sum, item) => sum + item.nightTrips, 0);
  const repeatTrips = grouped.reduce((sum, item) => sum + item.repeatTrips, 0);
  const newDestinationTrips = grouped.reduce((sum, item) => sum + item.newDestinationTrips, 0);
  const outZoneRatio = num(monthlyEvidence.out_zone_distance_ratio);
  const riskScore = num(scores.out_zone_pattern_change_risk);
  const repeatRate = tripCount ? repeatTrips / tripCount : 0;
  const topDestinations = grouped.slice(0, 3).map((item) => item.label);

  let headline = "생활권 안 반복 안정 주행";
  if (riskScore >= CARE_REVIEW_RISK_THRESHOLD || riskEvents >= Math.max(3, tripCount * 0.25)) {
    headline = "위험행동이 증가한 월";
  } else if (outZoneRatio >= 0.25 && repeatRate >= 0.5 && riskEvents <= Math.max(1, tripCount * 0.12)) {
    headline = "반복 목적지 중심의 생활권 밖 이동";
  } else if (newDestinationTrips >= Math.max(2, tripCount * 0.2)) {
    headline = "신규 목적지 증가 관찰";
  } else if (outZoneRatio < 0.12 && riskEvents === 0) {
    headline = "생활권 안 안정 주행 유지";
  } else {
    headline = "생활권 안 반복 안정 주행";
  }

  const outerPattern =
    outZoneRatio < 0.12
      ? "생활권 밖 비중이 낮아 기준 생활권 중심의 월로 해석됩니다."
      : repeatRate >= 0.5
        ? "생활권 밖 이동은 있으나 반복 경로와 반복 목적지가 있어 자동 위험으로 보지 않습니다."
        : "생활권 밖 이동이 분산되어 다음 달에도 같은 패턴을 재확인해야 합니다.";

  const riskPattern =
    riskEvents === 0
      ? "급감속이나 과속과 같은 위험행동 신호가 거의 없습니다."
      : riskScore >= CARE_REVIEW_RISK_THRESHOLD
        ? `위험행동 ${riskEvents}건과 위험변화 점수 ${riskScore.toFixed(1)}점이 함께 높아 예방 케어 검토가 권장됩니다.`
        : `위험행동 ${riskEvents}건이 관찰됐지만 위험변화 신호는 제한적입니다.`;

  const action =
    riskScore >= CARE_REVIEW_RISK_THRESHOLD
      ? "상담 시 안전운전 리포트, 차량 점검, 야간 또는 낯선 경로 주의 안내를 우선합니다."
      : outZoneRatio >= 0.25 && repeatRate >= 0.5
        ? "생활권 밖 주행이라는 이유만으로 불리하게 보지 말고 반복 목적지와 낮은 위험행동을 함께 설명합니다."
        : "연간 산식 근거로 누적하고 다음 갱신 월에 변화폭을 재확인합니다.";

  return {
    grouped,
    headline,
    topDestinations,
    outZoneRatio,
    repeatRate,
    riskEvents,
    nightTrips,
    newDestinationTrips,
    outerPattern,
    riskPattern,
    action
  };
}

function buildReportFeatures(driver: JsonObject, snapshot: JsonObject, month: number, basePremiumInput?: number) {
  const comparison = toRecord(driver.ab_comparison);
  void basePremiumInput;
  const annualScore = toRecord(driver.annual_score);
  const monthlyEvidence = toRecord(snapshot.monthly_evidence);
  const scores = toRecord(snapshot.scores);
  const basisWindow = toRecord(snapshot.basis_window);
  const buffer = toRecord(toRecord(snapshot.living_zone).buffer);
  const leakageGuard = toRecord(snapshot.leakage_guard);
  const sourceEvent = toRecord(snapshot.source_event);
  const reasonCodes = toArray(comparison.annual_reason_codes).map(String);
  const monthlyReasonCodes = toArray(monthlyEvidence.reason_codes)
    .map(String)
    .filter((code) => {
      if (code === "OUT_ZONE_RATIO_INCREASE") return num(monthlyEvidence.out_zone_ratio_delta) > 0;
      if (code === "NIGHT_DRIVING_INCREASE") return num(monthlyEvidence.night_ratio_delta) > 0;
      if (code === "RISK_EVENT_INCREASE" || code === "HARSH_BRAKE_INCREASE") return num(monthlyEvidence.risk_rate_delta_per_100km) > 0;
      if (code === "OUT_ZONE_PATTERN_CHANGE_RISK") return num(scores.out_zone_pattern_change_risk) >= 50;
      return true;
    });
  const decision = decisionLabel(text(comparison.annual_decision_signal, text(annualScore.annual_decision_signal, "기본")));
  const careRequired = Boolean(comparison.preventive_care_required);
  const livingZone = toRecord(snapshot.living_zone);
  const grouped = groupedTripEvidence(snapshot).slice(0, 8).map((item) => ({
    destination_type: item.key,
    destination_label: item.label,
    trip_count: item.count,
    distance_km: Number(item.distanceKm.toFixed(1)),
    risk_event_count: item.riskEvents,
    night_trip_count: item.nightTrips,
    repeat_trip_count: item.repeatTrips,
    new_destination_trip_count: item.newDestinationTrips,
    dominant_interpretation: interpretationLabel(dominantInterpretation(item))
  }));

  return {
    report_role: "보험사 직원을 위한 월별 주행 근거 설명 리포트",
    report_month: month,
    generation_contract: {
      pricing_is_already_calculated: true,
      llm_must_not_recalculate_discount: true,
      monthly_report_must_not_include_premium_amounts: true,
      monthly_evidence_is_for_annual_decision_explanation: true,
      avoid_penalty_language_for_senior_customer: true,
      privacy_filter: "원본 좌표와 식별자는 제외하고 요약 피처만 LLM에 전달"
    },
    driver_profile: {
      display_name: personaName(driver.customer_id),
      persona_type: text(driver.persona_type),
      persona_display_name: personaTypeLabel(driver.persona_type),
      vehicle_class: text(driver.vehicle_class),
      living_area_pattern: englishLivingPattern(driver.living_pattern),
      care_context: englishCareContext(driver.care_context)
    },
    annual_decision_reference: {
      annual_distance_km: num(comparison.annual_total_distance_km),
      annual_distance_scope: distanceScopeLabel(comparison.annual_distance_scope),
      existing_mileage_tier_label: translateKnownText(comparison.existing_matched_tier_label),
      proposed_integrated_formula: {
        rule_id: text(comparison.proposed_discount_rule_id),
        rationale_code: text(comparison.proposed_rationale_code),
        decision_signal: decision,
        preventive_care_required: careRequired
      },
      pricing_note: "보험료와 할인액은 연간 산식 화면 또는 최종 판단 패널에서 별도로 계산하며, 월별 리포트 본문에는 금액을 쓰지 않습니다.",
      annual_scores: {
        mileage_score: num(annualScore.annual_mileage_score),
        in_zone_safe_driving_score: num(annualScore.annual_in_zone_safe_driving_score),
        out_zone_safe_driving_score: num(annualScore.annual_out_zone_safe_driving_score),
        senior_safe_mileage_score: num(annualScore.annual_senior_safe_mileage_score),
        out_zone_pattern_change_risk: num(annualScore.annual_out_zone_pattern_change_risk),
        score_tier: text(annualScore.annual_score_tier)
      },
      reason_codes: reasonCodes.map((code) => ({ code, label: reasonLabel(code) }))
    },
    monthly_living_area_evidence: {
      service_month: text(snapshot.service_month),
      basis_window: {
        start_date: text(basisWindow.start_date),
        end_date: text(basisWindow.end_date),
        days: num(basisWindow.days),
        basis_trip_count: num(basisWindow.basis_trip_count),
        scored_trip_count: num(basisWindow.scored_trip_count),
        basis_status: basisLabel(basisWindow.basis_status)
      },
      living_area_model: {
        backend: text(livingZone.zone_model_backend),
        cluster_count: num(livingZone.cluster_count),
        departure_p90_threshold_m: num(buffer.departure_p90_threshold_m),
        departure_threshold_percentile: num(buffer.departure_threshold_percentile)
      },
      leakage_guard: {
        current_month_excluded_from_zone_fit: Boolean(leakageGuard.current_month_excluded_from_zone_fit),
        current_month_trip_count_in_basis: num(leakageGuard.current_month_trip_count_in_basis)
      },
      monthly_evidence: {
        distance_km: num(monthlyEvidence.monthly_distance_km),
        trip_count: num(monthlyEvidence.trip_count),
        in_zone_distance_ratio_pct: Number((num(monthlyEvidence.in_zone_distance_ratio) * 100).toFixed(1)),
        out_zone_distance_ratio_pct: Number((num(monthlyEvidence.out_zone_distance_ratio) * 100).toFixed(1)),
        out_zone_ratio_delta_pct_point: Number((num(monthlyEvidence.out_zone_ratio_delta) * 100).toFixed(1)),
        night_ratio_delta_pct_point: Number((num(monthlyEvidence.night_ratio_delta) * 100).toFixed(1)),
        risk_rate_delta_per_100km: Number(num(monthlyEvidence.risk_rate_delta_per_100km).toFixed(2)),
        interpretation_counts: monthlyEvidence.interpretation_counts,
        reason_codes: monthlyReasonCodes.map((code) => ({ code, label: reasonLabel(code) }))
      },
      four_scores: {
        mileage_score: num(scores.mileage_score),
        in_zone_safe_driving_score: num(scores.in_zone_safe_driving_score),
        out_zone_safe_driving_score: num(scores.out_zone_safe_driving_score),
        out_zone_pattern_change_risk: num(scores.out_zone_pattern_change_risk),
        monthly_integrated_evidence_score: num(scores.monthly_integrated_evidence_score),
        score_role: text(scores.score_role)
      },
      trip_group_evidence: grouped,
      source_event: {
        label: translateKnownText(sourceEvent.event_label_ko),
        interpretation: translateKnownText(sourceEvent.living_zone_interpretation_ko)
      }
    }
  };
}

function buildReportPrompt(features: ReportFeatures) {
  const systemPrompt = [
    "당신은 자동차보험 상품기획 및 심사 직원을 위한 내부 주행 리포트를 작성하는 어시스턴트입니다.",
    "입력값은 이미 산식과 XAI 파이프라인에서 계산된 값이므로 할인율, 점수, 금액을 다시 계산하거나 추정하지 마세요.",
    "이 리포트는 고객 안내문이 아니라 내부 검토, 상담 준비, 예방 케어 판단을 위한 설명문입니다.",
    "고령 고객에게 벌점, 제재, 낙인처럼 들리는 표현을 피하고 예방 케어와 근거 확인 중심으로 작성하세요.",
    "월별 리포트는 연간 판단을 설명하는 근거 리포트이며 보험료 계산서가 아닙니다.",
    "본문에서 기존 할인액, 제안 할인액, 최종 보험료 차이, 인상, 할증, 보험료 상승을 언급하지 마세요.",
    "월별 근거값과 연간 할인율을 명확히 구분하세요.",
    "직원이 10초 안에 핵심을 이해할 수 있도록 월별 결론, 핵심 근거, 추천 조치를 먼저 배치하세요.",
    "Markdown으로 작성하고, 표는 최대 1개만 사용하며, 입력된 숫자 피처값은 그대로 보존하세요.",
    "각 섹션은 2~4개 bullet로 작성하고, 필요하면 구체적인 피처값과 reason code를 함께 언급하세요."
  ].join("\n");

  const userPrompt = [
    "아래 privacy_filtered_features만 사용해 한국어로 리포트를 작성하세요.",
    "반드시 다음 7개 Markdown 섹션 제목을 그대로 사용하세요. 섹션을 생략하거나 이름을 바꾸지 마세요.",
    "## 1. 월별 결론 요약",
    "## 2. 연간 산식 반영",
    "## 3. 생활권 판단 근거",
    "## 4. 월별 주행 패턴",
    "## 5. XAI 주요 원인",
    "## 6. 상담 및 케어 액션",
    "## 7. 검토 한계와 확인 필요사항",
    "",
    "작성 규칙:",
    "- 1번 섹션은 이번 달 생활권/위험변화 신호와 다음 직원 조치를 3줄 안에 요약하세요. 보험료 변화는 언급하지 마세요.",
    "- 2번 섹션은 이번 달 근거가 4개 지표(주행거리, 생활권 안 안전, 생활권 밖 안전, 위험변화) 중 어디에 기여하는지 설명하세요. 할인율이나 최종 보험료를 계산하지 마세요.",
    "- 3번 섹션은 가입 전 또는 직전 60일 생활권 산출, P90 인정반경, 생활권 안/밖 비중을 구분해 설명하세요.",
    "- 4번 섹션은 목적지 그룹, 반복 목적지, 신규 목적지, 야간 주행, 위험행동을 직원이 이해하기 쉽게 해석하세요.",
    "- 5번 섹션은 4개 지표가 월별 근거 해석에 어떻게 영향을 주었는지 설명하세요.",
    "- 6번 섹션은 필요 시 예방 케어, 안전운전 리포트, 차량 점검, 다음 달 재확인 액션을 제안하세요.",
    "- 7번 섹션은 원본 좌표가 숨겨져 있고, 월별 근거는 연간 판단 설명용이며, 실제 청구 데이터 검증이 아직 필요하다는 점을 짧게 적으세요.",
    `privacy_filtered_features=${JSON.stringify(features, null, 2)}`
  ].join("\n");

  return { systemPrompt, userPrompt };
}

function extractOpenAIErrorMessage(body: string) {
  try {
    const payload = JSON.parse(body) as JsonObject;
    const error = toRecord(payload.error);
    return text(error.message, body.slice(0, 400));
  } catch {
    return body.slice(0, 400);
  }
}

function extractResponseDelta(event: JsonObject) {
  const eventType = text(event.type);
  if (eventType === "response.output_text.delta" && typeof event.delta === "string") return event.delta;
  if (eventType === "response.refusal.delta" && typeof event.delta === "string") return event.delta;
  if (eventType.endsWith(".delta") && typeof event.delta === "string") return event.delta;
  if (eventType.endsWith(".delta") && typeof event.text === "string") return event.text;
  return "";
}

async function pipeOpenAIEventStream(response: Awaited<ReturnType<typeof fetch>>, res: ServerResponse) {
  if (!response.body) {
    throw new Error("OpenAI response body is empty");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split(/\n\n/);
    buffer = events.pop() ?? "";

    for (const eventBlock of events) {
      const data = eventBlock
        .split(/\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data || data === "[DONE]") continue;

      try {
        const parsed = JSON.parse(data) as JsonObject;
        const delta = extractResponseDelta(parsed);
        if (delta) res.write(delta);
      } catch {
        // Ignore non-JSON stream control frames.
      }
    }
  }
}

async function streamOpenAIReport(res: ServerResponse, features: ReportFeatures) {
  const apiKey = envValue("OPENAI_API_KEY");
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is not set, so the AI report cannot be generated. Add OPENAI_API_KEY to .env and restart the server.");
  }

  const model = envValue("OPENAI_REPORT_MODEL") || envValue("OPENAI_MODEL") || "gpt-4o-mini";
  const { systemPrompt, userPrompt } = buildReportPrompt(features);
  const openAIResponse = await fetch(envValue("OPENAI_RESPONSES_URL") || openAIResponsesUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model,
      stream: true,
      metadata: {
        purpose: "senior_safe_mileage_insurer_report",
        report_month: String(features.report_month)
      },
      input: [
        {
          role: "system",
          content: [{ type: "input_text", text: systemPrompt }]
        },
        {
          role: "user",
          content: [{ type: "input_text", text: userPrompt }]
        }
      ]
    })
  });

  if (!openAIResponse.ok) {
    const body = await openAIResponse.text();
    throw new Error(`OpenAI report stream failed (${openAIResponse.status}): ${extractOpenAIErrorMessage(body)}`);
  }

  res.statusCode = 200;
  res.setHeader("Content-Type", "text/markdown; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Report-Mode", "openai-responses-stream");
  res.setHeader("X-Report-Model", model);

  await pipeOpenAIEventStream(openAIResponse, res);
  res.end();
}

async function streamLiveReport(res: ServerResponse, driver: JsonObject, snapshot: JsonObject, month: number, basePremiumInput?: number) {
  await streamOpenAIReport(res, buildReportFeatures(driver, snapshot, month, basePremiumInput));
}

function configureApiServer(server: ViteDevServer) {
  server.middlewares.use(async (req, res, next) => {
    if (!req.url || !req.url.startsWith("/api/")) {
      next();
      return;
    }

    try {
      const requestUrl = new URL(req.url, "http://localhost");
      const viewModel = await readJson(viewModelPath);

      if (requestUrl.pathname === "/api/personas") {
        sendJson(res, 200, {
          product_frame: englishProductFrame(),
          summary: {
            ...toRecord(viewModel.summary),
            decision_counts: translateDecisionCounts(toRecord(viewModel.summary).decision_counts)
          },
          persona_summaries: toArray(viewModel.persona_summaries).map(englishPersonaSummary),
          existing_tier_segments: toArray(viewModel.existing_tier_segments).map(englishTierSegment),
          driver_options: toArray(viewModel.driver_options).map(englishDriverOption),
          source_artifacts: viewModel.source_artifacts,
          default_customer_id: "cust_011"
        });
        return;
      }

      if (requestUrl.pathname === "/api/reports/stream") {
        const driverId = requestUrl.searchParams.get("driverId") ?? "";
        const month = Number(requestUrl.searchParams.get("month") ?? "1");
        const basePremiumInput = Number(requestUrl.searchParams.get("basePremiumKrw") ?? "");
        const driver = findDriver(viewModel, driverId);

        if (!driver) {
          sendJson(res, 404, { message: `unknown driver: ${driverId}` });
          return;
        }

        const zones = await readJson(zoneSnapshotPath);
        const snapshot = findZoneSnapshot(zones, driver.customer_id, month);

        if (!snapshot) {
          sendJson(res, 404, { message: `report source not found for ${driver.customer_id} month ${month}` });
          return;
        }

        await streamLiveReport(res, driver, snapshot, month, Number.isFinite(basePremiumInput) ? basePremiumInput : undefined);
        return;
      }

      const driverRoute = requestUrl.pathname.match(/^\/api\/drivers\/([^/]+)\/([^/]+)$/);
      if (driverRoute) {
        const driverId = decodeURIComponent(driverRoute[1]);
        const resource = driverRoute[2];
        const driver = findDriver(viewModel, driverId);

        if (!driver) {
          sendJson(res, 404, { message: `unknown driver: ${driverId}` });
          return;
        }

        if (resource === "annual-summary") {
          const { monthly_evidence: _monthlyEvidence, ...summary } = driver;
          sendJson(res, 200, englishDriverSummary(summary));
          return;
        }

        if (resource === "monthly-snapshots") {
          sendJson(res, 200, {
            customer_id: driver.customer_id,
            driver_id: driver.driver_id,
            monthly_evidence: driver.monthly_evidence
          });
          return;
        }

        if (resource === "zone-map") {
          const month = Number(requestUrl.searchParams.get("month") ?? "1");
          const zones = await readJson(zoneSnapshotPath);
          const snapshot = findZoneSnapshot(zones, driver.customer_id, month);

          if (!snapshot) {
            sendJson(res, 404, { message: `zone snapshot not found for ${driver.customer_id} month ${month}` });
            return;
          }

          sendJson(res, 200, {
            analysis_method: zones.analysis_method,
            source_artifacts: zones.source_artifacts,
            snapshot: englishZoneSnapshot(snapshot)
          });
          return;
        }

        if (resource === "report") {
          const month = Number(requestUrl.searchParams.get("month") ?? "1");
          const basePremiumInput = Number(requestUrl.searchParams.get("basePremiumKrw") ?? "");
          const zones = await readJson(zoneSnapshotPath);
          const snapshot = findZoneSnapshot(zones, driver.customer_id, month);

          if (!snapshot) {
            sendJson(res, 404, { message: `report source not found for ${driver.customer_id} month ${month}` });
            return;
          }

          await streamLiveReport(res, driver, snapshot, month, Number.isFinite(basePremiumInput) ? basePremiumInput : undefined);
          return;
        }
      }

      sendJson(res, 404, { message: `unknown API route: ${requestUrl.pathname}` });
    } catch (error) {
      if (res.headersSent) {
        res.end(`\n\n[Report Stream Error] ${error instanceof Error ? error.message : "unknown demo API error"}`);
        return;
      }
      sendJson(res, 500, {
        message: error instanceof Error ? error.message : "unknown demo API error"
      });
    }
  });
}

export default defineConfig({
  server: {
    allowedHosts: [".summit1123.co.kr"],
    port: 5173,
    strictPort: false
  },
  preview: {
    port: 4173,
    strictPort: false
  },
  plugins: [
    {
      name: "senior-safe-mileage-demo-api",
      configureServer: configureApiServer
    }
  ]
});

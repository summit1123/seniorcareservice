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
  return `KRW ${Math.round(num(value)).toLocaleString("en-US")}`;
}

function pct(value: unknown): string {
  return `${num(value).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
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
    CANDIDATE_LIVING_ZONE: "Candidate Safe Zone Observed",
    HARSH_BRAKE_INCREASE: "Harsh Braking Increase",
    LOW_MILEAGE: "Low-Mileage Condition",
    LOW_NIGHT_DRIVING: "Low Night Driving",
    LOW_RISK_EVENTS: "Low Risk Events",
    NIGHT_DRIVING_INCREASE: "Night Driving Increase",
    NO_RECENT_OUT_ZONE_SPIKE: "No Recent Out-Zone Spike",
    NO_STRONG_RISK_CHANGE: "No Strong Risk Change",
    OUT_ZONE_PATTERN_CHANGE_RISK: "Out-Zone Risk Change",
    OUT_ZONE_RATIO_INCREASE: "Out-Zone Share Increase",
    OUT_ZONE_SAFE: "Stable Out-Zone",
    OUT_ZONE_SAFE_DRIVING: "Safe Out-Zone Driving",
    PREVENTIVE_CARE_REVIEW: "Preventive Care Review",
    RISK_EVENT_INCREASE: "Risk Event Increase",
    STABLE_IN_ZONE_DRIVING: "Stable In-Zone Driving"
  };
  return labels[code] ?? code;
}

const personaNames = [
  "Alex Kim",
  "Soon Park",
  "Jung Lee",
  "Mia Choi",
  "Kevin Jung",
  "Bok Yoon",
  "Sang Han",
  "Mija Oh",
  "Moon Kang",
  "Rye Seo",
  "Han Jo",
  "Young Moon",
  "Sang Bae",
  "Ok Shin",
  "Man Yoo",
  "Kyung Lim",
  "Sung Noh",
  "Geum Hong",
  "Tae Kwon",
  "Soon Jang",
  "Jae Ko",
  "Young Baek",
  "Ki Nam",
  "Hwa Song",
  "Chun Yang",
  "Mikyung Cha",
  "Byung Joo",
  "Jung Min",
  "Seok Ha",
  "Young Do"
];

const CARE_REVIEW_RISK_THRESHOLD = 70;

function personaIndex(customerId: unknown) {
  const matched = text(customerId).match(/(\d+)$/);
  return matched ? Math.max(0, Number(matched[1]) - 1) : 0;
}

function personaName(customerId: unknown) {
  return personaNames[personaIndex(customerId)] ?? "Senior Driver";
}

function basisLabel(value: unknown) {
  if (value === "pre_policy_60_day_dbscan") return "Pre-policy 60-day baseline";
  if (value === "rolling_60_day_dbscan") return "Rolling previous 60 days";
  return text(value);
}

function distanceScopeLabel(value: unknown) {
  if (value === "evaluation_period_only") return "Evaluation period only";
  return text(value, "12-month evaluation");
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
    candidate_living_zone: "Candidate Safe Zone",
    existing_living_zone: "Baseline Safe Zone",
    out_zone_pattern_change_risk: "Out-Zone Risk Change",
    out_zone_safe_driving: "Stable Out-Zone"
  };
  return labels[text(value)] ?? text(value, "Unclassified");
}

function destinationLabel(value: unknown): string {
  const labels: Record<string, string> = {
    clinic: "Hospital",
    family: "Family House",
    family_home: "Family House",
    home: "Home",
    leisure: "Nearby Outing",
    market: "Mart",
    pharmacy: "Pharmacy",
    unknown_outer: "New External Destination"
  };
  return labels[text(value)] ?? text(value, "Unknown Destination");
}

function personaTypeLabel(value: unknown): string {
  const labels: Record<string, string> = {
    stable_local_low_mileage: "Stable Local Low-Mileage",
    stable_outer_safe: "Stable Out-Zone Driver",
    recent_outer_risk_change: "Recent Out-Zone Risk Change",
    in_zone_risky_low_mileage: "In-Zone Risk Behavior",
    medical_visit_pattern: "Repeated Medical-Visit Pattern",
    irregular_family_support: "Irregular Family-Care Travel"
  };
  return labels[text(value)] ?? text(value, "Senior Driver");
}

function decisionLabel(value: unknown): string {
  const labels: Record<string, string> = {
    우대: "Favorable",
    기본: "Standard",
    "예방 케어": "Preventive Care",
    Favorable: "Favorable",
    Preferred: "Favorable",
    Standard: "Standard",
    "Preventive Care": "Preventive Care"
  };
  return labels[text(value)] ?? text(value, "Standard");
}

function translateKnownText(value: unknown): string {
  const labels: Record<string, string> = {
    "3천km 이하": "Under 3,000 km",
    "4천km 이하": "Under 4,000 km",
    "5천km 이하": "Under 5,000 km",
    "6천km 이하": "Under 6,000 km",
    "7천km 이하": "Under 7,000 km",
    "8천km 이하": "Under 8,000 km",
    "9천km 이하": "Under 9,000 km",
    "주 2회 내외": "About 2 trips/week",
    "주 3~4회": "3-4 trips/week",
    "생활권 안 중심": "Mostly In-Zone",
    "위험행동 낮음": "Low risk events",
    "반복 외부 목적지 안정": "Repeated external destinations with stable behavior",
    "하반기 외부 목적지 증가": "Increase in external destinations in the second half",
    "하반기 야간/급제동 증가": "Increase in night driving and harsh braking in the second half",
    "생활권 안 과속/급감속 반복": "Repeated In-Zone speeding and harsh braking",
    "반복 병원 목적 외부 이동": "Repeated external hospital trips",
    "주간 병원 이동 중심, 위험행동 낮음": "Mostly daytime hospital trips with low risk events",
    "가족 돌봄 외부 이동 변동": "Variable external travel for family care",
    "외부 이동은 변동하나 위험행동 제한적": "External travel varies, but risk events remain limited",
    "생활권 안 반복 주행과 낮은 위험행동을 근거로 안정 저주행 고객으로 설명": "Explains the driver as a stable low-mileage customer based on repeated In-Zone driving and low risk events",
    "기존 거리 중심 산식과 제안 통합 산식 모두 우량으로 분류되어야 하는 기준 우량군": "Reference preferred group that should be classified as stable by both the existing mileage formula and the proposed integrated formula",
    "예방 케어로 잘못 분류되면 안정 고객 비용 효율 평가가 왜곡됨": "If misclassified into Preventive Care, the cost-efficiency assessment for stable customers is distorted",
    "생활권 밖 주행 자체를 과도하게 불리하게 보지 않는지 확인하는 공정성/오분류 방지군": "Fairness and misclassification-control group for checking that Out-Zone driving itself is not over-penalized",
    "외부 주행은 있으나 반복 목적지와 안정 운전으로 예방 케어 대상은 아님": "Has external driving, but repeated destinations and stable driving mean it should not automatically become a Preventive Care case",
    "생활권 밖 비율만으로 위험군 처리하면 모델 공정성이 약해짐": "Treating the driver as risky based only on Out-Zone share weakens model fairness",
    "저주행임에도 최근 생활권 밖 야간/위험행동이 함께 늘어난 예방 케어 신호": "Preventive Care signal: despite low mileage, recent Out-Zone night driving and risk events increased together",
    "기존 마일리지 산식이 놓칠 수 있는 저주행 위험변화 핵심 포착 대상군": "Core target group for detecting low-mileage risk changes that the existing mileage formula can miss",
    "핵심 타깃을 놓치면 A/B 우수성 승인 게이트를 통과하기 어려움": "Missing this target group makes it difficult to pass the A/B validation gate",
    "생활권 안 주행이라도 과속/급감속이 있으면 감점되는지 확인하는 엣지케이스": "Edge case for checking whether speeding and harsh braking are penalized even inside the safe zone",
    "생활권 내 주행이 많지만 위험행동이 있어 우대 판단은 보수적으로 설명": "Mostly In-Zone driving, but risk events require a conservative preferred decision",
    "생활권 안이라는 이유로 무조건 안정형 처리하면 모델 해석 원칙을 위반함": "Classifying as stable solely because it is In-Zone violates the model's interpretation principle",
    "반복 의료 목적 외부 이동을 신규 위험변화로 오판하지 않는지 확인하는 케어 맥락군": "Care-context group for checking that repeated medical trips are not mistaken for new risk changes",
    "정기 병원 방문처럼 반복 목적지가 있는 외부 이동은 변화 위험과 구분": "Repeated external trips, such as regular hospital visits, are separated from risk-change signals",
    "의료 목적 반복 이동을 위험변화로 오판하면 직원 설명 품질이 낮아짐": "If repeated medical trips are mistaken for risk changes, explanation quality for employees drops",
    "불규칙 외부 이동이 있어도 위험행동과 야간 증가가 동반되는지 분리 평가하는 엣지케이스": "Edge case for separately evaluating whether irregular external travel is accompanied by risk-event and night-driving increases",
    "불규칙 가족 지원 이동은 있으나 위험행동 증가가 제한적이면 예방 케어로 단정하지 않음": "Irregular family-support travel exists, but it should not be treated as Preventive Care when risk-event increases are limited",
    "외부 이동 증가만으로 케어 대상 처리하면 오탐 제한 조건에 불리함": "Treating external-travel increases alone as care cases hurts the false-positive control condition",
    "평소 생활권 중심": "Centered on the usual safe zone",
    "생활권 안 반복 주행": "Repeated In-Zone driving",
    "생활권 밖 반복 목적지 안정": "Stable repeated Out-Zone destinations",
    "최근 외부·야간 위험변화": "Recent external and night-driving risk change",
    "생활권 안 위험행동 관찰": "In-zone risk behavior observed",
    "정기 병원 목적지 반복": "Repeated regular hospital destinations",
    "가족·생활 목적지 혼합": "Mixed family-care and daily-life destinations",
    "상반기에는 외부 목적지와 야간 신호가 제한적임": "External destinations and night-driving signals were limited in the first half",
    "9월 이후 신규 외부 목적지와 야간/급제동 신호가 함께 증가함": "After September, new external destinations and night / harsh-braking signals increased together",
    "생활권 안 이동이 많지만 과속·급감속 이벤트가 반복됨": "Mostly In-Zone travel, but speeding and harsh-braking events repeat",
    "외부 이동이 있으나 반복 목적지와 주간 주행 중심임": "External travel exists, but it centers on repeated destinations and daytime trips",
    "외부 이동의 상당 부분이 반복 병원 목적지로 해석됨": "Much of the external travel is interpreted as repeated hospital destinations",
    "가족 돌봄 외부 이동 증가": "Increase in external travel for family care",
    "자녀집 방문이 늘지만 위험행동 증가는 제한적임": "Family-house visits increased, but risk-event increases remain limited",
    "생활 목적지와 가족 지원 이동이 혼재함": "Daily-life destinations and family-support travel are mixed",
    "자택·마트·병원 중심의 반복 이동이 유지됨": "Repeated travel centered on home, mart, and hospital is maintained"
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
    product_name_ko: "Senior Safe Zone Rider",
    existing_formula_ko: "Annual mileage + vehicle class -> existing mileage discount rate",
    proposed_formula_ko: "Annual mileage + 12-month Safe Zone stability + Out-Zone safety + risk change -> integrated-score discount adjustment",
    llm_boundary_ko: "The LLM does not calculate premiums; it converts calculated evidence into employee-facing explanations."
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

  let headline = "Repeated Stable In-Zone Driving";
  if (riskScore >= CARE_REVIEW_RISK_THRESHOLD || riskEvents >= Math.max(3, tripCount * 0.25)) {
    headline = "Month With Increasing Risk Events";
  } else if (outZoneRatio >= 0.25 && repeatRate >= 0.5 && riskEvents <= Math.max(1, tripCount * 0.12)) {
    headline = "Out-Zone Travel Centered on Repeated Destinations";
  } else if (newDestinationTrips >= Math.max(2, tripCount * 0.2)) {
    headline = "New Destination Increase Observed";
  } else if (outZoneRatio < 0.12 && riskEvents === 0) {
    headline = "Stable In-Zone Driving Maintained";
  }

  const outerPattern =
    outZoneRatio < 0.12
      ? "The Out-Zone share is low, so the month is interpreted as centered on the baseline safe zone."
      : repeatRate >= 0.5
        ? "Out-zone travel exists, but repeated routes and repeated destinations mean it should not be treated as automatically risky."
        : "Out-zone travel is dispersed, so the same pattern should be checked again next month.";

  const riskPattern =
    riskEvents === 0
      ? "There are almost no risk-event signals such as harsh braking or speeding."
      : riskScore >= CARE_REVIEW_RISK_THRESHOLD
        ? `${riskEvents} risk events and a ${riskScore.toFixed(1)} risk-change score increased together, so Preventive Care review is recommended.`
        : `${riskEvents} risk events were observed, but the risk-change signal is limited.`;

  const action =
    riskScore >= CARE_REVIEW_RISK_THRESHOLD
      ? "For counseling, prioritize a safe-driving report, vehicle check, and guidance around night driving or unfamiliar routes."
      : outZoneRatio >= 0.25 && repeatRate >= 0.5
        ? "Do not disadvantage the driver simply because the trips are Out-Zone; explain repeated destinations and low risk events together."
        : "Accumulate this as evidence for the annual formula and recheck the change magnitude in the next renewal month.";

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
    report_role: "Monthly driving explanation report for insurer staff",
    report_month: month,
    generation_contract: {
      pricing_is_already_calculated: true,
      llm_must_not_recalculate_discount: true,
      monthly_report_must_not_include_premium_amounts: true,
      monthly_evidence_is_for_annual_decision_explanation: true,
      avoid_penalty_language_for_senior_customer: true,
      privacy_filter: "Raw coordinates and identifiers are excluded; only summarized features are passed to the LLM"
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
      pricing_note: "Premiums and discount amounts are calculated separately in the annual formula screen / Decision Panel; the monthly report body must not include amounts.",
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
    "You are an assistant that writes internal driving reports for auto-insurance product planning and underwriting staff.",
    "The input values have already been calculated by the formula and XAI pipeline, so do not recalculate or estimate discount rates, scores, or amounts.",
    "The report is not customer-facing copy. It is an explanation for internal review, counseling preparation, and Preventive Care decisions.",
    "Avoid language that sounds like penalties, sanctions, or risk labeling for senior customers. Focus on Preventive Care and evidence confirmation.",
    "The monthly report is an evidence report explaining the annual decision, not a premium calculation statement.",
    "Do not mention existing discount amounts, proposed discount amounts, final premium differences, increases, decreases, surcharges, or premium hikes in the body.",
    "Clearly distinguish monthly evidence values from annual discount rates.",
    "Put the monthly conclusion, core evidence, and recommended action first so staff can understand the point within 10 seconds.",
    "Write in Markdown, use at most one table, and preserve the numeric feature values from the input.",
    "Each section should contain 2-4 bullets and, when useful, reference the concrete feature values and reason codes."
  ].join("\n");

  const userPrompt = [
    "Use only the privacy_filtered_features below and write the report in English.",
    "Use exactly the following 7 Markdown section headings. Do not omit or rename sections.",
    "## 1. Monthly Conclusion Summary",
    "## 2. Annual Formula Reflection",
    "## 3. Safe Zone Evidence",
    "## 4. Monthly Driving Pattern",
    "## 5. Key XAI Reasons",
    "## 6. Counseling and Care Actions",
    "## 7. Review Limits and Items to Confirm",
    "",
    "Writing rules:",
    "- Section 1 must summarize the Safe Zone / risk-change signals observed in this month and the next staff action within 3 lines. Do not mention premium changes.",
    "- Section 2 must explain which of the four indicators (Mileage, In-Zone, Out-Zone, Pattern Change) this month's evidence contributes to. Do not calculate discounts or final premiums.",
    "- Section 3 must distinguish pre-policy / rolling 60-day Safe Zone fitting, the P90 accepted radius, and In-Zone versus Out-Zone shares.",
    "- Section 4 must interpret destination groups, repeated destinations, new destinations, night driving, and risk events in staff-friendly language.",
    "- Section 5 must explain how the four indicators influenced the monthly evidence interpretation.",
    "- Section 6 must suggest Preventive Care, a safe-driving report, vehicle check, and next-month recheck actions where appropriate.",
    "- Section 7 must briefly note that raw coordinates are hidden, monthly evidence only explains the annual decision, and actual claim-data validation is still needed.",
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

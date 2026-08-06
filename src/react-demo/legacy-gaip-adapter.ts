import { calculateSandboxDecision, normalizeProductWeights } from "./gaip-decision.ts";
import type {
  GaipStudioBundle,
  ProductRules,
  SandboxResult,
  StudioDriver,
  StudioMonthlyResult
} from "./gaip-types.ts";
import type {
  AbComparison,
  DecisionSignal,
  Destination,
  DriverAnnualSummary,
  ExistingTierSegment,
  Interpretation,
  MatchedPairComparison,
  MatchedPairSide,
  MonthlyEvidence,
  MonthlySnapshotResponse,
  PersonaDirectoryResponse,
  PersonaSummary,
  ZoneCluster,
  ZoneMapResponse,
  ZoneTripInterpretation
} from "./types.ts";

const SAFE_SOURCE_ARTIFACTS = {
  simulation_bundle: "GAIP 합성 시뮬레이션 안전 요약 DTO",
  map_display: "원본 좌표를 포함하지 않는 정규화 도식",
  pricing_scope: "Korea Mileage Reference와 비구속 Masil 후보 비교"
};

const CONTRACT_ID = "MASIL-GAIP-SAFE-SUMMARY-V1";

function finite(value: number | undefined | null, fallback = 0): number {
  return value !== null && value !== undefined && Number.isFinite(value) ? value : fallback;
}

function round(value: number, digits = 2): number {
  const scale = 10 ** digits;
  return Math.round((value + Number.EPSILON) * scale) / scale;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + finite(value), 0);
}

function mean(values: Array<number | null | undefined>): number {
  const observed = values.filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));
  return observed.length ? sum(observed) / observed.length : 0;
}

function nullableMean(values: Array<number | null | undefined>): number | null {
  const observed = values.filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));
  return observed.length ? round(sum(observed) / observed.length) : null;
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function increment(target: Record<string, number>, key: string): void {
  target[key] = (target[key] ?? 0) + 1;
}

function driverById(bundle: GaipStudioBundle, driverId: string): StudioDriver {
  const driver = bundle.drivers.find((candidate) => candidate.id === driverId);
  if (!driver) throw new Error(`합성 운전자 ${driverId}를 찾을 수 없습니다.`);
  return driver;
}

function effectiveRules(bundle: GaipStudioBundle, rules?: ProductRules): ProductRules {
  return rules ?? bundle.product_rules;
}

function sandboxDecision(driver: StudioDriver, rules: ProductRules): SandboxResult {
  return calculateSandboxDecision({
    driver,
    weights: rules.weights,
    rewardThreshold: rules.reward_score_threshold,
    rewardRequiredMonths: rules.reward_required_months,
    minimumCoverage: rules.minimum_data_coverage_pct,
    careMobilityThreshold: rules.care_mobility_change_threshold,
    careRiskThreshold: rules.care_risky_behavior_threshold,
    rewardDiscount: rules.reward_discount_rate_pct ?? 0,
    rewardBonusFloor: rules.reward_bonus_floor_pct ?? 1,
    careDiscountReduction: rules.care_discount_reduction_pct ?? 0,
    candidateDiscountCap: rules.candidate_discount_cap_pct ?? 100
  });
}

function decisionSignal(result: SandboxResult): DecisionSignal {
  if (result.reward_eligible && result.care_review_eligible) return "Reward + Care Review";
  if (result.care_review_eligible) return "Care Review";
  if (result.reward_eligible) return "Reward";
  if (result.reward_state === "Hold" || result.care_state === "Hold") return "판단 보류";
  return "Neutral";
}

function koreaReferenceLabel(driver: StudioDriver): string {
  return `기존 마일리지 기준 ${round(driver.tariff?.korea_mileage_discount_rate_pct ?? 0, 1)}%`;
}

// Synthetic semantic hub labels for display; fallbacks stay clearly generic.
function hubDisplayLabel(driver: StudioDriver, index: number): string {
  return driver.mobility.routine_hubs[index]?.display_label_ko
    ?? `반복 거점 ${String.fromCharCode(65 + index)}`;
}

function newHubDisplayLabel(driver: StudioDriver): string {
  return driver.mobility.new_hub_label_ko ?? "신규 목적지";
}

function evaluationMonths(driver: StudioDriver): StudioMonthlyResult[] {
  return driver.monthly_results.filter((month) => month.period_role === "evaluation");
}

function baselineMonths(driver: StudioDriver): StudioMonthlyResult[] {
  return driver.monthly_results.filter((month) => month.period_role === "baseline");
}

function averageCoverage(driver: StudioDriver): number {
  return round(mean(evaluationMonths(driver).map((month) => month.data_coverage_pct)));
}

function evidenceStatus(driver: StudioDriver, result: SandboxResult): string {
  if (driver.mobility.zone_status !== "ready" && driver.mobility.zone_status !== "available") {
    return "simulated · 생활권 근거 부족 · 판단 보류";
  }
  if (result.reward_state === "Hold" || result.care_state === "Hold") {
    return "simulated · 데이터 충분성 미달 · 판단 보류";
  }
  return "simulated · 상품 후보 검토용";
}

function monthlyWeightedScore(month: StudioMonthlyResult, rules: ProductRules): number {
  const weights = normalizeProductWeights(rules.weights);
  const components: Array<[number | null, number]> = [
    [month.mileage_score, weights.mileage],
    [month.in_zone_safe_score, weights.in_zone_safe],
    [month.out_zone_safe_score, weights.out_zone_safe],
    [month.pattern_stability_score, weights.pattern_stability]
  ];
  const observed = components.filter((entry): entry is [number, number] => entry[0] !== null && Number.isFinite(entry[0]));
  const observedWeight = sum(observed.map(([, weight]) => weight));
  if (observedWeight <= 0) return 0;
  return round(sum(observed.map(([value, weight]) => value * weight)) / observedWeight);
}

function dominantInterpretation(month: StudioMonthlyResult, rules: ProductRules): Interpretation {
  if (!month.zone_available || month.data_coverage_pct < rules.minimum_data_coverage_pct) return "evidence_hold";
  const careGate =
    month.mobility_change_index_pct >= rules.care_mobility_change_threshold &&
    month.risky_behavior_change_index_pct >= rules.care_risky_behavior_threshold;
  if (careGate) return "out_zone_pattern_change_risk";
  if (month.outer_visit_share_pct > 0) return "out_zone_safe_driving";
  return "existing_living_zone";
}

function monthlyRewardState(month: StudioMonthlyResult, rules: ProductRules, evidenceReady: boolean): string {
  if (month.period_role === "baseline") return "Observation";
  if (!evidenceReady) return "Hold";
  // Recompute against the ACTIVE sandbox rules (weights + reward threshold) so the
  // monthly badge stays consistent with the annual tier and the donut when the
  // product manager moves the sliders — mirrors monthlyCareState, which recomputes.
  return monthlyWeightedScore(month, rules) >= rules.reward_score_threshold ? "Reward" : "Neutral";
}

/** 케어 2단계(회의 확정): 감지 = 직전 2개월 평균 대비 동시 급변, 유지 = 원래
 * 생활(장기 기준선) 복귀 전까지. 샌드박스 임계 변경 시에도 같은 규칙으로 재계산. */
function computeTwoStageCareOpen(months: StudioMonthlyResult[], rules: ProductRules): boolean[] {
  const share = (m: StudioMonthlyResult) => m.outer_visit_share_pct;
  const risk = (m: StudioMonthlyResult) => m.risky_behavior_rate_pct;
  const open: boolean[] = [];
  let careOpen = false;
  for (let i = 0; i < months.length; i += 1) {
    if (i < 2) { open.push(false); continue; }
    const cur = months[i];
    const trailMob = share(cur) - (share(months[i - 1]) + share(months[i - 2])) / 2;
    const trailRisk = risk(cur) - (risk(months[i - 1]) + risk(months[i - 2])) / 2;
    const fires = trailMob >= rules.care_mobility_change_threshold && trailRisk >= rules.care_risky_behavior_threshold;
    // 장기 이탈도(mobility/risky_change_index)는 복귀 판단용
    const sustained = cur.mobility_change_index_pct >= rules.care_mobility_change_threshold &&
      cur.risky_behavior_change_index_pct >= rules.care_risky_behavior_threshold;
    careOpen = fires || (careOpen && sustained);
    open.push(careOpen);
  }
  return open;
}

function monthlyCareState(month: StudioMonthlyResult, rules: ProductRules, evidenceReady: boolean, careOpen: boolean): string {
  if (month.period_role === "baseline") return "Observation";
  if (!evidenceReady) return "Hold";
  return careOpen ? "Care Review" : "None";
}

function monthlyEvidence(driver: StudioDriver, rules: ProductRules): MonthlyEvidence[] {
  const basisTripCount = sum(baselineMonths(driver).map((month) => month.trip_count));
  const careOpenByMonth = computeTwoStageCareOpen(driver.monthly_results, rules);
  return driver.monthly_results.map((month, index) => {
    const evidenceReady = month.zone_available && month.data_coverage_pct >= rules.minimum_data_coverage_pct;
    const basisStatus = month.period_role === "baseline"
      ? "baseline_observation"
      : !month.zone_available
        ? "living_zone_evidence_hold"
        : month.data_coverage_pct < rules.minimum_data_coverage_pct
          ? "data_coverage_hold"
          : "evaluation_ready";
    return {
      service_month: month.month,
      month: index + 1,
      basis_status: basisStatus,
      basis_trip_count: basisTripCount,
      scored_trip_count: evidenceReady ? month.trip_count : 0,
      monthly_total_distance_km: round(month.total_distance_km),
      mileage_score: round(month.mileage_score),
      in_zone_safe_driving_score: month.in_zone_safe_score === null ? null : round(month.in_zone_safe_score),
      out_zone_safe_driving_score: month.out_zone_safe_score === null ? null : round(month.out_zone_safe_score),
      // Legacy field retained for UI compatibility. The separate mobility/risky-behavior fields below govern Care.
      out_zone_pattern_change_risk: round(month.mobility_change_index_pct),
      monthly_integrated_evidence_score: monthlyWeightedScore(month, rules),
      dominant_interpretation: dominantInterpretation(month, rules),
      reason_codes: unique(month.reason_codes),
      scenario_phase: month.period_role === "baseline" ? "2개월 개인 기준선" : "12개월 평가",
      period_role: month.period_role,
      data_coverage_pct: round(month.data_coverage_pct),
      mobility_change_index_pct: round(month.mobility_change_index_pct),
      risky_behavior_change_index_pct: round(month.risky_behavior_change_index_pct),
      pattern_stability_score: round(month.pattern_stability_score),
      reward_state: monthlyRewardState(month, rules, evidenceReady),
      care_state: monthlyCareState(month, rules, evidenceReady, careOpenByMonth[index] ?? false),
      risk_event_type_counts: month.risk_event_type_counts ?? {}
    };
  });
}

function schematicSeed(driverId: string): number {
  return [...driverId].reduce((value, character) => ((value * 31) + character.charCodeAt(0)) >>> 0, 2166136261);
}

function schematicPoint(driverId: string, index: number): { x: number; y: number } {
  const seed = schematicSeed(driverId);
  const layouts = [
    { x: 28, y: 48 },
    { x: 63, y: 63 },
    { x: 46, y: 25 },
    { x: 78, y: 35 }
  ];
  const base = layouts[index % layouts.length];
  return {
    x: round(base.x + ((seed >> (index % 8)) % 7) - 3, 3),
    y: round(base.y + ((seed >> ((index + 3) % 8)) % 7) - 3, 3)
  };
}

function schematicDestinations(driver: StudioDriver): Record<string, Destination> {
  const destinations: Record<string, Destination> = {};
  driver.mobility.routine_hubs.forEach((hub, index) => {
    const key = `routine_hub_${String.fromCharCode(97 + index)}`;
    const point = schematicPoint(driver.id, index);
    destinations[key] = {
      label_ko: hubDisplayLabel(driver, index),
      living_zone_role: "core",
      longitude: point.x,
      latitude: point.y,
      coordinate_space: "schematic_normalized"
    };
  });
  const hasOuterContext = driver.monthly_results.some((month) => month.outer_visit_share_pct > 0);
  if (hasOuterContext) {
    const point = schematicPoint(driver.id, 3);
    destinations.outer_context = {
      label_ko: newHubDisplayLabel(driver),
      living_zone_role: "outer",
      longitude: point.x,
      latitude: point.y,
      coordinate_space: "schematic_normalized"
    };
  }
  return destinations;
}

/** 대조 표의 한쪽을 요약한다 — 요율은 현재 샌드박스 규칙으로 계산된 결과를 쓴다. */
function matchedPairSide(driver: StudioDriver, result: SandboxResult): MatchedPairSide {
  const evaluation = evaluationMonths(driver);
  const basePremium = finite(driver.tariff?.base_premium_krw);
  const referenceRate = finite(driver.tariff?.korea_mileage_discount_rate_pct);
  const referenceNet = driver.tariff?.korea_mileage_net_premium_krw ?? basePremium * (1 - referenceRate / 100);
  const candidateRate = result.proposed_discount_rate_pct;
  const candidateNet = result.proposed_net_premium_krw ?? basePremium * (1 - candidateRate / 100);
  const hasRiskCounts = evaluation.some((month) => month.risk_event_type_counts);
  return {
    driver_id: driver.id,
    display_label: driver.display_label,
    display_label_en: driver.display_label_en ?? driver.display_label,
    persona_label: driver.persona_label,
    annual_distance_km: round(driver.metrics.annual_distance_km),
    outer_share_pct: round(mean(evaluation.map((month) => month.outer_visit_share_pct)), 1),
    risk_event_count: hasRiskCounts
      ? sum(evaluation.map((month) => sum(Object.values(month.risk_event_type_counts ?? {}))))
      : null,
    in_zone_safe_score: driver.metrics.in_zone_safe_score === null ? null : round(driver.metrics.in_zone_safe_score, 1),
    out_zone_safe_score: driver.metrics.out_zone_safe_score === null ? null : round(driver.metrics.out_zone_safe_score, 1),
    integrated_score: round(result.score, 1),
    care_month_count: result.care_review_month_count,
    reward_state: result.reward_state,
    care_state: result.care_state,
    existing_rate_pct: round(referenceRate),
    existing_premium_krw: round(referenceNet),
    proposed_rate_pct: round(candidateRate),
    proposed_premium_krw: round(candidateNet)
  };
}

/**
 * '같은 조건, 다른 행동' 대조 상대를 찾는다.
 * 1단계: 기본보험료·기존 마일리지 요율이 모두 같은 반대 판정(케어↔우대) 사례 —
 *        기존 제도에서는 두 사람의 연 보험료가 원 단위까지 같다.
 * 2단계: 기본보험료만 같은(같은 차종) 반대 판정 사례.
 * 어느 단계든 연 주행거리(≤15% 차)와 생활권 밖 비중(≤5%p 차)이 함께 비슷해야 한다 —
 * 밖 비중이 벌어진 페어를 보여주면 '결국 위치로 가른 것 아니냐'는 반박을 자초한다.
 * 둘 다 없으면 null — UI는 표를 그리지 않는다. self가 보류·기본이면 '반대
 * 판정' 서사 자체가 성립하지 않으므로 역시 null이다(케어 또는 우대만 대조).
 * 판정·요율은 현재 샌드박스 규칙으로 재계산하므로 심사위원이 가중치를
 * 바꿔도 표가 함께 움직이고, 판정이 기본으로 떨어지면 표도 사라진다.
 */
function matchedPair(
  bundle: GaipStudioBundle,
  driver: StudioDriver,
  result: SandboxResult,
  rules: ProductRules
): MatchedPairComparison | null {
  const basePremium = driver.tariff?.base_premium_krw;
  const referenceRate = driver.tariff?.korea_mileage_discount_rate_pct;
  if (basePremium === undefined || referenceRate === undefined) return null;
  const selfIsCare = result.care_state === "Care Review";
  if (!selfIsCare && result.reward_state !== "Reward") return null;

  let bestIdentical: { candidate: StudioDriver; decision: SandboxResult } | null = null;
  let bestSameVehicle: { candidate: StudioDriver; decision: SandboxResult } | null = null;
  const selfDistance = driver.metrics.annual_distance_km;
  const selfOuterShare = mean(evaluationMonths(driver).map((month) => month.outer_visit_share_pct));
  const distanceGap = (candidate: StudioDriver) => Math.abs(candidate.metrics.annual_distance_km - selfDistance);
  // '같은 조건'이 성립하는 범위 — 넘으면 대조로 쓰지 않는다.
  const MAX_DISTANCE_GAP_PCT = 15;
  const MAX_OUTER_SHARE_GAP_PCT_POINTS = 5;
  const withinComparableRange = (candidate: StudioDriver) => {
    const maxDistance = Math.max(candidate.metrics.annual_distance_km, selfDistance, 1);
    const distanceGapPct = (Math.abs(candidate.metrics.annual_distance_km - selfDistance) / maxDistance) * 100;
    if (distanceGapPct > MAX_DISTANCE_GAP_PCT) return false;
    const candidateOuterShare = mean(evaluationMonths(candidate).map((month) => month.outer_visit_share_pct));
    return Math.abs(candidateOuterShare - selfOuterShare) <= MAX_OUTER_SHARE_GAP_PCT_POINTS;
  };

  for (const candidate of bundle.drivers) {
    if (candidate.id === driver.id) continue;
    if (candidate.tariff?.base_premium_krw !== basePremium) continue;
    const decision = sandboxDecision(candidate, rules);
    const candidateIsCare = decision.care_state === "Care Review";
    const isOpposite = selfIsCare
      ? !candidateIsCare && decision.reward_state === "Reward"
      : candidateIsCare;
    if (!isOpposite) continue;
    if (!withinComparableRange(candidate)) continue;
    if (candidate.tariff?.korea_mileage_discount_rate_pct === referenceRate) {
      if (!bestIdentical || distanceGap(candidate) < distanceGap(bestIdentical.candidate)) {
        bestIdentical = { candidate, decision };
      }
    } else if (!bestSameVehicle || distanceGap(candidate) < distanceGap(bestSameVehicle.candidate)) {
      bestSameVehicle = { candidate, decision };
    }
  }

  const matched = bestIdentical ?? bestSameVehicle;
  if (!matched) return null;
  return {
    match_tier: bestIdentical ? "identical" : "same_vehicle",
    base_premium_krw: round(finite(basePremium)),
    self: matchedPairSide(driver, result),
    other: matchedPairSide(matched.candidate, matched.decision)
  };
}

/**
 * 심사 화면용 대표 대조 페어 — 180개 시나리오 전수에서 '조건은 가장 비슷하고
 * 행동만 다른' 케어×우대 페어를 결정론적으로 고른다. 기본보험료·기존 요율이
 * 동일한 페어만 후보로 두고, 거리·생활권 밖 비중·환경·연령의 동일성과
 * 위험행동 대비 크기를 점수화한다(현재 데이터 1위: 한영자↔오종국).
 */
export function adaptRepresentativePair(bundle: GaipStudioBundle, rules?: ProductRules): MatchedPairComparison | null {
  const activeRules = effectiveRules(bundle, rules);
  const decisions = new Map<string, SandboxResult>();
  const decisionFor = (driver: StudioDriver): SandboxResult => {
    let result = decisions.get(driver.id);
    if (!result) {
      result = sandboxDecision(driver, activeRules);
      decisions.set(driver.id, result);
    }
    return result;
  };
  const outerShareOf = (driver: StudioDriver) => mean(evaluationMonths(driver).map((month) => month.outer_visit_share_pct));
  const riskCountOf = (driver: StudioDriver) =>
    sum(evaluationMonths(driver).map((month) => sum(Object.values(month.risk_event_type_counts ?? {}))));

  const cares: StudioDriver[] = [];
  const rewards: StudioDriver[] = [];
  for (const driver of bundle.drivers) {
    const result = decisionFor(driver);
    if (result.care_state === "Care Review") cares.push(driver);
    else if (result.reward_state === "Reward") rewards.push(driver);
  }

  let best: { care: StudioDriver; reward: StudioDriver; score: number } | null = null;
  for (const care of cares) {
    for (const reward of rewards) {
      const basePremium = care.tariff?.base_premium_krw;
      if (basePremium === undefined || reward.tariff?.base_premium_krw !== basePremium) continue;
      if (care.tariff?.korea_mileage_discount_rate_pct !== reward.tariff?.korea_mileage_discount_rate_pct) continue;
      const maxDistance = Math.max(care.metrics.annual_distance_km, reward.metrics.annual_distance_km, 1);
      const distanceGapPct = (Math.abs(care.metrics.annual_distance_km - reward.metrics.annual_distance_km) / maxDistance) * 100;
      const outerGap = Math.abs(outerShareOf(care) - outerShareOf(reward));
      const riskGap = riskCountOf(care) - riskCountOf(reward);
      // 표의 임무는 '생활권 밖에서의 운전이 갈랐다'를 보이는 것이다. 그래서
      // 밖 안전점수 격차를 최우선으로 보고, 밖에 나가는 '정도'는 비슷할수록,
      // 안에서는 둘 다 무난할수록(안 격차가 작을수록) 좋은 대조가 된다.
      // 쇼케이스로 쓰는 표라 '완벽한 사람'은 대조로 쓰지 않는다 — 위험 0건에
      // 안전점수 만점이면 합성 대조군(오탐 검증용 유형)이라 현실감이 없다.
      if (riskCountOf(reward) === 0) continue;
      if ((reward.metrics.in_zone_safe_score ?? 0) >= 99.5) continue;
      if ((reward.metrics.out_zone_safe_score ?? 0) >= 99.5) continue;
      const outSafeGap =
        care.metrics.out_zone_safe_score === null || reward.metrics.out_zone_safe_score === null
          ? 0
          : Math.abs(reward.metrics.out_zone_safe_score - care.metrics.out_zone_safe_score);
      const inSafeGap =
        care.metrics.in_zone_safe_score === null || reward.metrics.in_zone_safe_score === null
          ? 0
          : Math.abs(reward.metrics.in_zone_safe_score - care.metrics.in_zone_safe_score);
      const score =
        -distanceGapPct * 3 -
        outerGap * 0.5 +
        (care.environment_id === reward.environment_id ? 5 : 0) +
        outSafeGap / 2 -
        inSafeGap / 4;
      if (!best || score > best.score) best = { care, reward, score };
    }
  }
  if (!best) return null;
  return {
    match_tier: "identical",
    base_premium_krw: round(finite(best.care.tariff?.base_premium_krw)),
    self: matchedPairSide(best.care, decisionFor(best.care)),
    other: matchedPairSide(best.reward, decisionFor(best.reward))
  };
}

function annualComparison(driver: StudioDriver, result: SandboxResult): AbComparison {
  const basePremium = finite(driver.tariff?.base_premium_krw);
  const referenceRate = finite(driver.tariff?.korea_mileage_discount_rate_pct);
  const referenceNet = driver.tariff?.korea_mileage_net_premium_krw ?? basePremium * (1 - referenceRate / 100);
  const candidateRate = result.proposed_discount_rate_pct;
  const candidateNet = result.proposed_net_premium_krw ?? basePremium * (1 - candidateRate / 100);
  const signal = decisionSignal(result);
  const annualMobilityChange = Math.max(0, ...evaluationMonths(driver).map((month) => month.mobility_change_index_pct));
  const reasonCodes = unique([...(driver.reason_codes ?? []), ...result.reason_codes]);
  return {
    annual_total_distance_km: round(driver.metrics.annual_distance_km),
    annual_distance_scope: "12개월 평가기간 · 2개월 기준선 제외",
    baseline_60_day_excluded_from_discount: true,
    base_premium_krw: round(basePremium),
    existing_matched_tier_label: koreaReferenceLabel(driver),
    existing_discount_rate_pct: round(referenceRate),
    existing_discount_amount_krw: round(basePremium - referenceNet),
    existing_net_premium_krw: round(referenceNet),
    proposed_discount_rule_id: "MASIL_NONBINDING_SIMULATION_CANDIDATE",
    proposed_discount_rate_pct: round(candidateRate),
    proposed_discount_amount_krw: round(basePremium - candidateNet),
    proposed_net_premium_krw: round(candidateNet),
    discount_rate_delta_pct: round(candidateRate - referenceRate),
    discount_amount_delta_krw: round((basePremium - candidateNet) - (basePremium - referenceNet)),
    premium_delta_krw: round(candidateNet - referenceNet),
    annual_senior_safe_mileage_score: round(result.score),
    annual_score_tier: result.reward_state === "Hold" ? "Evidence Hold" : result.reward_eligible ? "Reward Candidate" : "Neutral",
    annual_decision_signal: signal,
    annual_out_zone_pattern_change_risk: round(annualMobilityChange),
    proposed_pricing_action: result.reward_state === "Hold"
      ? "비구속 할인 후보 계산 보류"
      : result.care_review_eligible
        ? "비구속 Reward 후보와 독립된 Care Review 제안"
        : "Korea Reference 대비 비구속 Masil 후보 비교",
    preventive_care_required: result.care_review_eligible,
    proposed_rationale_code: result.reason_codes.join(" · "),
    annual_reason_codes: reasonCodes,
    same_input_contract_id: CONTRACT_ID
  };
}

export function adaptAnnualSummary(
  bundle: GaipStudioBundle,
  driverId: string,
  rules?: ProductRules
): DriverAnnualSummary {
  const driver = driverById(bundle, driverId);
  const activeRules = effectiveRules(bundle, rules);
  const result = sandboxDecision(driver, activeRules);
  const comparison = annualComparison(driver, result);
  const evaluation = evaluationMonths(driver);
  const baseline = baselineMonths(driver);
  const primaryDestinations = driver.mobility.routine_hubs.map((_, index) => `routine_hub_${String.fromCharCode(97 + index)}`);
  const annualRiskChange = Math.max(0, ...evaluation.map((month) => month.risky_behavior_change_index_pct));
  const annualTripCount = sum(evaluation.map((month) => month.trip_count));
  const signal = decisionSignal(result);
  const status = evidenceStatus(driver, result);

  return {
    customer_id: driver.id,
    driver_id: driver.id,
    persona_type: driver.persona_id,
    persona_display_name_ko: driver.persona_label,
    vehicle_class: driver.scenario_label ?? "합성 시니어 운전자",
    base_premium_krw: round(finite(driver.tariff?.base_premium_krw)),
    living_pattern: {
      home_anchor: driver.mobility.routine_hubs.length
        ? "Routine Hub A · 정규화 도식 좌표"
        : "생활권 근거 없음 · 거점 생성 보류",
      weekly_outing_frequency_ko: `기준선 2개월 방문 이벤트 ${sum(baseline.map((month) => month.trip_count))}건`,
      primary_destinations: primaryDestinations,
      outer_trip_tendency: `평가기간 생활권 밖 맥락 평균 ${round(mean(evaluation.map((month) => month.outer_visit_share_pct)), 1)}% · 위치 자체 중립`,
      risk_behavior_tendency: `위험행동 변화지수 최고 ${round(annualRiskChange, 1)}%`,
    },
    care_context: {
      product_role: `Reward ${result.reward_state} · Care ${result.care_state}`,
      message_focus: result.care_review_eligible
        ? "같은 달에 이동맥락 변화와 위험행동 변화가 함께 확인되어 사람 검토를 제안합니다."
        : result.reward_state === "Hold" || result.care_state === "Hold"
          ? "근거가 부족하므로 불이익 없이 판단을 보류합니다."
          : "Outer 이동은 중립 맥락이며 Reward와 Care를 독립적으로 검토합니다.",
      false_positive_or_negative_risk: "합성 근거 기반 제안입니다. AI는 요율·인수·Care를 최종 결정하지 않습니다."
    },
    living_destinations: schematicDestinations(driver),
    annual_score: {
      annual_total_distance_km: round(driver.metrics.annual_distance_km),
      annual_trip_count: annualTripCount,
      annual_mileage_score: round(finite(result.component_scores.mileage)),
      annual_in_zone_safe_driving_score: result.component_scores.in_zone_safe === null ? null : round(result.component_scores.in_zone_safe),
      annual_out_zone_safe_driving_score: result.component_scores.out_zone_safe === null ? null : round(result.component_scores.out_zone_safe),
      annual_senior_safe_mileage_score: round(result.score),
      annual_score_tier: comparison.annual_score_tier,
      annual_decision_signal: signal,
      annual_out_zone_pattern_change_risk: comparison.annual_out_zone_pattern_change_risk,
      dominant_annual_interpretation: result.care_review_eligible
        ? "out_zone_pattern_change_risk"
        : result.reward_state === "Hold"
          ? "evidence_hold"
          : driver.metrics.out_zone_safe_score === null
            ? "existing_living_zone"
            : "out_zone_safe_driving",
      annual_reason_codes: comparison.annual_reason_codes
    },
    ab_comparison: comparison,
    environment_id: driver.environment_id,
    environment_display_name_ko: driver.environment_label,
    reward_state: result.reward_state,
    care_state: result.care_state,
    zone_status: driver.mobility.zone_status,
    evidence_status: status,
    model_version: bundle.metadata.bundle_version ?? "masil-gaip-simulation/v1",
    mobility_profile: driver.mobility_profile ?? null,
    matched_pair: matchedPair(bundle, driver, result, activeRules)
  };
}

export function adaptMonthlySnapshots(
  bundle: GaipStudioBundle,
  driverId: string,
  rules?: ProductRules
): MonthlySnapshotResponse {
  const driver = driverById(bundle, driverId);
  return {
    customer_id: driver.id,
    driver_id: driver.id,
    monthly_evidence: monthlyEvidence(driver, effectiveRules(bundle, rules))
  };
}

function personaSummaries(bundle: GaipStudioBundle, rules: ProductRules): PersonaSummary[] {
  return bundle.personas.map((persona) => {
    const drivers = bundle.drivers.filter((driver) => driver.persona_id === persona.id);
    const results = drivers.map((driver) => sandboxDecision(driver, rules));
    const counts: Record<string, number> = {};
    results.forEach((result) => increment(counts, decisionSignal(result)));
    return {
      persona_type: persona.id,
      persona_display_name_ko: persona.label,
      customer_count: drivers.length,
      avg_annual_distance_km: round(mean(drivers.map((driver) => driver.metrics.annual_distance_km))),
      avg_annual_score: round(mean(results.map((result) => result.score))),
      decision_counts: counts,
      preventive_care_count: results.filter((result) => result.care_review_eligible).length,
      avg_existing_discount_rate_pct: round(mean(drivers.map((driver) => driver.tariff?.korea_mileage_discount_rate_pct))),
      avg_proposed_discount_rate_pct: round(mean(results.map((result) => result.proposed_discount_rate_pct)))
    };
  });
}

function tierSegments(bundle: GaipStudioBundle, rules: ProductRules): ExistingTierSegment[] {
  const groups = new Map<string, StudioDriver[]>();
  bundle.drivers.forEach((driver) => {
    const label = koreaReferenceLabel(driver);
    groups.set(label, [...(groups.get(label) ?? []), driver]);
  });
  return [...groups.entries()].map(([label, drivers]) => {
    const personaCounts: Record<string, number> = {};
    const decisionCounts: Record<string, number> = {};
    const candidateRates: number[] = [];
    drivers.forEach((driver) => {
      const result = sandboxDecision(driver, rules);
      increment(personaCounts, driver.persona_id);
      increment(decisionCounts, decisionSignal(result));
      candidateRates.push(result.proposed_discount_rate_pct);
    });
    return {
      existing_matched_tier_label: label,
      customer_count: drivers.length,
      customer_ids: drivers.map((driver) => driver.id),
      persona_counts: personaCounts,
      proposed_decision_signal_counts: decisionCounts,
      proposed_discount_rate_range_pct: [Math.min(...candidateRates), Math.max(...candidateRates)]
    };
  });
}

export function adaptDirectory(bundle: GaipStudioBundle, rules?: ProductRules): PersonaDirectoryResponse {
  const activeRules = effectiveRules(bundle, rules);
  const rows = bundle.drivers.map((driver) => ({ driver, result: sandboxDecision(driver, activeRules) }));
  const basePremiums = rows.map(({ driver }) => finite(driver.tariff?.base_premium_krw));
  const existingNet = rows.map(({ driver }) => {
    const base = finite(driver.tariff?.base_premium_krw);
    const rate = finite(driver.tariff?.korea_mileage_discount_rate_pct);
    return driver.tariff?.korea_mileage_net_premium_krw ?? base * (1 - rate / 100);
  });
  const candidateNet = rows.map(({ driver, result }) => {
    const base = finite(driver.tariff?.base_premium_krw);
    return result.proposed_net_premium_krw ?? base * (1 - result.proposed_discount_rate_pct / 100);
  });
  const decisionCounts: Record<string, number> = {};
  rows.forEach(({ result }) => increment(decisionCounts, decisionSignal(result)));
  const defaultDriver = rows.find(({ result }) => result.care_review_eligible)?.driver
    ?? rows.find(({ result }) => result.reward_state === "Hold")?.driver
    ?? bundle.drivers[0];

  return {
    product_frame: {
      product_name_ko: "FourSure · Masil — 저주행 시니어 생활권 맥락 특약",
      existing_formula_ko: "Korea Mileage Reference · 연간 주행거리 기준",
      proposed_formula_ko: "비구속 Masil 후보 · 30:30:20:20 기본안과 조정 가능한 상품 규칙",
      llm_boundary_ko: "Reason Code를 설명문으로 바꾸는 보조 역할만 수행하며 요율·인수·Care를 결정하지 않습니다.",
      competition_context_ko: "GAIP 2026 · Korea-first, Asia-ready 상품설계 검증",
      data_scope_ko: `${bundle.metadata.customer_count ?? bundle.drivers.length}명 합성 코호트 · 2개월 기준선 + 12개월 평가`,
      algorithm_role_ko: "DBSCAN은 실행 기준, Grid Count와 HDBSCAN은 별도 오프라인 비교 후보"
    },
    summary: {
      customer_count: bundle.drivers.length,
      same_input_contract_all_rows: true,
      baseline_60_day_excluded_all_rows: true,
      total_base_premium_krw: round(sum(basePremiums)),
      avg_base_premium_krw: round(mean(basePremiums)),
      existing_total_discount_krw: round(sum(basePremiums) - sum(existingNet)),
      proposed_total_discount_krw: round(sum(basePremiums) - sum(candidateNet)),
      discount_amount_delta_krw: round((sum(basePremiums) - sum(candidateNet)) - (sum(basePremiums) - sum(existingNet))),
      preventive_care_count: rows.filter(({ result }) => result.care_review_eligible).length,
      decision_counts: decisionCounts,
      existing_tier_count: new Set(bundle.drivers.map(koreaReferenceLabel)).size,
      avg_existing_discount_rate_pct: round(mean(bundle.drivers.map((driver) => driver.tariff?.korea_mileage_discount_rate_pct))),
      avg_proposed_discount_rate_pct: round(mean(rows.map(({ result }) => result.proposed_discount_rate_pct))),
      avg_annual_score: round(mean(rows.map(({ result }) => result.score)))
    },
    persona_summaries: personaSummaries(bundle, activeRules),
    existing_tier_segments: tierSegments(bundle, activeRules),
    driver_options: rows.map(({ driver, result }) => ({
      customer_id: driver.id,
      driver_id: driver.id,
      label: driver.display_label,
      label_en: driver.display_label_en,
      persona_type: driver.persona_id,
      annual_decision_signal: decisionSignal(result),
      existing_matched_tier_label: koreaReferenceLabel(driver),
      environment_id: driver.environment_id,
      environment_display_name_ko: driver.environment_label,
      reward_state: result.reward_state,
      care_state: result.care_state,
      zone_status: driver.mobility.zone_status,
      data_coverage_pct: averageCoverage(driver)
    })),
    source_artifacts: SAFE_SOURCE_ARTIFACTS,
    default_customer_id: defaultDriver?.id ?? "",
    product_rules: activeRules,
    algorithm_candidates: bundle.algorithms,
    source_status: "합성 시뮬레이션 · 상품 후보값 · 실제 손해효과 미검증"
  };
}

function selectedMonthlyResult(driver: StudioDriver, month: number | string): { result: StudioMonthlyResult; index: number } {
  const index = typeof month === "number"
    ? Math.max(0, Math.min(driver.monthly_results.length - 1, Math.round(month) - 1))
    : driver.monthly_results.findIndex((candidate) => candidate.month === month);
  if (index < 0 || !driver.monthly_results[index]) {
    throw new Error(`${driver.id}에서 ${month}월의 합성 근거를 찾을 수 없습니다.`);
  }
  return { result: driver.monthly_results[index], index };
}

function schematicClusters(driver: StudioDriver): ZoneCluster[] {
  // An empty routine_hubs array is preserved as an empty zone; no fallback centroid is invented.
  return driver.mobility.routine_hubs.map((hub, index) => {
    const point = schematicPoint(driver.id, index);
    const p90 = finite(hub.p90_radius_m);
    const core = finite(hub.core_radius_m, 500);
    return {
      cluster_id: index + 1,
      center_longitude: point.x,
      center_latitude: point.y,
      display_x: point.x,
      display_y: point.y,
      label_ko: hubDisplayLabel(driver, index),
      visit_count: hub.visit_count,
      p90_radius_m: round(p90, 1),
      radius_metric_m: round(p90, 1),
      core_radius_m: round(core, 1),
      boundary_area_km2: round(Math.PI * (p90 / 1000) ** 2, 4)
    };
  });
}

function schematicTrips(
  driver: StudioDriver,
  month: StudioMonthlyResult,
  rules: ProductRules
): ZoneTripInterpretation[] {
  const careGate =
    month.mobility_change_index_pct >= rules.care_mobility_change_threshold &&
    month.risky_behavior_change_index_pct >= rules.care_risky_behavior_threshold;

  const buildTrip = (
    destIndex: number,
    tripIndex: number,
    isOuter: boolean,
    hubIndex: number,
    distanceKm: number,
    riskEvents: number
  ): ZoneTripInterpretation => ({
    trip_id: `${driver.id}-${month.month}-d${destIndex}-${String(tripIndex + 1).padStart(2, "0")}`,
    destination_type: isOuter ? "outer_context" : `routine_hub_${String.fromCharCode(97 + hubIndex)}`,
    destination_label_ko: isOuter ? newHubDisplayLabel(driver) : hubDisplayLabel(driver, hubIndex),
    zone_label_from_dbscan_p90: isOuter ? "Outer · 위치 자체 중립" : "Routine Hub · Core/P90 근거",
    interpretation: isOuter
      ? careGate ? "out_zone_pattern_change_risk" : "out_zone_safe_driving"
      : "existing_living_zone",
    distance_km: round(distanceKm),
    risk_event_count: riskEvents,
    // The safe bundle has no night/new-destination detail, so these stay neutral.
    night_drive_flag: 0,
    route_repeat_flag: isOuter ? 0 : 1,
    new_destination_flag: 0
  });

  // Preferred path: per-destination aggregates from the REAL events, so risky events
  // and km land on the destination that produced them (a co-change person's outer
  // night route shows the risk; the in-zone market does not).
  const breakdown = month.destination_breakdown ?? [];
  if (breakdown.length) {
    const trips: ZoneTripInterpretation[] = [];
    breakdown.forEach((dest, destIndex) => {
      const count = Math.max(0, Math.round(dest.trip_count));
      if (!count) return;
      const hubIndex = dest.visit_label === "Routine Hub B" ? 1 : 0;
      const distancePer = dest.distance_km / count;
      const risk = Math.max(0, Math.round(dest.risk_event_count));
      for (let i = 0; i < count; i += 1) {
        const riskEvents = Math.floor(risk / count) + (i < risk % count ? 1 : 0);
        trips.push(buildTrip(destIndex, i, dest.is_outer, hubIndex, distancePer, riskEvents));
      }
    });
    return trips;
  }

  // Fallback: even-split from monthly aggregates (bundles without per-destination data).
  const tripCount = Math.max(0, Math.round(month.trip_count));
  if (!tripCount) return [];
  const hubs = driver.mobility.routine_hubs;
  const reportedOut = month.out_zone_trip_count ?? Math.round(tripCount * month.outer_visit_share_pct / 100);
  const outCount = Math.max(0, Math.min(tripCount, Math.round(reportedOut)));
  const inCount = tripCount - outCount;
  const totalRiskEvents = Math.max(0, Math.round(month.risky_events_per_100_km * month.total_distance_km / 100));
  const distancePerTrip = month.total_distance_km / tripCount;
  const trips: ZoneTripInterpretation[] = [];
  for (let index = 0; index < tripCount; index += 1) {
    const isOuter = index >= inCount || hubs.length === 0;
    const hubIndex = hubs.length ? index % hubs.length : 0;
    const riskEvents = Math.floor(totalRiskEvents / tripCount) + (index < totalRiskEvents % tripCount ? 1 : 0);
    trips.push(buildTrip(index, index, isOuter, hubIndex, distancePerTrip, riskEvents));
  }
  return trips;
}

export function adaptZoneMap(
  bundle: GaipStudioBundle,
  driverId: string,
  month: number | string,
  rules?: ProductRules
): ZoneMapResponse {
  const driver = driverById(bundle, driverId);
  const activeRules = effectiveRules(bundle, rules);
  const selected = selectedMonthlyResult(driver, month);
  const monthResult = selected.result;
  const clusters = schematicClusters(driver);
  const trips = clusters.length ? schematicTrips(driver, monthResult, activeRules) : [];
  const basis = baselineMonths(driver);
  const basisTripCount = sum(basis.map((row) => row.trip_count));
  const interpretations: Record<string, number> = {};
  trips.forEach((trip) => increment(interpretations, trip.interpretation));
  const p90 = clusters.length ? Math.max(...clusters.map((cluster) => cluster.p90_radius_m)) : 0;
  const evidenceReady = monthResult.zone_available && monthResult.data_coverage_pct >= activeRules.minimum_data_coverage_pct;
  const basisStatus = monthResult.period_role === "baseline"
    ? "baseline_observation"
    : !monthResult.zone_available
      ? "living_zone_evidence_hold"
      : evidenceReady ? "evaluation_ready" : "data_coverage_hold";

  return {
    analysis_method: {
      coordinate_policy: "schematic_normalized_only",
      location_semantics: "raw GPS and place semantics are not exposed",
      reference_algorithm: `${driver.mobility.algorithm} · 실행 기준`,
      product_zone: "각 Routine Hub에 Core 500m와 max(500m, min(radial P90, 2km)) Buffer를 별도 적용",
      outer_policy: "Outer는 중립 이동맥락이며 위치만으로 감점하지 않음",
      decision_scope: "비구속 상품 후보 및 사람 검토 지원"
    },
    source_artifacts: SAFE_SOURCE_ARTIFACTS,
    snapshot: {
      customer_id: driver.id,
      driver_id: driver.id,
      persona_type: driver.persona_id,
      service_month: monthResult.month,
      month: selected.index + 1,
      basis_window: {
        start_date: basis[0]?.month ?? "baseline-1",
        end_date: basis.at(-1)?.month ?? "baseline-2",
        days: 60,
        basis_trip_count: basisTripCount,
        scored_trip_count: evidenceReady ? monthResult.trip_count : 0,
        basis_status: basisStatus
      },
      leakage_guard: {
        current_month_excluded_from_zone_fit: true,
        current_month_trip_count_in_basis: 0
      },
      living_zone: {
        zone_model_backend: `${driver.mobility.algorithm} reference · haversine metres`,
        cluster_count: clusters.length,
        clusters,
        buffer: {
          departure_p90_threshold_m: round(p90, 1),
          departure_threshold_percentile: 90
        }
      },
      monthly_evidence: {
        monthly_distance_km: round(monthResult.total_distance_km),
        trip_count: monthResult.trip_count,
        in_zone_distance_ratio: round(Math.max(0, 1 - monthResult.outer_visit_share_pct / 100), 4),
        out_zone_distance_ratio: round(Math.min(1, monthResult.outer_visit_share_pct / 100), 4),
        interpretation_counts: interpretations,
        reason_codes: unique(monthResult.reason_codes)
      },
      scores: {
        mileage_score: round(monthResult.mileage_score),
        in_zone_safe_driving_score: monthResult.in_zone_safe_score === null ? null : round(monthResult.in_zone_safe_score),
        out_zone_safe_driving_score: monthResult.out_zone_safe_score === null ? null : round(monthResult.out_zone_safe_score),
        out_zone_pattern_change_risk: round(monthResult.mobility_change_index_pct),
        monthly_integrated_evidence_score: monthlyWeightedScore(monthResult, activeRules),
        score_role: evidenceReady ? "상품 후보 근거 · 최종결정 아님" : "근거 부족 · 판단 보류"
      },
      trip_interpretations: trips,
      // 실측 방문점(자택 기준 상대변위) — 선택 월 전체 + 기준선 2개월 고스트(솎음).
      visit_scatter: {
        selected: (monthResult.destination_breakdown ?? []).flatMap((d) =>
          (d.visit_points ?? []).map((pt) => [pt[0], pt[1], pt[2], d.is_outer ? 1 : 0])
        ),
        baseline: driver.monthly_results
          .filter((m) => m.period_role === "baseline")
          .flatMap((m) => (m.destination_breakdown ?? []).flatMap((d) => d.visit_points ?? []))
          .filter((_, i) => i % 2 === 0)
          .slice(0, 30)
          .map((pt) => [pt[0], pt[1]])
      }
    }
  };
}

export function buildEvidenceReport(
  bundle: GaipStudioBundle,
  driverId: string,
  month: number | string,
  rules?: ProductRules
): string {
  const driver = driverById(bundle, driverId);
  const activeRules = effectiveRules(bundle, rules);
  const picked = selectedMonthlyResult(driver, month);
  const selected = picked.result;
  const result = sandboxDecision(driver, activeRules);
  const score = monthlyWeightedScore(selected, activeRules);
  const evidenceReady = selected.zone_available && selected.data_coverage_pct >= activeRules.minimum_data_coverage_pct;
  const careOpenByMonth = computeTwoStageCareOpen(driver.monthly_results, activeRules);
  const selectedIdx = driver.monthly_results.findIndex((m) => m.month === selected.month);
  const careOpen = careOpenByMonth[selectedIdx] ?? false;
  const careGate = selected.period_role === "evaluation" && evidenceReady && careOpen;
  const outScore = selected.out_zone_safe_score === null ? "N/A (해당 월 관찰 없음)" : `${round(selected.out_zone_safe_score)}점`;
  const rewardLabel = monthlyRewardState(selected, activeRules, evidenceReady);
  const careLabel = monthlyCareState(selected, activeRules, evidenceReady, careOpen);

  return [
    `# ${selected.month} 근거 검토 초안`,
    "",
    `> ${driver.display_label} · ${driver.persona_label} · ${driver.environment_label}`,
    "> 합성 시뮬레이션 기반 설명 초안이며, 실제 요율·인수·케어 결정이 아닙니다.",
    "",
    "## 1. 관찰된 합성 근거",
    `- 기간 역할: ${selected.period_role === "baseline" ? "개인 기준선 관찰" : "평가기간"}`,
    `- 데이터 사용률: ${round(selected.data_coverage_pct)}%`,
    `- 주행: ${selected.trip_count}건 · ${round(selected.total_distance_km)}km`,
    `- 생활권 안 안전점수: ${selected.in_zone_safe_score === null ? "N/A" : `${round(selected.in_zone_safe_score)}점`}`,
    `- 생활권 밖 안전점수: ${outScore}`,
    `- 생활권 밖 맥락 비중: ${round(selected.outer_visit_share_pct)}% (위치 자체는 중립)`,
    `- 이동맥락 변화지수: ${round(selected.mobility_change_index_pct)}%`,
    `- 위험행동 변화지수: ${round(selected.risky_behavior_change_index_pct)}%`,
    "",
    "## 2. 상품 후보 해석",
    `- 가용 항목 재정규화 점수: ${score}점`,
    `- 선택 월 우대 상태: ${rewardLabel}`,
    `- 선택 월 케어 상태: ${careLabel}`,
    `- 연간 후보 상태(참고): 우대 ${result.reward_state} · 케어 ${result.care_state}`,
    `- 같은 달 동시 게이트: ${careGate ? "충족 — 사람 검토 제안" : "미충족"}`,
    `- Reason Code: ${unique(selected.reason_codes).join(", ") || "등록 없음"}`,
    "",
    "## 3. 사람 검토 범위",
    "- 위치나 이동거리만으로 불이익을 주지 않습니다.",
    "- 실제 장소명과 원본 좌표는 이 보고서에 포함하지 않습니다.",
    "- 담당자는 데이터 충분성, 계산 재현성, 정정 요청을 확인한 뒤 승인·보류·추가근거 요청을 기록합니다.",
    "- LLM은 위 계산 근거를 문장으로 정리할 수 있지만 최종 판단 권한은 없습니다."
  ].join("\n");
}

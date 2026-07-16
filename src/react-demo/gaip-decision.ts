import type {
  ProductComponentScores,
  ProductWeights,
  SandboxResult,
  StudioDriver,
  StudioMonthlyResult
} from "./gaip-types";

export interface SandboxDecisionInput {
  driver: StudioDriver;
  weights: ProductWeights;
  rewardThreshold: number;
  rewardRequiredMonths: number;
  minimumCoverage: number;
  careMobilityThreshold: number;
  careRiskThreshold: number;
  rewardDiscount: number;
  rewardBonusFloor?: number;
  careDiscountReduction?: number;
  candidateDiscountCap: number;
}

const WEIGHT_KEYS: Array<keyof ProductWeights> = [
  "mileage",
  "in_zone_safe",
  "out_zone_safe",
  "pattern_stability"
];

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, finite(value, min)));
}

export function productWeightTotal(weights: ProductWeights): number {
  return WEIGHT_KEYS.reduce((sum, key) => sum + Math.max(0, finite(weights[key])), 0);
}

export function productWeightsAreValid(weights: ProductWeights): boolean {
  return productWeightTotal(weights) === 100;
}

export function normalizeProductWeights(weights: ProductWeights): ProductWeights {
  const total = productWeightTotal(weights);
  if (total <= 0) {
    return { mileage: 25, in_zone_safe: 25, out_zone_safe: 25, pattern_stability: 25 };
  }

  const raw = WEIGHT_KEYS.map((key) => ({ key, value: (Math.max(0, finite(weights[key])) / total) * 100 }));
  const rounded = raw.map((item) => ({ ...item, value: Math.floor(item.value) }));
  let remainder = 100 - rounded.reduce((sum, item) => sum + item.value, 0);

  raw
    .map((item, index) => ({ index, fraction: item.value - Math.floor(item.value) }))
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index)
    .forEach(({ index }) => {
      if (remainder > 0) {
        rounded[index].value += 1;
        remainder -= 1;
      }
    });

  return rounded.reduce(
    (result, item) => ({ ...result, [item.key]: item.value }),
    {} as ProductWeights
  );
}

function monthlyScore(month: StudioMonthlyResult, weights: ProductWeights): {
  score: number | null;
  observedWeightPct: number;
} {
  const components: Array<[keyof ProductWeights, number | null]> = [
    ["mileage", month.mileage_score],
    ["in_zone_safe", month.in_zone_safe_score],
    ["out_zone_safe", month.out_zone_safe_score],
    ["pattern_stability", month.pattern_stability_score]
  ];
  const observed = components.filter((entry): entry is [keyof ProductWeights, number] =>
    entry[1] !== null && Number.isFinite(entry[1])
  );
  const observedWeight = observed.reduce((sum, [key]) => sum + weights[key], 0);
  if (observedWeight <= 0) return { score: null, observedWeightPct: 0 };
  return {
    score: observed.reduce((sum, [key, value]) => sum + value * weights[key], 0) / observedWeight,
    observedWeightPct: observedWeight
  };
}

function isEvaluationMonth(month: StudioMonthlyResult): boolean {
  return month.period_role === "evaluation";
}

function isEligibleMonth(month: StudioMonthlyResult, minimumCoverage: number): boolean {
  return month.zone_available && month.data_coverage_pct >= minimumCoverage;
}

export function calculateSandboxDecision(input: SandboxDecisionInput): SandboxResult {
  const {
    driver,
    weights,
    rewardThreshold,
    rewardRequiredMonths,
    minimumCoverage,
    careMobilityThreshold,
    careRiskThreshold,
    rewardDiscount,
    rewardBonusFloor = 1,
    careDiscountReduction = 0,
    candidateDiscountCap
  } = input;
  const normalizedWeights = normalizeProductWeights(weights);
  const evaluation = driver.monthly_results.filter(isEvaluationMonth);
  const careEligible = evaluation.filter((month) => isEligibleMonth(month, minimumCoverage));
  const scored = careEligible
    .map((month) => ({ month, ...monthlyScore(month, normalizedWeights) }))
    .filter((row): row is { month: StudioMonthlyResult; score: number; observedWeightPct: number } => row.score !== null);
  const averageObserved = (select: (month: StudioMonthlyResult) => number | null): number | null => {
    const values = scored.map(({ month }) => select(month)).filter((value): value is number => value !== null && Number.isFinite(value));
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  };
  const componentScores: ProductComponentScores = {
    mileage: averageObserved((month) => month.mileage_score),
    in_zone_safe: averageObserved((month) => month.in_zone_safe_score),
    out_zone_safe: averageObserved((month) => month.out_zone_safe_score),
    pattern_stability: averageObserved((month) => month.pattern_stability_score)
  };
  const scores = scored.map(({ score }) => score);
  const score = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : 0;
  const requiredMonths = Math.max(1, Math.round(finite(rewardRequiredMonths, 9)));
  const rewardMonths = scored.filter(({ score: monthScore }) => monthScore >= rewardThreshold);
  const careMonths = careEligible.filter(
    (month) =>
      month.mobility_change_index_pct >= careMobilityThreshold &&
      month.risky_behavior_change_index_pct >= careRiskThreshold
  );

  const rewardEvidenceSufficient = scored.length >= requiredMonths;
  const rewardEligible = rewardEvidenceSufficient && rewardMonths.length >= requiredMonths;
  const careReviewEligible = careMonths.length > 0;
  const careEvidenceSufficient = careEligible.length > 0;
  const rewardState: SandboxResult["reward_state"] = rewardEvidenceSufficient
    ? rewardEligible ? "Reward" : "Neutral"
    : "Hold";
  const careState: SandboxResult["care_state"] = careEvidenceSufficient
    ? careReviewEligible ? "Care Review" : "None"
    : "Hold";

  let outcome: SandboxResult["outcome"];
  if (rewardEligible && careReviewEligible) outcome = "Reward + Care Review";
  else if (careReviewEligible) outcome = "Care Review";
  else if (rewardEligible) outcome = "Reward";
  else if (rewardState === "Hold") outcome = "Hold";
  else outcome = "Neutral";

  const reasonCodes = [
    `SCORED_MONTHS_${scored.length}_OF_${evaluation.length}`,
    rewardEligible
      ? "REWARD_REQUIRED_MONTHS_MET"
      : rewardState === "Hold"
        ? "REWARD_EVIDENCE_INSUFFICIENT"
        : "REWARD_REQUIRED_MONTHS_NOT_MET",
    careReviewEligible ? "SAME_MONTH_CARE_GATE_MET" : careState === "Hold" ? "CARE_EVIDENCE_INSUFFICIENT" : "SAME_MONTH_CARE_GATE_NOT_MET"
  ];
  const partialComponentMonthCount = scored.filter(({ observedWeightPct }) => observedWeightPct < 100).length;
  const minimumObservedScoreWeightPct = scored.length
    ? Math.min(...scored.map(({ observedWeightPct }) => observedWeightPct))
    : 0;
  if (partialComponentMonthCount > 0) {
    reasonCodes.push(`PARTIAL_SCORE_COMPONENT_MONTHS_${partialComponentMonthCount}`);
  }
  if (careReviewEligible) reasonCodes.push("HUMAN_CARE_REVIEW_SUGGESTED");
  // Pricing couples the axes on purpose: while a care review is open, the earned
  // Favorable bonus is SUSPENDED (not lost) — disclose it as a reason code so the
  // "-13%p" delta is a declared rule, not a silent constant.
  if (rewardEligible && careReviewEligible) reasonCodes.push("REWARD_BONUS_SUSPENDED_PENDING_CARE_REVIEW");

  const koreaMileageRate = driver.tariff?.korea_mileage_discount_rate_pct ?? 0;
  // Reward bonus scales with the integrated score: floor at the reward threshold,
  // max at 100 — so a stronger driver earns a visibly larger discount. Mirrors the
  // backend pricing_sandbox exactly. Care cases take the leakage-prevention
  // reduction instead of a bonus.
  const bonusMax = clamp(rewardDiscount, 0, 50);
  const bonusFloor = clamp(rewardBonusFloor, 0, bonusMax);
  const scoreSpan = Math.max(1, 100 - rewardThreshold);
  const scoreFrac = clamp((score - rewardThreshold) / scoreSpan, 0, 1);
  const rewardBonus = rewardEligible && !careReviewEligible ? bonusFloor + scoreFrac * (bonusMax - bonusFloor) : 0;
  const careReduction = careReviewEligible ? clamp(careDiscountReduction, 0, 100) : 0;
  const proposedDiscount = clamp(
    Math.min(clamp(candidateDiscountCap, 0, 100), koreaMileageRate + rewardBonus - careReduction),
    0,
    100
  );
  const basePremium = driver.tariff?.base_premium_krw;
  const holdReason = rewardState === "Hold"
    ? evaluation.length === 0
      ? "평가월 데이터가 없어 상품 판단을 보류합니다."
      : `상품 판정 가능한 평가월이 ${scored.length}개월로, Reward 판단에 필요한 ${requiredMonths}개월보다 적습니다.`
    : undefined;

  return {
    score,
    outcome,
    outcome_ko: outcome === "Hold" ? "판단 보류" : outcome,
    reward_state: rewardState,
    care_state: careState,
    reward_eligible: rewardEligible,
    care_review_eligible: careReviewEligible,
    care_gate_met: careReviewEligible,
    hold_reason: holdReason,
    normalized_weights: normalizedWeights,
    component_scores: componentScores,
    partial_component_month_count: partialComponentMonthCount,
    minimum_observed_score_weight_pct: minimumObservedScoreWeightPct,
    reward_month_count: rewardMonths.length,
    care_review_month_count: careMonths.length,
    eligible_month_count: scored.length,
    evaluation_month_count: evaluation.length,
    reward_required_months: requiredMonths,
    reason_codes: reasonCodes,
    proposed_discount_rate_pct: proposedDiscount,
    proposed_net_premium_krw:
      basePremium === undefined ? undefined : basePremium * (1 - proposedDiscount / 100)
  };
}

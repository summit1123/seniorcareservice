import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { normalizeGaipStudioBundle } from "../src/react-demo/gaip-api.ts";
import {
  calculateSandboxDecision,
  normalizeProductWeights,
  productWeightsAreValid
} from "../src/react-demo/gaip-decision.ts";
import type { ProductWeights, StudioDriver, StudioMonthlyResult } from "../src/react-demo/gaip-types.ts";

const DEFAULT_WEIGHTS: ProductWeights = {
  mileage: 30,
  in_zone_safe: 30,
  out_zone_safe: 20,
  pattern_stability: 20
};

function month(index: number, overrides: Partial<StudioMonthlyResult> = {}): StudioMonthlyResult {
  return {
    month: `2026-${String(index + 1).padStart(2, "0")}`,
    period_role: "evaluation",
    trip_count: 10,
    total_distance_km: 100,
    zone_available: true,
    data_coverage_pct: 98,
    outer_visit_share_pct: 0,
    risky_behavior_rate_pct: 0,
    risky_events_per_100_km: 0,
    mileage_score: 90,
    in_zone_safe_score: 90,
    out_zone_safe_score: 90,
    pattern_stability_score: 90,
    mobility_change_index_pct: 0,
    risky_behavior_change_index_pct: 0,
    reason_codes: [],
    source_status: "simulated",
    ...overrides
  };
}

function driver(months: StudioMonthlyResult[]): StudioDriver {
  return {
    id: "gaip-test-001",
    display_label: "합성 운전자 테스트",
    persona_id: "test",
    persona_label: "테스트형",
    environment_id: "dense_urban",
    environment_label: "고밀도 도심형",
    metrics: {
      mileage_score: 90,
      in_zone_safe_score: 90,
      out_zone_safe_score: 90,
      pattern_stability_score: 90,
      mobility_change_index_pct: 0,
      risky_behavior_change_index_pct: 0,
      data_coverage_pct: 98,
      annual_distance_km: 1000,
      total_trips: 120
    },
    mobility: {
      zone_status: "available",
      algorithm: "DBSCAN",
      repeated_hub_count: 1,
      routine_hubs: []
    },
    monthly_results: months,
    tariff: {
      base_premium_krw: 1_000_000,
      korea_mileage_discount_rate_pct: 40,
      korea_mileage_net_premium_krw: 600_000
    }
  };
}

function decide(months: StudioMonthlyResult[], overrides: Partial<Parameters<typeof calculateSandboxDecision>[0]> = {}) {
  return calculateSandboxDecision({
    driver: driver(months),
    weights: DEFAULT_WEIGHTS,
    rewardThreshold: 75,
    rewardRequiredMonths: 9,
    minimumCoverage: 80,
    careMobilityThreshold: 25,
    careRiskThreshold: 20,
    rewardDiscount: 3,
    candidateDiscountCap: 45,
    ...overrides
  });
}

test("Reward uses the same monthly formula and requires 9 of 12 eligible months", () => {
  const months = Array.from({ length: 12 }, (_, index) => month(index, index < 8 ? {} : {
    mileage_score: 40,
    in_zone_safe_score: 40,
    out_zone_safe_score: 40,
    pattern_stability_score: 40
  }));
  const result = decide(months);

  assert.equal(result.reward_month_count, 8);
  assert.equal(result.reward_state, "Neutral");
  assert.equal(result.reward_eligible, false);
  assert.equal(result.proposed_discount_rate_pct, 40);
});

test("Care requires mobility and risky-behavior changes in the same eligible month", () => {
  const months = Array.from({ length: 12 }, (_, index) => month(index));
  months[2] = month(2, { outer_visit_share_pct: 40, mobility_change_index_pct: 40 });
  months[7] = month(7, { risky_behavior_rate_pct: 40, risky_behavior_change_index_pct: 40 });
  const result = decide(months);

  assert.equal(result.care_review_month_count, 0);
  assert.equal(result.care_state, "None");
  assert.equal(result.care_review_eligible, false);
  assert.ok(result.reason_codes.includes("SAME_MONTH_CARE_GATE_NOT_MET"));
});

test("Reward and Care are independent axes, and Care routes pricing to the reduction", () => {
  const months = Array.from({ length: 12 }, (_, index) => month(index));
  months[6] = month(6, {
    outer_visit_share_pct: 40,
    risky_behavior_rate_pct: 30,
    mobility_change_index_pct: 40,
    risky_behavior_change_index_pct: 30
  });
  const result = decide(months, { careDiscountReduction: 13 });

  // Both axes fire independently.
  assert.equal(result.reward_state, "Reward");
  assert.equal(result.care_state, "Care Review");
  assert.equal(result.outcome, "Reward + Care Review");
  assert.equal(result.reward_month_count, 12);
  assert.equal(result.care_review_month_count, 1);
  // A Care case takes the leakage-prevention reduction instead of the safe-driver
  // bonus: korea 40% − 13pp reduction, no bonus.
  assert.equal(result.proposed_discount_rate_pct, 27);
});

test("Reward bonus scales with the integrated safety score", () => {
  const highScore = decide(
    Array.from({ length: 12 }, (_, index) =>
      month(index, { mileage_score: 100, in_zone_safe_score: 100, out_zone_safe_score: 100, pattern_stability_score: 100 })
    )
  );
  const lowScore = decide(
    Array.from({ length: 12 }, (_, index) =>
      month(index, { mileage_score: 76, in_zone_safe_score: 76, out_zone_safe_score: 76, pattern_stability_score: 76 })
    )
  );

  assert.equal(highScore.reward_state, "Reward");
  assert.equal(lowScore.reward_state, "Reward");
  // A stronger safety score earns a strictly larger proposed discount.
  assert.ok(highScore.proposed_discount_rate_pct > lowScore.proposed_discount_rate_pct);
});

test("missing out-zone evidence is N/A and observed weights are renormalized", () => {
  const months = Array.from({ length: 12 }, (_, index) => month(index, {
    mileage_score: 80,
    in_zone_safe_score: 90,
    out_zone_safe_score: null,
    pattern_stability_score: 70,
    out_zone_trip_count: 0
  }));
  const result = decide(months, { rewardThreshold: 83 });

  assert.equal(result.score, 81.25);
  assert.equal(result.reward_state, "Neutral");
  assert.equal(result.component_scores.out_zone_safe, null);
  assert.equal(result.partial_component_month_count, 12);
  assert.equal(result.minimum_observed_score_weight_pct, 80);
  assert.ok(result.reason_codes.includes("PARTIAL_SCORE_COMPONENT_MONTHS_12"));
});

test("insufficient eligible months hold Reward without inventing a penalty", () => {
  const months = Array.from({ length: 12 }, (_, index) => month(index, index < 8 ? {} : { zone_available: false }));
  const result = decide(months);

  assert.equal(result.eligible_month_count, 8);
  assert.equal(result.reward_state, "Hold");
  assert.equal(result.outcome, "Hold");
  assert.equal(result.proposed_discount_rate_pct, 40);
  assert.match(result.hold_reason ?? "", /필요한 9개월보다 적습니다/);
});

test("weight normalization is deterministic and validity requires exactly 100", () => {
  const invalid = { mileage: 40, in_zone_safe: 30, out_zone_safe: 20, pattern_stability: 20 };
  assert.equal(productWeightsAreValid(invalid), false);
  assert.deepEqual(normalizeProductWeights(invalid), {
    mileage: 37,
    in_zone_safe: 27,
    out_zone_safe: 18,
    pattern_stability: 18
  });
  assert.equal(productWeightsAreValid(normalizeProductWeights(invalid)), true);
});

test("bundle normalization rejects empty and missing-month payloads", () => {
  assert.throws(() => normalizeGaipStudioBundle({}), /합성 운전자 데이터가 없습니다/);
  assert.throws(
    () => normalizeGaipStudioBundle({
      drivers: [{ driver_id: "missing-months" }],
      algorithm: { reference: { name: "DBSCAN" } }
    }),
    /월별 평가 근거가 없어/
  );
});

test("monthly normalization uses an allowlist and strips coordinates and place semantics", () => {
  const bundle = normalizeGaipStudioBundle({
    metadata: { synthetic_data: true },
    algorithm: {
      reference: { name: "DBSCAN" },
      offline_comparison_candidates: [
        { name: "Grid Count", result_status: "not_run" },
        { name: "HDBSCAN", result_status: "not_run" }
      ]
    },
    drivers: [{
      driver_id: "gaip-safe",
      persona_type: "stable_local_safe",
      environment_id: "dense_urban",
      mobility: { zone_status: "available", algorithm: "DBSCAN", cluster_count: 1 },
      monthly_results: [{
        month: "2026-01",
        period_role: "evaluation",
        zone_available: true,
        data_coverage_pct: 98,
        mileage_score: 90,
        in_zone_safe_score: 90,
        out_zone_safe_score: 90,
        pattern_stability_score: 90,
        mobility_change_index: 0.1,
        risky_behavior_change_index: 0.2,
        latitude: 37.5,
        longitude: 127,
        destination_type: "clinic"
      }]
    }]
  });
  const normalized = bundle.drivers[0].monthly_results[0] as unknown as Record<string, unknown>;

  assert.equal(normalized.mobility_change_index_pct, 10);
  assert.equal(normalized.risky_behavior_change_index_pct, 20);
  assert.equal("latitude" in normalized, false);
  assert.equal("longitude" in normalized, false);
  assert.equal("destination_type" in normalized, false);
  assert.deepEqual(bundle.algorithms.map(({ label, status }) => [label, status]), [
    ["DBSCAN", "active"],
    ["Grid Count", "not_run"],
    ["HDBSCAN", "not_run"]
  ]);
});

test("monthly normalization preserves missing safety evidence as null", () => {
  const bundle = normalizeGaipStudioBundle({
    algorithm: { reference: { name: "DBSCAN" } },
    drivers: [{
      driver_id: "gaip-missing-component",
      persona_type: "safe_multi_hub",
      environment_id: "dense_urban",
      mobility: { zone_status: "available", cluster_count: 1 },
      monthly_results: [{
        month: "2026-01",
        period_role: "evaluation",
        zone_available: true,
        data_coverage_pct: 99,
        mileage_score: 80,
        in_zone_safe_score: 90,
        out_zone_safe_score: null,
        out_zone_trip_count: 0,
        pattern_stability_score: 95
      }]
    }]
  });

  const normalized = bundle.drivers[0].monthly_results[0];
  assert.equal(normalized.out_zone_safe_score, null);
  assert.equal(normalized.out_zone_trip_count, 0);
});

test("default UI calculation matches the generated backend decision for all 180 driver cases", () => {
  const raw = JSON.parse(readFileSync("data/fixtures/gaip_simulation_bundle.json", "utf8")) as {
    drivers: Array<Record<string, unknown>>;
  };
  const bundle = normalizeGaipStudioBundle(raw);
  const sourceById = new Map(raw.drivers.map((item) => [String(item.driver_id), item]));
  const rewardLabels: Record<string, "Reward" | "Neutral" | "Hold"> = {
    reward: "Reward",
    neutral: "Neutral",
    hold: "Hold"
  };
  const careLabels: Record<string, "Care Review" | "None" | "Hold"> = {
    care_review: "Care Review",
    none: "None",
    hold: "Hold"
  };

  assert.equal(bundle.drivers.length, 180);
  for (const driverItem of bundle.drivers) {
    const source = sourceById.get(driverItem.id);
    assert.ok(source, driverItem.id);
    const rules = bundle.product_rules;
    const result = calculateSandboxDecision({
      driver: driverItem,
      weights: rules.weights,
      rewardThreshold: rules.reward_score_threshold,
      rewardRequiredMonths: rules.reward_required_months,
      minimumCoverage: rules.minimum_data_coverage_pct,
      careMobilityThreshold: rules.care_mobility_change_threshold,
      careRiskThreshold: rules.care_risky_behavior_threshold,
      rewardDiscount: rules.reward_discount_rate_pct ?? 0,
      candidateDiscountCap: rules.candidate_discount_cap_pct ?? 45
    });

    assert.equal(result.reward_state, rewardLabels[String(source.annual_reward_state)], `${driverItem.id} Reward`);
    assert.equal(result.care_state, careLabels[String(source.annual_care_state)], `${driverItem.id} Care`);
    assert.equal(result.reward_month_count, Number(source.reward_month_count), `${driverItem.id} Reward months`);
    assert.equal(result.care_review_month_count, Number(source.care_review_month_count), `${driverItem.id} Care months`);
  }
});

test("an explicitly active upstream challenger is rejected because DBSCAN is the locked runtime", () => {
  const base = JSON.parse(readFileSync("data/fixtures/gaip_simulation_bundle.json", "utf8"));
  base.algorithms = [
    { id: "dbscan", label: "DBSCAN", role: "reference", status: "complete" },
    { id: "hdbscan", label: "HDBSCAN", role: "challenger", status: "active" },
    { id: "grid_count", label: "Grid Count", role: "baseline", status: "not_run" }
  ];
  assert.throws(() => normalizeGaipStudioBundle(base), /DBSCAN만 허용/);
});

test("offline comparison candidates cannot be presented as completed results", () => {
  const base = JSON.parse(readFileSync("data/fixtures/gaip_simulation_bundle.json", "utf8"));
  base.algorithms = [
    { id: "dbscan", label: "DBSCAN", role: "reference", status: "active" },
    { id: "hdbscan", label: "HDBSCAN", role: "challenger", status: "complete" },
    { id: "grid_count", label: "Grid Count", role: "baseline", status: "not_run" }
  ];
  assert.throws(() => normalizeGaipStudioBundle(base), /not_run/);
});

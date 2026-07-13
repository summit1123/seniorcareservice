import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { sanitizeGaipBundleForUi } from "../src/gaip_server_policy.ts";
import { normalizeGaipStudioBundle } from "../src/react-demo/gaip-api.ts";
import {
  adaptAnnualSummary,
  adaptDirectory,
  adaptMonthlySnapshots,
  adaptZoneMap,
  buildEvidenceReport
} from "../src/react-demo/legacy-gaip-adapter.ts";

const raw = JSON.parse(readFileSync("data/fixtures/gaip_simulation_bundle.json", "utf8"));
const bundle = normalizeGaipStudioBundle(sanitizeGaipBundleForUi(raw));

test("legacy dashboard adapter preserves the original IA contract with 60 drivers and 14 months", () => {
  const directory = adaptDirectory(bundle);
  assert.equal(directory.driver_options.length, 60);
  assert.equal(directory.summary.customer_count, 60);
  assert.equal(directory.default_customer_id, "gaip-051");
  assert.equal(directory.algorithm_candidates?.filter((candidate) => candidate.status === "active").length, 1);
  assert.equal(directory.algorithm_candidates?.find((candidate) => candidate.status === "active")?.label, "DBSCAN");

  const months = adaptMonthlySnapshots(bundle, "gaip-051").monthly_evidence;
  assert.equal(months.length, 14);
  assert.equal(months.filter((month) => month.period_role === "baseline").length, 2);
  assert.equal(months.filter((month) => month.period_role === "evaluation").length, 12);
});

test("Care remains independent and requires both changes in the same evaluation month", () => {
  const summary = adaptAnnualSummary(bundle, "gaip-051");
  assert.equal(summary.reward_state, "Neutral");
  assert.equal(summary.care_state, "Care Review");

  const months = adaptMonthlySnapshots(bundle, "gaip-051").monthly_evidence;
  const careMonths = months.filter((month) => month.care_state === "Care Review");
  assert.ok(careMonths.length > 0);
  assert.ok(careMonths.every((month) => (month.mobility_change_index_pct ?? 0) >= 25));
  assert.ok(careMonths.every((month) => (month.risky_behavior_change_index_pct ?? 0) >= 20));
});

test("no-zone evidence never fabricates a hub and results in a no-penalty hold", () => {
  const summary = adaptAnnualSummary(bundle, "gaip-010");
  const map = adaptZoneMap(bundle, "gaip-010", 3);
  assert.equal(summary.reward_state, "Hold");
  assert.equal(summary.care_state, "Hold");
  assert.equal(Object.keys(summary.living_destinations).length, 0);
  assert.equal(map.snapshot.living_zone.cluster_count, 0);
  assert.deepEqual(map.snapshot.living_zone.clusters, []);
  assert.deepEqual(map.snapshot.trip_interpretations, []);
});

test("map and evidence report use only generic place labels and explicit human-review boundaries", () => {
  const map = adaptZoneMap(bundle, "gaip-051", 10);
  const serialized = JSON.stringify(map);
  assert.match(serialized, /Routine Hub/);
  for (const forbidden of ["병원", "자녀", "자택", "마트", "약국"]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }

  const report = buildEvidenceReport(bundle, "gaip-051", 10);
  assert.match(report, /실제 요율·인수·Care 결정이 아닙니다/);
  assert.match(report, /같은 달 AND Gate: 충족/);
  assert.match(report, /원본 좌표는 이 보고서에 포함하지 않습니다/);

  const nonCareMonth = buildEvidenceReport(bundle, "gaip-051", 3);
  assert.match(nonCareMonth, /선택 월 Care 상태: None/);
  assert.match(nonCareMonth, /같은 달 AND Gate: 미충족/);
  assert.match(nonCareMonth, /연간 후보 상태\(참고\): Reward Neutral · Care Care Review/);
});

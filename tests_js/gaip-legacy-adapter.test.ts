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
const directory = adaptDirectory(bundle);

function firstOption(predicate: (option: (typeof directory.driver_options)[number]) => boolean): string {
  const option = directory.driver_options.find(predicate);
  assert.ok(option, "expected a matching driver option");
  return option.driver_id;
}

test("legacy dashboard adapter preserves the original IA contract with 180 driver cases and 14 months", () => {
  // 60 synthetic people x 3 mobility environments = 180 selectable driver cases.
  assert.equal(directory.driver_options.length, 180);
  assert.equal(directory.summary.customer_count, 180);
  assert.equal(directory.algorithm_candidates?.filter((candidate) => candidate.status === "active").length, 1);
  assert.equal(directory.algorithm_candidates?.find((candidate) => candidate.status === "active")?.label, "DBSCAN");

  // The default landing case is the first Care Review case, so the dashboard opens
  // on the most instructive decision path.
  const defaultSummary = adaptAnnualSummary(bundle, directory.default_customer_id);
  assert.equal(defaultSummary.care_state, "Care Review");

  // Driver options display the synthetic person name with age, and the Korea
  // reference tier label is rendered in Korean (display-only).
  for (const option of directory.driver_options) {
    assert.match(option.label, /^[가-힣]{2,4} \(\d{2}세\)$/, option.label);
    assert.match(option.existing_matched_tier_label, /^기존 마일리지 기준 \d+(\.\d+)?%$/);
  }

  const months = adaptMonthlySnapshots(bundle, directory.default_customer_id).monthly_evidence;
  assert.equal(months.length, 14);
  assert.equal(months.filter((month) => month.period_role === "baseline").length, 2);
  assert.equal(months.filter((month) => month.period_role === "evaluation").length, 12);
});

test("Care remains independent and requires both changes in the same evaluation month", () => {
  const careDriverId = firstOption((option) => option.care_state === "Care Review");
  const summary = adaptAnnualSummary(bundle, careDriverId);
  assert.equal(summary.care_state, "Care Review");

  const months = adaptMonthlySnapshots(bundle, careDriverId).monthly_evidence;
  const careMonths = months.filter((month) => month.care_state === "Care Review");
  assert.ok(careMonths.length > 0);
  assert.ok(careMonths.every((month) => (month.mobility_change_index_pct ?? 0) >= 25));
  assert.ok(careMonths.every((month) => (month.risky_behavior_change_index_pct ?? 0) >= 20));

  // Reward and Care are independent axes: the same Reward verdict appears both
  // with and without a Care Review, so Care is not determined by the Reward tier.
  const rewardWithCare = directory.driver_options.some(
    (option) => option.reward_state === "Reward" && option.care_state === "Care Review"
  );
  const rewardWithoutCare = directory.driver_options.some(
    (option) => option.reward_state === "Reward" && option.care_state !== "Care Review"
  );
  assert.ok(rewardWithCare && rewardWithoutCare);
});

test("sparse evidence surfaces a no-penalty hold and never fabricates a hub", () => {
  // No fixture person has zero living-zone evidence, but a few sparse-data people
  // fall to Hold. The map must mirror only the real routine hubs — it never invents
  // a centroid — and the hold carries no location penalty.
  const holdDriverId = firstOption((option) => option.reward_state === "Hold");
  const summary = adaptAnnualSummary(bundle, holdDriverId);
  const map = adaptZoneMap(bundle, holdDriverId, 3);
  const driver = bundle.drivers.find((candidate) => candidate.id === holdDriverId);
  assert.ok(driver);
  assert.equal(summary.reward_state, "Hold");
  assert.equal(summary.care_state, "Hold");
  // Clusters are exactly the driver's routine hubs, one-to-one — no fabrication.
  assert.equal(map.snapshot.living_zone.cluster_count, driver.mobility.routine_hubs.length);
  assert.equal(map.snapshot.living_zone.clusters.length, driver.mobility.routine_hubs.length);
  // Location is never itself penalised: any outer trips stay on neutral interpretations.
  for (const trip of map.snapshot.trip_interpretations) {
    assert.notEqual(trip.interpretation, "out_zone_pattern_change_risk");
  }
});

// Policy: hub labels shown to the UI are synthetic semantic Korean labels from the
// engine's APPROVED_HUB_LABELS_KO union (src/gaip_simulation/engine.py). They must
// stay in this approved union, and raw coordinate field names must remain absent.
const APPROVED_SYNTHETIC_HUB_LABELS = new Set([
  // APPROVED_HUB_LABELS_KO values (home / secondary / new-hub labels)
  "자택 인근", "두 번째 생활권", "신규 외출지", "야간 신규 목적지",
  "신규 목적지", "야간 외곽 경로", "원거리 정기 방문지",
  // display-only fallbacks in the legacy adapter
  "반복 거점 A", "반복 거점 B"
]);

test("map and evidence report use only approved synthetic labels and explicit human-review boundaries", () => {
  const richDriverId = firstOption((option) => {
    const map = adaptZoneMap(bundle, option.driver_id, 10);
    return [
      ...map.snapshot.living_zone.clusters.map((cluster) => cluster.label_ko ?? ""),
      ...map.snapshot.trip_interpretations.map((trip) => trip.destination_label_ko ?? "")
    ].some((label) => label.length > 0);
  });
  const map = adaptZoneMap(bundle, richDriverId, 10);
  const serialized = JSON.stringify(map);
  const mapLabels = [
    ...map.snapshot.living_zone.clusters.map((cluster) => cluster.label_ko ?? ""),
    ...map.snapshot.trip_interpretations.map((trip) => trip.destination_label_ko ?? "")
  ].filter((label): label is string => label.length > 0);
  assert.ok(mapLabels.length > 0);
  for (const label of mapLabels) {
    assert.ok(APPROVED_SYNTHETIC_HUB_LABELS.has(label), `unapproved label: ${label}`);
  }
  for (const forbiddenField of ['"latitude"', '"longitude"']) {
    assert.equal(serialized.includes(forbiddenField), false, forbiddenField);
  }

  const careDriverId = firstOption((option) => option.care_state === "Care Review");
  const evidence = adaptMonthlySnapshots(bundle, careDriverId).monthly_evidence;
  const careMonth = evidence.find((month) => month.care_state === "Care Review");
  const noneMonth = evidence.find((month) => month.care_state === "None");
  assert.ok(careMonth && noneMonth);

  const report = buildEvidenceReport(bundle, careDriverId, careMonth.month);
  assert.match(report, /실제 요율·인수·케어 결정이 아닙니다/);
  assert.match(report, /같은 달 동시 게이트: 충족/);
  assert.match(report, /원본 좌표는 이 보고서에 포함하지 않습니다/);

  const careSummary = adaptAnnualSummary(bundle, careDriverId);
  const nonCareMonth = buildEvidenceReport(bundle, careDriverId, noneMonth.month);
  assert.match(nonCareMonth, /선택 월 케어 상태: None/);
  assert.match(nonCareMonth, /같은 달 동시 게이트: 미충족/);
  assert.match(
    nonCareMonth,
    new RegExp(`연간 후보 상태\\(참고\\): 우대 ${careSummary.reward_state} · 케어 ${careSummary.care_state}`)
  );
});

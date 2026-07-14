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

  // Driver options display the synthetic person name with age, and the Korea
  // reference tier label is now rendered in Korean (display-only change).
  for (const option of directory.driver_options) {
    assert.match(option.label, /^[가-힣]{2,4} \(\d{2}세\)$/, option.label);
    assert.match(option.existing_matched_tier_label, /^기존 마일리지 기준 \d+(\.\d+)?%$/);
  }

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

// Policy change (2026-07): hub labels shown to the UI are synthetic semantic
// Korean labels from the engine's PERSONA_HUB_LABELS union. They must stay in
// this approved union, and raw coordinate field names must remain absent.
const APPROVED_SYNTHETIC_HUB_LABELS = new Set([
  // PERSONA_HUB_LABELS values (src/gaip_simulation/engine.py)
  "자택·마트 동선", "경로당", "신규 외출지",
  "자택 인근", "시장", "야간 신규 목적지",
  "자택(본가)", "자녀 집", "새 모임 장소",
  "자택(농가)", "읍내 마트·병원", "원거리 정기 방문지",
  "복지관", "병원 정기 경로",
  "마트", "야간 외곽 경로",
  // display-only fallbacks in the legacy adapter
  "반복 거점 A", "반복 거점 B", "신규 목적지"
]);

test("map and evidence report use only approved synthetic labels and explicit human-review boundaries", () => {
  const map = adaptZoneMap(bundle, "gaip-051", 10);
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

  const report = buildEvidenceReport(bundle, "gaip-051", 10);
  assert.match(report, /실제 요율·인수·Care 결정이 아닙니다/);
  assert.match(report, /같은 달 AND Gate: 충족/);
  assert.match(report, /원본 좌표는 이 보고서에 포함하지 않습니다/);

  const nonCareMonth = buildEvidenceReport(bundle, "gaip-051", 3);
  assert.match(nonCareMonth, /선택 월 Care 상태: None/);
  assert.match(nonCareMonth, /같은 달 AND Gate: 미충족/);
  assert.match(nonCareMonth, /연간 후보 상태\(참고\): Reward Neutral · Care Care Review/);
});

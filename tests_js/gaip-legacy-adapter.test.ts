import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { sanitizeGaipBundleForUi } from "../src/gaip_server_policy.ts";
import { normalizeGaipStudioBundle } from "../src/react-demo/gaip-api.ts";
import {
  adaptAnnualSummary,
  adaptDirectory,
  adaptMonthlySnapshots,
  adaptRepresentativePair,
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

  // Driver options keep the synthetic display name and birth year in separate
  // fields so the UI can place "Birth year" on its own line.
  for (const option of directory.driver_options) {
    assert.match(option.label, /^(?:[가-힣]{2,4}|Jackie Chan|Tom Hanks)$/, option.label);
    assert.equal(Number.isInteger(option.birth_year), true, option.label);
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

test("matched pair contrasts the same vehicle class and never exceeds the base premium", () => {
  // gaip-114(한영자/Sylvia Moore)는 케어 검토 — 1단계 매칭이면 기존 요율·기존 보험료까지
  // 동일한 우대 사례가 붙는다 (오종국/Kenneth Young 페어가 대표 사례).
  const care = adaptAnnualSummary(bundle, "gaip-114");
  assert.equal(care.care_state, "Care Review");
  const pair = care.matched_pair;
  assert.ok(pair, "care driver should find a reward counterpart");
  assert.equal(pair.match_tier, "identical");
  assert.equal(pair.self.existing_premium_krw, pair.other.existing_premium_krw);
  assert.equal(pair.self.existing_rate_pct, pair.other.existing_rate_pct);
  assert.equal(pair.other.care_state, "None");
  assert.equal(pair.other.reward_state, "Reward");

  // 요율은 '할인'만 존재 — 어느 쪽도 기준 보험료를 넘지 않는다(할증 없음).
  for (const side of [pair.self, pair.other]) {
    assert.ok(side.proposed_premium_krw <= pair.base_premium_krw, `${side.driver_id} premium above base`);
    assert.ok(side.proposed_rate_pct >= 0);
  }

  // 우대 쪽에서 찾아도 반대 판정(케어)이 붙고, 차종(기본보험료)은 항상 동일하다.
  const reward = adaptAnnualSummary(bundle, "gaip-066");
  const rewardPair = reward.matched_pair;
  assert.ok(rewardPair, "reward driver should find a care counterpart");
  assert.equal(rewardPair.other.care_state, "Care Review");
  assert.equal(rewardPair.match_tier, "identical");

  // 보류(근거 부족)·기본 판정은 '반대 판정' 서사가 성립하지 않으므로 표가 없다.
  const hold = adaptAnnualSummary(bundle, "gaip-019");
  assert.equal(hold.reward_state, "Hold");
  assert.equal(hold.matched_pair ?? null, null);

  // 대조 상대가 없는 시나리오는 null — 표를 그리지 않는다 (커버리지 전수 검증).
  let shown = 0;
  for (const option of directory.driver_options) {
    const summary = adaptAnnualSummary(bundle, option.driver_id);
    if (summary.matched_pair) {
      shown += 1;
      const self = summary.matched_pair.self;
      assert.equal(self.driver_id, option.driver_id);
      assert.notEqual(summary.matched_pair.other.driver_id, option.driver_id);
      // 표가 뜨는 쪽은 항상 케어 또는 우대 — 보류·기본 노출 금지 계약.
      assert.ok(self.care_state === "Care Review" || self.reward_state === "Reward", `${self.driver_id} pole violation`);
      // '같은 조건'이 성립하는 범위 안에서만 표시한다 — 거리 15% · 밖 비중 5%p.
      const other = summary.matched_pair.other;
      const distanceGapPct = (Math.abs(other.annual_distance_km - self.annual_distance_km) / Math.max(other.annual_distance_km, self.annual_distance_km, 1)) * 100;
      assert.ok(distanceGapPct <= 15, `${self.driver_id} distance gap ${distanceGapPct.toFixed(1)}%`);
      assert.ok(Math.abs(other.outer_share_pct - self.outer_share_pct) <= 5, `${self.driver_id} outer-share gap`);
    }
  }
  assert.ok(shown >= 8, `matched-pair coverage too low: ${shown}/180`);
});

test("representative pair picks the most-alike care/reward contrast deterministically", () => {
  const pair = adaptRepresentativePair(bundle);
  assert.ok(pair, "expected a representative pair");
  assert.equal(pair.match_tier, "identical");
  assert.equal(pair.self.care_state, "Care Review");
  assert.equal(pair.other.reward_state, "Reward");
  assert.equal(pair.self.existing_premium_krw, pair.other.existing_premium_krw);
  // 현재 데이터 기준 1위 페어 — 데이터 재생성으로 순위가 정당하게 바뀌면 이 두 줄만 갱신.
  assert.equal(pair.self.driver_id, "gaip-106");
  assert.equal(pair.other.driver_id, "gaip-154");
  // 쇼케이스 표에 '완벽한 사람'을 세우지 않는다 — 합성 대조군으로 보인다.
  assert.ok((pair.other.risk_event_count ?? 0) > 0, "우대 쪽 위험행동이 0건이면 안 된다");
  assert.ok((pair.other.in_zone_safe_score ?? 0) < 99.5, "우대 쪽 안 안전점수가 만점이면 안 된다");
  assert.ok((pair.other.out_zone_safe_score ?? 0) < 99.5, "우대 쪽 밖 안전점수가 만점이면 안 된다");
  // 표의 임무 — '갈린 지점이 생활권 밖'임이 숫자로 보여야 한다.
  const outGap = Math.abs((pair.other.out_zone_safe_score ?? 0) - (pair.self.out_zone_safe_score ?? 0));
  const inGap = Math.abs((pair.other.in_zone_safe_score ?? 0) - (pair.self.in_zone_safe_score ?? 0));
  assert.ok(outGap > inGap, `밖 격차(${outGap.toFixed(1)})가 안 격차(${inGap.toFixed(1)})보다 커야 한다`);
});

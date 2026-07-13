import assert from "node:assert/strict";
import test from "node:test";

import {
  hasTraversalSegments,
  isAllowedRequestHost,
  isAllowedRequestOrigin,
  isPrivateArtifactRequest,
  isViteFileSystemRequest,
  sanitizeGaipBundleForUi
} from "../src/gaip_server_policy.ts";

test("every data artifact path is private, including encoded and @fs variants", () => {
  assert.equal(isPrivateArtifactRequest("/data/fixtures/gaip_visit_events.csv"), true);
  assert.equal(isPrivateArtifactRequest("/%2564ata/fixtures/gaip_visit_events.csv?download=1"), true);
  assert.equal(isPrivateArtifactRequest("/@fs/Users/example/project/data/processed/monthly_zone_snapshots.json"), true);
  assert.equal(isPrivateArtifactRequest("/data/fixtures/annual_trip_logs.csv/"), true);
  assert.equal(isPrivateArtifactRequest("/api/gaip/studio"), false);
  assert.equal(hasTraversalSegments("/api/gaip/%2e%2e/gaip/studio"), true);
  assert.equal(isViteFileSystemRequest("/@fs/etc/passwd"), true);
  assert.equal(isViteFileSystemRequest("/%2540fs/etc/passwd"), true);
  assert.equal(isViteFileSystemRequest("/@vite/client"), false);
});

test("request host and origin policy allows only loopback and the approved tunnel domain", () => {
  for (const host of ["localhost:5174", "127.0.0.1:5174", "[::1]:5174", "demo.summit1123.co.kr"])
    assert.equal(isAllowedRequestHost(host), true, host);
  for (const host of [undefined, "evil.com:5174", "summit1123.co.kr.evil.test", "127.0.0.1.evil.test"])
    assert.equal(isAllowedRequestHost(host), false, String(host));
  assert.equal(isAllowedRequestOrigin(undefined), true);
  assert.equal(isAllowedRequestOrigin("http://127.0.0.1:5174"), true);
  assert.equal(isAllowedRequestOrigin("https://demo.summit1123.co.kr"), true);
  assert.equal(isAllowedRequestOrigin("https://evil.test"), false);
  assert.equal(isAllowedRequestOrigin("null"), false);
  assert.equal(isAllowedRequestOrigin("https://demo.summit1123.co.kr/path"), false);
  assert.equal(isAllowedRequestOrigin("https://user@demo.summit1123.co.kr"), false);
});

test("UI DTO is an allowlist and drops coordinates, raw paths, hashes, and unknown fields", () => {
  const source = {
    metadata: {
      schema_version: "test/v1",
      synthetic_data: true,
      simulation_seed: 7,
      source_artifacts: { raw_visit_events: { path: "data/private.csv", sha256: "secret-hash" } }
    },
    periods: { baseline_months: ["2025-11"], evaluation_months: ["2026-01"] },
    cohort: { persona_counts: { safe: 1 }, personas: [], environments: [] },
    algorithm: {
      reference: { name: "DBSCAN" },
      product_zone: {
        core_radius_m: 500,
        buffer_rule: "per_hub_max_core_min_radial_p90_cap",
        buffer_cap_m: 2000,
        outer_policy: "context_only_no_location_penalty"
      },
      offline_comparison_candidates: []
    },
    product_rules: { weights: { mileage_score: 100 }, reward_threshold: 75 },
    trip_visit_summary: { trip_count: 1 },
    drivers: [{
      driver_id: "gaip-001",
      persona_type: "safe",
      center_latitude: 37.5,
      center_longitude: 127,
      start_gps_x: 127,
      point: [127, 37.5],
      wkt: "POINT (127 37.5)",
      unknown_profile_field: "drop-me",
      mobility: {
        zone_status: "available",
        routine_hubs: [{ hub_id: "hub-1", visit_count: 3, coordinates: [127, 37.5] }]
      },
      tariff: { base_premium_krw: 1_000_000 },
      monthly_results: [{
        month: "2026-01",
        period_role: "evaluation",
        zone_available: true,
        data_coverage_pct: 99,
        outer_visit_share: 0.25,
        risky_behavior_rate: 0.04,
        risky_events_per_100_km: 1.5,
        mileage_score: 90,
        in_zone_safe_score: 90,
        out_zone_safe_score: null,
        pattern_stability_score: 95,
        location_penalty: 0,
        latitude: 37.5,
        destination_type: "clinic"
      }]
    }],
    validation_results: { result_status: "passed", checks: [] }
  };

  const sanitized = sanitizeGaipBundleForUi(source) as Record<string, unknown>;
  const serialized = JSON.stringify(sanitized).toLowerCase();
  assert.equal(serialized.includes("gaip-001"), true);
  assert.equal(serialized.includes("out_zone_safe_score"), true);
  assert.equal(serialized.includes("outer_visit_share"), true);
  assert.equal(serialized.includes("risky_events_per_100_km"), true);
  assert.equal(serialized.includes("per_hub_max_core_min_radial_p90_cap"), true);
  assert.equal(serialized.includes("context_only_no_location_penalty"), true);
  for (const forbidden of [
    "latitude", "longitude", "gps_x", "coordinates", "point (", "destination_type",
    "private.csv", "secret-hash", "unknown_profile_field", "drop-me"
  ]) assert.equal(serialized.includes(forbidden), false, forbidden);
  assert.equal(JSON.stringify(source).includes("secret-hash"), true, "projection must not mutate the source");
});

test("non-synthetic bundles are rejected at the server projection boundary", () => {
  assert.throws(
    () => sanitizeGaipBundleForUi({ metadata: { synthetic_data: false }, drivers: [] }),
    /only explicitly synthetic/
  );
  assert.throws(() => sanitizeGaipBundleForUi({}), /only explicitly synthetic/);
});

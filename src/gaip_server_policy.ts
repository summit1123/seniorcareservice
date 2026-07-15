type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function fields(source: unknown, names: readonly string[]): JsonRecord {
  const input = record(source);
  const output: JsonRecord = {};
  for (const name of names) {
    if (input[name] !== undefined) output[name] = input[name];
  }
  return output;
}

function decodePath(value: string): string {
  let decoded = value;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      decoded = next;
    } catch {
      break;
    }
  }
  return decoded.replace(/\\/g, "/").toLowerCase();
}

export function isPrivateArtifactRequest(rawUrl: string): boolean {
  const path = decodePath(rawUrl.split("?", 1)[0]);
  return /(^|\/)data(?:\/|$)/.test(path);
}

/**
 * Vite's /@fs escape hatch is useful for local tooling but must never be part
 * of the dashboard's public HTTP surface. Keep this check separate from the
 * data-directory rule so every filesystem path is rejected, not just GAIP
 * fixture paths.
 */
export function isViteFileSystemRequest(rawUrl: string): boolean {
  const path = decodePath(rawUrl.split("?", 1)[0]);
  return path === "/@fs" || path.startsWith("/@fs/");
}

export function hasTraversalSegments(rawUrl: string): boolean {
  const path = decodePath(rawUrl.split("?", 1)[0]);
  return path.split("/").some((segment) => segment === ".." || segment === ".");
}

function requestHostname(hostHeader: string): string | null {
  try {
    return new URL(`http://${hostHeader}`).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export function isAllowedRequestHost(hostHeader: string | undefined): boolean {
  if (!hostHeader) return false;
  const hostname = requestHostname(hostHeader.trim());
  if (!hostname) return false;
  return hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    (hostname === "::1" || hostname === "[::1]") ||
    hostname === "summit1123.co.kr" ||
    hostname.endsWith(".summit1123.co.kr");
}

export function isAllowedRequestOrigin(originHeader: string | undefined): boolean {
  if (!originHeader) return true;
  try {
    const origin = new URL(originHeader);
    return (origin.protocol === "http:" || origin.protocol === "https:") &&
      !origin.username &&
      !origin.password &&
      origin.pathname === "/" &&
      !origin.search &&
      !origin.hash &&
      isAllowedRequestHost(origin.host);
  } catch {
    return false;
  }
}

function projectHub(value: unknown): JsonRecord {
  return fields(value, [
    "hub_id",
    "display_label",
    "display_label_ko",
    "visit_count",
    "distinct_day_count",
    "radial_p90_m",
    "p90_radius_m",
    "core_radius_m",
    "buffer_radius_m",
    "source_status",
    "zone_source_status"
  ]);
}

function projectMonthlyResult(value: unknown): JsonRecord {
  const base = fields(value, [
    "month",
    "period_role",
    "trip_count",
    "total_distance_km",
    "data_coverage_pct",
    "outer_visit_share",
    "risky_behavior_rate",
    "risky_events_per_100_km",
    "mileage_score",
    "in_zone_trip_count",
    "out_zone_trip_count",
    "in_zone_safe_score",
    "out_zone_safe_score",
    "zone_available",
    "mobility_change_index",
    "risky_behavior_change_index",
    "pattern_stability_score",
    "reward_state",
    "care_state",
    "integrated_score",
    "location_penalty",
    "reason_codes",
    "observed_score_weight_pct",
    "component_availability",
    "source_status"
  ]);
  // Per-destination aggregates: allowlist only the summary fields (no coordinates).
  const raw = record(value).destination_breakdown;
  const destination_breakdown = Array.isArray(raw)
    ? raw.map((entry) => fields(entry, ["visit_label", "trip_count", "distance_km", "risk_event_count", "is_outer"]))
    : [];
  return { ...base, destination_breakdown };
}

function projectMobilityProfile(value: unknown): JsonRecord | null {
  if (value === null || value === undefined) return null;
  const profile = record(value);
  return {
    ...fields(profile, [
      "reasoning_ko",
      "reasoning_en",
      "home_label_ko",
      "home_label_en",
      "change_month",
      "change_trigger_ko",
      "change_trigger_en",
      "generator"
    ]),
    zones: list(profile.zones).map((zone) =>
      fields(zone, [
        "label_ko",
        "label_en",
        "kind",
        "role",
        "bearing_deg",
        "distance_band",
        "visit_share",
        "active_from_month",
        "active_to_month"
      ])
    )
  };
}

function projectDriver(value: unknown): JsonRecord {
  const driver = record(value);
  const mobility = record(driver.mobility);
  const tariff = record(driver.tariff);
  return {
    mobility_profile: projectMobilityProfile(driver.mobility_profile),
    ...fields(driver, [
      "driver_id",
      "driver_name_ko",
      "age",
      "persona_type",
      "persona_display_name_ko",
      "persona_summary_ko",
      "environment_id",
      "environment_display_name_ko",
      "dataset_partition",
      "scenario_variant",
      "scenario_label",
      "mileage_score",
      "in_zone_safe_score",
      "out_zone_safe_score",
      "pattern_stability_score",
      "risky_behavior_rate",
      "data_coverage_pct",
      "mobility_change_index",
      "risky_behavior_change_index",
      "annual_distance_km",
      "total_trips",
      "annual_reward_state",
      "annual_care_state",
      "reward_month_count",
      "care_review_month_count",
      "source_status"
    ]),
    mobility: {
      ...fields(mobility, [
        "zone_status",
        "algorithm",
        "distance_metric",
        "eps_m",
        "min_distinct_days",
        "repeated_hub_count",
        "new_hub_label_ko",
        "basis_visit_count",
        "noise_visit_count",
        "noise_ratio_pct"
      ]),
      routine_hubs: list(mobility.routine_hubs).map(projectHub)
    },
    tariff: fields(tariff, [
      "base_premium_krw",
      "annual_distance_km",
      "korea_mileage_discount_rate_pct",
      "korea_mileage_net_premium_krw",
      "masil_candidate_discount_rate_pct",
      "masil_candidate_net_premium_krw",
      "candidate_reward_bonus_rate_pct",
      "candidate_surcharge_rate_pct",
      "source_status"
    ]),
    monthly_results: list(driver.monthly_results).map(projectMonthlyResult)
  };
}

/**
 * Construct the exact insurer-UI DTO. This is intentionally an allowlist rather
 * than a recursive key denylist so new source fields cannot silently cross the
 * privacy boundary when the simulation schema evolves.
 */
export function sanitizeGaipBundleForUi(payload: unknown): unknown {
  const root = record(payload);
  const metadata = record(root.metadata);
  if (metadata.synthetic_data !== true) {
    throw new Error("GAIP Studio serves only explicitly synthetic simulation bundles.");
  }

  const cohort = record(root.cohort);
  const algorithm = record(root.algorithm);
  const reference = record(algorithm.reference);
  const productZone = record(algorithm.product_zone);
  const validation = record(root.validation_results);

  return {
    metadata: fields(metadata, [
      "schema_version",
      "artifact_timestamp",
      "simulation_seed",
      "project",
      "competition_context",
      "synthetic_data",
      "persona_naming_note",
      "decision_scope",
      "disclaimer"
    ]),
    periods: fields(root.periods, ["baseline_months", "evaluation_months", "total_month_count"]),
    cohort: {
      ...fields(cohort, [
        "driver_count",
        "persona_count",
        "persona_counts",
        "environment_counts",
        "scenario_variant_counts"
      ]),
      personas: list(cohort.personas).map((value) => fields(value, [
        "persona_type",
        "display_name_ko",
        "summary_ko"
      ])),
      environments: list(cohort.environments).map((value) => fields(value, [
        "environment_id",
        "display_name_ko",
        "source_status"
      ]))
    },
    algorithm: {
      reference: fields(reference, [
        "name",
        "purpose",
        "distance_metric",
        "min_distinct_days",
        "environment_eps_m",
        "parameter_status",
        "no_cluster_policy"
      ]),
      product_zone: fields(productZone, [
        "core_radius_m",
        "core_radius_status",
        "buffer_rule",
        "buffer_cap_m",
        "outer_policy",
        "separation_note"
      ]),
      offline_comparison_candidates: list(algorithm.offline_comparison_candidates)
        .map((value) => fields(value, ["name", "role", "purpose", "result_status"]))
    },
    product_rules: fields(root.product_rules, [
      "weights",
      "reward_threshold",
      "reward_required_months",
      "min_data_coverage_pct",
      "care_thresholds",
      "reward_bonus_discount_rate_pct",
      "candidate_discount_cap_pct",
      "core_radius_m",
      "buffer_cap_m",
      "outer_zone_policy",
      "pattern_stability_basis",
      "tariff_status"
    ]),
    trip_visit_summary: fields(root.trip_visit_summary, [
      "trip_count",
      "visit_event_count",
      "one_visit_event_per_trip",
      "source_status"
    ]),
    drivers: list(root.drivers).map(projectDriver),
    validation_results: {
      result_status: validation.result_status,
      checks: list(validation.checks).map((value) => fields(value, ["check_id", "result_status"])),
      claim_boundary: validation.claim_boundary
    }
  };
}

import type {
  AlgorithmCandidate,
  EvidenceItem,
  EvidenceStatus,
  GaipStudioBundle,
  MobilityEnvironment,
  MobilityProfile,
  PersonaType,
  ProductRules,
  RoutineHub,
  StudioDriver,
  StudioMetrics,
  StudioMonthlyResult
} from "./gaip-types";

type JsonRecord = Record<string, unknown>;

const DEFAULT_ENVIRONMENTS: MobilityEnvironment[] = [
  {
    id: "dense_urban",
    label: "고밀도 도심형",
    count: 20,
    description: "짧은 이동과 가까운 반복 거점이 많은 환경"
  },
  {
    id: "suburban_mid_density",
    label: "교외·중소도시형",
    count: 20,
    description: "생활 거점 사이의 거리가 중간 수준인 환경"
  },
  {
    id: "wide_low_density",
    label: "광역 저밀도형",
    count: 20,
    description: "반복 거점이 멀리 떨어지고 이동 반경이 넓은 환경"
  }
];

const DEFAULT_PERSONAS: PersonaType[] = [
  { id: "stable_reward", label: "안정 저주행형", count: 10 },
  { id: "in_zone_risky", label: "생활권 내 위험행동형", count: 10 },
  { id: "mobility_change_safe", label: "이동변화·안전유지형", count: 10 },
  { id: "mobility_risk_cochange", label: "이동·위험행동 동시변화형", count: 10 },
  { id: "multi_zone", label: "복수 생활권형", count: 10 },
  { id: "wide_area_safe", label: "광역 이동·안전형", count: 10 }
];

const DEFAULT_RULES: ProductRules = {
  weights: {
    mileage: 30,
    in_zone_safe: 30,
    out_zone_safe: 20,
    pattern_stability: 20
  },
  reward_score_threshold: 75,
  minimum_data_coverage_pct: 80,
  reward_required_months: 9,
  care_mobility_change_threshold: 25,
  care_risky_behavior_threshold: 20,
  reward_discount_rate_pct: 7,
  reward_bonus_floor_pct: 1,
  care_discount_reduction_pct: 13,
  candidate_discount_cap_pct: 45
};

const DEFAULT_ALGORITHMS: AlgorithmCandidate[] = [
  {
    id: "dbscan",
    label: "DBSCAN",
    role: "reference",
    status: "active",
    summary: "현재 상품 시뮬레이션의 반복 거점 탐지 기준"
  },
  {
    id: "grid_count",
    label: "Grid Count",
    role: "baseline",
    status: "not_run",
    summary: "오프라인 비교용 최소 기준선"
  },
  {
    id: "hdbscan",
    label: "HDBSCAN",
    role: "challenger",
    status: "not_run",
    summary: "서로 다른 밀도 환경을 검증할 오프라인 후보"
  }
];

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown): JsonRecord {
  return isRecord(value) ? value : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function number(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function boolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function evidenceStatus(value: unknown, fallback: EvidenceStatus = "simulated"): EvidenceStatus {
  if (value === "observed" || value === "simulated" || value === "assumed") return value;
  const normalized = text(value).toLowerCase();
  if (normalized.includes("observed")) return "observed";
  if (normalized.includes("assum") || normalized.includes("illustrative") || normalized.includes("candidate")) return "assumed";
  if (normalized.includes("simulat") || normalized.includes("derived")) return "simulated";
  return fallback;
}

function percentage(value: unknown, fallback = 0): number {
  const parsed = number(value, fallback);
  return Math.abs(parsed) <= 1 ? parsed * 100 : parsed;
}

function first(recordValue: JsonRecord, keys: string[]): unknown {
  for (const key of keys) {
    if (recordValue[key] !== undefined && recordValue[key] !== null) return recordValue[key];
  }
  return undefined;
}

function environmentLabel(id: string): string {
  return DEFAULT_ENVIRONMENTS.find((item) => item.id === id)?.label ?? text(id, "환경 미지정");
}

function personaLabel(id: string): string {
  return DEFAULT_PERSONAS.find((item) => item.id === id)?.label ?? text(id, "유형 미지정");
}

function normalizeEnvironments(root: JsonRecord): MobilityEnvironment[] {
  const cohort = record(root.cohort);
  const counts = record(first(cohort, ["environment_counts"]));
  const source = array(first(root, ["environments", "mobility_environments"]))
    .concat(array(first(cohort, ["environments", "mobility_environments"])))
    .filter(isRecord);

  if (!source.length) return DEFAULT_ENVIRONMENTS;

  return source.map((item, index) => {
    const id = text(first(item, ["id", "environment_id", "type"]), DEFAULT_ENVIRONMENTS[index]?.id ?? `environment_${index + 1}`);
    return {
      id,
      label: text(first(item, ["label", "label_ko", "display_name", "display_name_ko"]), environmentLabel(id)),
      count: number(first(item, ["count", "customer_count", "driver_count"]), number(counts[id], 0)),
      description: text(first(item, ["description", "description_ko", "note"])) || undefined
    };
  });
}

function normalizePersonas(root: JsonRecord): PersonaType[] {
  const cohort = record(root.cohort);
  const counts = record(first(cohort, ["persona_counts"]));
  const source = array(first(root, ["personas", "persona_types"]))
    .concat(array(first(cohort, ["personas", "persona_types"])))
    .filter(isRecord);

  if (!source.length) return DEFAULT_PERSONAS;

  return source.map((item, index) => {
    const id = text(first(item, ["id", "persona_id", "persona_type"]), DEFAULT_PERSONAS[index]?.id ?? `persona_${index + 1}`);
    return {
      id,
      label: text(first(item, ["label", "label_ko", "display_name", "display_name_ko", "persona_display_name_ko"]), personaLabel(id)),
      count: number(first(item, ["count", "customer_count", "driver_count"]), number(counts[id], 0)),
      description: text(first(item, ["description", "description_ko", "summary_ko", "note"])) || undefined,
      expected_outcome: text(first(item, ["expected_outcome", "expected_signal"])) || undefined
    };
  });
}

function normalizeMetrics(item: JsonRecord): StudioMetrics {
  const metrics = record(first(item, ["metrics", "features", "annual_metrics", "annual_score"]));
  const combined = { ...item, ...metrics };
  const evaluationMonths = array(item.monthly_results)
    .filter(isRecord)
    .filter((row) => text(row.period_role) !== "baseline");
  const monthlyMobilityChange = evaluationMonths.length
    ? Math.max(...evaluationMonths.map((row) => number(row.mobility_change_index, 0) * 100))
    : 0;
  const monthlyRiskChange = evaluationMonths.length
    ? Math.max(...evaluationMonths.map((row) => number(row.risky_behavior_change_index, 0) * 100))
    : 0;
  const mobilityIndex = first(combined, ["mobility_change_index", "annual_mobility_change_index"]);
  const riskIndex = first(combined, ["risky_behavior_change_index", "annual_risky_behavior_change_index"]);
  const patternChangeRisk = monthlyMobilityChange ||
    (mobilityIndex === undefined
      ? percentage(first(combined, ["pattern_change_risk", "annual_out_zone_pattern_change_risk"]), 0)
      : number(mobilityIndex, 0) * 100);
  const riskyBehaviorChange = monthlyRiskChange ||
    (riskIndex === undefined
      ? percentage(first(combined, ["risky_behavior_rate", "risk_event_rate", "risk_event_rate_pct"]), 0)
      : number(riskIndex, 0) * 100);
  return {
    mileage_score: number(first(combined, ["mileage_score", "annual_mileage_score"]), 0),
    in_zone_safe_score: nullableNumber(first(combined, ["in_zone_safe_score", "in_zone_safe_driving_score", "annual_in_zone_safe_driving_score"])),
    out_zone_safe_score: nullableNumber(first(combined, ["out_zone_safe_score", "out_zone_safe_driving_score", "annual_out_zone_safe_driving_score"])),
    pattern_stability_score: number(first(combined, ["pattern_stability_score", "mobility_stability_score"]), Math.max(0, 100 - patternChangeRisk)),
    mobility_change_index_pct: patternChangeRisk,
    risky_behavior_change_index_pct: riskyBehaviorChange,
    data_coverage_pct: number(first(combined, ["data_coverage_pct", "coverage_pct", "usable_data_pct"]), 100),
    annual_distance_km: number(first(combined, ["annual_distance_km", "annual_total_distance_km", "distance_km"]), 0),
    total_trips: number(first(combined, ["total_trips", "annual_trip_count", "trip_count"]), 0)
  };
}

function normalizeMonthlyResults(item: JsonRecord): StudioMonthlyResult[] {
  return array(first(item, ["monthly_results", "months", "monthly_evidence"]))
    .filter(isRecord)
    .map((month, index) => ({
      // Explicit allowlist: raw coordinates, centroids, routes and place semantics never cross this boundary.
      month: text(first(month, ["month", "service_month", "period"]), `month-${index + 1}`),
      period_role: text(first(month, ["period_role", "role"]), "evaluation"),
      trip_count: number(first(month, ["trip_count"]), 0),
      total_distance_km: number(first(month, ["total_distance_km", "monthly_distance_km"]), 0),
      zone_available: boolean(first(month, ["zone_available", "living_zone_available"]), false),
      data_coverage_pct: number(first(month, ["data_coverage_pct", "coverage_pct", "usable_data_pct"]), 0),
      outer_visit_share_pct: percentage(first(month, ["outer_visit_share", "out_zone_share"]), 0),
      risky_behavior_rate_pct: percentage(first(month, ["risky_behavior_rate", "risk_event_rate"]), 0),
      risky_events_per_100_km: number(first(month, ["risky_events_per_100_km"]), 0),
      mileage_score: number(first(month, ["mileage_score"]), 0),
      in_zone_safe_score: nullableNumber(first(month, ["in_zone_safe_score", "in_zone_safe_driving_score"])),
      out_zone_safe_score: nullableNumber(first(month, ["out_zone_safe_score", "out_zone_safe_driving_score"])),
      in_zone_trip_count: number(first(month, ["in_zone_trip_count"]), 0),
      out_zone_trip_count: number(first(month, ["out_zone_trip_count"]), 0),
      destination_breakdown: array(first(month, ["destination_breakdown"]))
        .filter(isRecord)
        .map((dest) => ({
          visit_label: text(first(dest, ["visit_label"]), "Routine Hub A"),
          trip_count: number(first(dest, ["trip_count"]), 0),
          distance_km: number(first(dest, ["distance_km"]), 0),
          risk_event_count: number(first(dest, ["risk_event_count"]), 0),
          is_outer: boolean(first(dest, ["is_outer"]), false),
          visit_points: array(first(dest, ["visit_points"]))
            .filter((pt): pt is unknown[] => Array.isArray(pt))
            .map((pt) => pt.map((v) => number(v, 0)))
        })),
      risk_event_type_counts: Object.fromEntries(
        Object.entries(
          (first(month, ["risk_event_type_counts"]) as Record<string, unknown> | undefined) ?? {}
        ).map(([key, value]) => [key, number(value, 0)])
      ),
      observed_score_weight_pct: number(first(month, ["observed_score_weight_pct"]), 0),
      pattern_stability_score: number(first(month, ["pattern_stability_score", "mobility_stability_score"]), 0),
      mobility_change_index_pct: number(first(month, ["mobility_change_index"]), 0) * 100,
      risky_behavior_change_index_pct: number(first(month, ["risky_behavior_change_index"]), 0) * 100,
      reward_state: text(first(month, ["reward_state"])) || undefined,
      care_state: text(first(month, ["care_state"])) || undefined,
      integrated_score: nullableNumber(first(month, ["integrated_score"])),
      location_penalty: number(first(month, ["location_penalty"]), 0),
      reason_codes: array(first(month, ["reason_codes"]))
        .map((value) => text(value))
        .filter(Boolean),
      source_status: evidenceStatus(first(month, ["source_status", "status"]), "simulated")
    }));
}

function normalizeHubs(mobility: JsonRecord): RoutineHub[] {
  const source = array(first(mobility, ["routine_hubs", "hubs", "clusters"]))
    .filter(isRecord);

  return source.map((hub, index) => ({
    id: text(first(hub, ["id", "hub_id", "cluster_id", "source_cluster_id"]), `routine_hub_${index + 1}`),
    // Raw coordinates are intentionally never propagated to the insurer UI.
    label: `Routine Hub ${String.fromCharCode(65 + index)}`,
    // Synthetic semantic display label produced by the engine (never a real place).
    display_label_ko: text(first(hub, ["display_label_ko"])) || undefined,
    visit_count: number(first(hub, ["visit_count", "visits", "basis_visit_count"]), 0),
    p90_radius_m: number(first(hub, ["p90_radius_m", "radial_p90_m", "radius_metric_m", "buffer_radius_m"]), 0) || undefined,
    core_radius_m: number(first(hub, ["core_radius_m"]), 0) || undefined,
    buffer_radius_m: number(first(hub, ["buffer_radius_m", "product_buffer_radius_m"]), 0) || undefined,
    confidence: number(first(hub, ["confidence", "stability", "stability_score"]), 0) || undefined,
    source_status: evidenceStatus(first(hub, ["source_status", "status"]), "simulated")
  }));
}

function normalizeMobilityProfile(item: JsonRecord): MobilityProfile | null {
  const raw = first(item, ["mobility_profile"]);
  if (!raw || typeof raw !== "object") return null;
  const profile = record(raw);
  const zones = array(first(profile, ["zones"]))
    .map((entry) => {
      const zone = record(entry);
      return {
        label_ko: text(first(zone, ["label_ko"])) || undefined,
        label_en: text(first(zone, ["label_en"])) || undefined,
        kind: text(first(zone, ["kind"])) || undefined,
        role: text(first(zone, ["role"])) || undefined,
        bearing_deg: number(first(zone, ["bearing_deg"]), 0),
        distance_band: text(first(zone, ["distance_band"])) || undefined,
        visit_share: number(first(zone, ["visit_share"]), 0),
        active_from_month: number(first(zone, ["active_from_month"]), 1),
        active_to_month: number(first(zone, ["active_to_month"]), 14)
      };
    });
  if (!zones.length) return null;
  const changeMonth = first(profile, ["change_month"]);
  return {
    reasoning_ko: text(first(profile, ["reasoning_ko"])) || undefined,
    reasoning_en: text(first(profile, ["reasoning_en"])) || undefined,
    home_label_ko: text(first(profile, ["home_label_ko"])) || undefined,
    home_label_en: text(first(profile, ["home_label_en"])) || undefined,
    change_month: changeMonth === null || changeMonth === undefined ? null : number(changeMonth, 0),
    change_trigger_ko: text(first(profile, ["change_trigger_ko"])) || null,
    change_trigger_en: text(first(profile, ["change_trigger_en"])) || null,
    zones,
    generator: text(first(profile, ["generator"])) || undefined
  };
}

function normalizeDrivers(root: JsonRecord, personas: PersonaType[], environments: MobilityEnvironment[]): StudioDriver[] {
  const cohort = record(root.cohort);
  const source = array(first(root, ["drivers", "driver_summaries", "customers"]))
    .concat(array(first(cohort, ["drivers", "driver_summaries", "customers"])))
    .filter(isRecord);

  return source.map((item, index) => {
    // The safe DTO strips the generation-only designed_type, but keeps the
    // synthetic archetype label. Recover the persona grouping id from that label
    // so the profile view names the behaviour type correctly; the positional
    // fallback is only a last resort for a malformed payload.
    const personaDisplayName = text(first(item, ["persona_display_name_ko", "persona_label"]));
    const personaId = text(
      first(item, ["persona_id", "persona_type"]),
      personas.find((persona) => persona.label === personaDisplayName)?.id
        ?? personas[index % Math.max(personas.length, 1)]?.id
        ?? "unknown"
    );
    const environmentId = text(first(item, ["environment_id", "mobility_environment", "environment"]), environments[index % Math.max(environments.length, 1)]?.id ?? "unknown");
    const mobility = record(first(item, ["mobility", "mobility_evidence", "living_zone"]));
    const tariff = record(first(item, ["tariff", "tariff_comparison", "pricing"]));
    const noiseRatio = first(mobility, ["noise_ratio_pct", "noise_pct"]);
    const id = text(first(item, ["id", "driver_id", "customer_id"]), `synthetic-driver-${String(index + 1).padStart(3, "0")}`);
    const hubs = normalizeHubs(mobility);
    const monthlyResults = normalizeMonthlyResults(item);
    const driverNameKo = text(first(item, ["driver_name_ko"])) || undefined;
    const driverNameEn = text(first(item, ["driver_name_en"])) || undefined;
    const driverAge = nullableNumber(first(item, ["age"])) ?? undefined;

    const monthlyReasonCodes = array(item.monthly_results)
      .filter(isRecord)
      .flatMap((row) => array(row.reason_codes))
      .map((value) => text(value))
      .filter(Boolean);
    const directReasonCodes = array(first(item, ["reason_codes", "annual_reason_codes"]))
      .map((value) => text(value))
      .filter(Boolean);

    return {
      id,
      display_label: text(
        first(item, ["display_label", "display_name", "label"]),
        driverNameKo && driverAge !== undefined
          ? `${driverNameKo} (${driverAge}세)`
          : `합성 운전자 ${String(index + 1).padStart(2, "0")}`
      ),
      driver_name_ko: driverNameKo,
      driver_name_en: driverNameEn,
      // English display label — romanized name for non-Korean locales.
      display_label_en: driverNameEn && driverAge !== undefined ? `${driverNameEn} (${driverAge})` : undefined,
      age: driverAge,
      persona_id: personaId,
      persona_label: text(first(item, ["persona_label", "persona_display_name_ko"]), personas.find((persona) => persona.id === personaId)?.label ?? personaLabel(personaId)),
      environment_id: environmentId,
      environment_label: text(first(item, ["environment_label", "mobility_environment_label", "environment_display_name_ko"]), environments.find((environment) => environment.id === environmentId)?.label ?? environmentLabel(environmentId)),
      scenario_label: text(first(item, ["scenario_label", "scenario_name"])) || undefined,
      dataset_partition: text(first(item, ["dataset_partition"])) || undefined,
      scenario_variant: text(first(item, ["scenario_variant"])) || undefined,
      annual_reward_state: text(first(item, ["annual_reward_state"])) || undefined,
      annual_care_state: text(first(item, ["annual_care_state"])) || undefined,
      reward_month_count: number(first(item, ["reward_month_count"]), 0),
      care_review_month_count: number(first(item, ["care_review_month_count"]), 0),
      metrics: normalizeMetrics(item),
      mobility: {
        zone_status: text(first(mobility, ["zone_status", "status", "basis_status"]), "insufficient_data"),
        zone_status_label: text(first(mobility, ["zone_status_label", "status_label"])) || undefined,
        algorithm: text(first(mobility, ["algorithm", "zone_model_backend", "model"]), "DBSCAN"),
        eps_m: number(first(mobility, ["eps_m", "dbscan_eps_m"]), 0) || undefined,
        min_distinct_days: number(first(mobility, ["min_distinct_days", "min_samples_distinct_days"]), 0) || undefined,
        repeated_hub_count: number(first(mobility, ["repeated_hub_count", "hub_count", "cluster_count"]), hubs.length),
        routine_hubs: hubs,
        new_hub_label_ko: text(first(mobility, ["new_hub_label_ko"])) || undefined,
        basis_visit_count: number(first(mobility, ["basis_visit_count", "visit_count"]), 0) || undefined,
        noise_ratio_pct: noiseRatio === undefined ? undefined : number(noiseRatio, 0),
        note: text(first(mobility, ["note", "explanation"])) || undefined
      },
      mobility_profile: normalizeMobilityProfile(item),
      monthly_results: monthlyResults,
      tariff: Object.keys(tariff).length
        ? {
            base_premium_krw: number(first(tariff, ["base_premium_krw", "annual_base_premium_krw"]), 0) || undefined,
            korea_mileage_discount_rate_pct: number(first(tariff, ["korea_mileage_discount_rate_pct", "existing_discount_rate_pct"]), 0),
            korea_mileage_net_premium_krw: number(first(tariff, ["korea_mileage_net_premium_krw", "existing_net_premium_krw"]), 0) || undefined,
            masil_candidate_discount_rate_pct: number(first(tariff, ["masil_candidate_discount_rate_pct", "proposed_discount_rate_pct"]), 0),
            masil_candidate_net_premium_krw: number(first(tariff, ["masil_candidate_net_premium_krw", "proposed_net_premium_krw"]), 0) || undefined,
            status: evidenceStatus(first(tariff, ["status", "source_status"]), "simulated")
          }
        : undefined,
      reason_codes: [...new Set(directReasonCodes.length ? directReasonCodes : monthlyReasonCodes)]
    };
  });
}

function normalizeRules(root: JsonRecord): ProductRules {
  const product = record(first(root, ["product_rules", "rules", "product"]));
  const weights = record(first(product, ["weights", "score_weights"]));
  return {
    weights: {
      mileage: number(first(weights, ["mileage", "mileage_score"]), DEFAULT_RULES.weights.mileage),
      in_zone_safe: number(first(weights, ["in_zone_safe", "in_zone_safe_score", "in_zone_safe_driving"]), DEFAULT_RULES.weights.in_zone_safe),
      out_zone_safe: number(first(weights, ["out_zone_safe", "out_zone_safe_score", "out_zone_safe_driving"]), DEFAULT_RULES.weights.out_zone_safe),
      pattern_stability: number(first(weights, ["pattern_stability", "pattern_stability_score", "pattern_change"]), DEFAULT_RULES.weights.pattern_stability)
    },
    reward_score_threshold: number(first(product, ["reward_score_threshold", "reward_threshold"]), DEFAULT_RULES.reward_score_threshold),
    minimum_data_coverage_pct: number(first(product, ["minimum_data_coverage_pct", "minimum_coverage_pct", "min_data_coverage_pct"]), DEFAULT_RULES.minimum_data_coverage_pct),
    reward_required_months: number(first(product, ["reward_required_months", "annual_reward_required_months"]), DEFAULT_RULES.reward_required_months),
    care_mobility_change_threshold: percentage(
      first(record(first(product, ["care_thresholds"])), ["mobility_change_index"]),
      number(first(product, ["care_mobility_change_threshold", "care_pattern_change_threshold", "pattern_change_threshold"]), DEFAULT_RULES.care_mobility_change_threshold)
    ),
    care_risky_behavior_threshold: percentage(
      first(record(first(product, ["care_thresholds"])), ["risky_behavior_change_index"]),
      number(first(product, ["care_risky_behavior_threshold", "risky_behavior_threshold"]), DEFAULT_RULES.care_risky_behavior_threshold)
    ),
    reward_discount_rate_pct: number(first(product, ["reward_discount_rate_pct", "reward_bonus_discount_rate_pct"]), DEFAULT_RULES.reward_discount_rate_pct),
    reward_bonus_floor_pct: number(first(product, ["reward_bonus_floor_pct"]), DEFAULT_RULES.reward_bonus_floor_pct ?? 1),
    care_discount_reduction_pct: number(first(product, ["care_discount_reduction_pct"]), DEFAULT_RULES.care_discount_reduction_pct ?? 0),
    candidate_discount_cap_pct: number(first(product, ["candidate_discount_cap_pct", "discount_cap_pct"]), DEFAULT_RULES.candidate_discount_cap_pct)
  };
}

function normalizeAlgorithms(root: JsonRecord): AlgorithmCandidate[] {
  const explicitSource = array(first(root, ["algorithms", "algorithm_candidates", "algorithm_comparison"]))
    .filter(isRecord);
  let normalized: AlgorithmCandidate[];

  if (explicitSource.length) {
    normalized = explicitSource.map((item, index) => ({
      id: text(first(item, ["id", "algorithm_id"]), `algorithm_${index + 1}`),
      label: text(first(item, ["label", "name"]), `Algorithm ${index + 1}`),
      role: text(first(item, ["role", "comparison_role"]), "challenger"),
      status: text(first(item, ["status", "run_status", "result_status"]), "not_run"),
      summary: text(first(item, ["summary", "description", "note", "purpose"])) || undefined
    }));
  } else {
    const contract = record(root.algorithm);
    const reference = record(contract.reference);
    const offline = array(first(contract, ["offline_comparison_candidates", "candidates"])).filter(isRecord);
    if (!Object.keys(reference).length) return DEFAULT_ALGORITHMS;

    const referenceName = text(first(reference, ["name", "label"]), "Reference algorithm");
    normalized = [
      {
        id: text(first(reference, ["id", "algorithm_id"]), referenceName.toLowerCase().replace(/[^a-z0-9]+/g, "_")),
        label: referenceName,
        role: text(first(reference, ["role", "comparison_role"]), "reference"),
        status: text(first(reference, ["status", "run_status", "result_status"]), "active"),
        summary: text(first(reference, ["summary", "description", "note", "purpose"])) || undefined
      },
      ...offline.map((item, index) => {
        const name = text(first(item, ["name", "label"]), `Algorithm ${index + 2}`);
        return {
          id: text(first(item, ["id", "algorithm_id"]), name.toLowerCase().replace(/[^a-z0-9]+/g, "_")),
          label: name,
          role: text(first(item, ["role", "comparison_role"]), name.toLowerCase().includes("grid") ? "baseline" : "challenger"),
          status: text(first(item, ["status", "run_status", "result_status"]), "not_run"),
          summary: text(first(item, ["summary", "description", "note", "purpose"])) || undefined
        } satisfies AlgorithmCandidate;
      })
    ];
  }

  const active = normalized.filter((algorithm) => algorithm.status === "active");
  if (active.length !== 1) {
    throw new Error(`알고리즘 계약 오류: active 모델은 정확히 1개여야 하지만 ${active.length}개입니다.`);
  }
  const activeId = `${active[0].id} ${active[0].label}`.toLowerCase();
  if (!activeId.includes("dbscan") || activeId.includes("hdbscan") || active[0].role !== "reference") {
    throw new Error("알고리즘 계약 오류: 현재 실행 기준은 reference 역할의 DBSCAN만 허용됩니다.");
  }
  const executedOffline = normalized.filter((algorithm) => algorithm !== active[0] && algorithm.status !== "not_run");
  if (executedOffline.length) {
    throw new Error(`알고리즘 계약 오류: 오프라인 비교 후보는 not_run이어야 합니다: ${executedOffline.map((item) => item.label).join(", ")}`);
  }
  return normalized;
}

function normalizeEvidence(root: JsonRecord): EvidenceItem[] {
  const source = array(first(root, ["evidence_register", "evidence", "source_register"]))
    .filter(isRecord);

  if (!source.length) {
    const validation = record(root.validation_results);
    const checks = array(validation.checks).filter(isRecord);
    const passedChecks = checks.filter((check) => text(check.result_status) === "passed").length;
    return [
      { id: "cohort", status: "simulated", label: "코호트·주행로그", value: "합성 시뮬레이션" },
      {
        id: "invariants",
        status: "simulated",
        label: "예외·불변조건 검증",
        value: checks.length ? `${passedChecks}/${checks.length} 통과` : "검증 결과 미등록",
        note: "Outer 중립, Care AND Gate, 생활권 미생성 시 판단 보류를 포함합니다."
      },
      { id: "rules", status: "assumed", label: "상품 가중치·임계치", value: "후보 설정" },
      { id: "tariff", status: "assumed", label: "Masil 할인 후보", value: "확정 요율 아님" }
    ];
  }

  return source.map((item, index) => ({
    id: text(first(item, ["id", "evidence_id"]), `evidence_${index + 1}`),
    status: evidenceStatus(first(item, ["status", "source_status"])),
    label: text(first(item, ["label", "name"]), `근거 ${index + 1}`),
    value: text(first(item, ["value", "summary"]), "—"),
    note: text(first(item, ["note", "limitation"])) || undefined
  }));
}

export function normalizeGaipStudioBundle(payload: unknown): GaipStudioBundle {
  if (!isRecord(payload)) {
    throw new Error("GAIP Studio 응답 형식이 올바르지 않습니다.");
  }
  const root = payload;
  const metadata = record(first(root, ["metadata", "meta"]));
  const summary = record(root.summary);
  const cohort = record(root.cohort);
  const periods = record(root.periods);
  const tripSummary = record(first(root, ["trip_visit_summary", "trip_summary"]));
  const environmentDefinitions = normalizeEnvironments(root);
  const personaDefinitions = normalizePersonas(root);
  const drivers = normalizeDrivers(root, personaDefinitions, environmentDefinitions);
  if (!drivers.length) {
    throw new Error("GAIP Studio 응답에 합성 운전자 데이터가 없습니다.");
  }
  const missingMonthlyEvidence = drivers.find(
    (driver) => !driver.monthly_results.some((month) => month.period_role === "evaluation")
  );
  if (missingMonthlyEvidence) {
    throw new Error(`${missingMonthlyEvidence.id}의 월별 평가 근거가 없어 상품 결과를 계산할 수 없습니다.`);
  }
  const environments = environmentDefinitions.map((environment) => ({
    ...environment,
    count: drivers.filter((driver) => driver.environment_id === environment.id).length
  }));
  const personas = personaDefinitions.map((persona) => ({
    ...persona,
    count: drivers.filter((driver) => driver.persona_id === persona.id).length
  }));
  const tripCount = drivers.reduce((sum, driver) => sum + driver.metrics.total_trips, 0);

  return {
    metadata: {
      title: text(first(metadata, ["title", "name"]), "FourSure · MASIL / GAIP 2026 Product Simulation Studio"),
      bundle_version: text(first(metadata, ["bundle_version", "version", "schema_version"])) || undefined,
      generated_at: text(first(metadata, ["generated_at", "created_at", "artifact_timestamp"])) || undefined,
      simulation_seed: first(metadata, ["simulation_seed", "seed"]) as number | string | undefined,
      customer_count: drivers.length,
      trip_count: number(first(metadata, ["trip_count", "total_trip_count"]), number(first(tripSummary, ["trip_count", "total_trip_count"]), number(first(summary, ["trip_count", "total_trip_count"]), tripCount))),
      baseline_months: number(first(metadata, ["baseline_months", "baseline_period_months"]), array(first(periods, ["baseline_months"])).length || 2),
      evaluation_months: number(first(metadata, ["evaluation_months", "evaluation_period_months"]), array(first(periods, ["evaluation_months"])).length || 12),
      synthetic: boolean(first(metadata, ["synthetic", "is_synthetic", "synthetic_data"]), true)
    },
    environments,
    personas,
    drivers,
    product_rules: normalizeRules(root),
    algorithms: normalizeAlgorithms(root),
    evidence_register: normalizeEvidence(root)
  };
}

async function getJson(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    signal,
    headers: { Accept: "application/json" }
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = record(await response.json());
      message = text(payload.message, message);
    } catch {
      // Preserve the HTTP status when a non-JSON error is returned.
    }
    throw new Error(message);
  }

  return response.json();
}

export const gaipStudioApi = {
  async getStudio(signal?: AbortSignal): Promise<GaipStudioBundle> {
    return normalizeGaipStudioBundle(await getJson("/api/gaip/studio", signal));
  }
};

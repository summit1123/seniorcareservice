export type EvidenceStatus = "observed" | "simulated" | "assumed";

export type MobilityEnvironmentId =
  | "dense_urban"
  | "suburban_mid_density"
  | "wide_low_density"
  | string;

export type ZoneStatus = "ready" | "insufficient_data" | "no_zone" | "hold" | string;

export type ReviewDecision = "pending" | "approved" | "held";

export interface SourceBadge {
  status: EvidenceStatus;
  label?: string;
  note?: string;
}

export interface StudioMetadata {
  title?: string;
  bundle_version?: string;
  generated_at?: string;
  simulation_seed?: number | string;
  customer_count?: number;
  trip_count?: number;
  baseline_months?: number;
  evaluation_months?: number;
  synthetic?: boolean;
}

export interface MobilityEnvironment {
  id: MobilityEnvironmentId;
  label: string;
  count: number;
  description?: string;
}

export interface PersonaType {
  id: string;
  label: string;
  count: number;
  description?: string;
  expected_outcome?: string;
}

export interface StudioMetrics {
  mileage_score: number;
  in_zone_safe_score: number | null;
  out_zone_safe_score: number | null;
  pattern_stability_score: number;
  mobility_change_index_pct: number;
  risky_behavior_change_index_pct: number;
  data_coverage_pct: number;
  annual_distance_km: number;
  total_trips: number;
}

export interface DestinationBreakdown {
  visit_label: string;
  trip_count: number;
  distance_km: number;
  risk_event_count: number;
  is_outer: boolean;
  /** 자택 기준 상대변위 실측 방문점 [dx_east_m, dy_north_m, risk_flag] (10m 반올림, 월 24점 상한). */
  visit_points?: number[][];
}

export interface StudioMonthlyResult {
  month: string;
  period_role: "baseline" | "evaluation" | string;
  trip_count: number;
  total_distance_km: number;
  zone_available: boolean;
  data_coverage_pct: number;
  outer_visit_share_pct: number;
  risky_behavior_rate_pct: number;
  risky_events_per_100_km: number;
  mileage_score: number;
  in_zone_safe_score: number | null;
  out_zone_safe_score: number | null;
  in_zone_trip_count?: number;
  out_zone_trip_count?: number;
  /** Per-destination (visit_label) aggregates from the real events, so risk/km land on the destination that produced them. */
  destination_breakdown?: DestinationBreakdown[];
  observed_score_weight_pct?: number;
  pattern_stability_score: number;
  mobility_change_index_pct: number;
  risky_behavior_change_index_pct: number;
  reward_state?: string;
  care_state?: string;
  integrated_score?: number | null;
  location_penalty?: number;
  reason_codes: string[];
  source_status?: EvidenceStatus;
}

export interface RoutineHub {
  id: string;
  label: string;
  /** Synthetic semantic label for UI display (e.g. 마트, 경로당); never a real place. */
  display_label_ko?: string;
  visit_count: number;
  p90_radius_m?: number;
  core_radius_m?: number;
  buffer_radius_m?: number;
  confidence?: number;
  source_status?: EvidenceStatus;
}

export interface DriverMobilityEvidence {
  zone_status: ZoneStatus;
  zone_status_label?: string;
  algorithm: string;
  eps_m?: number;
  min_distinct_days?: number;
  repeated_hub_count: number;
  routine_hubs: RoutineHub[];
  /** Synthetic semantic label for New-Hub/outer destinations (UI display only). */
  new_hub_label_ko?: string;
  basis_visit_count?: number;
  noise_ratio_pct?: number;
  note?: string;
}

export interface MobilityProfileZone {
  label_ko?: string;
  label_en?: string;
  kind?: string;
  role?: string;
  bearing_deg?: number;
  distance_band?: string;
  visit_share?: number;
  active_from_month?: number;
  active_to_month?: number;
}

/** Agent-generated mobility profile (Option C): the LLM's reasoning + named living
 * zones. Descriptors only (no coordinates); the deterministic engine expands and
 * scores it blind. */
export interface MobilityProfile {
  reasoning_ko?: string;
  reasoning_en?: string;
  home_label_ko?: string;
  home_label_en?: string;
  change_month?: number | null;
  change_trigger_ko?: string | null;
  change_trigger_en?: string | null;
  zones: MobilityProfileZone[];
  generator?: string;
}

export interface TariffComparison {
  base_premium_krw?: number;
  korea_mileage_discount_rate_pct?: number;
  korea_mileage_net_premium_krw?: number;
  masil_candidate_discount_rate_pct?: number;
  masil_candidate_net_premium_krw?: number;
  status?: EvidenceStatus;
}

export interface StudioDriver {
  id: string;
  display_label: string;
  /** Romanized display label ("Yun Soon-ye (68)") for non-Korean locales. */
  display_label_en?: string;
  /** Synthetic Korean person name (실존 인물 아님). */
  driver_name_ko?: string;
  driver_name_en?: string;
  /** Synthetic age (66-84). */
  age?: number;
  persona_id: string;
  persona_label: string;
  environment_id: MobilityEnvironmentId;
  environment_label: string;
  scenario_label?: string;
  dataset_partition?: string;
  scenario_variant?: string;
  annual_reward_state?: string;
  annual_care_state?: string;
  reward_month_count?: number;
  care_review_month_count?: number;
  metrics: StudioMetrics;
  mobility: DriverMobilityEvidence;
  mobility_profile?: MobilityProfile | null;
  monthly_results: StudioMonthlyResult[];
  tariff?: TariffComparison;
  reason_codes?: string[];
}

export interface ProductWeights {
  mileage: number;
  in_zone_safe: number;
  out_zone_safe: number;
  pattern_stability: number;
}

export type ProductComponentScores = {
  [Key in keyof ProductWeights]: number | null;
};

export interface ProductRules {
  weights: ProductWeights;
  reward_score_threshold: number;
  minimum_data_coverage_pct: number;
  reward_required_months: number;
  care_mobility_change_threshold: number;
  care_risky_behavior_threshold: number;
  reward_discount_rate_pct?: number;
  reward_bonus_floor_pct?: number;
  care_discount_reduction_pct?: number;
  candidate_discount_cap_pct?: number;
}

export interface AlgorithmCandidate {
  id: string;
  label: string;
  role: "reference" | "challenger" | "baseline" | string;
  status: "active" | "not_run" | "complete" | string;
  summary?: string;
}

export interface EvidenceItem {
  id: string;
  status: EvidenceStatus;
  label: string;
  value: string;
  note?: string;
}

export interface GaipStudioBundle {
  metadata: StudioMetadata;
  environments: MobilityEnvironment[];
  personas: PersonaType[];
  drivers: StudioDriver[];
  product_rules: ProductRules;
  algorithms: AlgorithmCandidate[];
  evidence_register: EvidenceItem[];
}

export interface SandboxResult {
  score: number;
  outcome: "Reward" | "Neutral" | "Care Review" | "Reward + Care Review" | "Hold";
  outcome_ko: "Reward" | "Neutral" | "Care Review" | "Reward + Care Review" | "판단 보류";
  reward_state: "Reward" | "Neutral" | "Hold";
  care_state: "Care Review" | "None" | "Hold";
  reward_eligible: boolean;
  care_review_eligible: boolean;
  care_gate_met: boolean;
  hold_reason?: string;
  normalized_weights: ProductWeights;
  component_scores: ProductComponentScores;
  partial_component_month_count: number;
  minimum_observed_score_weight_pct: number;
  reward_month_count: number;
  care_review_month_count: number;
  eligible_month_count: number;
  evaluation_month_count: number;
  reward_required_months: number;
  reason_codes: string[];
  proposed_discount_rate_pct: number;
  proposed_net_premium_krw?: number;
}

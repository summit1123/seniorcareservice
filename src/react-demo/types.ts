import type { AlgorithmCandidate, MobilityProfile, ProductRules } from "./gaip-types";

export type DecisionSignal = "우대" | "기본" | "예방 케어" | string;

export type Interpretation =
  | "existing_living_zone"
  | "candidate_living_zone"
  | "out_zone_safe_driving"
  | "out_zone_pattern_change_risk"
  | string;

export interface ProductFrame {
  product_name_ko: string;
  existing_formula_ko: string;
  proposed_formula_ko: string;
  llm_boundary_ko: string;
  competition_context_ko?: string;
  data_scope_ko?: string;
  algorithm_role_ko?: string;
}

export interface DemoSummary {
  customer_count: number;
  same_input_contract_all_rows: boolean;
  baseline_60_day_excluded_all_rows: boolean;
  total_base_premium_krw: number;
  avg_base_premium_krw: number;
  existing_total_discount_krw: number;
  proposed_total_discount_krw: number;
  discount_amount_delta_krw: number;
  preventive_care_count: number;
  decision_counts: Record<string, number>;
  existing_tier_count: number;
  avg_existing_discount_rate_pct: number;
  avg_proposed_discount_rate_pct: number;
  avg_annual_score: number;
}

export interface PersonaSummary {
  persona_type: string;
  persona_display_name_ko: string;
  customer_count: number;
  avg_annual_distance_km: number;
  avg_annual_score: number;
  decision_counts: Record<string, number>;
  preventive_care_count: number;
  avg_existing_discount_rate_pct: number;
  avg_proposed_discount_rate_pct: number;
}

export interface ExistingTierSegment {
  existing_matched_tier_label: string;
  customer_count: number;
  customer_ids: string[];
  persona_counts: Record<string, number>;
  proposed_decision_signal_counts: Record<string, number>;
  proposed_discount_rate_range_pct: [number, number];
}

export interface DriverOption {
  customer_id: string;
  driver_id: string;
  label: string;
  /** Romanized label for non-Korean locales. */
  label_en?: string;
  persona_type: string;
  annual_decision_signal: DecisionSignal;
  existing_matched_tier_label: string;
  environment_id?: string;
  environment_display_name_ko?: string;
  reward_state?: string;
  care_state?: string;
  zone_status?: string;
  data_coverage_pct?: number;
}

export interface PersonaDirectoryResponse {
  product_frame: ProductFrame;
  summary: DemoSummary;
  persona_summaries: PersonaSummary[];
  existing_tier_segments: ExistingTierSegment[];
  driver_options: DriverOption[];
  source_artifacts: Record<string, string>;
  default_customer_id: string;
  product_rules?: ProductRules;
  algorithm_candidates?: AlgorithmCandidate[];
  source_status?: string;
}

export interface Destination {
  label_ko: string;
  living_zone_role: "core" | "buffer" | "outer" | string;
  longitude: number;
  latitude: number;
  coordinate_space?: "schematic_normalized" | string;
}

export interface LivingPattern {
  home_anchor: string;
  weekly_outing_frequency_ko: string;
  primary_destinations: string[];
  outer_trip_tendency: string;
  risk_behavior_tendency: string;
}

export interface CareContext {
  product_role: string;
  message_focus: string;
  false_positive_or_negative_risk: string;
}

export interface AnnualScore {
  annual_total_distance_km: number;
  annual_trip_count: number;
  annual_mileage_score: number;
  annual_in_zone_safe_driving_score: number | null;
  annual_out_zone_safe_driving_score: number | null;
  annual_senior_safe_mileage_score: number;
  annual_score_tier: string;
  annual_decision_signal: DecisionSignal;
  annual_out_zone_pattern_change_risk: number;
  dominant_annual_interpretation: Interpretation;
  annual_reason_codes: string[];
}

export interface AbComparison {
  annual_total_distance_km: number;
  annual_distance_scope: string;
  baseline_60_day_excluded_from_discount: boolean;
  base_premium_krw: number;
  existing_matched_tier_label: string;
  existing_discount_rate_pct: number;
  existing_discount_amount_krw: number;
  existing_net_premium_krw: number;
  proposed_discount_rule_id: string;
  proposed_discount_rate_pct: number;
  proposed_discount_amount_krw: number;
  proposed_net_premium_krw: number;
  discount_rate_delta_pct: number;
  discount_amount_delta_krw: number;
  premium_delta_krw: number;
  annual_senior_safe_mileage_score: number;
  annual_score_tier: string;
  annual_decision_signal: DecisionSignal;
  annual_out_zone_pattern_change_risk: number;
  proposed_pricing_action: string;
  preventive_care_required: boolean;
  proposed_rationale_code: string;
  annual_reason_codes: string[];
  same_input_contract_id: string;
}

export interface MonthlyEvidence {
  risk_event_type_counts?: Record<string, number>;
  service_month: string;
  month: number;
  basis_status: string;
  basis_trip_count: number;
  scored_trip_count: number;
  monthly_total_distance_km: number;
  mileage_score: number;
  in_zone_safe_driving_score: number | null;
  out_zone_safe_driving_score: number | null;
  out_zone_pattern_change_risk: number;
  monthly_integrated_evidence_score: number;
  dominant_interpretation: Interpretation;
  reason_codes: string[];
  scenario_phase: string;
  period_role?: "baseline" | "evaluation" | string;
  data_coverage_pct?: number;
  mobility_change_index_pct?: number;
  risky_behavior_change_index_pct?: number;
  pattern_stability_score?: number;
  reward_state?: string;
  care_state?: string;
}

/** '같은 조건, 다른 행동' 대조 표의 한쪽(본인 또는 대조 상대). */
export interface MatchedPairSide {
  driver_id: string;
  display_label: string;
  display_label_en: string;
  persona_label: string;
  annual_distance_km: number;
  outer_share_pct: number;
  /** 평가기간 위험행동 실측 건수. 유형별 집계가 없는 시나리오는 null. */
  risk_event_count: number | null;
  /** 연간 안/밖 안전점수 — 갈린 지점이 '생활권 밖'임을 표에서 보이게 한다. */
  in_zone_safe_score: number | null;
  out_zone_safe_score: number | null;
  /** 연간 4개 지표 가중합(관측된 가중치로 정규화) — 보너스 계산의 입력값. */
  integrated_score: number;
  care_month_count: number;
  reward_state: string;
  care_state: string;
  existing_rate_pct: number;
  existing_premium_krw: number;
  proposed_rate_pct: number;
  proposed_premium_krw: number;
}

export interface MatchedPairComparison {
  /** "identical" = 기본보험료·기존 요율 모두 동일(기존 보험료 원 단위 동일), "same_vehicle" = 기본보험료만 동일. */
  match_tier: "identical" | "same_vehicle";
  base_premium_krw: number;
  self: MatchedPairSide;
  other: MatchedPairSide;
}

export interface DriverAnnualSummary {
  customer_id: string;
  driver_id: string;
  persona_type: string;
  persona_display_name_ko: string;
  vehicle_class: string;
  base_premium_krw: number;
  living_pattern: LivingPattern;
  care_context: CareContext;
  living_destinations: Record<string, Destination>;
  annual_score: AnnualScore;
  ab_comparison: AbComparison;
  environment_id?: string;
  environment_display_name_ko?: string;
  reward_state?: string;
  care_state?: string;
  zone_status?: string;
  evidence_status?: string;
  model_version?: string;
  mobility_profile?: MobilityProfile | null;
  /** 같은 조건(차종/기존 요율)에서 반대 판정을 받은 실제 시나리오와의 대조. 상대가 없으면 null. */
  matched_pair?: MatchedPairComparison | null;
}

export interface MonthlySnapshotResponse {
  customer_id: string;
  driver_id: string;
  monthly_evidence: MonthlyEvidence[];
}

export interface ZoneCluster {
  cluster_id: number;
  center_longitude: number;
  center_latitude: number;
  visit_count: number;
  p90_radius_m: number;
  radius_metric_m: number;
  boundary_area_km2: number;
  display_x?: number;
  display_y?: number;
  core_radius_m?: number;
  label_ko?: string;
}

export interface ZoneTripInterpretation {
  trip_id: string;
  destination_type: string;
  destination_label_ko: string;
  zone_label_from_dbscan_p90: string;
  interpretation: Interpretation;
  distance_km: number;
  risk_event_count: number;
  night_drive_flag: number;
  route_repeat_flag: number;
  new_destination_flag: number;
}

export interface ZoneSnapshot {
  customer_id: string;
  driver_id: string;
  persona_type: string;
  service_month: string;
  month: number;
  basis_window: {
    start_date: string;
    end_date: string;
    days: number;
    basis_trip_count: number;
    scored_trip_count: number;
    basis_status: string;
  };
  leakage_guard: {
    current_month_excluded_from_zone_fit: boolean;
    current_month_trip_count_in_basis: number;
  };
  living_zone: {
    zone_model_backend: string;
    cluster_count: number;
    clusters: ZoneCluster[];
    buffer: {
      departure_p90_threshold_m: number;
      departure_threshold_percentile: number;
    };
  };
  monthly_evidence: {
    monthly_distance_km: number;
    trip_count: number;
    in_zone_distance_ratio: number;
    out_zone_distance_ratio: number;
    interpretation_counts: Record<string, number>;
    reason_codes: string[];
  };
  scores: {
    mileage_score: number;
    in_zone_safe_driving_score: number | null;
    out_zone_safe_driving_score: number | null;
    out_zone_pattern_change_risk: number;
    monthly_integrated_evidence_score: number;
    score_role: string;
  };
  trip_interpretations: ZoneTripInterpretation[];
  /** 실측 방문점: selected=[dx,dy,risk,outer][], baseline=[dx,dy][] (자택 기준 m). */
  visit_scatter?: { selected: number[][]; baseline: number[][] };
  source_event?: {
    event_label_ko: string;
    living_zone_interpretation_ko: string;
  };
}

export interface ZoneMapResponse {
  analysis_method: Record<string, string>;
  source_artifacts: Record<string, string>;
  snapshot: ZoneSnapshot;
}

# Senior Safe Mileage Simulation Summary

- Schema: `senior-report-agent/v1`
- Report mode: `deterministic_template`
- Selected policy: `policy_30_30_20_20_p20_a75`
- Approval gate passed: `True`
- Critic verdict: `pass`
- Risk-change capture: `5/5`
- Non-target false positives: `1`
- Total misclassifications: `1`

## Portfolio Report

제안 Senior Safe Mileage Score는 합성 30명 fixture에서 저주행 위험변화 대상 5명 중 5명을 포착했고, 비대상 오탐은 1명입니다. Critic Agent verdict는 pass입니다.

## Critic Follow-ups
- Review misclassified `in_zone_risky_low_mileage` customers before using the candidate in demos.

## Customer Reports

### cust_001 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `73.06`, senior `90.14`, risk change `5.28`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 90.1와 낮은 위험변화 점수 5.3를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_002 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `75.5`, senior `91.45`, risk change `2.34`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 91.5와 낮은 위험변화 점수 2.3를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_003 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `64.88`, senior `87.15`, risk change `3.43`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 87.2와 낮은 위험변화 점수 3.4를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_004 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `77.85`, senior `90.29`, risk change `11.26`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 90.3와 낮은 위험변화 점수 11.3를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_005 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `70.55`, senior `88.51`, risk change `6.69`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 88.5와 낮은 위험변화 점수 6.7를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_006 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `45.66`, senior `80.03`, risk change `5.49`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 80.0와 낮은 위험변화 점수 5.5를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_007 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `52.38`, senior `81.53`, risk change `6.39`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 81.5와 낮은 위험변화 점수 6.4를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_008 / stable_outer_safe

- Decision: `기본`
- Scores: baseline `31.84`, senior `74.02`, risk change `9.38`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 74.0와 위험변화 점수 9.4를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_009 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `37.1`, senior `76.08`, risk change `9.44`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 76.1와 낮은 위험변화 점수 9.4를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_010 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `54.56`, senior `80.05`, risk change `17.51`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 80.0와 낮은 위험변화 점수 17.5를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_011 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `66.33`, senior `51.71`, risk change `97.8`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 최근 생활권 밖 위험변화 점수 97.8와 통합 점수 51.7를 기준으로 예방 케어 검토가 필요한 고객입니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_012 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `63.7`, senior `48.73`, risk change `100.0`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 최근 생활권 밖 위험변화 점수 100.0와 통합 점수 48.7를 기준으로 예방 케어 검토가 필요한 고객입니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_013 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `68.41`, senior `46.48`, risk change `100.0`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 최근 생활권 밖 위험변화 점수 100.0와 통합 점수 46.5를 기준으로 예방 케어 검토가 필요한 고객입니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_014 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `64.42`, senior `54.51`, risk change `89.32`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 최근 생활권 밖 위험변화 점수 89.3와 통합 점수 54.5를 기준으로 예방 케어 검토가 필요한 고객입니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_015 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `57.04`, senior `42.23`, risk change `99.09`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 최근 생활권 밖 위험변화 점수 99.1와 통합 점수 42.2를 기준으로 예방 케어 검토가 필요한 고객입니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_016 / in_zone_risky_low_mileage

- Decision: `기본`
- Scores: baseline `74.04`, senior `69.08`, risk change `25.54`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 69.1와 위험변화 점수 25.5를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_017 / in_zone_risky_low_mileage

- Decision: `기본`
- Scores: baseline `64.46`, senior `56.99`, risk change `27.34`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 57.0와 위험변화 점수 27.3를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_018 / in_zone_risky_low_mileage

- Decision: `기본`
- Scores: baseline `64.04`, senior `65.42`, risk change `28.84`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 65.4와 위험변화 점수 28.8를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_019 / in_zone_risky_low_mileage

- Decision: `예방 케어`
- Scores: baseline `68.77`, senior `63.0`, risk change `41.14`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, BORDERLINE_PATTERN_CHANGE_MONITORED, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `fail` score `0.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 0.0점으로 기준 80.0점 대비 fail이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=True, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 최근 생활권 밖 위험변화 점수 41.1와 통합 점수 63.0를 기준으로 예방 케어 검토가 필요한 고객입니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_020 / in_zone_risky_low_mileage

- Decision: `우대`
- Scores: baseline `75.9`, senior `77.49`, risk change `24.11`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 77.5와 낮은 위험변화 점수 24.1를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_021 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `48.89`, senior `78.57`, risk change `12.48`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 78.6와 낮은 위험변화 점수 12.5를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_022 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `54.89`, senior `81.65`, risk change `8.67`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 81.7와 낮은 위험변화 점수 8.7를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_023 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `45.34`, senior `78.16`, risk change `7.75`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 78.2와 낮은 위험변화 점수 7.8를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_024 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `58.41`, senior `83.06`, risk change `11.16`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 83.1와 낮은 위험변화 점수 11.2를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_025 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `49.4`, senior `77.81`, risk change `5.43`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 77.8와 낮은 위험변화 점수 5.4를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_026 / irregular_family_support

- Decision: `기본`
- Scores: baseline `44.09`, senior `72.54`, risk change `27.63`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 72.5와 위험변화 점수 27.6를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_027 / irregular_family_support

- Decision: `우대`
- Scores: baseline `58.2`, senior `76.48`, risk change `26.96`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 76.5와 낮은 위험변화 점수 27.0를 기준으로 생활권 중심 안정 주행 우대 대상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_028 / irregular_family_support

- Decision: `기본`
- Scores: baseline `34.71`, senior `67.49`, risk change `28.16`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 67.5와 위험변화 점수 28.2를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_029 / irregular_family_support

- Decision: `기본`
- Scores: baseline `41.6`, senior `69.39`, risk change `26.13`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 69.4와 위험변화 점수 26.1를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_030 / irregular_family_support

- Decision: `기본`
- Scores: baseline `30.06`, senior `64.36`, risk change `33.98`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `deterministic_template`
- Staff summary: 통합 점수 64.4와 위험변화 점수 34.0를 기준으로 기본 조건 유지가 적절한 고객입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

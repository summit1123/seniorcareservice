# Senior Safe Mileage Simulation Summary

- Schema: `senior-report-agent/v1`
- Report mode: `llm_generated`
- Selected policy: `policy_30_30_20_20_p20_a75`
- Approval gate passed: `True`
- Critic verdict: `pass`
- Risk-change capture: `5/5`
- Non-target false positives: `1`
- Total misclassifications: `1`

## Portfolio Report

### Senior Safe Mileage 정책 검증 결과 요약

- **고객 수**: 30명
- **위험 변화 목표 수**: 5
- **제안된 캡처 수**: 5
- **비목표 잘못 탐지 수**: 1
- **총 분류 오류 수**: 1
- **에이전트 검증 통과율**: 96.67%
- **비평 판단**: 통과
- **비평 위험 수**: 2

#### 선택된 정책 가중치
- 주행 거리: 30%
- 존 내: 30%
- 안전한 존 외: 20%
- 존 변화: 20%

#### 선택된 정책 임계값
- 케어 임계값: 41.14
- 케어 임계값 백분위수: 20%
- 케어 임계값 출처: 위험 변화 점수 상위 백분위
- 예상 상위 N 수: 6

#### 티어 임계값
- S: 85
- A: 75
- B: 65
- C: 0

이 결과는 정책의 신뢰성과 유효성을 검증하는 데 기여하며, 향후 조정 시 고려될 수 있습니다.

## Critic Follow-ups
- Review misclassified `in_zone_risky_low_mileage` customers before using the candidate in demos.

## Customer Reports

### cust_001 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `73.06`, senior `90.14`, risk change `5.28`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**판정**: 우대
**리포트 요약**: 통합 점수 90.1과 낮은 위험변화 점수 5.3를 기준으로 생활권 중심 안정 주행 우대 대상입니다.

**이유 코드**:
- 낮은 주행 거리 기준 적격
- 생활권 DBSCAN P90 입력 사용
- 생활권 안정 주행
- 강한 위험 변화 없음
- 제안된 모델 유리 또는 기준

**주행 데이터**:
- 기준 총 주행 거리: 517.93 km
- 최근 총 주행 거리: 269.4 km
- 연간화된 최근 주행 거리: 3,232.8 km
- 최근 주행 횟수: 12회
- 최근 생활권 내 주행 비율: 92.98%
- 최근 생활권 내 주행 거리: 250.5 km
- 최근 생활권 내 주행 횟수: 11회
- 최근 위험률 (100km당): 0.3992

**추천 조치**: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_002 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `75.5`, senior `91.45`, risk change `2.34`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**판정:** 우대
**이유:**
- 낮은 주행 거리 기준 적격
- 생활권 중심 DBSCAN P90 데이터 사용
- 생활권 내 안정 주행
- 위험 변화 없음
- 제안된 모델 우대 또는 표준

**통합 점수:** 91.5
**위험 변화 점수:** 2.3
**최근 총 주행 거리:** 244.96 km
**최근 생활권 내 주행 거리:** 244.96 km
**주간 주행 비율:** 100%
**최근 주행 횟수:** 11회

**요약:** 생활권 중심 안정 주행 우대 대상으로 판별됨.

**추천 조치:** 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_003 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `64.88`, senior `87.15`, risk change `3.43`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

- **우대 판정**: 고객은 생활권 중심 안정 주행 우대 대상입니다.

- **기초 정보**:
  - 총 주행 거리: 704.28 km
  - 최근 주행 거리: 351.17 km
  - 연간 주행 거리 예측: 4214.04 km
  - 최근 여행 횟수: 15회
  - 생활권 내 비율: 94.47%
  - 생활권 외 비율: 5.53%

- **위험 평가**:
  - 위험 변화 점수: 3.43 (낮은 위험 변화)
  - 생활권 내 위험 점수: 0.9043 per 100km
  - 생활권 외 위험 점수: 0.0 per 100km

- **추천 조치**: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

- **요약**: 통합 점수 87.2와 낮은 위험변화 점수 3.4를 기준으로 우대 판정.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_004 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `77.85`, senior `90.29`, risk change `11.26`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **고객 판정**: 우대
- **이유 코드**:
  - 저주행 기준 적합
  - 생활권 데이터 분석 사용
  - 생활권 내 안정적인 주행
  - 위험 변화 없음
  - 모델 제안이 유리 또는 표준

- **통합 점수**: 90.3
- **위험 변화 점수**: 11.3

**판별 요약**: 생활권 중심 안정 주행 우대 대상입니다.

**추천 행동**: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_005 / stable_local_low_mileage

- Decision: `우대`
- Scores: baseline `70.55`, senior `88.51`, risk change `6.69`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **고객 판정**: 우대
- **판정 근거**:
  - 낮은 주행 거리 기준 적격
  - 생활권 중심 DBSCAN P90 입력 사용
  - 안정된 생활권 주행
  - 강한 위험 변화 없음
  - 제안된 모델에서 유리하거나 표준

- **통합 점수**: 88.5
- **위험 변화 점수**: 6.7
- **생활권 주행 실적**:
  - 최근 총 주행 거리: 294.46 km
  - 생활권 내 주행 거리: 272.48 km (93%)
  - 최근 주행 횟수: 14회 (13회 생활권 내)

- **제안된 조치**:
  - 생활권 중심 안정 주행 우대 근거 확인 후, 일반 갱신 안내에 반영.

**비고**: 고객은 안정적인 낮은 주행 거리 패턴을 보이고 있으며, 이로 인해 우대 인정.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_006 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `45.66`, senior `80.03`, risk change `5.49`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **진단 결정**: 우대
- **판정 근거**:
  - 낮은 주행 거리 기준 적격
  - 생활권 중심 데이터 분석 입력 사용
  - 생활권 내 안정 주행
  - 위험 변화 없음
  - 우대 모델 기준에 부합

- **통합 점수**: 80.0
- **위험 변화 점수**: 5.5

- **요약**: 생활권 중심 안정 주행 우대 대상입니다.

- **추천 조치**: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_007 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `52.38`, senior `81.53`, risk change `6.39`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

- **판정 결과**: 우대
- **기초 점수**:
  - 통합 점수: 81.5
  - 위험변화 점수: 6.4
- **주요 사유 코드**:
  - LOW_MILEAGE_BASELINE_ELIGIBLE
  - LIVING_ZONE_DBSCAN_P90_INPUT_USED
  - LIVING_ZONE_STABLE_DRIVING
  - NEW_DESTINATION_OUT_ZONE_SIGNAL
  - NO_STRONG_RISK_CHANGE
  - PROPOSED_MODEL_FAVORABLE_OR_STANDARD

- **요약**:
  - 생활권 중심 안정 주행 우대 대상입니다.

- **추천 조치**:
  - 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### 주행 데이터 요약
- **총 주행 거리 (기초)**: 956.67 km
- **최근 총 주행 거리**: 476.18 km
- **연간 예상 주행 거리**: 5714.16 km
- **최근 주행 횟수**: 14회
- **생활권 내 주행 비율**: 75.74%
- **생활권 외 주행 비율**: 24.26% (변동: 2.28%)
- **위험율 변화 (100km당)**: 0.3174

#### 생활권 내/외 주행 데이터
- **생활권 내 주행 거리**: 360.65 km (주행 횟수: 11)
- **생활권 외 주행 거리**: 115.53 km (주행 횟수: 3)
- **생활권 내 위험율 (100km당)**: 0.5546
- **생활권 외 위험율 (100km당)**: 1.7312

### 안전 점수
- 생활권 외 안전 점수: 90.48
- 주행 점수: 52.38
- 위험 변화 점수: 6.39
- Senior Safe Mileage 점수: 81.53

이상입니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_008 / stable_outer_safe

- Decision: `기본`
- Scores: baseline `31.84`, senior `74.02`, risk change `9.38`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: **고객별 Senior Safe Mileage 판정 리포트**

- **판정 결과**: 기본
- **판정 사유**:
  - 저주행거리 기준 적합
  - 거주 구역 분석 사용
  - 새로운 목적지가 구역 외 신호
  - 위험 변화 없음

- **통합 점수**: 74.0
- **위험 변화 점수**: 9.4
- **고객 상태**: 기본 조건 유지가 적절

- **추천 조치**:
  - 기본 조건 유지
  - 다음 관측기간의 위험 변화 점수 모니터링

**주요 데이터**:
- 총 주행 거리: 1381.49 km
- 최근 주행 거리: 681.62 km (연간화: 8179.44 km)
- 최근 주행 회수: 19회
- 구역 내 비율: 66.9%
- 구역 외 비율: 33.1%
- 위험률 변화 (100km당): 0.1603
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_009 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `37.1`, senior `76.08`, risk change `9.44`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**고객 판정:** 우대
**판정 근거:**
- 낮은 주행거리 기준 적격
- 생활권 중심 안정 주행
- 새로운 목적지 신호
- 위험 변화 없음
- 모델 유리 또는 표준

**통합 점수:** 76.1
**위험 변화 점수:** 9.4

**주행 데이터:**
- 기준 주행거리: 1130.94 km
- 최근 주행거리: 628.99 km
- 연간화 최근 주행: 7547.88 km
- 최근 주행 수: 17회
- 주거 지역 내 주행 비율: 69.33%
- 주거 지역 외 주행 비율: 30.67%

**위험 평점:**
- 주거 지역 내 위험 평점: 1.1466 per 100km
- 주거 지역 외 위험 평점: 0.5183 per 100km

**추천 조치:**
생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_010 / stable_outer_safe

- Decision: `우대`
- Scores: baseline `54.56`, senior `80.05`, risk change `17.51`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**판정: 우대**
**사유 코드:**
- 낮은 주행 거리 기준 적격
- 생활권 DBSCAN P90 입력 사용
- 생활권 중심 안정 주행
- 새로운 목적지 외부 지역 신호
- 강력한 위험 변화 없음
- 제안 모델 우대 또는 표준

**통합 점수:** 80.0
**위험 변화 점수:** 17.5

**생활권 중심 안정 주행 우대 대상**

**권장 조치:** 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

**기타 정보:**
- 기준 주행 거리: 927.41 km
- 최근 주행 거리: 454.42 km (연환산: 5453.04 km)
- 최근 주행 횟수: 13회
- 생활권 내 주행 비율: 67.38%
- 생활권 외 주행 비율: 32.62% (Δ: 10.05%)
- 안전 점수 (생활권 외): 88.87
- 주행 거리 기준 점수: 54.56
- 위험 변화 점수: 17.51
- Senior Safe Mileage 점수: 80.05

검토 후 업데이트 필요.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_011 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `66.33`, senior `51.71`, risk change `97.8`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 정보**
- **케어 결정:** 예방 케어
- **리포트 사유 코드:**
  - 저주행 기준 적격
  - 생활권 DBSCAN P90 입력 사용
  - 새로운 목적지 외부 신호
  - 생활권 패턴 변화 위험
  - 최근 야간 주행 증가
  - 위험 사건 비율 증가
  - 제안된 예방 케어 모델

**요약**
- 최근 생활권 밖 위험 변화 점수: **97.8**
- 통합 점수: **51.7**
- 예방 케어 검토 필요 대상

**추천 조치**
- 상담 또는 안전운전 안내 대상으로 검토
- 최근 생활권 밖 주행 변화 원인 확인

**주행 데이터 요약**
- **기준 총 주행 거리:** 648.84 km
- **최근 총 주행 거리:** 336.66 km
- **연간 최근 주행 거리:** 4039.92 km
- **최근 주행 횟수:** 13 회
- **최근 생활권 내 비율:** 62.34%
- **최근 생활권 밖 비율:** 37.66%
- **외부 비율 변화:** 34.19%
- **야간 비율 변화:** 22.8%
- **100km당 위험률 변화:** 5.4783

**위험 점수**
- 생활권 밖 안전 점수: **77.78**
- 주행 기준 점수: **66.33**
- 위험 변화 점수: **97.8**
- Senior Safe Mileage 점수: **51.71**

상기 정보를 바탕으로 고객의 안전 운전 습관을 살펴보고, 필요한 예방 조치를 취해주시기 바랍니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_012 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `63.7`, senior `48.73`, risk change `100.0`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

- **케어 결정**: 예방 케어
- **리포트 요약**: 최근 생활권 밖 위험변화 점수 100.0과 통합 점수 48.7을 기준으로 예방 케어 검토가 필요한 고객입니다.

#### 이유 코드:
- LOW_MILEAGE_BASELINE_ELIGIBLE
- LIVING_ZONE_DBSCAN_P90_INPUT_USED
- NEW_DESTINATION_OUT_ZONE_SIGNAL
- OUT_ZONE_PATTERN_CHANGE_RISK
- RECENT_NIGHT_DRIVING_INCREASE
- RISK_EVENT_RATE_INCREASE
- PROPOSED_MODEL_PREVENTIVE_CARE

#### 최근 주행 데이터:
- **기준 총 주행 거리**: 722.96 km
- **최근 총 주행 거리**: 363.01 km (연간화: 4356.12 km)
- **최근 주행 횟수**: 15회
- **생활권 주행 비율**: 60%
- **비생활권 주행 비율**: 40%
- **비생활권 변경 비율**: 33.61%
- **야간 주행 증가 비율**: 26.86%
- **위험률 변화**: 5.64 (100 km 당)

#### 최근 주행 분석:
- **생활권 내 주행 거리**: 217.79 km (주행 횟수: 9회, 야간 비율: 24.88%, 위험률: 6.43)
- **비생활권 주행 거리**: 145.22 km (주행 횟수: 6회, 야간 비율: 29.84%, 위험률: 6.20)

#### 점수:
- **비생활권 안전 점수**: 60.44
- **주행 거리 기준 점수**: 63.7
- **위험 변화 점수**: 100.0
- **Senior Safe Mileage 점수**: 48.73

### 추천 조치
상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_013 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `68.41`, senior `46.48`, risk change `100.0`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 판정: 예방 케어**
**이유 코드:**
- LOW_MILEAGE_BASELINE_ELIGIBLE
- LIVING_ZONE_DBSCAN_P90_INPUT_USED
- NEW_DESTINATION_OUT_ZONE_SIGNAL
- OUT_ZONE_PATTERN_CHANGE_RISK
- RECENT_NIGHT_DRIVING_INCREASE
- RISK_EVENT_RATE_INCREASE
- PROPOSED_MODEL_PREVENTIVE_CARE

**요약:**
최근 생활권 밖 위험변화 점수 100.0과 통합 점수 46.5를 기준으로 예방 케어 검토가 필요한 고객입니다.

**권장 조치:**
상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

**주요 지표:**
- **기준 총 주행 거리:** 579.12 km
- **최근 총 주행 거리:** 315.89 km (연간 환산: 3790.68 km, 최근 주행 횟수: 12회)
- **생활권 내 비율:** 58.45%, **생활권 외 비율:** 41.55% (생활권 외 비율 변화: 33.63%)
- **밤 주행 비율 변화:** 33.99%
- **위험률 변화 (100km당):** 6.9357
- **생활권 내 주행 거리:** 184.65 km (위험률: 8.1235)
- **생활권 외 주행 거리:** 131.24 km (위험률: 6.0957)
- **생활권 외 안전 점수:** 52.89
- **마일리지 기준 점수:** 68.41
- **위험 변화 점수:** 100.0
- **Senior Safe Mileage 점수:** 46.48

보고서 요약: 고객은 최근 다양한 지표에서 위험 변화가 감지되어 예방 케어가 필요함.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_014 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `64.42`, senior `54.51`, risk change `89.32`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 판정:** 예방 케어
**이유 코드:**
- 저주행 기준 적격
- 생활권 DBSCAN P90 입출력 사용
- 새로운 목적지 생활권 외 신호
- 생활권 외 패턴 변화 위험
- 최근 야간 주행 증가
- 위험 사건 비율 증가
- 제안된 예방 케어 모델

**최근 생활권 외 위험 변화 점수:** 89.3
**통합 점수:** 54.5

**상황 요약:**
최근 생활권 밖 위험변화 점수와 통합 점수를 기준으로 예방 케어 검토 필요.

**권장 조치:**
상담 또는 안전운전 안내 대상으로 검토하고, 최근 생활권 밖 주행 변화 원인 확인 필요.

**프라이버시 필터링된 특징:**
- 개인 유형: 최근 외부 위험 변화
- 기준 총 주행: 777.74 km
- 최근 총 주행: 355.77 km
- 연간화된 최근 주행: 4269.24 km
- 최근 주행 건수: 17
- 최근 생활권 내 비율: 63.58%
- 최근 생활권 외 비율: 36.42%
- 외부 비율 변화: 27.52%
- 야간 비율 변화: 20.01%
- 100km당 위험 비율 변화: 4.4405

**세부 사항:**
- 최근 생활권 내 주행: 226.21 km (건수: 11, 야간 비율: 29.57%, 위험 비율: 5.7469 per 100km)
- 최근 생활권 외 주행: 129.56 km (건수: 6, 야간 비율: 12.96%, 위험 비율: 4.6311 per 100km)
- 외부 안전 점수: 72.3
- 주행 기준 점수: 64.42
- 위험 변화 점수: 89.32
- Senior Safe Mileage 점수: 54.51
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_015 / recent_outer_risk_change

- Decision: `예방 케어`
- Scores: baseline `57.04`, senior `42.23`, risk change `99.09`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, OUT_ZONE_PATTERN_CHANGE_RISK, RECENT_NIGHT_DRIVING_INCREASE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 0.0점 fail입니다. 제안 모델 decision_detected=True, ground_truth_target=True, proxy_label_target=True, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**고객 케어 결정:** 예방 케어
**이유 코드:**
- LOW_MILEAGE_BASELINE_ELIGIBLE
- LIVING_ZONE_DBSCAN_P90_INPUT_USED
- NEW_DESTINATION_OUT_ZONE_SIGNAL
- OUT_ZONE_PATTERN_CHANGE_RISK
- RECENT_NIGHT_DRIVING_INCREASE
- RISK_EVENT_RATE_INCREASE
- PROPOSED_MODEL_PREVENTIVE_CARE

**최근 생활권 밖 위험변화 점수:** 99.1
**통합 점수:** 42.2

**Fallback Summary:**
최근 생활권 밖 위험변화 점수 99.1와 통합 점수 42.2를 기준으로 예방 케어 검토가 필요한 고객입니다.

**추천 행동:**
상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

---

**기타 정보:**
- 기본 연간 주행 거리: 5,154.6 km
- 최근 주행 거리: 429.55 km
- 최근 주행 횟수: 18회
- 최근 생활권 내 주행 거리: 266.22 km
- 최근 생활권 외 주행 거리: 163.33 km
- 안전 점수: 38.49
- 마일리지 기준 점수: 57.04
- 위험 변화 점수: 99.09
- Senior Safe Mileage 점수: 42.23
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_016 / in_zone_risky_low_mileage

- Decision: `기본`
- Scores: baseline `74.04`, senior `69.08`, risk change `25.54`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **고객 판정**: 기본
- **판정 기준**: 통합 점수 69.1, 위험변화 점수 25.5
- **사유 코드**:
  - LOW_MILEAGE_BASELINE_ELIGIBLE
  - LIVING_ZONE_DBSCAN_P90_INPUT_USED
  - LIVING_ZONE_STABLE_DRIVING
  - NO_STRONG_RISK_CHANGE
  - RISK_EVENT_RATE_INCREASE

- **프라이버시 필터링된 특징**:
  - 인구 유형: 위험 낮은 주행거리 지역 내
  - 기준 주행거리: 520.98 km
  - 최근 총 주행거리: 259.59 km
  - 최근 주행횟수: 12회
  - 지역 내 주행 비율: 90.38%
  - 지역 밖 주행 비율: 9.62%

- **위험 변화 점수**: 25.5
- **추천 조치**: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

**결론**: 위험 변화가 크지 않으며 안정적인 주행 환경으로 판단되어 기본 조건 유지를 권장합니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_017 / in_zone_risky_low_mileage

- Decision: `기본`
- Scores: baseline `64.46`, senior `56.99`, risk change `27.34`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **고객 상태**: 기본 조건 유지
- **이유 코드**:
  - 저주행 거리 기준 적합
  - 거주 구역 데이터 사용
  - 안정적인 운전 패턴
  - 강한 위험 변화 없음
  - 위험 사건 비율 증가

- **요약**:
  - 통합 점수: 57.0
  - 위험 변화 점수: 27.3
  - 분석 결과에 따라 기본 조건 유지가 적절함.

- **추천 조치**:
  - 기본 조건 유지
  - 다음 관측기간의 위험 변화 점수 추이를 모니터링

- **주요 지표**:
  - 총 주행 거리 (기준): 672.55 km
  - 최근 총 주행 거리: 355.41 km
  - 연간화된 최근 주행 거리: 4264.92 km
  - 최근 주행 횟수: 16회
  - 구역 내 비율: 92.66%
  - 구역 외 비율: 7.34%
  - 위험 비율 변화 (100km 당): 2.9189
  - 구역 내 위험 비율: 5.4656 (100km 당)
  - 구역 외 위험 비율: 15.3374 (100km 당)

이 리포트는 고객의 운전 습관을 평가하여 안전한 조건을 유지하기 위한 것입니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_018 / in_zone_risky_low_mileage

- Decision: `기본`
- Scores: baseline `64.04`, senior `65.42`, risk change `28.84`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: 고객별 Senior Safe Mileage 판정 리포트

- **판정 결과**: 기본 조건 유지
- **이유 코드**:
  - 저주행 기준 적격
  - 생활권 내 안정적 운전
  - 위험 변화 없음
  - 위험 이벤트 비율 증가

- **통합 점수**: 65.4
- **위험 변화 점수**: 28.8

- **추천 조치**: 기본 조건을 유지하되, 다음 관측기간의 위험 변화 점수 추이를 모니터링합니다.

**추가 정보**:
- 연간 주행 거리: 4315.08 km
- 최근 주행 거리: 359.59 km
- 최근 주행 횟수: 17회
- 생활권 내 주행 비율: 94.51%
- 저녁 시간 주행 비율의 변화: 4.2% 증가

고객의 현재 주행 패턴은 안정적이며, 향후 모니터링이 필요합니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_019 / in_zone_risky_low_mileage

- Decision: `예방 케어`
- Scores: baseline `68.77`, senior `63.0`, risk change `41.14`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, BORDERLINE_PATTERN_CHANGE_MONITORED, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_PREVENTIVE_CARE`
- Hybrid evaluation: proposed `fail` score `0.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 0.0점으로 기준 80.0점 대비 fail이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=True, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 판정:** 예방 케어
**이유 코드:**
- LOW_MILEAGE_BASELINE_ELIGIBLE
- LIVING_ZONE_DBSCAN_P90_INPUT_USED
- LIVING_ZONE_STABLE_DRIVING
- BORDERLINE_PATTERN_CHANGE_MONITORED
- RISK_EVENT_RATE_INCREASE
- PROPOSED_MODEL_PREVENTIVE_CARE

**최근 분석 요약:**
고객은 최근 생활권 밖 위험변화 점수 41.1과 통합 점수 63.0을 기준으로 예방 케어 검토가 필요합니다.

**제안된 조치:**
상담 또는 안전운전 안내 대상으로 검토하고, 최근 생활권 밖 주행 변화 원인을 확인합니다.

### 고객 특성
- **인구 유형:** 위험이 낮은 생활권 내 주행
- **기준 총 주행 거리:** 624.01 km
- **최근 총 주행 거리:** 312.34 km
- **연간 주행 거리:** 3748.08 km
- **최근 주행 횟수:** 15회
- **생활권 내 비율:** 93.81%
- **생활권 외 비율:** 6.19%
- **비율 변화:** 3.52%
- **야간 비율 변화:** 1.23%
- **100km당 위험률 변화:** 4.96
- **생활권 내 주행 거리:** 293.0 km
- **생활권 내 주행 횟수:** 14회
- **생활권 내 야간 비율:** 5.51%
- **생활권 내 100km당 위험률:** 7.51
- **생활권 외 주행 거리:** 19.34 km
- **생활권 외 주행 횟수:** 1회
- **생활권 외 야간 비율:** 0.0%
- **생활권 외 100km당 위험률:** 5.17
- **생활권 외 안전 점수:** 71.56
- **주행 거리 기준 점수:** 68.77
- **위험 변화 점수:** 41.14
- **Senior Safe Mileage 점수:** 63.0

---

고객별 추가 검토가 필요합니다.
- Recommended action: 상담 또는 안전운전 안내 대상으로 검토하고 최근 생활권 밖 주행 변화 원인을 확인합니다.

### cust_020 / in_zone_risky_low_mileage

- Decision: `우대`
- Scores: baseline `75.9`, senior `77.49`, risk change `24.11`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, RISK_EVENT_RATE_INCREASE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

- **우대 판정**: 우대
- **판정 근거**:
  - 낮은 주행 기준 점수 적합
  - 생활권 중심 안정 주행
  - 위험 변화 없음
  - 위험 사건 비율 증가
  - 제안된 모델이 우대 또는 표준

- **통합 점수**: 77.5
- **위험 변화 점수**: 24.1

- **주행 정보**:
  - 총 주행 거리(최근): 241.05 km
  - 연간 기준 주행 거리: 2892.6 km
  - 최근 주행 횟수: 11회
  - 생활권 내 주행 비율: 100%

- **위험률**:
  - 최근 위험률(생활권 내): 5.8079 per 100 km

- **추천 행동**: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_021 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `48.89`, senior `78.57`, risk change `12.48`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**판정:** 우대
**리우딩 요인:**
- 낮은 주행거리 기준 적격
- 생활권 DBSCAN P90 입력 사용
- 생활권 중심 안정 주행
- 강한 위험 변화 없음
- 제안 모델 우대 또는 표준

**통합 점수:** 78.6
**위험 변화 점수:** 12.5
**생활권 중심 안정 주행 우대 대상 확인 요약:**
최근 주행 거리: 511.06 km
연간화된 최근 주행: 6,132.72 km
최근 생활권 내 주행: 383.73 km
최근 생활권 내 주행 비율: 75.09%

**추천 조치:**
생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_022 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `54.89`, senior `81.65`, risk change `8.67`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **우대 판정**: 고객은 생활권 중심 안정 주행 우대 대상입니다.
- **기본 점수**: 통합 점수 81.7
- **위험변화 점수**: 8.7 (낮음)
- **최근 주행 거리**: 451.11 km
- **연간화된 최근 주행 거리**: 5413.32 km
- **최근 주행 횟수**: 15회
- **생활권 내 주행 비율**: 71.12%
- **생활권 외 주행 비율**: 28.88%
- **안정 주행 이유**: 생활권 중심 안정 주행, 위험 변화 없음, 제안 모델 유리 또는 표준

### 권장 조치
생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_023 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `45.34`, senior `78.16`, risk change `7.75`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

**판정**: 우대
**우대 사유**:
- 저주행 기반 점수 적합
- 생활권 중심 데이터 사용
- 안정적인 주행 패턴
- 신규 목적지 외부 신호
- 위험 변화 없음
- 모델 우대 또는 표준

**통합 점수**: 78.2
**위험변화 점수**: 7.8

**생활권 중심 안정 주행 우대 대상**: 해당 고객은 생활권 내 안정적인 주행을 유지하며, 위험 변화가 적어 우대 대상입니다.

**추천 조치**:
생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

**주행 데이터 요약**:
- 기초 총 주행 거리: 1120.14 km
- 최근 총 주행 거리: 546.59 km
- 연간 전환 주행 거리: 6559.08 km
- 최근 주행 횟수: 19회
- 생활권 내 비율: 73.64%
- 생활권 외 비율: 26.36%

**위험 점수 요약**:
- 생활권 내 위험 점수 (100km당): 1.739
- 생활권 외 위험 점수 (100km당): 0.6941
- 위험 변화 점수: 7.75

해당 리포트는 고객의 안전 운전 습관을 반영하며, 지속적인 안정성을 유지할 수 있도록 지원하기 위해 작성되었습니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_024 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `58.41`, senior `83.06`, risk change `11.16`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

- **고객 판정**: 우대
- **우대 사유**:
  - 저주행 거리 기준 적격
  - 생활권 중심 DBSCAN P90 입력 사용
  - 생활권 안정 주행
  - 강력한 위험 변동 없음
  - 제안된 모델: 유리하거나 표준

- **통합 점수**: 83.1
- **위험 변동 점수**: 11.2
- **생활권 주행 상태**: 안정적

- **추천 조치**: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

#### 추가 정보
- **기준 주행 거리**: 747.98 km
- **최근 주행 거리**: 415.91 km
- **연간 주행 거리**: 4,990.92 km
- **최근 주행 횟수**: 13
- **구역 내 비율**: 77.77%
- **구역 외 비율**: 22.23%
- **위험율 변화 (100km당)**: 0.2933

해당 정보는 고객의 주행 안전성과 위험을 평가하는 데 도움이 됩니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_025 / medical_visit_pattern

- Decision: `우대`
- Scores: baseline `49.4`, senior `77.81`, risk change `5.43`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

- **우대 판정**: 우대
- **이유 코드**:
  - 저주행 기준 적합
  - 생활권 중심 주행 데이터 사용
  - 생활권 안정 주행
  - 위험 변화 없음
  - 모델 우대 또는 표준

- **통합 점수**: 77.8
- **위험 변화 점수**: 5.4
- **생활권 중심 안정 주행 우대 대상**: 확인됨

- **최근 주행 데이터**:
  - 총 주행 거리: 506.05 km
  - 연평균 주행 거리: 6072.6 km
  - 최근 여행 횟수: 18회
  - 생활권 내 주행 비율: 80.96%
  - 생활권 외 주행 비율: 19.04%

- **위험 점수**:
  - 생활권 내: 0.9763 per 100km
  - 생활권 외: 3.114 per 100km

- **추천 조치**: 생활권 중심 안정 주행 우대 근거를 검토하고 일반 갱신 안내에 반영할 것.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_026 / irregular_family_support

- Decision: `기본`
- Scores: baseline `44.09`, senior `72.54`, risk change `27.63`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 판정:** 기본
**이유 코드:**
- 낮은 마일리지 기준 적격
- 거주 지역 DBSCAN P90 입력 사용
- 새로운 목적지 아웃존 신호
- 위험 변화 없음

**통합 점수:** 72.5
**위험 변화 점수:** 27.6

**요약:** 통합 점수 72.5와 위험 변화 점수 27.6를 기준으로 기본 조건 유지가 적절한 고객입니다.

**추천 조치:** 기본 조건을 유지하되 다음 관측 기간의 위험 변화 점수 추이를 모니터링합니다.

### 개인정보 보호 필터링된 정보
- **고객 유형:** 비정기 가족 지원
- **기준 마일리지:** 1045.62 km
- **최근 총 마일리지:** 559.06 km
- **연환산 최근 마일리지:** 6708.72 km
- **최근 여행 횟수:** 16
- **최근 인존 비율:** 73.07%
- **최근 아웃존 비율:** 26.93%
- **아웃존 비율 변화:** 11.6%
- **야간 비율 변화:** 2.53%
- **100 km당 위험 비율 변화:** 0.4374
- **최근 인존 km:** 408.5
- **최근 인존 여행 횟수:** 12
- **최근 인존 야간 비율:** 8.6%
- **최근 인존 100 km당 위험 비율:** 2.6928
- **최근 아웃존 km:** 150.56
- **최근 아웃존 여행 횟수:** 4
- **최근 아웃존 야간 비율:** 0%
- **최근 아웃존 100 km당 위험 비율:** 0.0
- **아웃존 안전 점수:** 100.0
- **마일리지 기준 점수:** 44.09
- **위험 변화 점수:** 27.63
- **시니어 세이프 마일리지 점수:** 72.54
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_027 / irregular_family_support

- Decision: `우대`
- Scores: baseline `58.2`, senior `76.48`, risk change `26.96`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE, PROPOSED_MODEL_FAVORABLE_OR_STANDARD`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 유형:** 비정기 가족 지원
**주행 거리 요약:**
- 기준 총 주행 거리: 868.09 km
- 최근 총 주행 거리: 417.98 km
- 최근 연간화 주행 거리: 5015.76 km
- 최근 주행 횟수: 14회

**생활권 내/외 비율:**
- 생활권 내 비율: 73.05%
- 생활권 외 비율: 26.95%

**안전 점수 및 위험 변화:**
- 생활권 외 안전 점수: 86.8
- 주행 거리 기준 점수: 58.2
- 위험 변화 점수: 26.96
- Senior Safe Mileage 점수: 76.48

**판정 결정:** 우대
**이유 코드:**
- LOW_MILEAGE_BASELINE_ELIGIBLE
- LIVING_ZONE_DBSCAN_P90_INPUT_USED
- LIVING_ZONE_STABLE_DRIVING
- NEW_DESTINATION_OUT_ZONE_SIGNAL
- NO_STRONG_RISK_CHANGE
- PROPOSED_MODEL_FAVORABLE_OR_STANDARD

**요약:** 통합 점수 76.5와 낮은 위험변화 점수 27.0를 기준으로 생활권 중심 안정 주행 우대 대상입니다.

**권장 조치:** 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.
- Recommended action: 생활권 중심 안정 주행 우대 근거를 확인하고 일반 갱신 안내에 반영합니다.

### cust_028 / irregular_family_support

- Decision: `기본`
- Scores: baseline `34.71`, senior `67.49`, risk change `28.16`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### 고객별 Senior Safe Mileage 판정 리포트

- **판정 결과**: 기본
- **이유 코드**:
  - 저주행 기준 적격
  - 거주지 구역 P90 데이터 사용
  - 신규 목적지 외부 구역 신호
  - 위험 변화 없음

- **통합 점수**: 67.5
- **위험 변화 점수**: 28.2

- **개요**: 기본 조건 유지가 적절한 고객입니다.

- **추천 조치**: 기본 조건을 유지하되, 다음 관측 기간의 위험 변화 점수 추이를 모니터링합니다.

- **주행 세부정보**:
  - 기준 주행 거리: 1306.04 km
  - 최근 주행 거리: 652.91 km
  - 연간화된 최근 주행 거리: 7834.92 km
  - 최근 운행 횟수: 20회
  - 최근 구역 내 비율: 71.2%
  - 최근 구역 외 비율: 28.8%
  - 구역 외 비율 변화: 12.63%
  - 야간 비율 변화: 2.14%
  - 100km당 위험율 변화: 0.3066

- **구역 내 / 외 주행 데이터**:
  - 최근 구역 내 주행 거리: 464.85 km (14회)
  - 최근 구역 외 주행 거리: 188.06 km (6회)
  - 구역 외 안전 점수: 80.97
  - 주행 거리 기준 점수: 34.71
  - 위험 변화 점수: 28.16
  - Senior Safe Mileage 점수: 67.49

이 고객에 대한 지속적인 모니터링이 필요합니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_029 / irregular_family_support

- Decision: `기본`
- Scores: baseline `41.6`, senior `69.39`, risk change `26.13`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: ### Senior Safe Mileage 판정 리포트

**고객 판정:** 기본
**이유 코드:**
- 저주행 기준 적합
- 생활 구역 안전성 확인
- 강한 위험 변화 없음

**통합 점수:** 69.4
**위험 변화 점수:** 26.1
**추천 행동:** 기본 조건을 유지하되 다음 관측기간의 위험 변화 점수를 모니터링합니다.

**주요 지표:**
- 기준 주행 거리: 1167.35 km
- 최근 주행 거리: 584.03 km
- 최근 연환산 주행 거리: 7008.36 km
- 최근 여행 횟수: 19회
- 구역 내 주행 비율: 73.67%
- 구역 외 주행 비율: 26.33%
- 구역 외 비율 변화: 9.95%
- 야간 주행 비율 변화: 7.52%
- 100 km당 위험률 변화: 0.7695

**구역 내/외 안전 점수:**
- 구역 내 위험률 (100 km당): 2.0919
- 구역 외 위험률 (100 km당): 3.2512
- 구역 외 안전 점수: 82.12
- 주행 거리 기준 점수: 41.6
- 위험 변화 점수: 26.13

고객은 기본 조건 유지가 적절합니다.
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

### cust_030 / irregular_family_support

- Decision: `기본`
- Scores: baseline `30.06`, senior `64.36`, risk change `33.98`
- XAI reason codes: `LOW_MILEAGE_BASELINE_ELIGIBLE, LIVING_ZONE_DBSCAN_P90_INPUT_USED, LIVING_ZONE_STABLE_DRIVING, NEW_DESTINATION_OUT_ZONE_SIGNAL, NO_STRONG_RISK_CHANGE`
- Hybrid evaluation: proposed `pass` score `100.0` / threshold `80.0`
- Hybrid rationale: hybrid 평가는 ground truth 0.8, proxy label 0.2 가중치를 적용합니다. 제안 모델은 100.0점으로 기준 80.0점 대비 pass이며, 기존 산식은 100.0점 pass입니다. 제안 모델 decision_detected=False, ground_truth_target=False, proxy_label_target=False, exception_rule=none.
- Report mode: `llm_generated`
- Staff summary: **Senior Safe Mileage 판정 리포트**

- **고객군**: 비정기적 가족 지원
- **기본 주행 거리**: 1,322.78 km
- **최근 주행 거리**: 699.44 km
- **연간화된 최근 주행 거리**: 8,393.28 km
- **최근 여행 건수**: 21건
- **내부 구역 비율**: 69.64%
- **외부 구역 비율**: 30.36%
- **위험 변화 점수**: 34.0

**통합 점수**: 64.4
**최종판단**: 기본 조건 유지가 적절함.

**추천 조치**: 기본 조건 유지, 다음 관측기간의 위험변화 점수 모니터링 필요.

**리포트 이유 코드**:
- 저주행 거리 기준 적합
- 안정적인 거주 구역 주행
- 새로운 목적지 신호 감지
- 위험 변동 없음
- Recommended action: 기본 조건을 유지하되 다음 관측기간의 위험변화 점수 추이를 모니터링합니다.

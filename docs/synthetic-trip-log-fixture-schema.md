# 합성 Trip Log Fixture Schema

## 1. 목적

이 문서는 Senior Safe Mileage Score 제품 검증에 사용할 합성 Trip Log fixture의 필드, 데이터 타입, 제약조건, 예시 레코드를 정의합니다.

기존 파이프라인의 표준 Trip 입력 컬럼은 유지하되, 6개 시니어 페르소나, baseline 60일, recent 30일, Agent 검증, A/B 비교, XAI reason code 생성을 재현할 수 있도록 합성 데이터 전용 메타데이터를 추가합니다.

## 2. Fixture 파일

합성 데이터 생성기는 아래 산출물을 고정된 seed로 재현 가능하게 저장합니다.

| 파일 | 형식 | 역할 |
|---|---|---|
| `data/fixtures/senior_trip_logs.csv` | CSV | Trip 단위 합성 주행 로그 |
| `data/fixtures/senior_customers.json` | JSON | 고객/페르소나/시나리오 메타데이터 |
| `data/fixtures/scenario_config.json` | JSON | 페르소나별/고객별 baseline 60일 및 recent 30일 주행 생성 규칙 |
| `data/fixtures/simulation_manifest.json` | JSON | 생성 seed, 버전, 기간, 검증 요약 |

이 Sub-AC의 필수 계약은 `senior_trip_logs.csv`입니다. JSON 파일은 이후 Agent 오케스트레이션과 화면 표시를 위한 보조 fixture입니다.

`scenario_config.json`은 Scenario Agent가 `persona_templates.yaml`, `senior_customers.json`,
`customer_driving_parameters.json`을 결합해 생성합니다. 6개 페르소나 각각의
baseline/recent 생성 범위와 30명 고객 각각의 baseline 패턴, recent 30일 규칙,
기대 recent 변화량을 명시합니다.

## 3. 생성 단위 제약

| 항목 | 제약조건 |
|---|---|
| 고객 수 | 정확히 30명 |
| 페르소나 구성 | 6개 `persona_type` 각각 5명 |
| 관측기간 | 총 90일 |
| 기간 분리 | `baseline` 60일 + `recent` 30일 |
| Trip 수 | 고객별 baseline 최소 20건, recent 최소 8건 |
| 저주행 위험변화형 | 5명 포함 |
| 식별자 | 고객명, 전화번호, 주소, 차량번호, 원본 trip id 금지 |
| 좌표 | 정확한 GPS 대신 합성 중심점 주변 jitter 좌표만 허용 |
| 재현성 | 동일 `simulation_seed`와 schema version이면 동일 fixture 생성 |

## 4. 페르소나 값

`persona_type`은 아래 6개 값만 허용합니다.

| 값 | 의미 |
|---|---|
| `stable_local_low_mileage` | 생활권 안 저주행 안정형 |
| `stable_outer_safe` | 생활권 밖 주행이 있으나 안정적인 형 |
| `recent_outer_risk_change` | 최근 생활권 밖 위험변화형 |
| `in_zone_risky_low_mileage` | 저주행이지만 생활권 안 위험행동형 |
| `medical_visit_pattern` | 병원 방문 등 반복 외부 목적지형 |
| `irregular_family_support` | 가족 돌봄 등 불규칙 외부 이동형 |

## 5. `senior_trip_logs.csv` 필드

| 컬럼 | 타입 | 필수 | 제약조건 | 예시 |
|---|---|---:|---|---|
| `customer_id` | string | Y | `cust_001` 형식, 30개 고유값, 비식별 | `cust_001` |
| `driver_id` | string | Y | 기존 파이프라인 호환 ID, `customer_id`와 1:1 | `driver_001` |
| `persona_type` | enum string | Y | 4장의 6개 값 중 하나 | `stable_local_low_mileage` |
| `scenario_id` | string | Y | 시나리오 추적용 비식별 ID | `scenario_stable_local_01` |
| `simulation_seed` | integer | Y | 1 이상의 정수 | `20260507` |
| `observation_period` | enum string | Y | `baseline` 또는 `recent` | `baseline` |
| `observation_day_index` | integer | Y | baseline은 1-60, recent는 61-90 | `12` |
| `service_date` | date string | Y | ISO `YYYY-MM-DD`, 90일 범위 안 | `2026-01-12` |
| `trip_id` | string | Y | 합성 ID, `trip_{customer_id}_{NNNN}` 형식 | `trip_cust_001_0004` |
| `trip_sequence` | integer | Y | 고객별 1부터 증가 | `4` |
| `trip_start_time` | datetime string | Y | `YYYY-MM-DD HH:MM:SS`, 종료보다 이전 | `2026-01-12 09:10:00` |
| `trip_end_time` | datetime string | Y | `YYYY-MM-DD HH:MM:SS`, 시작보다 이후 | `2026-01-12 09:34:00` |
| `start_gps_x` | float | Y | 합성 경도, 서울/수도권 예시 범위 `126.70-127.30` | `126.978120` |
| `start_gps_y` | float | Y | 합성 위도, 서울/수도권 예시 범위 `37.35-37.75` | `37.566410` |
| `end_gps_x` | float | Y | 합성 경도, 서울/수도권 예시 범위 `126.70-127.30` | `126.982300` |
| `end_gps_y` | float | Y | 합성 위도, 서울/수도권 예시 범위 `37.35-37.75` | `37.570210` |
| `zone_label` | enum string | Y | `core`, `buffer`, `outer` 중 하나 | `core` |
| `destination_type` | enum string | Y | `home`, `market`, `clinic`, `family`, `leisure`, `unknown_outer` 중 하나 | `market` |
| `trip_distance_km` | float | Y | `0.2-120.0`, km 단위, 소수 2자리 권장 | `4.80` |
| `trip_duration_min` | float | Y | `3.0-240.0`, 분 단위 | `24.0` |
| `avg_speed` | float | Y | `trip_distance_km / trip_duration_min * 60`, 허용 오차 1.0km/h | `12.0` |
| `max_speed` | float | Y | `avg_speed` 이상, `120.0` 이하 | `43.0` |
| `night_drive_flag` | boolean integer | Y | 22:00-05:59 시작이면 `1`, 아니면 `0` | `0` |
| `speeding_count` | integer | Y | 0 이상의 정수 | `0` |
| `harsh_accel_count` | integer | Y | 0 이상의 정수 | `0` |
| `harsh_brake_count` | integer | Y | 0 이상의 정수 | `1` |
| `sharp_turn_count` | integer | Y | 0 이상의 정수 | `0` |
| `stop_count` | integer | Y | 0 이상의 정수 | `2` |
| `night_driving_signal` | boolean integer | Y | `night_drive_flag`와 동일한 야간주행 탐지 신호 | `0` |
| `sudden_braking_signal` | boolean integer | Y | `harsh_brake_count > 0`이면 `1` | `1` |
| `route_deviation_signal` | boolean integer | Y | recent 외부/미확인 목적지, 가족지원 장기 공백 후 외부 이동 등 페르소나별 경로 이탈 신호 | `1` |
| `reduced_activity_signal` | boolean integer | Y | baseline 대비 recent 일평균 trip 빈도 하락과 3일 이상 trip 공백이 함께 있으면 `1` | `0` |
| `fatigue_indicator` | boolean integer | Y | 야간 장거리/장시간 또는 야간 위험 이벤트가 있으면 `1` | `1` |
| `risk_signal_codes` | string | Y | `NIGHT_DRIVING`, `SUDDEN_BRAKING`, `ROUTE_DEVIATION`, `REDUCED_ACTIVITY`, `FATIGUE_INDICATOR`를 `\|`로 연결, 없으면 `none` | `NIGHT_DRIVING\|ROUTE_DEVIATION` |
| `persona_risk_annotation` | enum string | Y | 페르소나 맥락을 반영한 trip 단위 risk annotation | `recent_out_zone_risk_signal` |
| `synthetic_risk_tag` | enum string | Y | `normal`, `safe_outer`, `recent_risk_increase`, `in_zone_risk`, `edge_case` 중 하나 | `normal` |

## 6. 타입 규칙

- CSV에는 header를 반드시 포함합니다.
- 문자열은 UTF-8로 저장합니다.
- 날짜/시간은 timezone 없는 local wall time 문자열로 저장합니다.
- boolean 값은 CSV 호환성을 위해 `0` 또는 `1`로 저장합니다.
- 모든 count 계열 컬럼은 결측 없이 0 이상의 정수로 저장합니다.
- 거리, 시간, 속도 계열 컬럼은 결측 없이 0보다 큰 숫자로 저장합니다.
- 좌표는 실제 고객 위치가 아니라 합성 중심점과 합성 jitter로 생성한 값만 저장합니다.

## 7. 기간 및 패턴 제약

### 7.1 baseline

- `observation_period = baseline`
- `observation_day_index`는 1부터 60까지입니다.
- 생활권 중심, 반복 목적지, 평소 위험행동률을 만드는 기준 데이터입니다.
- `recent_outer_risk_change` 페르소나라도 baseline에서는 외부 위험행동이 낮아야 합니다.

### 7.2 recent

- `observation_period = recent`
- `observation_day_index`는 61부터 90까지입니다.
- baseline 대비 외부 주행 비율, 야간주행, 과속, 급감속 변화가 드러나야 합니다.
- 저주행 위험변화형 5명은 recent 기간에 `synthetic_risk_tag = recent_risk_increase` Trip을 3건 이상 포함해야 합니다.
- trip별 위험 신호는 `night_driving_signal`, `sudden_braking_signal`, `route_deviation_signal`, `reduced_activity_signal`, `fatigue_indicator`로 분해해 저장하고, `risk_signal_codes`와 `persona_risk_annotation`으로 Agent/XAI가 바로 사용할 수 있는 annotation을 함께 남깁니다.
- `recent_outer_risk_change` 페르소나는 recent 기간에 외부/미확인 목적지 중심의 `route_deviation_signal`과 야간 또는 피로 신호가 함께 관찰되어야 합니다.

## 8. 일관성 검증 규칙

Consistency Check Agent는 최소한 아래 규칙을 검증합니다.

| 검증 항목 | 통과 기준 |
|---|---|
| 시간 일관성 | `trip_start_time < trip_end_time` |
| 기간 일관성 | `service_date`와 `observation_day_index`가 같은 90일 달력에 위치 |
| 고객별 90일 커버리지 | 고객별 Trip이 baseline 시작일 `1`, baseline 종료일 `60`, recent 시작일 `61`, recent 종료일 `90`을 모두 포함 |
| baseline 커버리지 | 고객별 baseline Trip이 60일 관측창의 시작일 `1`과 종료일 `60`을 모두 포함 |
| recent 커버리지 | 고객별 recent Trip이 30일 관측창의 시작일 `61`과 종료일 `90`을 모두 포함 |
| 평균속도 | 계산 평균속도와 `avg_speed` 차이가 1.0km/h 이하 |
| 최고속도 | `max_speed >= avg_speed` |
| 좌표 범위 | 모든 좌표가 허용 합성 범위 안에 존재 |
| 이벤트 카운트 | 모든 위험운전 count가 0 이상 |
| 위험신호 annotation | 신호 flag는 0/1이고, 야간 신호는 `night_drive_flag`, 급제동 신호는 `harsh_brake_count`와 일관됨 |
| 생활권 라벨 | baseline core/buffer 목적지가 생활권 중심 주변에 반복 출현 |
| recent 변화 | 위험변화형은 recent 외부 위험행동률이 baseline보다 높음 |
| 개인정보 | 금지 식별자 컬럼과 원본 trip id가 없음 |

## 9. OpenAI API 전송 금지 및 허용

외부 LLM API에는 `senior_trip_logs.csv` 원본 레코드를 전송하지 않습니다.

전송 금지:

- `customer_id`
- `driver_id`
- `trip_id`
- `trip_start_time`
- `trip_end_time`
- 모든 GPS 좌표
- 고객명, 전화번호, 주소, 차량번호 같은 직접 식별자

전송 허용 요약 피처:

- `persona_type`
- baseline/recent 총 주행거리
- baseline/recent 외부 주행 비율
- baseline/recent 야간주행 비율
- 100km당 위험행동 요약값
- `risk_change_score`
- `senior_safe_mileage_score`
- `care_decision`
- `reason_codes`

## 10. 예시 레코드

```csv
customer_id,driver_id,persona_type,scenario_id,simulation_seed,observation_period,observation_day_index,service_date,trip_id,trip_sequence,trip_start_time,trip_end_time,start_gps_x,start_gps_y,end_gps_x,end_gps_y,zone_label,destination_type,trip_distance_km,trip_duration_min,avg_speed,max_speed,night_drive_flag,speeding_count,harsh_accel_count,harsh_brake_count,sharp_turn_count,stop_count,night_driving_signal,sudden_braking_signal,route_deviation_signal,reduced_activity_signal,fatigue_indicator,risk_signal_codes,persona_risk_annotation,synthetic_risk_tag
cust_001,driver_001,stable_local_low_mileage,scenario_stable_local_01,20260507,baseline,12,2026-01-12,trip_cust_001_0004,4,2026-01-12 09:10:00,2026-01-12 09:34:00,126.978120,37.566410,126.982300,37.570210,core,market,4.80,24.0,12.0,43.0,0,0,0,0,0,2,0,0,0,0,0,none,no_trip_risk_signal,normal
cust_001,driver_001,stable_local_low_mileage,scenario_stable_local_01,20260507,recent,72,2026-03-13,trip_cust_001_0028,28,2026-03-13 10:20:00,2026-03-13 10:43:00,126.982220,37.570180,126.977980,37.566530,buffer,home,4.60,23.0,12.0,41.0,0,0,0,0,0,1,0,0,0,0,0,none,no_trip_risk_signal,normal
cust_011,driver_011,recent_outer_risk_change,scenario_recent_risk_01,20260507,baseline,44,2026-02-13,trip_cust_011_0018,18,2026-02-13 14:05:00,2026-02-13 14:31:00,127.025100,37.500120,127.030800,37.504100,buffer,clinic,6.40,26.0,14.8,48.0,0,0,0,0,1,2,0,0,0,0,0,none,no_trip_risk_signal,normal
cust_011,driver_011,recent_outer_risk_change,scenario_recent_risk_01,20260507,recent,81,2026-03-22,trip_cust_011_0031,31,2026-03-22 22:40:00,2026-03-22 23:27:00,127.025000,37.500040,127.101900,37.612300,outer,unknown_outer,24.50,47.0,31.3,86.0,1,2,1,3,1,3,1,1,1,0,1,NIGHT_DRIVING|SUDDEN_BRAKING|ROUTE_DEVIATION|FATIGUE_INDICATOR,recent_out_zone_risk_signal,recent_risk_increase
cust_018,driver_018,in_zone_risky_low_mileage,scenario_in_zone_risk_03,20260507,recent,76,2026-03-17,trip_cust_018_0027,27,2026-03-17 16:15:00,2026-03-17 16:31:00,126.913100,37.482900,126.916700,37.486200,core,market,3.70,16.0,13.9,55.0,0,1,1,2,1,4,0,1,0,0,0,SUDDEN_BRAKING,in_zone_braking_risk_signal,in_zone_risk
```

## 11. JSON 고객 메타데이터 예시

`senior_customers.json`은 Trip CSV에 반복 저장하지 않아도 되는 고객 단위 설정을 담습니다.

```json
{
  "customer_id": "cust_011",
  "driver_id": "driver_011",
  "persona_type": "recent_outer_risk_change",
  "scenario_id": "scenario_recent_risk_01",
  "expected_care_decision": "preventive_care",
  "expected_reason_codes": [
    "LOW_MILEAGE_WITH_RECENT_OUT_ZONE_RISK",
    "NIGHT_DRIVING_INCREASE",
    "HARSH_BRAKE_INCREASE"
  ],
  "living_zone_seed": {
    "center_gps_x": 127.025,
    "center_gps_y": 37.5,
    "jitter_m": 350
  }
}
```

## 12. Schema Version

현재 schema version은 `senior-trip-log-fixture/v1`입니다.

호환성을 위해 기존 파이프라인 필수 컬럼은 아래 이름을 그대로 유지합니다.

```text
driver_id
trip_id
trip_start_time
trip_end_time
start_gps_x
start_gps_y
end_gps_x
end_gps_y
trip_distance_km
trip_duration_min
avg_speed
max_speed
speeding_count
harsh_accel_count
harsh_brake_count
sharp_turn_count
stop_count
```

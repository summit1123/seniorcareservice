# 데이터 입력 필드 정의

## 1. 목적

이 문서는 데이터 담당자가 수집한 공공 사업용차량 데이터를 AI 모델 담당자가 바로 사용할 수 있도록 입력 컬럼을 맞추는 기준입니다.

실제 서비스에서는 삼성화재 앱, TMAP, 커넥티드카 등 고객 동의 기반 주행 데이터를 사용합니다.
공모전 검증 단계에서는 공공 사업용차량 데이터를 활용해 생활권 생성과 feature pipeline이 가능한지 확인합니다.

Senior Safe Mileage Score 제품 검증용 합성 fixture의 상세 스키마는 `docs/synthetic-trip-log-fixture-schema.md`를 따릅니다.

## 2. 모델 입력용 Trip 테이블

파일명:

```text
data/raw/trip_sample.csv
```

필수 컬럼:

| 컬럼 | 설명 | 예시 |
|---|---|---|
| driver_id | 익명화된 운전자 ID | driver_001 |
| trip_id | Trip 고유 ID | trip_0001 |
| trip_start_time | 운행 시작 시각 | 2024-01-01 09:10:00 |
| trip_end_time | 운행 종료 시각 | 2024-01-01 09:35:00 |
| start_gps_x | 시작 GPS X 좌표 또는 경도 | 126.9780 |
| start_gps_y | 시작 GPS Y 좌표 또는 위도 | 37.5665 |
| end_gps_x | 종료 GPS X 좌표 또는 경도 | 126.9900 |
| end_gps_y | 종료 GPS Y 좌표 또는 위도 | 37.5700 |
| trip_distance_km | Trip 운행거리 | 8.4 |
| trip_duration_min | Trip 운행시간 | 25 |
| avg_speed | 평균운행속도 | 32.1 |
| max_speed | 최고속도 | 61.0 |
| speeding_count | 과속건수 | 1 |
| harsh_accel_count | 급가속건수 | 0 |
| harsh_brake_count | 급감속건수 | 2 |
| sharp_turn_count | 급좌회전건수 + 급우회전건수 | 1 |
| stop_count | 운행중 정지건수 | 3 |

## 3. 공공데이터 원본 컬럼 매핑

| 모델 컬럼 | 공공데이터 후보 컬럼 |
|---|---|
| driver_id | 자동차등록번호 또는 운수회사코드 + 자동차등록번호 |
| trip_id | 운행일자 + 자동차등록번호 + 시동ON일시 |
| trip_start_time | 시동ON일시 |
| trip_end_time | 시동OFF일시 |
| start_gps_x | 시작 GPS X좌표 |
| start_gps_y | 시작 GPS Y좌표 |
| end_gps_x | 종료 GPS X좌표 |
| end_gps_y | 종료 GPS Y좌표 |
| trip_distance_km | TRIP 운행거리 |
| trip_duration_min | TRIP 운행시간 |
| avg_speed | 평균운행속도 |
| max_speed | 최고속도 |
| speeding_count | 과속건수 |
| harsh_accel_count | 급가속건수 |
| harsh_brake_count | 급감속건수 |
| sharp_turn_count | 급좌회전건수 + 급우회전건수 |
| stop_count | 운행중정지건수 |

### 3.1 실제 CSV 수신 후 검증 명령

팀원이 받은 원본 CSV를 `data/raw/`에 넣은 뒤 아래 명령을 실행합니다.

```bash
python3 scripts/validate_trip_csv_mapping.py data/raw/<원본파일명>.csv --run-pipeline --generate-visuals
```

검증 스크립트는 다음 순서로 판단합니다.

| 단계 | 확인 내용 | 산출물 또는 실패 메시지 |
|---|---|---|
| 헤더 감지 | UTF-8, UTF-8 BOM, CP949, EUC-KR 인코딩과 CSV 구분자를 확인 | `.codex-loop/artifacts/csv-mapping/*-mapping-report.md` |
| 컬럼 매핑 | 원본 컬럼이 모델 표준 컬럼으로 직접 매핑되는지 확인 | 표준 컬럼별 `직접 매핑`, `생성`, `누락` 상태 |
| 보완 가능성 | `trip_id`, `trip_duration_min`, `avg_speed`, `sharp_turn_count`처럼 생성 가능한 컬럼을 계산 | 생성 규칙 기록 |
| 파이프라인 연결 | 매핑이 통과하면 feature, score, decision, figure를 재생성 | `data/processed/*.csv`, `reports/figures/*.svg`, `reports/model_demo_summary.md` |
| 실행 불가 사유 | 필수 컬럼이 없으면 파이프라인을 멈춤 | `필수 컬럼 누락: ...` |

### 3.2 자동 생성 가능한 컬럼

| 표준 컬럼 | 생성 조건 | 생성 방식 |
|---|---|---|
| driver_id | 차량번호 또는 회사코드 + 차량번호 존재 | 원본 식별자를 노출하지 않고 `driver_###`로 익명화 |
| trip_id | 차량 식별자와 운행 시작 시각 존재 | 행 번호와 익명 driver_id 기반으로 생성 |
| trip_duration_min | 시작/종료 시각 존재 | 두 시각의 차이를 분 단위로 계산 |
| avg_speed | 운행거리와 운행시간 존재 | 거리 / 시간으로 계산 |
| sharp_turn_count | 급좌회전건수와 급우회전건수 존재 | 두 컬럼을 합산 |

자동 생성은 파이프라인 연결성을 높이기 위한 정규화 절차입니다. 보험 상품 판단 로직을 바꾸거나 누락 데이터를 임의로 추정하는 절차가 아닙니다.

## 4. 처리 기준

### 4.1 ID 처리

- 차량번호, 사업자등록번호, 운수회사코드 등 식별자는 원문 그대로 쓰지 않습니다.
- 모델에는 `driver_001`, `driver_002` 같은 익명 ID만 사용합니다.

### 4.2 GPS 처리

- 원본 좌표는 생활권 생성에만 사용합니다.
- 모델 feature table에는 원본 좌표 대신 grid 또는 생활권 안/밖 요약값을 사용합니다.
- 발표에서는 개인정보 보호를 위해 원본 좌표를 직접 활용하지 않는다고 설명합니다.

### 4.3 거리와 시간

- `trip_distance_km`는 km 단위로 통일합니다.
- `trip_duration_min`는 분 단위로 통일합니다. 정수와 소수 모두 허용합니다.
- 0km 이하 주행, 0분 이하 주행은 제외하거나 별도 확인 대상으로 둡니다.

### 4.3.1 baseline/recent 분리

- 생활권 생성과 평소패턴 변화 감지는 같은 운전자 또는 차량의 반복 Trip이 있어야 의미가 있습니다.
- 여러 월의 데이터가 있으면 마지막 월을 recent, 이전 월을 baseline으로 봅니다.
- 한 달 데이터만 있으면 같은 driver_id 안에서 시간순으로 앞부분을 baseline, 뒷부분을 recent로 나눕니다.
- 단일 Trip만 있는 driver_id는 평소 대비 변화 감지에 필요한 기준 데이터가 부족하므로 최종 판단표에서 제외될 수 있습니다.

### 4.4 위험운전 이벤트

- 결측치는 0으로 처리합니다.
- 음수 값은 오류로 보고 제거합니다.
- 급좌회전과 급우회전은 합쳐서 `sharp_turn_count`로 사용합니다.

## 5. 모델 feature table 컬럼

Trip 데이터를 가공하면 아래 테이블을 만듭니다.

파일명:

```text
data/processed/model_feature_table.csv
```

컬럼:

| 컬럼 | 설명 |
|---|---|
| driver_id | 익명화된 운전자 ID |
| zone_model_backend | 생활권 생성에 사용한 밀도 기반 클러스터링 백엔드 |
| zone_buffer_m | baseline 목적지 이탈거리 P90 임계값을 반영한 생활권 버퍼 반경 |
| living_zone_departure_p90_raw_m | 고객별 baseline 목적지와 가장 가까운 생활권 중심 간 거리의 원시 P90(m) |
| living_zone_departure_p90_threshold_m | 고객별 생활권 이탈 판정에 쓰는 P90 임계값(m), `max(500m, min(P90, 2km))` 적용 |
| living_zone_departure_threshold_sample_count | P90 임계값 계산에 사용한 baseline 목적지 수 |
| living_zone_departure_threshold_percentile | 생활권 이탈 임계값 계산 분위수, 기본 `0.9` |
| baseline_trip_distance_p90_km | 고객별 baseline Trip 이동거리의 P90 임계값(km) |
| baseline_trip_distance_threshold_sample_count | 이동거리 P90 임계값 계산에 사용한 baseline Trip 수 |
| baseline_trip_distance_threshold_percentile | 이동거리 임계값 계산 분위수, 기본 `0.9` |
| start_living_zone_distance_m | Trip 시작점과 가장 가까운 생활권 중심 간 거리(m) |
| end_living_zone_distance_m | Trip 종료점과 가장 가까운 생활권 중심 간 거리(m) |
| living_zone_segment_max_distance_m | Trip 시작/종료점 중 생활권 중심에서 더 먼 거리(m) |
| living_zone_outside_threshold_m | 생활권 밖 주행 구간 판정 임계값(m), 고객별 `living_zone_departure_p90_threshold_m`와 동일 |
| living_zone_outside_segment_criteria | 생활권 밖 주행 구간 판정 기준. 기본 `start_or_end_distance_gt_living_zone_departure_p90_threshold_m` |
| living_zone_outside_segment_flag | 시작 또는 종료점 중 하나라도 생활권 이탈 P90 임계값 밖이면 1 |
| living_zone_cluster_count | DBSCAN으로 식별된 고객별 생활권 클러스터 수 |
| primary_zone_center_longitude | 방문 빈도가 가장 높은 대표 생활권 중심 경도 |
| primary_zone_center_latitude | 방문 빈도가 가장 높은 대표 생활권 중심 위도 |
| primary_zone_visit_frequency | baseline DBSCAN 입력 visit 중 대표 클러스터가 차지한 비율 |
| primary_zone_radius_m | 대표 생활권 중심점과 클러스터 내 point 간 거리의 P90 기반 반경 지표(m) |
| primary_zone_p90_radius_m | 대표 클러스터 중심 기준 P90 반경(m) |
| primary_zone_outer_extent_radius_m | 대표 클러스터 중심에서 가장 먼 point까지의 외곽 반경(m) |
| primary_zone_boundary_area_km2 | 대표 클러스터 point 분포의 경계 박스 면적(km2) |
| primary_zone_boundary_width_m | 대표 클러스터 point 분포의 경계 박스 동서 폭(m) |
| primary_zone_boundary_height_m | 대표 클러스터 point 분포의 경계 박스 남북 높이(m) |
| living_zone_clusters_json | 클러스터별 중심점, 방문/point 빈도, start/end point 수, 평균/중앙값/P90/최대 반경, 외곽 반경, 경계 박스와 대표 반경 지표 JSON |
| total_km | 총 주행거리 |
| trip_count | Trip 수 |
| avg_trip_km | 평균 Trip 거리 |
| speeding_per_100km | 100km당 과속건수 |
| harsh_accel_per_100km | 100km당 급가속건수 |
| harsh_brake_per_100km | 100km당 급감속건수 |
| sharp_turn_per_100km | 100km당 급회전건수 |
| core_zone_ratio | DBSCAN 중심 주변 최소 500m 핵심 생활권 주행 비율 |
| buffer_zone_ratio | 핵심 생활권 밖이지만 P90 버퍼 안 주행 비율 |
| in_zone_ratio | 핵심 또는 버퍼 생활권 안 주행 비율 |
| out_zone_ratio | P90 버퍼 밖 외부 주행 비율 |
| living_zone_outside_segment_criteria | 생활권 밖 주행 구간 집계에 사용한 판정 기준 |
| living_zone_outside_segment_count | recent 기간 생활권 밖 주행 구간 Trip 수 |
| living_zone_outside_segment_ratio | recent 기간 전체 Trip 중 생활권 밖 주행 구간 비율 |
| living_zone_outside_segment_km | recent 기간 생활권 밖 주행 구간 이동거리 |
| living_zone_outside_segment_distance_ratio | recent 기간 전체 이동거리 중 생활권 밖 주행 구간 이동거리 비율 |
| living_zone_outside_segment_night_ratio | recent 생활권 밖 주행 구간 중 야간 주행거리 비율 |
| baseline_living_zone_outside_segment_ratio | baseline 기간 전체 Trip 중 생활권 밖 주행 구간 비율 |
| baseline_living_zone_outside_segment_distance_ratio | baseline 기간 전체 이동거리 중 생활권 밖 주행 구간 이동거리 비율 |
| baseline_living_zone_outside_segment_risk_events_per_100km | baseline 생활권 밖 주행 구간 100km당 위험 이벤트 |
| baseline_living_zone_outside_segment_night_ratio | baseline 생활권 밖 주행 구간 중 야간 주행거리 비율 |
| living_zone_outside_segment_ratio_delta | recent 생활권 밖 구간 Trip 비율 - baseline 비율 |
| living_zone_outside_segment_distance_ratio_delta | recent 생활권 밖 구간 이동거리 비율 - baseline 비율 |
| living_zone_outside_segment_risk_events_delta_per_100km | recent 생활권 밖 구간 100km당 위험 이벤트 - baseline 값 |
| living_zone_outside_segment_night_ratio_delta | recent 생활권 밖 구간 야간 비율 - baseline 값 |
| living_zone_outside_segment_risk_change_score | 생활권 밖 주행 구간의 노출/위험/야간 변화 기반 0~100 위험 변화 지표 |
| route_repeat_ratio | 반복 경로 비율 |
| new_destination_count | 신규 목적지 수 |
| zone_stability_score | 생활권 안정성 점수 |

## 5.1 고객별 이동 이력 집계 테이블 컬럼

파일명:

```text
data/processed/movement_history_table.csv
```

컬럼:

| 컬럼 | 설명 |
|---|---|
| customer_id | 비식별 고객 ID |
| driver_id | 익명화된 운전자 ID |
| persona_type | 합성 시뮬레이션 페르소나 유형 |
| period | baseline 또는 recent 관측 기간 |
| observation_days | 관측 기간 일수 |
| active_day_count | 실제 주행이 있었던 일수 |
| trip_count | 기간 내 Trip 수 |
| trip_frequency_per_day | 관측 일수 기준 일평균 주행 빈도 |
| trip_frequency_per_active_day | 실제 주행일 기준 일평균 주행 빈도 |
| baseline_movement_frequency_p90_per_day | 고객별 baseline 주행일의 일별 Trip 수 P90 임계값 |
| baseline_movement_frequency_threshold_sample_count | 이동 빈도 P90 임계값 계산에 사용한 baseline 주행일 수 |
| baseline_movement_frequency_threshold_percentile | 이동 빈도 임계값 계산 분위수 |
| total_distance_km | 기간 내 총 이동 거리 |
| avg_trip_distance_km | Trip당 평균 이동 거리 |
| avg_daily_distance_km | 관측 일수 기준 일평균 이동 거리 |
| core_zone_trip_count | 핵심 생활권 Trip 수 |
| buffer_zone_trip_count | 버퍼 생활권 Trip 수 |
| in_zone_trip_count | 생활권 안 Trip 수 |
| out_zone_trip_count | 생활권 밖 Trip 수 |
| out_zone_trip_ratio | 생활권 밖 Trip 비율 |
| out_zone_distance_km | 생활권 밖 이동 거리 |
| out_zone_distance_ratio | 총 이동거리 중 생활권 밖 이동거리 비율 |
| living_zone_outside_segment_criteria | 생활권 밖 주행 구간 판정 기준 |
| living_zone_outside_segment_count | 기간 내 생활권 밖 주행 구간 Trip 수 |
| living_zone_outside_segment_ratio | 기간 내 전체 Trip 중 생활권 밖 주행 구간 비율 |
| living_zone_outside_segment_km | 기간 내 생활권 밖 주행 구간 이동 거리 |
| living_zone_outside_segment_distance_ratio | 기간 내 전체 이동거리 중 생활권 밖 주행 구간 이동거리 비율 |
| living_zone_outside_segment_night_ratio | 기간 내 생활권 밖 주행 구간 중 야간 주행거리 비율 |
| living_zone_departure_p90_raw_m | 고객별 baseline 목적지 이탈거리 원시 P90(m) |
| living_zone_departure_p90_threshold_m | 고객별 생활권 이탈 판정 P90 임계값(m) |
| living_zone_departure_threshold_sample_count | P90 임계값 계산에 사용한 baseline 목적지 수 |
| living_zone_departure_threshold_percentile | 생활권 이탈 임계값 계산 분위수 |
| baseline_trip_distance_p90_km | 고객별 baseline Trip 이동거리의 P90 임계값(km) |
| baseline_trip_distance_threshold_sample_count | 이동거리 P90 임계값 계산에 사용한 baseline Trip 수 |
| baseline_trip_distance_threshold_percentile | 이동거리 임계값 계산 분위수 |
| living_zone_departure_count | 생활권 이탈 Trip 수 |
| living_zone_departure_distance_km | 생활권 이탈 이동 거리 |
| living_zone_departure_frequency_per_day | 관측 일수 기준 일평균 생활권 이탈 빈도 |
| route_repeat_count | 반복 경로 Trip 수 |
| route_repeat_ratio | 반복 경로 Trip 비율 |
| new_destination_count | 신규 목적지 수 |

## 5.1.1 고객별 생활권 분석 저장 레코드

파일명:

```text
data/processed/customer_living_zone_records.json
```

이 파일은 `zone_feature_table.csv`의 고객별 평면 feature를 화면과 Agent 계약에서 바로 읽기 쉬운 JSON 구조로 저장합니다. 로컬 웹앱 조인과 생활권 시각화를 위해 `customer_id`, `driver_id`, 생활권 중심 좌표를 포함할 수 있지만, 외부 LLM API에는 이 레코드 전체를 보내지 않습니다. LLM 리포트 요청에는 각 레코드의 `privacy_filtered_features`만 사용할 수 있습니다.

최상위 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `schema_version` | string | 현재 `customer-living-zone-result/v1` |
| `customer_id` | string | 로컬 조인용 비식별 고객 ID |
| `driver_id` | string | 로컬 조인용 익명 운전자 ID |
| `persona_type` | string | 6개 합성 페르소나 중 하나 |
| `observation_period` | object | baseline 60일, recent 30일, 생활권 생성 기준 기간과 점수 산정 기간 |
| `analysis_method` | object | DBSCAN/P90 분석 파라미터와 버퍼 clamp 기준 |
| `living_zone` | object | 고객별 생활권 분석 결과 본문 |
| `privacy_filtered_features` | object | 외부 LLM 전송 허용 요약 피처. 고객/운전자/trip ID, 정확한 GPS 좌표, 원본 trip 시각을 포함하지 않음 |

`observation_period` 필드:

| 필드 | 설명 |
|---|---|
| `baseline_days` | 생활권 기준 생성에 사용하는 baseline 관측 일수, 고정 60 |
| `recent_days` | 최근 점수 산정 관측 일수, 고정 30 |
| `source_period_for_zone` | DBSCAN 생활권 중심 생성 기준 기간, 기본 `baseline` |
| `scored_period` | 생활권 안/밖 비율과 안정성 점수 산정 기간, 기본 `recent` |

`analysis_method` 필드:

| 필드 | 설명 |
|---|---|
| `zone_model_backend` | 생활권 생성 백엔드, 기본 `dbscan_density_cluster` |
| `dbscan_eps` | DBSCAN 이웃 반경 파라미터 |
| `dbscan_min_samples` | DBSCAN 클러스터 최소 point 수 |
| `buffer_percentile` | 생활권 버퍼 계산 분위수, 기본 0.9 |
| `buffer_min_m` | 생활권 버퍼 하한, 500m |
| `buffer_max_m` | 생활권 버퍼 상한, 2,000m |

`living_zone` 필드:

| 필드 | 설명 |
|---|---|
| `cluster_count` | DBSCAN으로 식별된 고객별 생활권 클러스터 수 |
| `primary_zone` | 대표 생활권 중심 좌표, 방문 빈도, P90 반경, 외곽 반경, 경계 박스 면적/폭/높이 |
| `buffer` | baseline 목적지 이탈거리 P90 원시값, clamp 적용 임계값, sample 수, 분위수 |
| `baseline_thresholds` | baseline Trip 거리 P90 임계값, sample 수, 분위수 |
| `recent_zone_mix` | recent 기간 `core`, `buffer`, `in_zone`, `out_zone` 주행 비율 |
| `outside_living_zone_segments` | 생활권 밖 주행 구간 판정 기준, 임계값, recent 구간 수/비율/거리 |
| `route_repeat_ratio` | recent 기간 baseline 반복 경로 비율 |
| `new_destination_count` | recent 기간 신규 목적지 grid 수 |
| `zone_stability_score` | 생활권 안정성 점수 |
| `clusters` | 대표/보조 생활권 클러스터 목록. 각 클러스터는 중심, 방문/point 빈도, radius/boundary 지표를 포함하고 원본 trip point 목록은 저장하지 않음 |

## 5.2 평소패턴 변화 감지 테이블 컬럼

파일명:

```text
data/processed/pattern_change_score.csv
```

컬럼:

| 컬럼 | 설명 |
|---|---|
| driver_id | 익명화된 운전자 ID |
| pattern_change_score | 최근 주행이 baseline 대비 얼마나 달라졌는지 나타내는 0~100 점수 |
| anomaly_flag | 변화 점수가 예방 케어 후보 기준 이상인지 여부 |
| pattern_model_backend | 이상탐지 점수를 만든 모델 백엔드 |
| top_change_signal | 최근 변화 점수에 가장 크게 기여한 feature 신호 |
| top_change_contribution | 주요 변화 신호의 평균 기여도 |

## 6. 최종 판단 테이블 컬럼

파일명:

```text
data/processed/decision_table.csv
```

컬럼:

| 컬럼 | 설명 |
|---|---|
| driver_id | 익명화된 운전자 ID |
| safe_driving_score | 안전운전 점수 |
| familiar_zone_score | 생활권 안정성 점수 |
| pattern_change_score | 평소패턴 변화 점수 |
| out_zone_behavior_risk | 생활권 밖 위험행동 점수 |
| care_trigger | 예방 케어 여부 |
| living_zone_outside_segment_criteria | 생활권 밖 주행 구간 판정 기준 |
| living_zone_outside_segment_count | recent 기간 생활권 밖 주행 구간 Trip 수 |
| living_zone_outside_segment_ratio | recent 기간 생활권 밖 주행 구간 비율 |
| living_zone_outside_segment_km | recent 기간 생활권 밖 주행 구간 이동거리 |
| living_zone_outside_segment_distance_ratio | recent 기간 생활권 밖 주행 구간 이동거리 비율 |
| living_zone_outside_segment_night_ratio | recent 생활권 밖 주행 구간 야간 비율 |
| baseline_living_zone_outside_segment_ratio | baseline 생활권 밖 주행 구간 비율 |
| baseline_living_zone_outside_segment_distance_ratio | baseline 생활권 밖 주행 구간 이동거리 비율 |
| baseline_living_zone_outside_segment_risk_events_per_100km | baseline 생활권 밖 구간 100km당 위험 이벤트 |
| baseline_living_zone_outside_segment_night_ratio | baseline 생활권 밖 구간 야간 비율 |
| living_zone_outside_segment_ratio_delta | 생활권 밖 구간 Trip 비율 변화 |
| living_zone_outside_segment_distance_ratio_delta | 생활권 밖 구간 이동거리 비율 변화 |
| living_zone_outside_segment_risk_events_delta_per_100km | 생활권 밖 구간 100km당 위험 이벤트 변화 |
| living_zone_outside_segment_night_ratio_delta | 생활권 밖 구간 야간 비율 변화 |
| living_zone_outside_segment_risk_change_score | 생활권 밖 주행 구간 위험 변화 지표 |
| outside_living_zone_segments_json | 생활권 밖 주행 구간 판정 기준과 플래그 집계 JSON |
| decision | 추가 리워드, 기본 유지, 예방 케어 |
| reason_1 | 판단 이유 1 |
| reason_2 | 판단 이유 2 |
| reason_3 | 판단 이유 3 |

## 7. 팀원 전달용 요약

데이터는 우선 Trip 단위로 정리합니다.

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

원본 좌표는 생활권 생성용으로만 쓰고, 최종 모델에는 핵심/버퍼/외부 생활권 비율과 위험운전 요약값을 넣습니다.

실제 CSV가 들어오면 모델 담당자는 먼저 매핑 리포트를 남깁니다. 리포트가 통과하지 못한 경우에는 누락 컬럼을 보완한 뒤 다시 실행하며, 원본 데이터를 직접 수정하지 않고 표준화된 중간 CSV를 생성해 파이프라인에 연결합니다.

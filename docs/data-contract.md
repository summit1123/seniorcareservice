# 데이터 입력 필드 정의

## 1. 목적

이 문서는 데이터 담당자가 수집한 공공 사업용차량 데이터를 AI 모델 담당자가 바로 사용할 수 있도록 입력 컬럼을 맞추는 기준입니다.

실제 서비스에서는 삼성화재 앱, TMAP, 커넥티드카 등 고객 동의 기반 주행 데이터를 사용합니다.
공모전 검증 단계에서는 공공 사업용차량 데이터를 활용해 생활권 생성과 feature pipeline이 가능한지 확인합니다.

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
- `trip_duration_min`는 분 단위로 통일합니다.
- 0km 이하 주행, 0분 이하 주행은 제외하거나 별도 확인 대상으로 둡니다.

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
| total_km | 총 주행거리 |
| trip_count | Trip 수 |
| avg_trip_km | 평균 Trip 거리 |
| speeding_per_100km | 100km당 과속건수 |
| harsh_accel_per_100km | 100km당 급가속건수 |
| harsh_brake_per_100km | 100km당 급감속건수 |
| sharp_turn_per_100km | 100km당 급회전건수 |
| in_zone_ratio | 생활권 안 주행 비율 |
| out_zone_ratio | 생활권 밖 주행 비율 |
| route_repeat_ratio | 반복 경로 비율 |
| new_destination_count | 신규 목적지 수 |
| zone_stability_score | 생활권 안정성 점수 |

## 5.1 평소패턴 변화 감지 테이블 컬럼

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

원본 좌표는 생활권 생성용으로만 쓰고, 최종 모델에는 생활권 안/밖 비율과 위험운전 요약값을 넣습니다.

실제 CSV가 들어오면 모델 담당자는 먼저 매핑 리포트를 남깁니다. 리포트가 통과하지 못한 경우에는 누락 컬럼을 보완한 뒤 다시 실행하며, 원본 데이터를 직접 수정하지 않고 표준화된 중간 CSV를 생성해 파이프라인에 연결합니다.

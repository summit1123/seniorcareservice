# 구현 마일스톤

이 문서는 앞으로 실제 모델 견본을 만들 때 커밋을 어떻게 쪼갤지 정리한 실행 계획입니다.

## 1. 구현 원칙

- 한 커밋은 한 가지 작업만 담습니다.
- 데이터, feature, 모델, 점수, 판단 로직을 섞어서 커밋하지 않습니다.
- 각 단계는 결과 CSV 또는 실행 가능한 Python 파일을 남깁니다.
- 실제 공공데이터가 오기 전에는 샘플 데이터로 먼저 전체 흐름을 완성합니다.

## 2. 세부 커밋 계획

### 2.1 샘플 데이터

커밋:

```text
data : Trip 샘플 데이터 추가
```

파일:

```text
data/raw/trip_sample.csv
```

완료 기준:

- 운전자 3명 이상
- 운전자별 Trip 10개 이상
- 안정 운전, 생활권 밖 증가, 위험행동 증가 케이스 포함

### 2.2 데이터 로더

커밋:

```text
feat : Trip 데이터 로더 추가
```

파일:

```text
src/data/load_trips.py
```

완료 기준:

- CSV를 읽어 표준 컬럼으로 변환
- 필수 컬럼 누락 여부 확인
- 거리, 시간, 이벤트 음수값 검증

### 2.3 생활권 feature

커밋:

```text
feat : 생활권 생성 feature 계산 추가
```

파일:

```text
src/features/zone_features.py
data/processed/zone_feature_table.csv
```

완료 기준:

- GPS grid 변환
- DBSCAN clustering
- baseline 목적지 이탈거리 P90 기반 생활권 버퍼 계산
- core_zone_ratio, buffer_zone_ratio 계산
- in_zone_ratio, out_zone_ratio 계산
- route_repeat_ratio 계산

### 2.4 운전행동 feature

커밋:

```text
feat : 운전행동 feature 집계 추가
```

파일:

```text
src/features/driving_features.py
data/processed/driving_feature_table.csv
```

완료 기준:

- speeding_per_100km 계산
- harsh_accel_per_100km 계산
- harsh_brake_per_100km 계산
- sharp_turn_per_100km 계산
- avg_trip_km 계산

### 2.5 모델 feature table

커밋:

```text
feat : 모델 feature table 생성 추가
```

파일:

```text
src/features/build_model_features.py
data/processed/model_feature_table.csv
```

완료 기준:

- 생활권 feature와 운전행동 feature 결합
- driver_id 단위 모델 입력 테이블 생성
- feature 컬럼 순서 고정

### 2.6 평소패턴 변화 감지 모델

커밋:

```text
feat : 평소패턴 변화 감지 모델 추가
```

파일:

```text
src/models/pattern_model.py
data/processed/pattern_change_score.csv
```

완료 기준:

- Isolation Forest 적용
- pattern_change_score 생성
- anomaly_flag 생성
- 결과가 운전자별로 저장됨

### 2.7 점수 계산

커밋:

```text
feat : 최종 점수 계산 추가
```

파일:

```text
src/models/score_rules.py
data/processed/score_table.csv
```

완료 기준:

- Safe Driving Score 생성
- Familiar Zone Score 생성
- Pattern Change Score 반영
- Out-Zone Behavior Risk 생성

### 2.8 상품 판단 로직

커밋:

```text
feat : 리워드 및 케어 판단 로직 추가
```

파일:

```text
src/product/decision_rules.py
data/processed/decision_table.csv
```

완료 기준:

- 추가 리워드 판단
- 기본 유지 판단
- 예방 케어 판단
- reason_1, reason_2, reason_3 생성

### 2.9 실행 스크립트

커밋:

```text
feat : 모델 파이프라인 실행 스크립트 추가
```

파일:

```text
src/run_pipeline.py
```

완료 기준:

- 샘플 데이터에서 최종 decision_table까지 한 번에 생성
- 실행 방법이 README에 설명됨

### 2.10 결과 리포트

커밋:

```text
report : 모델 결과 요약 리포트 추가
```

파일:

```text
reports/model_demo_summary.md
```

완료 기준:

- 고객 3명 예시 포함
- 각 고객별 점수와 판단 이유 포함
- 발표자료에 그대로 옮길 수 있는 문장 포함

## 3. 첫 구현 순서

가장 먼저 아래 네 커밋까지 완성합니다.

```text
data : Trip 샘플 데이터 추가
feat : Trip 데이터 로더 추가
feat : 생활권 생성 feature 계산 추가
feat : 운전행동 feature 집계 추가
```

여기까지 끝나면 모델 학습 전 단계인 feature pipeline이 완성됩니다.

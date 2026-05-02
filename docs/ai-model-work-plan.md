# AI 모델 작업계획

## 1. 목표

이 프로젝트의 AI는 고객 사고를 직접 예측하는 용도가 아닙니다.

목표는 다음 세 가지입니다.

1. 고객의 반복 주행 패턴을 바탕으로 생활권을 생성합니다.
2. 고객의 평소 운전 패턴을 학습하고 최근 주행 변화가 있는지 감지합니다.
3. 감지 결과를 추가 리워드 또는 예방 케어 판단으로 연결합니다.

최종 산출물은 아래 세 가지입니다.

```text
model_feature_table.csv
score_table.csv
decision_table.csv
```

## 2. 전체 파이프라인

```text
Trip 원본 데이터
-> 데이터 정제
-> GPS grid 변환
-> 생활권 생성
-> 운전행동 feature 집계
-> 평소패턴 변화 감지
-> 점수 계산
-> 리워드/케어 판단
```

## 3. 단계별 작업계획

### 3.1 데이터 입력 구조 확정

목표:

- 팀원이 수집하는 공공 사업용차량 데이터를 우리 모델 입력 형식으로 맞춥니다.

작업:

- 필요한 컬럼 정의
- 원본 컬럼과 모델 컬럼 매핑
- 결측치와 이상치 처리 기준 작성

산출물:

```text
docs/data-contract.md
```

예상 커밋:

```text
docs : 데이터 입력 필드 정의
```

### 3.2 샘플 Trip 데이터 준비

목표:

- 실제 데이터가 오기 전에도 전체 모델 흐름이 돌아가도록 작은 샘플 데이터를 만듭니다.

작업:

- 운전자 3명 이상
- 운전자별 Trip 10개 이상
- 생활권 안 주행, 생활권 밖 주행, 위험행동 증가 사례 포함

산출물:

```text
data/raw/trip_sample.csv
```

예상 커밋:

```text
data : Trip 샘플 데이터 추가
```

### 3.3 생활권 생성 feature 계산

목표:

- 시작/종료 GPS를 기반으로 고객별 자주 가는 영역을 찾습니다.

사용 모델:

```text
DBSCAN
```

작업:

- GPS 좌표를 grid로 변환
- driver_id별 출발/도착 지점 clustering
- Trip별 in_zone_flag, out_zone_flag 생성
- 운전자별 in_zone_ratio, out_zone_ratio 계산

산출물:

```text
data/processed/zone_feature_table.csv
src/features/zone_features.py
```

예상 커밋:

```text
feat : 생활권 생성 feature 계산 추가
```

### 3.4 운전행동 feature 집계

목표:

- 과속, 급가속, 급감속, 급회전 등 위험운전 행동을 주행거리 기준으로 정규화합니다.

작업:

- 총 주행거리 계산
- Trip 수 계산
- 과속/100km 계산
- 급가속/100km 계산
- 급감속/100km 계산
- 급회전/100km 계산

산출물:

```text
data/processed/driving_feature_table.csv
src/features/driving_features.py
```

예상 커밋:

```text
feat : 운전행동 feature 집계 추가
```

### 3.5 모델 feature table 생성

목표:

- 생활권 feature와 운전행동 feature를 합쳐 AI 모델 입력 테이블을 만듭니다.

작업:

- driver_id 기준 feature 결합
- 모델 입력 컬럼 순서 고정
- feature 결측치 처리

산출물:

```text
data/processed/model_feature_table.csv
src/features/build_model_features.py
```

예상 커밋:

```text
feat : 모델 feature table 생성 추가
```

### 3.6 평소패턴 변화 감지 모델

목표:

- 사고 라벨 없이도 고객별 평소와 다른 운전 변화를 감지합니다.

사용 모델:

```text
Isolation Forest
```

입력 feature:

```text
in_zone_ratio
out_zone_ratio
speeding_per_100km
harsh_accel_per_100km
harsh_brake_per_100km
sharp_turn_per_100km
route_repeat_ratio
new_destination_count
```

출력:

```text
pattern_change_score
anomaly_flag
```

산출물:

```text
data/processed/pattern_change_score.csv
src/models/pattern_model.py
notebooks/01_pattern_model_demo.ipynb
```

예상 커밋:

```text
feat : 평소패턴 변화 감지 모델 추가
```

### 3.7 최종 점수 계산

목표:

- 모델 결과를 상품 판단에 쓰기 쉬운 점수로 변환합니다.

점수:

| 점수 | 의미 |
|---|---|
| Safe Driving Score | 위험운전 행동이 적은지 |
| Familiar Zone Score | 생활권 중심 주행이 안정적인지 |
| Pattern Change Score | 최근 운전이 평소와 얼마나 다른지 |
| Out-Zone Behavior Risk | 생활권 밖 위험행동이 얼마나 큰지 |

산출물:

```text
data/processed/score_table.csv
src/models/score_rules.py
```

예상 커밋:

```text
feat : 최종 점수 계산 추가
```

### 3.8 리워드 및 예방 케어 판단

목표:

- 점수 결과를 실제 상품 판단으로 바꿉니다.

판단 유형:

| 유형 | 의미 |
|---|---|
| 추가 리워드 | 생활권 중심 주행이고 위험행동이 낮음 |
| 기본 유지 | 특이 변화가 크지 않음 |
| 예방 케어 | 평소와 다른 변화와 위험행동 증가가 함께 나타남 |

산출물:

```text
data/processed/decision_table.csv
src/product/decision_rules.py
```

예상 커밋:

```text
feat : 리워드 및 케어 판단 로직 추가
```

### 3.9 결과 리포트 작성

목표:

- 모델 견본 결과를 팀원과 발표자료에 바로 쓸 수 있게 정리합니다.

내용:

- 입력 데이터 구조
- 생성된 feature
- 모델 결과 예시
- 고객별 판단 예시
- 한계와 실제 서비스 적용 시 보완점

산출물:

```text
reports/model_demo_summary.md
```

예상 커밋:

```text
report : 모델 결과 요약 리포트 추가
```

## 4. 작업 우선순위

1. 데이터 계약서 작성
2. 샘플 데이터 생성
3. 생활권 feature 계산
4. 운전행동 feature 계산
5. Isolation Forest 모델 연결
6. 점수 계산
7. 판단 테이블 생성
8. 리포트 작성

## 5. 중요한 표현 기준

발표와 문서에서는 아래처럼 표현합니다.

```text
AI는 사고 발생 여부를 직접 예측하는 것이 아니라,
고객의 생활권과 평소 운전패턴을 학습해 최근 변화와 위험행동 증가를 감지한다.
```

TAAS 또는 공공 사고통계는 아래처럼 표현합니다.

```text
TAAS 사고통계는 개인 예측 라벨이 아니라,
과속, 안전거리 미확보, 야간, 노인운전자 사고 등 위험행동의 가중치 근거로 활용한다.
```

# 모델 견본 결과 요약

## 심사위원 질문 대응

| 질문 | 제출 패키지의 답변 | 확인 산출물 |
|---|---|---|
| AI가 무엇을 했는가 | DBSCAN 방식 밀도 기반 클러스터링으로 고객별 생활권 중심을 만들고, 최근 trip vector가 baseline보다 얼마나 달라졌는지 이상탐지 점수로 계산했다 | `zone_feature_table.csv`, `pattern_change_score.csv` |
| 왜 사고 예측이 아닌가 | 개인 사고 라벨 없이 과장된 예측을 하지 않고, 평소패턴 변화와 위험행동 증가를 분리해 예방 케어 후보만 찾는다 | `score_table.csv`, `decision_table.csv` |
| 결과를 어떻게 설명하는가 | 고객별 score, care trigger, reason code, top change signal을 함께 남겨 직원용 리포트와 고객 안내 문구로 전환할 수 있게 했다 | `decision_table.csv`, `reports/model_demo_summary.md` |

## 실행 결과

| 고객 | Safe Driving | Familiar Zone | Pattern Change | Out-Zone Risk | 최종 판단 |
|---|---:|---:|---:|---:|---|
| driver_001 | 90.9 | 100.0 | 5.5 | 7.9 | 추가 리워드 |
| driver_002 | 92.2 | 53.5 | 32.5 | 38.8 | 기본 유지 |
| driver_003 | 11.8 | 6.5 | 100.0 | 100.0 | 예방 케어 |

## 이상탐지 설명 신호

| 고객 | 변화 점수 | 이상 여부 | 주요 변화 신호 | 모델 백엔드 |
|---|---:|---:|---|---|
| driver_001 | 5.5 | 0 | 급감속 증가 (`harsh_brake_increase`) | baseline_distance_anomaly |
| driver_002 | 32.5 | 0 | 생활권 밖 주행 증가 (`out_zone_increase`) | baseline_distance_anomaly |
| driver_003 | 100.0 | 1 | 과속 증가 (`speeding_increase`) | baseline_distance_anomaly |

## 데이터 기준

- 입력 CSV는 `docs/data-contract.md`의 표준 Trip schema를 기준으로 검증한다.
- 팀원이 받은 공공 사업용차량 CSV는 `scripts/validate_trip_csv_mapping.py`로 원본 컬럼 매핑, 필수 컬럼 누락, 파이프라인 실행 가능 여부를 먼저 확인한다.
- 원본 차량 식별자는 `driver_###` 형식으로 익명화하고, 원본 좌표는 생활권 feature 생성 뒤 최종 모델 feature table에 직접 남기지 않는다.
- 현재 수치는 실제 보험료 산정값이 아니라 생활권 생성, 평소패턴 변화 감지, 예방 케어 판단 구조의 구현 견본이다.

## 해석

- `driver_001`은 생활권 중심 주행과 낮은 위험행동으로 추가 리워드 대상이다.
- `driver_002`는 생활권 밖 주행이 일부 있지만 위험행동 변화가 크지 않아 기본 유지 대상이다.
- `driver_003`은 생활권 밖 주행, 위험행동, 평소패턴 변화가 동시에 높아 예방 케어 대상이다.

## 발표에 사용할 문장

기존 마일리지·착한운전 특약이 거리와 일반 안전점수 중심이라면, 이 모델은 DBSCAN 생활권과 평소패턴 이상탐지를 결합해 익숙한 생활권 안에서의 안정 운전은 추가 리워드로, 평소와 다른 위험 변화는 예방 케어로 분리합니다.

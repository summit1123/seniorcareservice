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
| driver_074 | 8.9 | 0.0 | 74.2 | 26.1 | 기본 유지 |
| driver_075 | 27.2 | 80.0 | 31.6 | 22.2 | 기본 유지 |
| driver_076 | 11.4 | 0.0 | 35.5 | 97.1 | 기본 유지 |
| driver_077 | 26.4 | 60.0 | 18.5 | 9.0 | 기본 유지 |
| driver_078 | 8.2 | 70.0 | 90.9 | 44.3 | 기본 유지 |
| driver_079 | 42.0 | 0.0 | 1.4 | 0.0 | 기본 유지 |

## 이상탐지 설명 신호

| 고객 | 변화 점수 | 이상 여부 | 주요 변화 신호 | 모델 백엔드 |
|---|---:|---:|---|---|
| driver_074 | 74.2 | 1 | 급감속 증가 (`harsh_brake_increase`) | baseline_distance_anomaly |
| driver_075 | 31.6 | 0 | 급감속 증가 (`harsh_brake_increase`) | baseline_distance_anomaly |
| driver_076 | 35.5 | 0 | 급감속 증가 (`harsh_brake_increase`) | baseline_distance_anomaly |
| driver_077 | 18.5 | 0 | 급감속 증가 (`harsh_brake_increase`) | baseline_distance_anomaly |
| driver_078 | 90.9 | 1 | 급감속 증가 (`harsh_brake_increase`) | baseline_distance_anomaly |
| driver_079 | 1.4 | 0 | 급회전 증가 (`sharp_turn_increase`) | baseline_distance_anomaly |

## 데이터 기준

- 입력 CSV는 `docs/data-contract.md`의 표준 Trip schema를 기준으로 검증한다.
- 팀원이 받은 공공 사업용차량 CSV는 `scripts/validate_trip_csv_mapping.py`로 원본 컬럼 매핑, 필수 컬럼 누락, 파이프라인 실행 가능 여부를 먼저 확인한다.
- 원본 차량 식별자는 `driver_###` 형식으로 익명화하고, 원본 좌표는 생활권 feature 생성 뒤 최종 모델 feature table에 직접 남기지 않는다.
- 현재 수치는 실제 보험료 산정값이 아니라 생활권 생성, 평소패턴 변화 감지, 예방 케어 판단 구조의 구현 견본이다.

## 해석

- 이번 실행에서는 총 6명의 판단 결과가 생성되었고, 결과 분포는 기본 유지 6명입니다.
- 같은 운전자에 대해 baseline과 recent trip이 모두 있는 경우에만 생활권 안정성과 평소패턴 변화 해석이 유효합니다.
- 단일 trip만 있는 운전자는 생활권 학습과 평소 대비 변화 감지에 필요한 기준 데이터가 부족하므로 최종 판단표에서 제외됩니다.

## 발표에 사용할 문장

기존 마일리지·착한운전 특약이 거리와 일반 안전점수 중심이라면, 이 모델은 DBSCAN 생활권과 평소패턴 이상탐지를 결합해 익숙한 생활권 안에서의 안정 운전은 추가 리워드로, 평소와 다른 위험 변화는 예방 케어로 분리합니다.

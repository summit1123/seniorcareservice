# Senior Care Service

생활권 기반 시니어 안심주행 특약의 AI 모델 검증용 저장소입니다.

이 프로젝트는 사고 발생 여부를 직접 예측하는 모델을 먼저 만들기보다, 고객의 평소 운전 패턴과 최근 운전 패턴의 차이를 학습해 추가 리워드 또는 예방 케어 판단에 활용하는 구조를 검증합니다.

## 핵심 방향

- 생활권 생성: 고객이 자주 출발하거나 도착하는 지점과 반복 경로를 기반으로 생활권을 생성합니다.
- 평소패턴 학습: 고객별 정상 운전 패턴을 학습하고 최근 운전이 평소와 달라졌는지 감지합니다.
- 위험행동 점수화: 과속, 급가속, 급감속, 급회전 등 위험운전 행동을 주행거리 기준으로 정규화합니다.
- 상품 적용: 마일리지 할인은 유지하고, AI 결과는 추가 리워드 또는 예방 케어 안내에 활용합니다.

## 현재 목표

1. 공공 사업용차량 주행 데이터와 동일한 구조의 샘플 데이터를 준비합니다.
2. Trip 데이터를 driver-period 단위 feature table로 변환합니다.
3. DBSCAN 기반 생활권 생성 견본을 만듭니다.
4. Isolation Forest 기반 평소패턴 변화 감지 견본을 만듭니다.
5. 최종 score table과 decision table을 생성합니다.

## 디렉터리 구조

```text
data/
  raw/            원본 데이터
  processed/      가공 데이터와 feature table
docs/             작업계획, 데이터 계약, 커밋 규칙
notebooks/        탐색 및 모델 검증 노트북
reports/          결과 리포트
src/              재사용 가능한 Python 코드
```

## 커밋 방식

커밋은 작은 단위로 쪼개서 남깁니다.

```text
type : 한국어 설명
```

예시:

```text
docs : AI 모델 작업계획 추가
feat : 생활권 생성 feature 계산 추가
test : 점수 계산 테스트 추가
```

## Ralph / SummitHarness

이 저장소는 SummitHarness 기반 Ralph loop를 사용할 수 있도록 bootstrap되어 있습니다.

환경 점검:

```bash
python3 scripts/preflight.py run
```

컨텍스트 갱신:

```bash
python3 scripts/context_engine.py refresh --source setup
```

Ralph 실행:

```bash
./ralph.sh
```

시각화 자료 생성:

```bash
python3 scripts/generate_visual_assets.py
```

모델 파이프라인 실행:

```bash
python3 -m src.run_pipeline
```

분석 결과 시각화 생성:

```bash
python3 scripts/generate_analysis_outputs.py
```

TAAS 사고통계 가중치 생성:

```bash
python3 scripts/build_taas_weights.py
```

생성되는 기본 자료:

```text
reports/figures/01_ai_pipeline.svg
reports/figures/02_score_structure.svg
reports/figures/03_decision_flow.svg
reports/figures/04_driver_score_comparison.svg
reports/figures/05_decision_result_summary.svg
reports/model_demo_summary.md
data/processed/taas_weight_table.csv
```

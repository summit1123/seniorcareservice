# Senior Care Service

생활권 기반 시니어 안심주행 특약의 심사위원용 React 데모 저장소입니다.

이 프로젝트는 실제 사고/청구 예측을 주장하지 않습니다. 대신 같은 연간 주행거리 고객을 기존 마일리지 방식과 제안 통합 산식으로 함께 평가해, 기존 거리 기준만으로는 구분되지 않는 생활권 안정성·생활권 밖 안전성·최근 위험변화를 보여줍니다.

## 핵심 방향

- 기존 기준선: 삼성화재 마일리지 할인표의 연간 주행거리/차종별 할인율을 비교군으로 사용합니다.
- 제안 산식: Mileage Score, In-Zone Safe Driving Score, Out-Zone Safe Driving Score, Out-Zone Pattern Change Risk를 연간 통합 점수로 계산합니다.
- 생활권 분석: 사전 60일은 생활권 기준을 만들기 위한 관찰 데이터로만 쓰고, 할인 비교는 평가기간 12개월 주행거리로만 계산합니다.
- 리포트: LLM은 보험료를 결정하지 않고, XAI reason code와 월별 근거를 보험사 직원용 설명문으로 바꾸는 역할만 합니다.

## 현재 목표

1. 30명 시니어 페르소나와 12개월 주행 시나리오를 준비합니다.
2. 월별 DBSCAN/P90 생활권과 4개 지표를 계산합니다.
3. 기존 마일리지 vs 제안 통합 산식의 연간 A/B 비교를 생성합니다.
4. React Decision Dashboard에서 사례 선택, 생활권 지도, 보험료 입력, XAI 리포트를 한 화면에서 보여줍니다.

## 실행

```bash
npm install
npm run dev -- --port 5174
```

브라우저에서 확인:

```text
http://127.0.0.1:5174/
```

## 검증

```bash
npm run build
python3 -m unittest discover -s tests
python3 scripts/preflight.py run
```

## 주요 산출물

```text
data/fixtures/annual_persona_profiles.json
data/fixtures/annual_trip_logs.csv
data/processed/monthly_score_table.csv
data/processed/annual_ab_comparison.csv
data/fixtures/judge_demo_view_model.json
reports/judge-demo-summary.md
reports/react-demo-screenshots/
```

## Ralph / SummitHarness

```bash
./ralph.sh
```

Ralph 산출물과 검증 로그는 `.codex-loop/` 아래에 남습니다.

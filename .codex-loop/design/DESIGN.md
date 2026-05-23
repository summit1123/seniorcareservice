# 디자인 계약

Preset: product-ops
Reference-Pack: impeccable-operator

## 이 문서의 역할

이제 이 프로젝트의 핵심 산출물은 정적 문서가 아니라 심사위원이 직접 보는 React 제품 데모다. 따라서 디자인 기준은 `document-editorial`이 아니라 `product-ops`로 고정한다.

보조 레퍼런스는 `analyst-workbench`다. 보험료 비교, 월별 생활권 변화, reason code 검토처럼 근거를 읽어야 하는 패널은 분석 워크벤치처럼 조밀하고 명확해야 한다.

## 핵심 화면 원칙

- 첫 화면은 문제정의, 기존 마일리지와 제안 산식 차이, 핵심 수치를 20초 안에 이해시킨다.
- UI는 보험사 직원과 심사위원이 함께 볼 수 있는 운영형 데모여야 한다.
- 예쁜 React shell이 아니라 데이터, 산식, A/B 비교, XAI 리포트가 실제로 연결된 제품 표면이어야 한다.
- 기존 할인액과 제안 할인액의 차이가 입력 보험료 기준으로 바로 보여야 한다.
- 월별 패널은 할인율이 아니라 생활권 버전, 주행거리, 위험변화, reason code의 변화 추이를 보여야 한다.

## 필수 패널

1. Executive Overview
   - 상품명, 문제정의, 기존 방식의 한계, 제안 산식의 역할
   - 기존 마일리지 할인표 기준 할인율과 제안 산식 결과를 함께 표시

2. Persona Lab
   - 30명 가상 시니어 운전자
   - 페르소나별 집, 병원, 마트, 자녀집, 외출빈도, 위험행동 성향

3. Living Zone Timeline
   - 1월~12월 월별 주행 요약
   - 매월 직전 60일 기준 생활권 snapshot
   - 기존 생활권, 후보 생활권, 생활권 밖 안정 주행, 위험변화 구간 구분

4. Mileage A/B Comparison
   - 기존 삼성화재 마일리지 할인표 lookup
   - 제안 Senior Safe Mileage Score
   - 최종 할인율, 할인액, 차액, 예방 케어 여부

5. XAI Report Panel
   - 선택 운전자의 reason code
   - 보험사 직원용 설명문
   - LLM은 보험료 판단이 아니라 설명문 생성만 담당한다는 안내

## Task 005 화면 구조 계약

첫 화면은 한 화면 안에서 `문제정의 -> 같은 기존 할인구간 안의 미구분 문제 -> 선택 운전자 상세 근거` 순서로 읽히게 한다. 화면 골격은 왼쪽 운전자/페르소나 탐색 레일, 가운데 연간 A/B와 월별 타임라인, 오른쪽 생활권 지도와 XAI inspector의 3영역 운영 콘솔로 고정한다.

심사위원의 기본 경로는 다음과 같다.

1. Executive Overview에서 `안심반경 시니어 마일리지`의 산식 차이와 30명 총괄 수치를 확인한다.
2. Persona Lab에서 6개 페르소나와 30명 운전자 중 하나를 선택한다.
3. Mileage A/B Comparison에서 동일한 평가기간 연간 주행거리와 보험료 입력으로 기존 할인액, 제안 할인액, 차액을 비교한다.
4. Living Zone Timeline에서 1월~12월 월별 근거가 할인율이 아니라 연간 판단 근거임을 확인한다.
5. Zone Map Inspector에서 선택 월의 DBSCAN/P90 생활권, 후보 생활권, 생활권 밖 안정 주행, 위험변화 trip 구성을 확인한다.
6. XAI Report Panel에서 4개 지표 reason code와 LLM 경계 문구를 확인한다.

상태 전이는 `loading`, `ready`, `driver-change loading`, `error/empty`를 갖는다. 선택 운전자가 바뀌면 연간 비교, 월별 timeline, 지도 inspector, XAI reason code가 함께 바뀌어야 한다. 지도 월 선택은 timeline 선택과 같은 상태를 공유한다.

## Task 005 자산 근거

- `data/fixtures/judge_demo_view_model.json`: React 데모의 product frame, 30명 driver options, persona summaries, annual A/B comparison, monthly evidence를 제공하는 승인 데이터 자산이다.
- `data/processed/monthly_zone_snapshots.json`: DBSCAN/P90 생활권 지도 inspector의 승인 데이터 자산이다. 원본 GPS 로그를 노출하지 않고 월별 cluster center, radius, trip interpretation만 사용한다.
- `data/processed/annual_ab_comparison.csv`: 같은 입력 보험료/연간 주행거리 기준의 기존 할인액, 제안 할인액, 차액을 검증하는 승인 계산 자산이다.
- Task 005는 위 자산을 React 정적 import로 직접 묶지 않고 API 조회 계약(`/api/personas`, `/api/drivers/{id}/annual-summary`, `/api/drivers/{id}/monthly-snapshots`, `/api/drivers/{id}/zone-map?month=...`)을 통해 읽는 구조를 전제로 한다.
- 런타임 스크린샷은 task 005 또는 task 007에서 `reports/react-demo-screenshots/` 아래에 보관하고, 실제 첫 화면의 텍스트 잘림과 선택 운전자 변경 상태를 증명해야 한다.

## 화면 데이터 계약

- Living Zone Timeline은 `data/processed/monthly_zone_snapshots.json`을 source로 사용한다.
- 타임라인의 월별 상태명은 `existing_living_zone`, `candidate_living_zone`, `out_zone_safe_driving`, `out_zone_pattern_change_risk` 네 가지로 고정한다.
- 월별 점수는 `data/processed/monthly_score_table.csv`의 `mileage_score`, `in_zone_safe_driving_score`, `out_zone_safe_driving_score`, `out_zone_pattern_change_risk`를 표시하되 할인율로 표현하지 않는다.
- 연간 종합 패널은 `data/processed/annual_score_table.csv`의 `annual_senior_safe_mileage_score`, `annual_out_zone_pattern_change_risk`, `annual_decision_signal`을 먼저 읽고, task 004의 A/B 비교 산출물이 생기면 기존 할인액/제안 할인액을 병렬로 붙인다.
- 1월은 평가기간 전 60일 baseline 주행 로그로 `pre_policy_60_day_dbscan` 생활권을 만든다. 2월~12월은 현재 월 주행을 제외한 직전 60일 DBSCAN/P90 결과만 생활권 기준으로 쓴다.

## 시각 스타일

- `impeccable-operator`: 정확하고, 조용하고, 운영 도구처럼 믿을 수 있는 화면.
- 강한 정보 위계를 유지한다. 제목, 핵심 수치, 비교표, 세부 근거의 순서가 분명해야 한다.
- 색은 navy, white, neutral gray, restrained blue/green/orange 상태색 위주로 제한한다.
- 상태색은 의미가 있어야 한다: 안정, 기본, 주의, 예방 케어.
- 표, timeline, inspector, comparison panel을 우선한다.
- 16:9 발표 캡처와 노트북 화면에서 모두 읽혀야 한다.

## 금지 패턴

- React scaffold만 만들고 실제 데이터 연결 없이 완료 선언
- 장식용 카드, pill, 동그라미, 의미 없는 KPI 타일 남발
- 기존 마일리지 + 통합 산식 우대처럼 보이는 카피
- 월별 할인율 또는 CAGR 비교
- 생활권 밖 자체를 위험으로 단정하는 표현
- 보험료 인상, 감시, 벌점처럼 보이는 문구
- 원본 GPS/개인식별자를 LLM 설명 패널에 노출

## 완료 증거

- 실제 로컬 앱 실행 또는 build 결과
- 데스크톱 스크린샷
- 핵심 첫 화면에서 텍스트 잘림 없음
- 선택 운전자 변경 시 비교와 리포트가 함께 바뀜
- 30명 페르소나와 12개월 데이터가 UI에 반영됨

# 기존 마일리지 비교 기준 계약

이 문서는 React 심사위원 데모에서 쓰는 기존 마일리지 기준선을 고정한다. 기준선은 삼성화재 다이렉트 마일리지 할인 특약의 공개 할인표를 비교군으로 사용하되, 실제 삼성화재 보험료 산정 시스템을 복제한다고 주장하지 않는다.

## Source

- 기준표: 삼성화재 다이렉트 마일리지 할인 특약
- URL: <https://direct.samsungfire.com/mall/PP030102_001.html>
- 확인일: 2026-05-10
- 표 기준: `'26.04.11 보험시작일 기준`
- 적용 범위: 개인 승용, 개인 승용 전기/수소, 개인 업무용 공개 할인율

## Input Contract

기존 마일리지 lookup은 두 입력만 사용한다.

| 필드 | 의미 |
| --- | --- |
| `annual_mileage_km` | 연간 주행거리 km |
| `vehicle_class` | 차종군. `personal_passenger_general`, `personal_passenger_ev_hydrogen`, `personal_business` 중 하나 |

이 기준선에는 `CAGR`, 월복리, 월별 할인율 환산을 쓰지 않는다. 월별 데이터는 할인율 산출용이 아니라 제안 산식의 연간 판단 근거를 설명하기 위한 증거다.

## Fixed Discount Table

| 연간 주행거리 | 개인 승용 일반 | 개인 승용 전기/수소 | 개인 업무용 |
| --- | ---: | ---: | ---: |
| 1천km 이하 | 40% | 42% | 16% |
| 2천km 이하 | 34% | 37% | 16% |
| 3천km 이하 | 28% | 31% | 16% |
| 4천km 이하 | 25% | 29% | 12% |
| 5천km 이하 | 23% | 27% | 12% |
| 6천km 이하 | 22% | 26% | 8% |
| 7천km 이하 | 21% | 25% | 8% |
| 8천km 이하 | 18% | 22% | 8% |
| 9천km 이하 | 16% | 20% | 8% |
| 1만km 이하 | 12% | 17% | 8% |
| 1만1천km 이하 | 9% | 13% | 3% |
| 1만2천km 이하 | 5% | 10% | 3% |
| 1만3천km 이하 | 3% | 3% | 3% |
| 1만4천km 이하 | 2% | 2% | 3% |
| 1만5천km 이하 | 1% | 1% | 3% |
| 1만5천km 초과 | 0% | 0% | 0% |

코드 source는 `data/fixtures/mileage_discount_table.json`이고, lookup API는 `src/product/mileage_discount_table.py`의 `lookup_existing_mileage_discount()`다. 예를 들어 `annual_mileage_km=3000`, `vehicle_class=personal_passenger_general`이면 기존 할인율은 28%다.

## Annual A/B Output Contract

Task 004의 구현 source는 `src/product/annual_ab_comparison.py`다. 출력은 다음 두 파일이다.

| 파일 | 역할 |
| --- | --- |
| `data/processed/annual_ab_comparison.csv` | 30명 운전자별 기존 마일리지 할인액과 제안 Senior Safe Mileage 할인액/케어 판단 비교 |
| `data/fixtures/judge_demo_view_model.json` | React 데모가 읽는 persona, 월별 근거, 연간 점수, A/B 비교 통합 view model |

같은 운전자에 대해 기존 방식과 제안 방식은 같은 입력 보험료, 같은 차종, 같은 평가기간 12개월 주행거리를 사용한다. 이 계약은 각 row의 `same_input_contract_id`와 `same_input_contract_json`으로 남긴다. 사전 baseline 60일은 1월 생활권 기준 생성과 변화 비교에만 쓰며 `annual_distance_scope=evaluation_period_only`와 `baseline_60_day_excluded_from_discount=1`로 할인액 산출에서 제외한다.

## 제안 4지표 도출 계약

제안 산식의 4개 지표는 임의로 더한 별도 가산 항목이 아니다. 순서는 다음과 같다.

1. 먼저 30명 1년 주행 시나리오에 기존 마일리지 할인표를 적용한다.
2. 같은 연간 주행거리 구간과 같은 차종군 안에 안정형, 생활권 밖 안전형, 최근 위험변화형이 함께 묶이는지 확인한다.
3. Agent는 이 미구분 패턴을 설명하기 위해 필요한 축만 좁힌다.
4. 최종 제안 산식은 연간 주행거리, 12개월 생활권 안정성, 12개월 생활권 밖 안전성, 12개월 위험변화를 한 번에 종합한다.

따라서 데모 카피는 "기존 할인에 통합 산식 우대를 얹는다"가 아니라 "기존 거리 기준선이 같은 할인율로 묶은 고객을 연간 통합 근거로 다시 설명한다"로 유지한다.

## 구현 경계

- 기존 기준선: 연간 주행거리 + 차종군 -> 연간 할인율 1개
- 제안 산식: 연간 주행거리 + 생활권 안정성 + 생활권 밖 안전성 + 위험변화 -> 연간 통합 점수와 케어 판단
- LLM/XAI 패널: 할인율 산정 주체가 아니라, 이미 계산된 근거와 reason code를 보험사 직원용 설명문으로 바꾸는 계층
- 금지 표현: 보험료 인상, 감시, 벌점, 생활권 밖 자체를 위험으로 단정하는 문구

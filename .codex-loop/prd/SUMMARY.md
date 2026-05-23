# PRD 요약

목표는 기존 검증용 HTML 대시보드를 버리고, 심사위원이 보는 **React 기반 제품 데모**를 새로 만드는 것이다.

핵심 비교군은 삼성화재 마일리지 할인표다.

```text
기존 마일리지:
연간 주행거리 + 차종 -> 연간 할인율 1개

제안 산식:
연간 주행거리
+ 12개월 생활권 안정성
+ 12개월 생활권 밖 안전성
+ 12개월 위험변화
-> 연간 통합 점수 1개
-> 제안 할인율/예방 케어 판단
```

월별 할인율, CAGR, 월복리 환산은 쓰지 않는다. 월별 데이터는 할인율이 아니라 판단 근거다.

새 데이터 구조:

```text
6개 시니어 페르소나 * 5명 = 30명
운전자별 사전 baseline 60일 주행 로그
운전자별 평가기간 12개월 주행 로그
매월 직전 60일 기준 DBSCAN/P90 생활권 계산
해당 월 주행 평가
12개월 결과를 연간 종합
```

사전 baseline 60일은 1월 생활권을 만들기 위한 관찰 데이터다. 기존 마일리지 할인율, 제안 연간 점수, 할인액 비교에는 평가기간 12개월 주행거리만 사용한다. 월별 평가에서도 평가월 주행은 같은 달 생활권 생성에 섞지 않는다.

중요한 설명 구조:

```text
기존 마일리지 할인표를 먼저 적용
-> 같은 할인 구간 안의 안정형/위험변화형 혼재 확인
-> Agent가 기존 기준이 놓친 설명 축을 탐색
-> 4개 지표 도출
-> 제안 통합 산식으로 A/B 검증
```

따라서 4개 지표는 임의로 만든 항목이 아니라, 기존 거리 기준 마일리지의 미구분 문제를 설명하기 위해 좁혀진 산식 구성요소로 보여줘야 한다.

React 데모 필수 화면:

1. Executive Overview
2. Persona Lab
3. Living Zone Timeline
4. Mileage A/B Comparison
5. XAI Report Panel

React 단독으로 끝내지 않는다. 데이터 조회와 리포트 생성은 서버가 담당한다.

필수 API:

```text
GET /api/personas
GET /api/drivers/{id}/annual-summary
GET /api/drivers/{id}/monthly-snapshots
GET /api/drivers/{id}/zone-map?month=...
GET 또는 POST /api/reports/stream
```

리포트는 보험사 직원용 Markdown streaming 프레임으로 표시한다. 내용은 운전자 프로필, 기존 마일리지 결과, 월별 운전 패턴, 생활권 변화, 4개 지표 영향, 판단 가이드, 한계 고지를 포함해야 한다.

디자인은 `product-ops` + `impeccable-operator`를 따른다. React scaffold만 만들면 실패다. 데이터 산출물, 계산 결과, 시각화 패널, XAI 리포트, 빌드/스크린샷 검증까지 함께 완료되어야 한다.

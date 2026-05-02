# 제품 요구사항 문서

## 작업 제목

생활권 기반 시니어 안심주행 특약 AI 모델 견본 및 시각화 패키지

## 문제 정의

기존 자동차보험 특약은 주행거리 또는 안전운전점수 중심으로 혜택을 판단한다. 그러나 시니어 운전자에게 중요한 “익숙한 생활권 중심의 안정 운전”과 “평소와 달라진 운전 변화”는 충분히 설명되지 않는다.

공모전 제출물은 이 차별점을 심사위원이 빠르게 이해할 수 있도록 데이터, AI 모델, 점수, 판단 결과, 시각화 자료를 함께 보여줘야 한다.

## 사용자

- 주요 사용자: 공모전 팀원, 삼성화재 공모전 심사위원
- 보조 사용자: 보험사 상품/데이터 담당자

## 기대 결과

- 팀원은 어떤 데이터를 준비해야 하는지 이해한다.
- 모델 담당자는 feature table, score table, decision table을 생성한다.
- 제안서 담당자는 모델 구조와 결과를 시각화 자료로 설명한다.
- 심사위원은 “마일리지 + 생활권 안정성 + 평소패턴 변화 감지”의 차별점을 이해한다.

## 핵심 흐름

1. Trip 데이터에서 시작/종료 좌표, 주행거리, 운전행동 이벤트를 읽는다.
2. 생활권 생성 AI가 고객별 반복 목적지와 반복 주행 패턴을 찾는다.
3. 운전행동 feature를 100km 기준으로 정규화한다.
4. Isolation Forest가 최근 운전이 평소와 얼마나 다른지 감지한다.
5. Safe Driving Score, Familiar Zone Score, Pattern Change Score, Out-Zone Behavior Risk를 계산한다.
6. 추가 리워드, 기본 유지, 예방 케어 중 하나로 판단한다.
7. 결과를 figure와 리포트로 만들어 proposal source에 연결한다.

## 기능 요구사항

- Trip 샘플 데이터 생성
- 데이터 로더와 필수 컬럼 검증
- 생활권 feature 계산
- 운전행동 feature 계산
- 평소패턴 변화 감지 모델
- 최종 점수 계산
- 리워드/케어 판단
- 제출용 시각화 자료 생성
- 모델 결과 요약 리포트 작성

## 비기능 요구사항

- 재현성: 샘플 데이터로 전체 pipeline을 재실행할 수 있어야 한다.
- 설명 가능성: 각 판단에는 reason code가 있어야 한다.
- 개인정보 보호: 원본 좌표는 최종 모델 feature에 직접 남기지 않는다.
- 문서 품질: PDF보다 Markdown source와 figure source가 먼저여야 한다.
- 디자인 품질: 검정 중심, 표 중심, 장식 없는 reviewer-facing 자료여야 한다.

## AI 동작 규칙

- DBSCAN/HDBSCAN은 생활권 후보를 생성한다.
- Isolation Forest는 사고 라벨 없이 평소패턴 변화를 감지한다.
- TAAS 또는 공공 사고통계는 개인 예측 라벨이 아니라 위험행동 가중치 근거로만 사용한다.
- LLM은 보험료나 케어 여부를 직접 결정하지 않는다. 설명문 생성 또는 리포트 문구 보조에만 쓴다.

## 디자인 방향

- `editorial-signal`을 기본 레퍼런스로 사용한다.
- score table과 decision table은 `analyst-workbench`의 비교/검토 톤을 따른다.
- 시각화 자료는 AI pipeline, score structure, decision flow, 고객별 판단 예시 중심으로 만든다.
- 장식용 도형과 빈 박스형 자료는 금지한다.

## 완료 기준

- `data/raw/trip_sample.csv`에서 `data/processed/decision_table.csv`까지 생성할 수 있다.
- `reports/figures/*.svg` 시각화가 생성된다.
- `reports/model_demo_summary.md`가 고객별 판단 예시를 포함한다.
- `docs/submissions/proposal.md`가 source review와 render 흐름에 연결된다.
- Ralph preflight와 context refresh가 정상 실행된다.

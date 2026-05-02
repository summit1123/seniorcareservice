# Summit 리서치 계획

모드: proposal
상태: 확정
리서치-깊이: standard

## 목적

생활권 기반 시니어 안심주행 특약이 공모전 제안서로 설득력을 가지려면, AI가 무엇을 학습하고 어떤 결과를 내는지 심사위원이 한눈에 이해해야 한다.

## 단계형 계획

### 1단계. 데이터 근거 확인

- 공공 사업용차량 Trip 데이터에서 시작/종료 GPS, Trip 거리, 운행시간, 과속, 급가속, 급감속, 급회전 필드를 확인한다.
- 이 필드를 `trip_sample.csv`와 `model_feature_table.csv`로 연결한다.

### 2단계. AI 구조 고정

- 생활권 생성 AI는 DBSCAN/HDBSCAN으로 설명한다.
- 평소패턴 변화 감지는 Isolation Forest를 기본 모델로 설명한다.
- TAAS는 개인 예측 라벨이 아니라 위험행동 가중치 근거로만 설명한다.

### 3단계. 시각화 산출물 정의

- AI pipeline diagram
- data-to-feature diagram
- score structure diagram
- decision flow diagram
- 고객 3명 판단 예시

### 4단계. 제출용 문서 게이트 연결

- Markdown proposal source를 먼저 작성한다.
- source review 후 render한다.
- PDF review는 마지막 검토 게이트로만 사용한다.

## 완료 기준

- 모델과 시각화가 같은 용어를 사용한다.
- 생활권 밖 주행을 무조건 위험으로 단정하지 않는다.
- 위험행동 증가와 평소패턴 변화가 함께 있을 때 예방 케어로 연결한다.

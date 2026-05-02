# Summit 워크플로우 온보딩

프로필: proposal-only
프로필-라벨: 제안서 전용
목표: 생활권 기반 시니어 안심주행 특약의 AI 모델 견본과 제출용 시각화 자료를 만든다
상태: 확정

## 공통 질문

### C1. 이번 런에서 지금 사용자가 하고 싶은 일은 무엇입니까?
답변:
- 삼성화재 공모전 제출을 위해 생활권 기반 시니어 안심주행 특약의 AI 모델 견본, 판단 로직, reviewer-facing 시각화 자료를 만든다.

### C2. 이번 런은 어디까지 진행하면 된다고 보십니까?
답변:
- Ralph/SummitHarness가 이 저장소에서 바로 돌 수 있고, 모델 견본과 제출용 시각화 자료를 만들 수 있는 작업 구조가 준비되면 된다.

### C3. 이번 런의 최종 산출물은 무엇입니까?
답변:
- AI 모델 작업계획
- 데이터 입력 필드 계약
- 시각화 산출물 계획
- Ralph runtime과 검토 게이트
- 향후 proposal PDF와 report figure를 만들 수 있는 source-first 구조

### C4. honest COMPLETE 기준은 무엇입니까?
답변:
- SummitHarness가 설치되어 있고 이 저장소가 bootstrap되어 있어야 한다.
- workflow, intake, research, design, task graph가 이 공모전 방향에 맞게 조정되어 있어야 한다.
- 시각화 자료가 어떤 파일명과 어떤 역할로 생성될지 명확해야 한다.
- 이후 모델/시각화 구현 커밋을 작은 단위로 이어갈 수 있어야 한다.

### C5. 이미 가지고 있는 입력 자료는 무엇입니까?
답변:
- 생활권 기반 시니어 안심주행 특약 기획 내용
- TAAS 지자체별 대상사고통계 API 필드 정리
- 공공 사업용차량 Trip 단위 위험운전운행데이터 후보
- AI 모델 작업계획 PDF와 데이터 feature 정리
- GitHub 저장소 `summit1123/seniorcareservice`
- Ralph 시스템 저장소 `summit1123/SummitHarness`

### C6. 누가 승인권자입니까?
답변:
- 동현. 팀원 공유 전 최종 방향과 커밋 흐름을 확인한다.

## 프로필별 질문

### P1. 최종 산출물은 무엇입니까?
답변:
- 공모전 제안서/리포트에 들어갈 모델 구조, 데이터 흐름, 점수 산식, 고객 판단 예시, 시각화 자료.

### P2. 심사위원이 가장 먼저 이해해야 하는 핵심 메시지는 무엇입니까?
답변:
- 이 특약은 “적게 운전한 시니어”가 아니라 “익숙한 생활권에서 안정적으로 운전한 시니어”에게 추가 혜택을 주는 보험이다.

### P3. 반드시 들어가야 할 근거, 표, 캡처, 사례, 수치가 있습니까?
답변:
- 기존 마일리지/착한운전 특약과의 차이
- 고객 주행 데이터에서 만드는 feature table
- 생활권 생성 AI와 평소패턴 변화 감지 AI의 역할
- TAAS는 개인 예측 라벨이 아니라 위험행동 가중치 근거로 쓰는 구조
- Safe Driving Score, Familiar Zone Score, Pattern Change Score, Care Trigger
- 고객 유형별 추가 리워드/기본 유지/예방 케어 판단 예시

## 확정 결정

- workflow profile은 `proposal-only`로 사용한다.
- 모델 구현은 제안서 근거와 시각화 자료를 만들기 위한 proof slice로 다룬다.
- PDF는 source of truth가 아니다. Markdown, CSV, script, figure source가 먼저다.

## 포함 영역

- proposal
- AI module
- data feature pipeline
- report visualization
- reviewer-facing documentation

## 제외 영역

- 실제 삼성화재 내부 사고/청구 데이터 학습
- 실제 보험료 산출 또는 요율 승인
- 실제 앱/네비 실시간 서비스 구현
- 원본 개인 위치 데이터 저장

## 증거 기준

- 각 산출물은 파일 경로와 생성 명령이 있어야 한다.
- 시각화 자료는 장식이 아니라 모델 구조, feature 흐름, 판단 결과를 설명해야 한다.
- 검토자는 proposal source, figure, score table, decision table을 보고 상품 로직을 이해할 수 있어야 한다.

# Summit 인테이크 승인

모드: proposal
상태: 승인
승인: 예
승인자: 동현
승인 시각: 2026-05-03

## 승인 체크리스트

- [x] 제출 대상 독자, 형식, 심사 기준이 명확합니다.
- [x] 첨부 문서 또는 PDF에 대한 기대 수준이 구체적입니다.
- [x] 폼 답변과 첨부 문서에 반드시 들어가야 할 근거를 팀이 알고 있습니다.

## 확정 목표

- 생활권 기반 시니어 안심주행 특약의 AI 모델 견본과 제출용 시각화 자료를 source-first 방식으로 만든다.

## 확정 산출물

- 데이터 입력 필드 계약서
- AI 모델 작업계획
- Ralph/SummitHarness 실행 구조
- 시각화 workflow 문서
- 모델 pipeline figure
- 점수 구조 figure
- decision flow figure
- 향후 proposal PDF render/review gate

## 확정 제외 범위

- 실제 보험료 산정
- 실제 네비게이션 경로 변경 서비스
- 실제 삼성화재 내부 사고/청구 데이터 학습
- 원본 개인 위치 데이터 기반 운영 설계

## COMPLETE 전 필수 증거

- `python3 scripts/preflight.py run` 실행 가능
- `.codex-loop/config.json`이 proposal workflow를 가리킴
- `.codex-loop/tasks.json`이 프로젝트 전용 task graph를 가짐
- 시각화 자료 생성 위치와 파일명이 문서화됨
- 이후 구현 커밋을 작은 단위로 이어갈 수 있음

## 승인 메모

- PDF만 예쁘게 만드는 방향은 금지한다.
- 시각화는 장식이 아니라 심사위원이 모델 로직을 이해하게 하는 증거여야 한다.

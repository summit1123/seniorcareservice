# Summit 워크플로우 상태

프로필: product-ui
목표: 안심반경 시니어 마일리지의 30명 1년 시뮬레이션 데이터와 React Decision Dashboard를 완성한다
현재-단계: frontend-integration
현재-모드: product-ui
상태: 최종 검증 대기

## 단계 체크리스트

- [x] onboarding: 공모전 목표와 심사 기준 확인
- [x] product-contract: 기존 마일리지 기준과 제안 통합 산식 계약 고정
- [x] data-simulation: 30명 페르소나, 사전 60일, 평가 12개월 주행 데이터 생성
- [x] model-pipeline: rolling 60일 생활권, 월별 4지표, 연간 통합 점수 계산
- [x] frontend-integration: React Decision Dashboard, 생활권 지도, 보험료 입력, XAI/리포트 스트림 구현
- [x] evidence-refresh: build/test/preflight/API/screenshot/source-framing 증거 갱신
- [> ] final-ralph-eval: Ralph precomplete 재평가

## 현재 단계 완료 결과

- 첫 화면은 왼쪽 사례 목록, 중앙 Summary/생활권 지도/월별 근거, 오른쪽 Decision Panel 구조로 시작한다.
- 기존 마일리지는 연간 주행거리와 차종 기준선으로 두고, 제안 산식은 `Mileage`, `In-Zone Safe Driving`, `Out-Zone Safe Driving`, `Out-Zone Pattern Change Risk` 4개 지표를 연간 통합 점수로 계산한다.
- 보험료 입력값은 기존/제안 할인액, 최종 보험료, 스트리밍 리포트 API 입력에 모두 반영된다.
- 보고서 스트림은 보험사 직원용 7개 섹션 Markdown으로 생성되며, `.env`의 `OPENAI_API_KEY`로 실제 OpenAI LLM을 호출한다. 키가 없으면 리포트를 생성하지 않는다.

## 다음 단계

- `./ralph.sh` precomplete evaluator를 재실행해 product-ui 완료 상태를 확인한다.
- 통과 후 커밋을 세밀하게 분리하고 원격 저장소에 push한다.

## 다음 단계로 넘기는 법

- `.codex-loop/tasks.json`의 모든 task가 `done`이고 `next_task_id`가 `null`인지 확인한다.
- `npm run build`, `python3 -m unittest discover -s tests`, `python3 scripts/preflight.py run`, `/api/reports/stream` 7섹션 로그, 최신 screenshot 증거가 모두 남아 있어야 한다.

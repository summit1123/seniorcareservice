# 안심반경 시니어 마일리지 데모 요약

## 핵심 구조

- 비교 기준은 기존 삼성화재 마일리지 할인표의 연간 주행거리/차종별 할인율이다.
- 제안 산식은 기존 마일리지에 별도 혜택을 붙이는 방식이 아니라, 같은 연간 입력 보험료 기준에서 4개 지표를 함께 평가하는 통합 산식이다.
- 4개 지표는 Mileage Score, In-Zone Safe Driving Score, Out-Zone Safe Driving Score, Out-Zone Pattern Change Risk다.

## 데이터 계약

- 페르소나 기반 시뮬레이션 운전자 30명을 생성했다.
- 원천 주행 로그는 사전 baseline 60일과 평가기간 12개월로 구성했다.
- 사전 baseline 60일은 1월 생활권 생성과 평소 패턴 비교에만 사용한다.
- 기존 마일리지 할인율, 제안 할인율, 연간 주행거리, 할인액 비교에는 평가기간 12개월만 사용한다.

## 구현 산출물

- 기존 마일리지 표 fixture와 lookup API
- 30명 persona profile과 annual trip log
- 월별 DBSCAN/P90 생활권 snapshot
- 월별 4지표 score table과 연간 통합 score table
- 기존 마일리지 vs 제안 산식 annual A/B comparison
- React judge demo UI
- Vite dev API와 Markdown streaming report endpoint
- Decision Dashboard 보험료 입력 기반 할인액/최종 보험료 재계산
- 7개 필수 섹션 Markdown streaming 리포트와 현재 생성 섹션 progress 표시

## 검증 결과

- `npm run build` 통과
- `python3 -m unittest discover -s tests` 223개 통과
- `python3 scripts/preflight.py run` 통과
- Playwright 1440px viewport 첫 화면 3영역 Decision Dashboard 렌더링 확인
- 콘솔 error 0건
- XAI report panel에서 현재 생성 섹션 progress와 7개 필수 섹션 Markdown streaming 리포트 생성 확인
- 최신 raw log: `.codex-loop/logs/latest-build.log`, `.codex-loop/logs/latest-unittest.log`, `.codex-loop/logs/latest-report-stream.md`
- 최신 framing check: `.codex-loop/logs/latest-framing-check.log`
- 최신 첫 화면 증거: `reports/react-demo-screenshots/ralph-first-screen-decision-contract-fullpage.png`, `reports/react-demo-screenshots/ralph-first-screen-decision-dashboard-element.png`
- 운전자 변경 증거: `reports/react-demo-screenshots/ralph-driver-change-decision-dashboard.png`, `.codex-loop/logs/latest-driver-change-evidence.md`
- 리포트 증거: `reports/react-demo-screenshots/ralph-report-current-named-section-panel.png`, `reports/react-demo-screenshots/ralph-report-seven-sections-expanded-panel.png`, `reports/react-demo-screenshots/ralph-report-seven-sections-stream-only.png`

## 주의 문구

이 데모는 실제 사고율이나 손해율을 입증하는 모델이 아니다. 실제 고객 사고/청구 데이터가 없기 때문에, 본 산출물은 생활권 생성, 4지표 산식, 기존 마일리지 대비 미구분 위험 패턴 탐지 가능성을 보여주는 심사용 구현 견본이다.

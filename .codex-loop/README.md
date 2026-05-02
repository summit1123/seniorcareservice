# .codex-loop

이 디렉터리는 SummitHarness가 프로젝트 안에서 사용하는 런타임 상태 저장소입니다.

- `workflow/`: 상위 온보딩, 워크플로우 프로필, 아이디어 옵션, 단계 상태
- `intake/`: 요청자 Q&A, 답변 기록, 첫 seed 실행 전 승인 잠금
- `research/`: 단계형 리서치 계획, 근거 정리, 승인된 방향
- `prd/`: 하네스가 따라야 할 제품 브리프와 요약
- `tasks.json`, `tasks/`: 실제 실행 graph
- `PROMPT.md`: 고정 루프 지침
- `STEERING.md`: 긴급한 방향 수정 메모
- `context/`: 압축 handoff 패킷과 누적 사실
- `assets/registry.json`: 승인된 참고 자산 목록
- `preflight/`: 환경 및 도구 점검 결과
- `logs/`, `history/`, `reviews/`, `evals/`: 실행 기록과 평가 흔적
- `ralph-loop.json`: Stop hook 기반 self-loop 상태

이 하네스는 재사용 가능한 구조이고, 이 디렉터리에서부터 프로젝트 고유 상태가 쌓입니다.

# 모드 계약: PRD

이 모드는 build 전에 요구사항, 사용자, 제약, 실행 가능한 task graph를 잠글 때 사용합니다.

## source of truth

- `.codex-loop/prd/PRD.md`
- `.codex-loop/prd/SUMMARY.md`
- `.codex-loop/tasks.json`
- `.codex-loop/tasks/TASK-*.json`

## 완료 기준

- PRD에 사용자, workflow, 범위, 제약, non-goal이 적혀 있습니다.
- acceptance criteria가 실제로 build와 verify를 이끌 수 있을 만큼 구체적입니다.
- task는 실제 남은 일을 반영하고, 바로 실행 가능한 다음 task가 하나 보입니다.

## 실패 조건

- PRD가 여전히 brainstorming 문서처럼 보입니다.
- task graph가 빠진 일을 숨깁니다.
- 요구사항이 모호하거나, 충돌하거나, 검증할 수 없습니다.

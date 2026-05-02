# 모드 계약: 구현

이 모드는 실제 코드, 테스트, 런타임 동작, 제품 수준 기능 단위를 만들 때 사용합니다.

## source of truth

- 실제 코드베이스
- tests와 local checks
- `.codex-loop/prd/PRD.md`
- `.codex-loop/tasks.json`

## 완료 기준

- 바뀐 경로가 end-to-end로 동작합니다.
- tests, checks, screenshots, logs 중 하나 이상의 증거가 남아 있습니다.
- 관련 계약 문서와 보조 문서가 repo 상태와 맞습니다.

## 실패 조건

- scaffolding만 있는 상태에서 완료를 선언합니다.
- checks를 건너뛰었거나 약합니다.
- UI나 workflow가 여전히 generic하거나 미완성입니다.

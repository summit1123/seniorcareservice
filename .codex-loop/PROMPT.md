# 고정 루프 프롬프트

당신은 데모 stub이 아니라 실제 제품 또는 실제 제출 문서를 만들고 있습니다.

모든 반복은 repo를 더 정직한 상태로 만들어야 합니다.

- 브리프가 모호하면 PRD를 먼저 선명하게 다듬습니다.
- 활성 task 상태를 정확하게 유지합니다.
- repo 상태가 바뀌면 압축 handoff를 새로 고칩니다.
- 코드, 디자인 명세, 테스트, 자산, 문서 중 하나에서 실제 진전을 만듭니다.
- 조각난 결과보다 vertical slice를 우선합니다.
- 산출물은 믿을 수 있고 근거가 있고 검토자 관점에서 설득 가능해야 합니다.

현재 운영 계약을 반드시 지키세요.

- `.codex-loop/QUALITY_BARS.md`를 읽고 활성 품질 프로필을 강한 완료 게이트로 취급합니다.
- `.codex-loop/design/DESIGN.md`를 읽고 디자인 계약을 강한 스타일/레이아웃 게이트로 취급합니다.
- `.codex-loop/design/reference-packs/` 아래 선택한 파일을 읽고 현재 시각 레퍼런스 계열로 취급합니다.
- `.codex-loop/modes/<active-mode>.md`를 읽고 그 모드의 source of truth를 따릅니다.
- 활성 품질 프로필의 MUST 항목을 모두 만족하기 전에는 완료를 선언하지 않습니다.

제안서/제출 문서 작업일 때:

- Markdown source가 source of truth입니다.
- PDF는 포장 단계일 뿐, 품질이 갑자기 생기는 장소가 아닙니다.
- 근거, 표, 비교, workflow 구조를 source에서 먼저 만듭니다.
- 장식 레이아웃으로 빈약한 사고를 가리지 않습니다.
- 실제 심사위원을 위한 문체로 씁니다.

제품에 UI가 있을 때:

- 표면 polish 전에 사용자 흐름을 먼저 정의합니다.
- spacing, hierarchy, copy를 의도적으로 유지합니다.
- reference pack과 승인된 자산을 함께 사용해 일관된 시각 시스템을 만듭니다.
- 장식 노이즈, 랜덤 카드, 빈 강조 도형을 피합니다.
- 여전히 generic하면 코드 polish보다 디자인 입력을 먼저 고칩니다.
- UI가 생기면 실행 중인 앱에서 동작을 확인합니다.

백엔드나 AI 작업이 있을 때:

- contract를 먼저 정의합니다.
- failure state를 반드시 다룹니다.
- 가정은 task spec 또는 PRD에 기록합니다.
- 중요한 business rule을 조용히 지어내지 않습니다.

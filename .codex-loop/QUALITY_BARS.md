# 품질 기준

활성 프로필은 `.codex-loop/config.json`의 `loop.quality_profile`에서 선택합니다.
비어 있으면 `proposal`, `planning`, `submission`, `contest`는 `proposal`로, `prd`는 `prd`로, `product-ui`, `ui`, `ux`, `design`은 `product-ui`로, 그 외는 `development`로 매핑합니다.
완료를 주장하려면 활성 프로필의 MUST 항목을 모두 만족해야 합니다.

## 개발

### MUST
1. 결과의 현실성
- 의미 있는 workflow, bugfix, feature slice가 end-to-end로 동작해야 합니다.
- runnable slice가 가능한데 scaffolding만으로 완료를 선언하면 안 됩니다.

2. 검증 증거
- 관련 tests, checks, screenshots가 실제로 실행되어 통과해야 합니다.
- UI 변경이면 source 코드뿐 아니라 렌더 증거가 있어야 합니다.

3. 제품 품질
- success, failure, loading, empty 상태 중 중요한 상태를 다뤄야 합니다.
- critical TODO, placeholder copy, fake data, 수동 절차를 사용자 합의 없이 남기면 안 됩니다.

4. 디자인 품질
- UI가 있다면 의도된 결과처럼 보여야 합니다.
- generic card spam, 약한 위계, 성긴 레이아웃, 미완성 polish는 실패입니다.

5. 통합의 정직함
- 동작이 바뀌면 계약 문서, 설정, 보조 파일도 함께 맞춰야 합니다.
- 요약과 문서의 주장은 실제 repo 상태와 일치해야 합니다.

## 제안서

### MUST
1. source의 정직함
- 실제 서사는 Markdown source에 살아 있어야 합니다.
- packaging 전에 source review를 통과해야 합니다.

2. 검토자 관점의 내용
- 대상 심사위원, 운영자, 구매자가 분명해야 합니다.
- 문제, 시급성, 해결책, 실현 가능성, 사업 경로, 기대 효과가 빠르게 재사용 가능한 언어로 정리되어야 합니다.
- 도우미 말투, 군더더기, 근거 없는 hype를 제거해야 합니다.

3. 근거 구조
- 빠르게 확인 가능한 표, 비교, workflow 설명, 캡처, 레퍼런스가 있어야 합니다.
- 정책·시장·규제·뉴스 맥락이 중요하면 source-backed evidence를 포함해야 합니다.

4. 페이지 밀도와 구성
- 페이지가 template-generic이 아니라 실제 작성된 문서처럼 느껴져야 합니다.
- 얇은 페이지, 장식용 동그라미, 빈 박스, 성긴 spread는 실패입니다.
- 함께 읽혀야 할 내용은 표로 정렬하고, 떠다니는 조각으로 흩뿌리지 않습니다.

## PRD

### MUST
1. 문제와 사용자 명확성
- 사용자 또는 운영자와 바뀌는 실제 workflow를 적습니다.
- 현재 pain과 원하는 결과를 분리합니다.

2. 범위 규율
- 필수 범위, 뒤로 미룬 범위, non-goal을 구분합니다.
- 가정은 숨기지 말고 기록합니다.

3. 실행 가능한 요구사항
- 요구사항은 build와 verify가 가능할 만큼 구체적이어야 합니다.
- acceptance criteria, dependency, constraint가 적혀 있어야 합니다.

4. task 준비도
- PRD, summary, task graph가 서로 맞아야 합니다.
- 바로 실행 가능한 다음 task가 하나 보여야 합니다.

## 제품 UI

### MUST
1. 흐름 우선
- 장식보다 먼저 핵심 사용자 경로가 분명해야 합니다.
- 화면 구조와 상태 전이가 명확해야 합니다.

2. 시각 시스템
- spacing, hierarchy, asset, 금지 패턴, reference pack이 구체적이어야 합니다.
- UI가 generic한 AI 출력처럼 보이면 실패입니다.

3. 자산 근거성
- 승인된 asset, screenshot, reference, generated input을 의도적으로 사용합니다.
- 각각의 자산이 어떤 역할인지 기록합니다.

4. 검증
- 실제로 다룬 UI 상태의 screenshot 또는 runtime evidence가 있어야 합니다.
- 텍스트가 잘 맞고 레이아웃이 버티며, 메인 화면이 비어 보이면 안 됩니다.

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from summit_intake import (
    canonical_mode,
    state_dir_from,
    write_text,
    read_text,
    load_json,
    write_json,
    ensure_intake_files,
    extract_field_any,
)
from summit_research import ensure_research_files

WORKFLOW_PROFILES: dict[str, dict[str, Any]] = {
    'proposal-only': {
        'label': '제안서 전용',
        'default_mode': 'proposal',
        'research_depth': 'deep',
        'when_to_use': [
            '공모전, 제안서, 사업계획서, 심사자료가 핵심 산출물일 때',
            '구현보다 reviewer-facing narrative와 증거 구조가 먼저일 때',
        ],
        'deliverables': [
            '폼 답변 초안',
            '심사위원용 첨부 문서 또는 PDF 원고',
            '근거 목록과 검토 체크리스트',
        ],
        'questions': [
            '이번 런의 최종 산출물은 무엇입니까? 예: 공모전 제출본, 제안서, 사업 계획서',
            '심사위원이나 검토자가 가장 먼저 이해해야 하는 핵심 메시지는 무엇입니까?',
            '반드시 들어가야 할 근거, 표, 캡처, 사례, 수치가 있습니까?',
        ],
        'stages': [
            {'id': 'onboarding', 'title': '온보딩', 'mode': 'proposal', 'outcome': '자료, 목표, 심사 맥락을 정리합니다.'},
            {'id': 'idea-screening', 'title': '인사이트 및 아이디어 선별', 'mode': 'proposal', 'outcome': '여러 방향을 비교하고 이번에 밀 방향을 하나 고릅니다.'},
            {'id': 'deep-research', 'title': '딥리서치', 'mode': 'proposal', 'outcome': '선택한 방향의 근거와 자료를 잠급니다.'},
            {'id': 'proposal-package', 'title': '제출 패키지 작성', 'mode': 'proposal', 'outcome': '제출용 본문과 첨부 문서를 완성합니다.'},
            {'id': 'review-and-submit', 'title': '최종 검토 및 제출', 'mode': 'proposal', 'outcome': '최종 검토, PDF 패키징, 제출 전 점검을 마칩니다.'},
        ],
    },
    'planning-only': {
        'label': '기획 전용',
        'default_mode': 'prd',
        'research_depth': 'standard',
        'when_to_use': [
            '아이디어는 어느 정도 정해졌지만 구현 전에 PRD와 task graph를 먼저 만들고 싶을 때',
            '팀 승인용 요구사항 문서와 실행 계획이 핵심 산출물일 때',
        ],
        'deliverables': [
            '확정된 PRD',
            'acceptance criteria가 달린 task graph',
            '오픈 질문과 리스크 목록',
        ],
        'questions': [
            '이번 런은 어디까지 기획으로 끝내고, 어디부터는 다음 단계로 넘길 계획입니까?',
            'PRD에서 가장 중요하게 잠가야 할 사용자 흐름과 비즈니스 규칙은 무엇입니까?',
            'task graph가 honest하다고 보려면 어떤 acceptance bar가 필요합니까?',
        ],
        'stages': [
            {'id': 'onboarding', 'title': '온보딩', 'mode': 'prd', 'outcome': '범위와 승인 기준을 잠급니다.'},
            {'id': 'brief-lock', 'title': '브리프 확정', 'mode': 'prd', 'outcome': '핵심 사용자, 문제, 비범위, 성공 조건을 명확히 합니다.'},
            {'id': 'deep-research', 'title': '딥리서치', 'mode': 'prd', 'outcome': '근거, 의존성, 제약, 오픈 이슈를 정리합니다.'},
            {'id': 'prd-and-task-graph', 'title': 'PRD 및 task graph', 'mode': 'prd', 'outcome': 'PRD와 실행 task graph를 완성합니다.'},
            {'id': 'approval-lock', 'title': '최종 승인 잠금', 'mode': 'prd', 'outcome': '실행 전 마지막 계획 승인 상태를 만듭니다.'},
        ],
    },
    'build-direct': {
        'label': '즉시 개발',
        'default_mode': 'implementation',
        'research_depth': 'standard',
        'when_to_use': [
            '아이디어와 요구사항이 이미 충분히 분명하고 바로 구현에 들어가고 싶을 때',
            '핵심 산출물이 동작하는 기능, 코드, 테스트, 검증일 때',
        ],
        'deliverables': [
            'repo 현실과 맞는 task graph',
            '동작하는 기능 단위',
            '검증 증거',
        ],
        'questions': [
            '이번 런에서 실제로 동작해야 하는 end-to-end workflow는 무엇입니까?',
            '반드시 통과해야 할 검증은 무엇입니까? 예: test, build, screenshot, smoke',
            '지금 바로 구현을 막는 외부 의존성이나 미정 규칙이 있습니까?',
        ],
        'stages': [
            {'id': 'onboarding', 'title': '온보딩', 'mode': 'implementation', 'outcome': '구현 목표와 evidence bar를 고정합니다.'},
            {'id': 'technical-research', 'title': '기술 조사', 'mode': 'implementation', 'outcome': 'repo 범위, 제약, 연동 조건을 빠르게 파악합니다.'},
            {'id': 'task-graph', 'title': 'Task graph 작성', 'mode': 'implementation', 'outcome': 'truthful task graph를 생성합니다.'},
            {'id': 'implementation', 'title': '구현', 'mode': 'implementation', 'outcome': '실제 기능을 구축합니다.'},
            {'id': 'verification', 'title': '검증', 'mode': 'implementation', 'outcome': 'local checks, review, evaluator까지 마칩니다.'},
        ],
    },
    'idea-to-service': {
        'label': '아이디어부터 서비스까지',
        'default_mode': 'proposal',
        'research_depth': 'deep',
        'when_to_use': [
            '공모전 자료나 문제 정의에서 시작해 실제 서비스 기획, 디자인, 개발까지 end-to-end로 가고 싶을 때',
            '아이디어 탐색부터 구현까지 단일 하네스 안에서 이어가고 싶을 때',
        ],
        'deliverables': [
            '아이디어 옵션과 최종 선택 방향',
            '딥리서치 패킷',
            'PRD와 task graph',
            '디자인 방향과 자산',
            '백엔드/프론트엔드 구현 및 검증',
        ],
        'questions': [
            '처음에 여러 아이디어 옵션을 받아보고 선택할지, 아니면 이미 고른 아이디어가 있는지 알려주세요.',
            '이번 런의 끝을 기획서 제출로 볼지, 동작하는 서비스까지 볼지, 둘 다 볼지 알려주세요.',
            '범위에 디자인, 프론트엔드, 백엔드, AI 모듈, 배포 검증까지 포함됩니까?',
        ],
        'stages': [
            {'id': 'onboarding', 'title': '온보딩', 'mode': 'proposal', 'outcome': '문제 정의, 자료, 기대 산출물, 범위를 정리합니다.'},
            {'id': 'insight-and-idea-options', 'title': '인사이트와 아이디어 옵션', 'mode': 'proposal', 'outcome': '문제에서 인사이트를 뽑고 여러 옵션을 제안합니다.'},
            {'id': 'deep-research', 'title': '딥리서치', 'mode': 'proposal', 'outcome': '선택한 방향의 근거와 현실 제약을 잠급니다.'},
            {'id': 'product-plan', 'title': '제품 기획', 'mode': 'prd', 'outcome': 'PRD, task graph, 서비스 범위를 만듭니다.'},
            {'id': 'design-system-and-flows', 'title': '디자인 시스템과 플로우', 'mode': 'product-ui', 'outcome': '디자인 방향, 핵심 화면, 상태, 자산을 정리합니다.'},
            {'id': 'backend-and-data', 'title': '백엔드와 데이터', 'mode': 'implementation', 'outcome': '서버, 데이터, AI contract를 구현합니다.'},
            {'id': 'frontend-integration', 'title': '프론트엔드 통합', 'mode': 'product-ui', 'outcome': '프론트엔드와 상호작용을 실제로 연결합니다.'},
            {'id': 'end-to-end-verification', 'title': 'End-to-end 검증', 'mode': 'implementation', 'outcome': '전체 흐름과 검증 증거를 마무리합니다.'},
        ],
    },
}

SEED_READY_STAGES = {
    'proposal-only': {'proposal-package', 'review-and-submit'},
    'planning-only': {'prd-and-task-graph', 'approval-lock'},
    'build-direct': {'task-graph', 'implementation', 'verification'},
    'idea-to-service': {'product-plan', 'design-system-and-flows', 'backend-and-data', 'frontend-integration', 'end-to-end-verification'},
}

COMMON_ONBOARDING = [
    '이번 런에서 지금 사용자가 하고 싶은 일은 무엇입니까?',
    '이번 런은 어디까지 진행하면 된다고 보십니까? 즉, 이번에 멈출 지점은 어디입니까?',
    '이번 런의 최종 산출물은 무엇입니까?',
    '이번 런에서 반드시 honest COMPLETE라고 부를 수 있는 기준은 무엇입니까?',
    '이미 가지고 있는 입력 자료는 무엇입니까? 예: 공모전 요강, PRD, repo, PDF, Figma, screenshots',
    '누가 승인권자입니까? 또는 누가 최종 의사결정을 합니까?',
]

FIELD_ALIASES = {
    'profile': ['프로필', 'Profile'],
    'profile_label': ['프로필-라벨', 'Profile-Label', 'Label'],
    'goal': ['목표', 'Goal'],
    'status': ['상태', 'Status'],
    'current_stage': ['현재-단계', 'Current-Stage'],
    'current_mode': ['현재-모드', 'Current-Mode'],
}


def workflow_dir_from(state_dir: Path) -> Path:
    return state_dir / '.codex-loop' / 'workflow' if state_dir.name != '.codex-loop' else state_dir / 'workflow'


def onboarding_path(state_dir: Path) -> Path:
    return workflow_dir_from(state_dir) / 'ONBOARDING.md'


def ideas_path(state_dir: Path) -> Path:
    return workflow_dir_from(state_dir) / 'IDEAS.md'


def profile_path(state_dir: Path) -> Path:
    return workflow_dir_from(state_dir) / 'PROFILE.md'


def status_path(state_dir: Path) -> Path:
    return workflow_dir_from(state_dir) / 'STATUS.md'


def profile_spec(profile: str) -> dict[str, Any]:
    key = (profile or '').strip().lower()
    if key not in WORKFLOW_PROFILES:
        raise KeyError(f'알 수 없는 워크플로우 프로필입니다: {profile}')
    return WORKFLOW_PROFILES[key]


def infer_profile(profile: str) -> str:
    key = (profile or '').strip().lower()
    return key if key in WORKFLOW_PROFILES else 'idea-to-service'


def build_onboarding_markdown(profile: str, goal: str) -> str:
    spec = profile_spec(profile)
    lines = [
        '# Summit 워크플로우 온보딩',
        '',
        f'프로필: {profile}',
        f'프로필-라벨: {spec["label"]}',
        f'목표: {goal or "대기 중."}',
        '상태: 초안',
        '',
        '이 문서는 `/ralph-start` 이후 가장 먼저 잠그는 상위 온보딩 문서입니다. 첫 질문은 사용자가 지금 무엇을 하고 싶은지 확인하는 것입니다.',
        '',
        '## 공통 질문',
    ]
    for index, question in enumerate(COMMON_ONBOARDING, start=1):
        lines.extend([
            f'### C{index}. {question}',
            '답변:',
            '- 대기 중.',
            '',
        ])
    lines.extend(['## 프로필별 질문'])
    for index, question in enumerate(spec['questions'], start=1):
        lines.extend([
            f'### P{index}. {question}',
            '답변:',
            '- 대기 중.',
            '',
        ])
    lines.extend([
        '## 확정 결정',
        '- 작성 필요: 선택한 workflow 경로와 그 이유를 적어주세요.',
        '',
        '## 포함 영역',
        '- 작성 필요: proposal, design, frontend, backend, AI module, deployment 중 실제 범위를 적어주세요.',
        '',
        '## 증거 기준',
        '- 작성 필요: 선택한 workflow가 단계 완료를 주장하기 전에 반드시 있어야 할 증거를 적어주세요.',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def build_ideas_markdown(profile: str) -> str:
    spec = profile_spec(profile)
    lines = [
        '# Summit 워크플로우 아이디어',
        '',
        f'프로필: {profile}',
        '상태: 초안',
        '',
        '아이디어 옵션이 필요한 프로필이라면 여기서 후보를 비교하고 한 방향으로 잠급니다.',
        '',
        '## 후보 방향',
        '- 옵션 A: 대기 중.',
        '- 옵션 B: 대기 중.',
        '- 옵션 C: 대기 중.',
        '',
        '## 비교',
        '| 옵션 | 강점 | 리스크 | 판단 |',
        '| --- | --- | --- | --- |',
        '| A | 대기 중 | 대기 중 | 대기 중 |',
        '| B | 대기 중 | 대기 중 | 대기 중 |',
        '| C | 대기 중 | 대기 중 | 대기 중 |',
        '',
        '## 선택한 방향',
        '- 작성 필요: 최종 선택 방향과 이 프로필에서 이 방향이 맞는 이유를 적어주세요.',
        '',
        '## 목표 산출물',
        *[f'- {item}' for item in spec['deliverables']],
    ]
    return '\n'.join(lines).rstrip() + '\n'


def build_profile_markdown(profile: str) -> str:
    spec = profile_spec(profile)
    lines = [
        '# Summit 워크플로우 프로필',
        '',
        f'프로필: {profile}',
        f'프로필-라벨: {spec["label"]}',
        f'기본-모드: {spec["default_mode"]}',
        '',
        '## 이런 경우에 사용합니다',
        *[f'- {item}' for item in spec['when_to_use']],
        '',
        '## 목표 산출물',
        *[f'- {item}' for item in spec['deliverables']],
        '',
        '## 단계 맵',
        '| 단계 ID | 권장 모드 | 완료 결과 |',
        '| --- | --- | --- |',
    ]
    for stage in spec['stages']:
        lines.append(f"| {stage['id']} | {stage['mode']} | {stage['outcome']} |")
    return '\n'.join(lines).rstrip() + '\n'


def build_status_markdown(profile: str, goal: str, current_stage: str | None = None) -> str:
    spec = profile_spec(profile)
    stages = spec['stages']
    active = current_stage or stages[0]['id']
    stage_ids = {stage['id'] for stage in stages}
    if active not in stage_ids:
        active = stages[0]['id']
    current = next(stage for stage in stages if stage['id'] == active)
    current_index = next((i for i, stage in enumerate(stages) if stage['id'] == current['id']), 0)
    lines = [
        '# Summit 워크플로우 상태',
        '',
        f'프로필: {profile}',
        f'목표: {goal or "대기 중."}',
        f'현재-단계: {current["id"]}',
        f'현재-모드: {current["mode"]}',
        '상태: 진행 중',
        '',
        '## 단계 체크리스트',
    ]
    for index, stage in enumerate(stages):
        if index < current_index:
            prefix = '[x]'
        elif stage['id'] == current['id']:
            prefix = '[> ]'
        else:
            prefix = '[ ]'
        lines.append(f"- {prefix} {stage['id']}: {stage['title']} ({stage['mode']})")
    lines.extend([
        '',
        '## 현재 단계 완료 결과',
        f"- {current['outcome']}",
        '',
        '## 다음 두 단계',
    ])
    remaining = spec['stages'][next((i for i, stage in enumerate(spec['stages']) if stage['id'] == current['id']), 0) + 1 :]
    for stage in remaining[:2]:
        lines.append(f"- {stage['id']} ({stage['mode']}): {stage['outcome']}")
    if not remaining:
        lines.append('- 없음. 이 프로필은 마지막 단계에 도달했습니다.')
    lines.extend([
        '',
        '## 다음 단계로 넘기는 법',
        '- 현재 단계가 정말 완료되었을 때 이 파일과 config를 함께 업데이트합니다.',
        '- `python3 scripts/summit_start.py advance --stage <stage-id>`로 다음 단계로 이동합니다.',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def ensure_workflow_files(state_dir: Path, profile: str, goal: str, force: bool = False) -> None:
    workflow_dir_from(state_dir).mkdir(parents=True, exist_ok=True)
    docs = {
        onboarding_path(state_dir): build_onboarding_markdown(profile, goal),
        ideas_path(state_dir): build_ideas_markdown(profile),
        profile_path(state_dir): build_profile_markdown(profile),
        status_path(state_dir): build_status_markdown(profile, goal),
    }
    for doc_path, doc_content in docs.items():
        if doc_path.exists() and not force:
            continue
        write_text(doc_path, doc_content)


def apply_config(state_dir: Path, profile: str, goal: str, stage_id: str | None = None) -> dict[str, Any]:
    spec = profile_spec(profile)
    stage = next((item for item in spec['stages'] if item['id'] == stage_id), spec['stages'][0])
    config = load_json(state_dir / 'config.json', {'loop': {}})
    loop = config.setdefault('loop', {})
    loop['workflow_profile'] = profile
    loop['workflow_stage'] = stage['id']
    loop['workflow_goal'] = goal
    loop['mode'] = canonical_mode(stage['mode'])
    loop.setdefault('require_intake_approval', True)
    loop.setdefault('require_research_plan', True)
    write_json(state_dir / 'config.json', config)
    return config


def sync_status_file(state_dir: Path, profile: str, goal: str, stage_id: str | None = None) -> None:
    write_text(status_path(state_dir), build_status_markdown(profile, goal, current_stage=stage_id))


def load_workflow_status(state_dir: Path) -> dict[str, Any]:
    config = load_json(state_dir / 'config.json', {})
    loop = config.get('loop', {}) if isinstance(config, dict) else {}
    profile = str(loop.get('workflow_profile', '')).strip()
    status_text = read_text(status_path(state_dir))
    if not profile:
        profile = extract_field_any(status_text, FIELD_ALIASES['profile'])
    initialized = bool(profile)
    if not initialized:
        return {
            'initialized': False,
            'profile': '',
            'currentStage': '',
            'currentMode': canonical_mode(str(loop.get('mode', 'implementation'))),
            'goal': str(loop.get('workflow_goal', '')).strip(),
            'summary': ['- 아직 워크플로우 프로필이 초기화되지 않았습니다.'],
            'nextStages': [],
        }

    spec = profile_spec(infer_profile(profile))
    stage_id = str(loop.get('workflow_stage', '')).strip() or extract_field_any(status_text, FIELD_ALIASES['current_stage']) or spec['stages'][0]['id']
    current = next((stage for stage in spec['stages'] if stage['id'] == stage_id), spec['stages'][0])
    goal = str(loop.get('workflow_goal', '')).strip() or extract_field_any(status_text, FIELD_ALIASES['goal'])
    current_index = next((i for i, stage in enumerate(spec['stages']) if stage['id'] == current['id']), 0)
    next_stages = spec['stages'][current_index + 1 : current_index + 3]
    summary = [
        f'- 워크플로우 프로필: {profile}',
        f"- 현재 단계: {current['id']} ({current['mode']})",
        f"- 현재 단계 목표: {current['outcome']}",
    ]
    if goal:
        summary.append(f'- 워크플로우 목표: {goal}')
    for stage in next_stages:
        summary.append(f"- 다음 단계: {stage['id']} -> {stage['outcome']}")
    seed_ready = current['id'] in SEED_READY_STAGES.get(profile, set())
    return {
        'initialized': True,
        'profile': profile,
        'label': spec['label'],
        'currentStage': current['id'],
        'currentStageTitle': current['title'],
        'currentMode': current['mode'],
        'goal': goal,
        'summary': summary,
        'nextStages': next_stages,
        'researchDepth': spec['research_depth'],
        'seedReady': seed_ready,
    }


def workflow_seed_gate_message(status: dict[str, Any]) -> str:
    if not status.get('initialized'):
        return '먼저 `python3 scripts/summit_start.py init ...`로 워크플로우 프로필을 초기화하세요.'
    if status.get('seedReady'):
        return '현재 워크플로우는 task seed 생성이 가능한 단계입니다.'
    current = status.get('currentStage') or '현재 단계'
    next_stages = status.get('nextStages', []) or []
    next_hint = f" 다음으로는 `{next_stages[0]['id']}` 단계까지 진행하는 것이 좋습니다." if next_stages else ''
    return f'현재 워크플로우 단계 `{current}` 는 아직 task seed 생성 이전 단계입니다. 온보딩, 아이디어 정리, 리서치를 먼저 마무리한 뒤 workflow를 다음 단계로 넘기세요.{next_hint}'


def workflow_status_block(state_dir: Path) -> str:
    status = load_workflow_status(state_dir)
    if not status.get('initialized'):
        return '- 워크플로우 프로필: 없음\n- 현재 단계: 없음\n- 목표: 없음'
    goal = status.get('goal') or '없음'
    return f"- 워크플로우 프로필: {status.get('profile')}\n- 현재 단계: {status.get('currentStage')}\n- 목표: {goal}"


def workflow_summary(state_dir: Path) -> str:
    status = load_workflow_status(state_dir)
    return '\n'.join(status.get('summary', []) or ['- 아직 워크플로우 프로필이 초기화되지 않았습니다.'])


def workflow_profile_text(state_dir: Path) -> str:
    return read_text(profile_path(state_dir)) or '아직 워크플로우 프로필 문서가 없습니다.'


def workflow_status_text(state_dir: Path) -> str:
    return read_text(status_path(state_dir)) or '아직 워크플로우 상태 문서가 없습니다.'


def command_init(root: Path, profile: str, goal: str, force: bool) -> int:
    state_dir = state_dir_from(root)
    state_dir.mkdir(parents=True, exist_ok=True)
    normalized = infer_profile(profile)
    spec = profile_spec(normalized)
    ensure_workflow_files(state_dir, normalized, goal, force=force)
    apply_config(state_dir, normalized, goal)
    ensure_intake_files(state_dir, spec['default_mode'], force=force)
    ensure_research_files(state_dir, spec['default_mode'], spec['research_depth'], force=force)
    sync_status_file(state_dir, normalized, goal)
    print(f'Summit 워크플로우 `{normalized}` 를 초기화했습니다: {workflow_dir_from(state_dir)}')
    print('다음 단계:')
    print('  1. `workflow/ONBOARDING.md`에 먼저 "이번 런에서 지금 사용자가 하고 싶은 일"부터 적습니다.')
    print('  2. 아이디어가 열려 있다면 `workflow/IDEAS.md`에서 옵션을 비교하고 하나를 잠급니다.')
    print('  3. 현재 단계 모드에 맞게 intake 승인과 research 승인을 완료합니다.')
    print('  4. `python3 scripts/context_engine.py refresh --source workflow-start`로 컨텍스트를 갱신합니다.')
    return 0


def command_advance(root: Path, stage: str) -> int:
    state_dir = state_dir_from(root)
    status = load_workflow_status(state_dir)
    if not status.get('initialized'):
        raise SystemExit('워크플로우가 아직 초기화되지 않았습니다. 먼저 `python3 scripts/summit_start.py init ...`를 실행하세요.')
    profile = str(status['profile'])
    spec = profile_spec(profile)
    target = next((item for item in spec['stages'] if item['id'] == stage), None)
    if target is None:
        raise SystemExit(f'프로필 `{profile}` 에는 `{stage}` 단계가 없습니다.')
    goal = status.get('goal', '')
    apply_config(state_dir, profile, goal, stage_id=stage)
    ensure_intake_files(state_dir, target['mode'], force=False)
    ensure_research_files(state_dir, target['mode'], spec['research_depth'], force=False)
    sync_status_file(state_dir, profile, goal, stage_id=stage)
    print(f'워크플로우 `{profile}` 를 `{stage}` 단계({target["mode"]})로 이동했습니다.')
    return 0


def command_status(root: Path, as_json: bool) -> int:
    status = load_workflow_status(state_dir_from(root))
    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    if not status.get('initialized'):
        print('워크플로우 프로필: 초기화되지 않음')
        print('다음 단계: 먼저 사용자에게 이번 런에서 무엇을 하고 싶은지 물은 뒤 `/ralph-start` 또는 `python3 scripts/summit_start.py init --profile ... --goal ...` 를 사용하세요.')
        return 0
    print(f"프로필: {status['profile']}")
    print(f"현재 단계: {status['currentStage']} ({status['currentMode']})")
    if status.get('goal'):
        print(f"목표: {status['goal']}")
    print('요약:')
    for item in status.get('summary', []):
        print(item)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='SummitHarness 워크플로우 프로필과 단계를 초기화하고 상태를 확인합니다.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    init_cmd = subparsers.add_parser('init', help='워크플로우 온보딩 문서와 단계 상태를 초기화합니다')
    init_cmd.add_argument('--profile', default='idea-to-service', choices=sorted(WORKFLOW_PROFILES.keys()))
    init_cmd.add_argument('--goal', default='', help='이번 런의 한 줄 목표')
    init_cmd.add_argument('--root', default='.', help='프로젝트 루트')
    init_cmd.add_argument('--force', action='store_true', help='기존 workflow 문서를 덮어씁니다')

    advance_cmd = subparsers.add_parser('advance', help='워크플로우를 다음 단계로 넘깁니다')
    advance_cmd.add_argument('--stage', required=True, help='선택한 프로필에 정의된 stage id')
    advance_cmd.add_argument('--root', default='.', help='프로젝트 루트')

    status_cmd = subparsers.add_parser('status', help='현재 워크플로우 프로필과 단계를 보여줍니다')
    status_cmd.add_argument('--root', default='.', help='프로젝트 루트')
    status_cmd.add_argument('--json', action='store_true')

    args = parser.parse_args()
    root = Path(getattr(args, 'root', '.')).expanduser().resolve()
    if args.command == 'init':
        return command_init(root, args.profile, args.goal.strip(), args.force)
    if args.command == 'advance':
        return command_advance(root, args.stage)
    if args.command == 'status':
        return command_status(root, args.json)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from summit_intake import (
    canonical_mode,
    state_dir_from,
    write_text,
    read_text,
    load_json,
    write_json,
    extract_field_any,
    parse_bool,
    normalize_status,
    extract_section_items,
)

PHASES = [
    ('문제 프레이밍', '인테이크에서 나온 문제, 대상 독자, 제약, 성공 기준을 다시 정리합니다.'),
    ('미확인 쟁점', '추측으로 덮지 말고 근거가 더 필요한 질문을 분리합니다.'),
    ('근거 수집', '정책, 기사, 저장소 사실, 스크린샷, 기술 제약 등 필요한 근거를 모읍니다.'),
    ('방향 비교', '가능한 방향을 비교하고 약한 경로나 가짜 완료 경로를 제거합니다.'),
    ('방향 결정', '이번 런에서 밀고 갈 방향을 하나로 잠급니다.'),
    ('실행 단계화', '선택한 방향을 에이전트가 따를 수 있는 단계별 실행안으로 바꿉니다.'),
]

MODE_GUIDANCE = {
    'proposal': {
        'research_focus': [
            '심사 기준, 제출 구조, 첨부 규칙',
            '문제 심각성을 보여줄 정책·시장·사회 맥락',
            '제안서의 신뢰도를 높이는 스크린샷, 사례, 수치, 레퍼런스',
        ],
        'deliverables': [
            '폼 답변과 첨부 문서에 바로 옮길 수 있는 검토자 관점 실행안',
            '문서에 반드시 남아야 할 핵심 근거 목록',
            '개요에서 최종 제출본까지 이어지는 단계별 작성 계획',
        ],
    },
    'prd': {
        'research_focus': [
            '첫 릴리스 범위와 이후 단계로 넘길 범위',
            '핵심 사용자 여정, 의존성, 리스크',
            '계획을 실제로 움직이게 할 acceptance criteria',
        ],
        'deliverables': [
            '권장 릴리스 경계',
            '기획과 검증의 우선순위 단계',
            'PRD에 끝까지 남겨야 할 핵심 미해결 사항',
        ],
    },
    'implementation': {
        'research_focus': [
            'repo 범위, 기술 제약, 검증 명령',
            '런타임, secret, 통합, 환경 제약',
            '겉보기 완료를 만들 수 있는 위험 요소',
        ],
        'deliverables': [
            '코딩 에이전트가 바로 따를 수 있는 단계별 실행 계획',
            '실제 검증 및 증거 기준',
            'task에 함께 가져가야 할 기술 리스크와 유예 항목',
        ],
    },
    'product-ui': {
        'research_focus': [
            '시각 레퍼런스, 위계 규칙, 금지 패턴',
            '필수 화면, 상태, breakpoint, asset',
            'generic한 AI 박스와 실제 인터페이스를 가르는 기준',
        ],
        'deliverables': [
            '승인된 시각 방향과 화면 범위 계획',
            '반드시 존재해야 할 스크린샷, asset, 상호작용 목록',
            '구조에서 polish까지 이어지는 단계별 UI 실행안',
        ],
    },
}

FIELD_ALIASES = {
    'mode': ['모드', 'Mode'],
    'status': ['상태', 'Status'],
    'approved': ['승인', 'Approved'],
    'approved_by': ['승인자', 'Approved-By'],
    'approved_at': ['승인 시각', 'Approved-At'],
}

SECTION_ALIASES = [
    ('권장 방향', ['권장 방향', 'Recommended Direction']),
    ('선택 이유', ['이 방향을 선택한 이유', 'Why This Direction Wins']),
    ('단계별 실행 계획', ['단계별 실행 계획', 'Staged Execution Plan']),
    ('리스크와 유의사항', ['리스크와 유의사항', 'Risks And Watchouts']),
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def research_dir_from(state_dir: Path) -> Path:
    return state_dir / '.codex-loop' / 'research' if state_dir.name != '.codex-loop' else state_dir / 'research'


def plan_path(state_dir: Path) -> Path:
    return research_dir_from(state_dir) / 'PLAN.md'


def findings_path(state_dir: Path) -> Path:
    return research_dir_from(state_dir) / 'FINDINGS.md'


def approval_path(state_dir: Path) -> Path:
    return research_dir_from(state_dir) / 'APPROVAL.md'


def build_plan_markdown(mode: str, depth: str) -> str:
    canonical = canonical_mode(mode)
    guidance = MODE_GUIDANCE.get(canonical, MODE_GUIDANCE['implementation'])
    lines = [
        '# Summit 리서치 계획',
        '',
        f'모드: {canonical}',
        '상태: 초안',
        f'리서치-깊이: {depth}',
        '',
        '인테이크 승인 이후, task seed 생성 전에 이 문서를 먼저 잠급니다.',
        '',
        '## 리서치 핵심 포인트',
        *[f'- {item}' for item in guidance['research_focus']],
        '',
        '## 단계',
    ]
    for index, (name, description) in enumerate(PHASES, start=1):
        lines.extend([
            f'### {index}단계. {name}',
            description,
            '이번 단계에서 답할 질문:',
            '- 대기 중.',
            '수집할 근거:',
            '- 대기 중.',
            '산출물:',
            '- 대기 중.',
            '',
        ])
    lines.extend([
        '## 예상 산출물',
        *[f'- {item}' for item in guidance['deliverables']],
        '',
        '## 단계별 실행 초안',
        '- 1단계: 대기 중.',
        '- 2단계: 대기 중.',
        '- 3단계: 대기 중.',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def build_findings_markdown(mode: str) -> str:
    canonical = canonical_mode(mode)
    return '\n'.join([
        '# Summit 리서치 결과',
        '',
        f'모드: {canonical}',
        '상태: 초안',
        '',
        '## 핵심 발견',
        '- 대기 중.',
        '',
        '## 근거 로그',
        '- 대기 중.',
        '',
        '## 기각한 방향',
        '- 대기 중.',
        '',
        '## 다음 단계로 넘길 리스크',
        '- 대기 중.',
    ]).rstrip() + '\n'


def build_approval_markdown(mode: str) -> str:
    canonical = canonical_mode(mode)
    return '\n'.join([
        '# Summit 리서치 승인',
        '',
        f'모드: {canonical}',
        '상태: 대기',
        '승인: 아니오',
        '승인자:',
        '승인 시각:',
        '',
        '## 권장 방향',
        '- 작성 필요: 리서치 후 선택한 방향을 적어주세요.',
        '',
        '## 이 방향을 선택한 이유',
        '- 작성 필요: 이번 런에서 이 방향이 맞는 이유를 적어주세요.',
        '',
        '## 단계별 실행 계획',
        '- 작성 필요: 1단계 실행 계획',
        '- 작성 필요: 2단계 실행 계획',
        '- 작성 필요: 3단계 실행 계획',
        '',
        '## 유지해야 할 근거',
        '- 작성 필요: 이후 단계에서도 계속 남아 있어야 할 근거를 적어주세요.',
        '',
        '## 리스크와 유의사항',
        '- 작성 필요: task graph에 함께 가져가야 할 리스크를 적어주세요.',
    ]).rstrip() + '\n'


def ensure_research_files(state_dir: Path, mode: str, depth: str, force: bool = False) -> None:
    canonical = canonical_mode(mode)
    research_dir_from(state_dir).mkdir(parents=True, exist_ok=True)
    docs = {
        plan_path(state_dir): build_plan_markdown(canonical, depth),
        findings_path(state_dir): build_findings_markdown(canonical),
        approval_path(state_dir): build_approval_markdown(canonical),
    }
    for path, content in docs.items():
        if path.exists() and not force:
            continue
        write_text(path, content)


def write_config(state_dir: Path, mode: str) -> None:
    config = load_json(state_dir / 'config.json', {'loop': {}})
    loop = config.setdefault('loop', {})
    loop['mode'] = canonical_mode(mode)
    loop.setdefault('require_research_plan', True)
    write_json(state_dir / 'config.json', config)


def extract_field(text: str, name: str) -> str:
    return extract_field_any(text, [name])


def extract_section_items_any(text: str, headings: list[str]) -> list[str]:
    for heading in headings:
        items = extract_section_items(text, heading)
        if items:
            return items
    return []


def load_research_status(state_dir: Path) -> dict[str, Any]:
    approval_text = read_text(approval_path(state_dir))
    config_mode = load_json(state_dir / 'config.json', {}).get('loop', {}).get('mode', 'implementation')
    mode = canonical_mode(extract_field_any(approval_text, FIELD_ALIASES['mode']) or str(config_mode))
    status_value = normalize_status(extract_field_any(approval_text, FIELD_ALIASES['status']) or 'pending')
    approved = parse_bool(extract_field_any(approval_text, FIELD_ALIASES['approved'])) and status_value in {'approved', 'locked', 'complete'}
    missing = []
    if not plan_path(state_dir).exists():
        missing.append('리서치 계획 문서가 없습니다')
    if not findings_path(state_dir).exists():
        missing.append('리서치 결과 문서가 없습니다')
    if not approval_path(state_dir).exists():
        missing.append('리서치 승인 문서가 없습니다')
    if not approved:
        missing.append('리서치 승인이 완료되지 않았습니다')

    summary = []
    for label, headings in SECTION_ALIASES:
        for item in extract_section_items_any(approval_text, headings)[:2]:
            summary.append(f'- {label}: {item}')

    return {
        'mode': mode,
        'status': status_value,
        'approved': approved,
        'approvedBy': extract_field_any(approval_text, FIELD_ALIASES['approved_by']),
        'approvedAt': extract_field_any(approval_text, FIELD_ALIASES['approved_at']),
        'missing': missing,
        'planExists': plan_path(state_dir).exists(),
        'findingsExists': findings_path(state_dir).exists(),
        'approvalExists': approval_path(state_dir).exists(),
        'summary': summary,
    }


def research_gate_message(status: dict[str, Any]) -> str:
    if status.get('approved'):
        return '리서치 계획 승인이 완료되었습니다.'
    missing = ', '.join(status.get('missing', [])[:3]) or '리서치 승인이 완료되지 않았습니다'
    return f'첫 seed 실행 전까지 `.codex-loop/research/APPROVAL.md`를 승인 상태로 잠그고, 단계형 deep research 계획을 완료하세요 ({missing}).'


def command_init(root: Path, mode: str, depth: str, force: bool) -> int:
    state_dir = state_dir_from(root)
    state_dir.mkdir(parents=True, exist_ok=True)
    canonical = canonical_mode(mode)
    write_config(state_dir, canonical)
    ensure_research_files(state_dir, canonical, depth, force=force)
    print(f'Summit 리서치 문서를 `{canonical}` 모드로 초기화했습니다: {research_dir_from(state_dir)}')
    print('다음 단계:')
    print('  1. `PLAN.md`에 실제 단계형 리서치 경로를 적습니다.')
    print('  2. `FINDINGS.md`에 근거와 기각한 방향을 기록합니다.')
    print('  3. `APPROVAL.md`에 권장 방향과 단계별 실행 계획을 잠급니다.')
    print('  4. 실제 승인 후 `승인: 예`와 `상태: 승인`으로 변경합니다.')
    return 0


def command_status(root: Path, as_json: bool) -> int:
    status = load_research_status(state_dir_from(root))
    payload = {
        'mode': status['mode'],
        'status': status['status'],
        'approved': status['approved'],
        'approvedBy': status['approvedBy'],
        'approvedAt': status['approvedAt'],
        'missing': status['missing'],
        'summary': status['summary'],
        'nextStep': research_gate_message(status),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"모드: {payload['mode']}")
    print(f"상태: {payload['status']}")
    print(f"승인: {'예' if payload['approved'] else '아니오'}")
    if payload['approvedBy']:
        print(f"승인자: {payload['approvedBy']}")
    if payload['approvedAt']:
        print(f"승인 시각: {payload['approvedAt']}")
    if payload['summary']:
        print('리서치 요약:')
        for item in payload['summary']:
            print(item)
    print(f"다음 단계: {payload['nextStep']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='SummitHarness 단계형 리서치 게이트를 초기화하고 상태를 확인합니다.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    init_cmd = subparsers.add_parser('init', help='단계형 리서치 문서를 생성하거나 새로 고칩니다')
    init_cmd.add_argument('--mode', default='implementation', help='proposal | prd | implementation | product-ui')
    init_cmd.add_argument('--depth', default='standard', help='light | standard | deep')
    init_cmd.add_argument('--force', action='store_true', help='기존 리서치 파일을 덮어씁니다')
    init_cmd.add_argument('--root', default='.', help='프로젝트 루트')

    status_cmd = subparsers.add_parser('status', help='첫 seed 실행 기준으로 리서치 승인 상태를 보여줍니다')
    status_cmd.add_argument('--root', default='.', help='프로젝트 루트')
    status_cmd.add_argument('--json', action='store_true', help='상태를 JSON으로 출력합니다')

    args = parser.parse_args()
    root = Path(getattr(args, 'root', '.')).expanduser().resolve()
    if args.command == 'init':
        return command_init(root, args.mode, args.depth, args.force)
    if args.command == 'status':
        return command_status(root, args.json)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

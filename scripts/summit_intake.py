#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

MODE_ALIASES = {
    'planning': 'proposal',
    'submission': 'proposal',
    'contest': 'proposal',
    'deck': 'proposal',
    'spec': 'prd',
    'ui': 'product-ui',
    'ux': 'product-ui',
    'design': 'product-ui',
}

COMMON_SECTIONS = [
    {
        'role': '요청자 / 제품',
        'purpose': '무엇을 실제로 만들려는지와, 어디까지를 첫 완성으로 볼지 분명히 합니다.',
        'questions': [
            '이번 런에서 실제로 만드는 것을 한 문장으로 적으면 무엇입니까?',
            '이 결과물을 가장 먼저 사용할 사람 또는 검토할 사람은 누구입니까?',
            '어떤 조건이 충족되어야 이 첫 버전을 정말 쓸 만하다고 말할 수 있습니까?',
            '이번 런에서 명시적으로 제외할 범위는 무엇입니까?',
        ],
    },
    {
        'role': '승인 / 검토',
        'purpose': '자율 실행 전에 실제 의사결정권자와 완료 판단 기준을 먼저 잠급니다.',
        'questions': [
            '이 브리프와 task graph를 최종 승인할 사람은 누구입니까?',
            'COMPLETE라고 말하기 전에 반드시 남아 있어야 할 증거와 산출물은 무엇입니까?',
            '유혹적이지만 허용할 수 없는 지름길은 무엇입니까?',
        ],
    },
]

MODE_SECTIONS = {
    'proposal': [
        {
            'role': '제출 전략',
            'purpose': '입력 폼, 심사위원 기대치, 첨부 문서 규칙을 먼저 정리합니다.',
            'questions': [
                '여기서 중요한 입력 항목, 분량 제한, 파일 규칙, 심사 기준은 정확히 무엇입니까?',
                '심사위원에게 어떤 톤과 문체로 써야 합니까?',
                '선택이 아니라 반드시 들어가야 할 근거, 레퍼런스, 스크린샷은 무엇입니까?',
            ],
        },
        {
            'role': '근거 / 스토리',
            'purpose': '제안서가 기능 나열이 아니라 설득력 있는 이야기와 근거를 갖추게 합니다.',
            'questions': [
                '문제의 심각성, 정책 환경, 시장 배경, 사회적 맥락 중 무엇을 앞부분에 꼭 밝혀야 합니까?',
                '심사위원이 읽고 나서 꼭 기억해야 할 구체적 시나리오는 무엇입니까?',
                '첨부 문서에는 텍스트 외에 어떤 시각 자료나 증거가 들어가야 합니까?',
            ],
        },
    ],
    'prd': [
        {
            'role': '제품 정의',
            'purpose': '거친 아이디어를 첫 릴리스 범위와 측정 가능한 경계로 바꿉니다.',
            'questions': [
                '첫 릴리스 범위는 어디까지이며, 의도적으로 뒤로 미룬 것은 무엇입니까?',
                '초기 계획에서 가장 중요한 사용자 여정은 무엇입니까?',
                'PRD에 반드시 드러나야 하는 제약, 의존성, 결정 사항은 무엇입니까?',
            ],
        },
        {
            'role': '검증 기준',
            'purpose': 'PRD가 선언문이 아니라 실제 실행 가능한 문서가 되도록 기준을 정합니다.',
            'questions': [
                '계획서에 반드시 포함되어야 할 지표, acceptance criteria, 운영 요구사항은 무엇입니까?',
                '추측으로 덮지 말고 끝까지 드러나 있어야 할 미해결 질문은 무엇입니까?',
            ],
        },
    ],
    'implementation': [
        {
            'role': '엔지니어링',
            'purpose': '이번 런에서 다룰 repo 범위, 실행 환경, 현실적인 구현 단위를 정합니다.',
            'questions': [
                '이번 런에서 범위에 포함되는 repo 또는 코드 영역은 어디입니까?',
                '실제 검증 기준으로 볼 명령은 무엇입니까? 예: build, test, lint, smoke, screenshot',
                '지금 사용할 수 없어 mock 처리하거나 뒤로 미뤄야 하는 연동, secret, 환경이 있습니까?',
            ],
        },
        {
            'role': '품질 / 운영',
            'purpose': '겉보기만 완료된 결과가 나가지 않도록 운영 관점의 기준을 잡습니다.',
            'questions': [
                '여기서 가장 비용이 큰 실패 모드나 회귀는 무엇입니까?',
                '다른 운영자도 결과를 신뢰할 수 있도록 repo 안에 어떤 증거가 남아 있어야 합니까?',
            ],
        },
    ],
    'product-ui': [
        {
            'role': '디자인',
            'purpose': '화면을 다듬기 전에 시각 방향, 위계, 상태 범위를 먼저 고정합니다.',
            'questions': [
                '이 UI는 어떤 제품, 편집물, 서비스 레퍼런스에 가장 가까운 감각이어야 합니까?',
                '반드시 설계되어야 하는 화면, 상태, breakpoint, edge case는 무엇입니까?',
                '이 프로젝트에서 절대 허용할 수 없는 시각적 안티패턴은 무엇입니까?',
            ],
        },
        {
            'role': '프론트엔드 / 상호작용',
            'purpose': '박스와 placeholder를 넘어서 무엇이 실제 UI인지 기준을 정합니다.',
            'questions': [
                '반드시 존재해야 하는 asset, media, 데이터 상태, 실제 상호작용은 무엇입니까?',
                '검토 시 가장 중요한 기기와 레이아웃은 무엇입니까?',
                'UI 완료라고 주장하기 전에 loop가 남겨야 할 스크린샷과 증거는 무엇입니까?',
            ],
        },
    ],
}

APPROVAL_CHECKLIST = {
    'proposal': [
        '제출 대상 독자, 형식, 심사 기준이 명확합니다.',
        '첨부 문서 또는 PDF에 대한 기대 수준이 구체적입니다.',
        '폼 답변과 첨부 문서에 반드시 들어가야 할 근거를 팀이 알고 있습니다.',
    ],
    'prd': [
        '릴리스 경계가 계획을 세울 수 있을 정도로 명확합니다.',
        '열린 질문이 모호한 문장 뒤에 숨지 않고 드러나 있습니다.',
        '가짜 완료를 막을 만큼 acceptance 기준이 충분히 강합니다.',
    ],
    'implementation': [
        '범위에 포함된 repo 영역과 검증 명령이 명확합니다.',
        '사용할 수 없는 연동이나 환경이 암묵적이지 않고 문서화되어 있습니다.',
        '어떤 로그, 테스트, 스크린샷, 산출물이 필요한지 증거 기준이 적혀 있습니다.',
    ],
    'product-ui': [
        '시각 방향이 generic한 AI 결과물로 흐르지 않을 만큼 구체적입니다.',
        '필수 화면, 상태, breakpoint가 명확합니다.',
        'COMPLETE 전에 필요한 스크린샷, asset, 동작 증거가 승인 기준에 적혀 있습니다.',
    ],
}

FIELD_ALIASES = {
    'mode': ['모드', 'Mode'],
    'status': ['상태', 'Status'],
    'approved': ['승인', 'Approved'],
    'approved_by': ['승인자', 'Approved-By'],
    'approved_at': ['승인 시각', 'Approved-At'],
}

LOCK_SECTION_ALIASES = [
    ('확정 목표', ['확정 목표', 'Locked Goal']),
    ('확정 산출물', ['확정 산출물', 'Locked Deliverable']),
    ('확정 제외 범위', ['확정 제외 범위', 'Locked Out Of Scope']),
    ('COMPLETE 전 필수 증거', ['COMPLETE 전 필수 증거', 'Required Evidence Before COMPLETE']),
]

PLACEHOLDER_PREFIXES = ('replace with', 'pending', '대기 중', '작성 필요')
STATUS_ALIASES = {
    'draft': 'draft',
    '초안': 'draft',
    'pending': 'pending',
    '대기': 'pending',
    'approved': 'approved',
    '승인': 'approved',
    'locked': 'locked',
    '확정': 'locked',
    'complete': 'complete',
    '완료': 'complete',
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def canonical_mode(mode: str) -> str:
    lowered = (mode or '').strip().lower()
    if lowered in MODE_ALIASES:
        return MODE_ALIASES[lowered]
    if lowered in {'proposal', 'prd', 'implementation', 'product-ui'}:
        return lowered
    return 'implementation'


def read_text(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8')


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return default.copy()
    return payload if isinstance(payload, dict) else default.copy()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


def state_dir_from(root: Path) -> Path:
    return root / '.codex-loop'


def intake_dir_from(state_dir: Path) -> Path:
    return state_dir / 'intake'


def questionnaire_path(state_dir: Path) -> Path:
    return intake_dir_from(state_dir) / 'QUESTIONNAIRE.md'


def answers_path(state_dir: Path) -> Path:
    return intake_dir_from(state_dir) / 'ANSWERS.md'


def approval_path(state_dir: Path) -> Path:
    return intake_dir_from(state_dir) / 'APPROVAL.md'


def read_config_mode(state_dir: Path) -> str:
    config = load_json(state_dir / 'config.json', {})
    return canonical_mode(str(config.get('loop', {}).get('mode', 'implementation')))


def write_config_mode(state_dir: Path, mode: str) -> None:
    config = load_json(state_dir / 'config.json', {'loop': {}})
    loop = config.setdefault('loop', {})
    loop['mode'] = canonical_mode(mode)
    loop.setdefault('require_intake_approval', True)
    write_json(state_dir / 'config.json', config)


def intake_sections(mode: str) -> list[dict[str, Any]]:
    canonical = canonical_mode(mode)
    return [*COMMON_SECTIONS, *MODE_SECTIONS.get(canonical, MODE_SECTIONS['implementation'])]


def build_questionnaire_markdown(mode: str) -> str:
    canonical = canonical_mode(mode)
    lines = [
        '# Summit 인테이크 질문지',
        '',
        f'모드: {canonical}',
        '',
        '브레인스토밍, task seed 생성, 장시간 자율 실행을 시작하기 전에 먼저 이 문서를 잠급니다.',
        '아직 답이 없는 질문만 물어도 되지만, 역할 섹션 전체를 통째로 건너뛰지는 마세요.',
        '',
        '## 사용 방법',
        '- 실제 요청자 또는 의사결정권자와 Q&A를 진행합니다.',
        '- 최종 답변은 `ANSWERS.md`에 정리합니다.',
        '- 첫 seed 실행 전에 승인된 목표, 범위, 증거 기준을 `APPROVAL.md`에 잠급니다.',
        '',
    ]
    q_index = 1
    for section in intake_sections(canonical):
        lines.extend([
            f"## {section['role']}",
            section['purpose'],
            '',
        ])
        for question in section['questions']:
            lines.append(f'{q_index}. {question}')
            q_index += 1
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def build_answers_markdown(mode: str) -> str:
    canonical = canonical_mode(mode)
    lines = [
        '# Summit 인테이크 답변',
        '',
        f'모드: {canonical}',
        '상태: 초안',
        '',
        '## 확정 목표 한 줄',
        '- 작성 필요: 이번 런의 실제 산출물을 한 문장으로 적어주세요.',
        '',
        '## 질문 기록',
        '',
    ]
    q_index = 1
    for section in intake_sections(canonical):
        lines.extend([
            f"## {section['role']}",
            '',
        ])
        for question in section['questions']:
            lines.extend([
                f'### Q{q_index}. {question}',
                '답변:',
                '- 대기 중.',
                '메모 / 근거:',
                '- 대기 중.',
                '',
            ])
            q_index += 1
    return '\n'.join(lines).rstrip() + '\n'


def build_approval_markdown(mode: str) -> str:
    canonical = canonical_mode(mode)
    checklist = APPROVAL_CHECKLIST.get(canonical, APPROVAL_CHECKLIST['implementation'])
    lines = [
        '# Summit 인테이크 승인',
        '',
        f'모드: {canonical}',
        '상태: 대기',
        '승인: 아니오',
        '승인자:',
        '승인 시각:',
        '',
        '## 승인 체크리스트',
        *[f'- [ ] {item}' for item in checklist],
        '',
        '## 확정 목표',
        '- 작성 필요: 승인된 목표 한 줄을 적어주세요.',
        '',
        '## 확정 산출물',
        '- 작성 필요: 이번 런에서 기대하는 구체적 산출물 또는 결과를 적어주세요.',
        '',
        '## 확정 제외 범위',
        '- 작성 필요: 이번 런에서 다루지 않을 항목을 적어주세요.',
        '',
        '## COMPLETE 전 필수 증거',
        '- 작성 필요: loop를 정직하게 멈추기 전에 반드시 남아 있어야 할 증거를 적어주세요.',
        '',
        '## 승인 메모',
        '- 작성 필요: 최종 유의사항, 결정 사항, 검토자 제약을 적어주세요.',
    ]
    return '\n'.join(lines).rstrip() + '\n'


def ensure_intake_files(state_dir: Path, mode: str, force: bool = False) -> None:
    canonical = canonical_mode(mode)
    intake_dir_from(state_dir).mkdir(parents=True, exist_ok=True)
    docs = {
        questionnaire_path(state_dir): build_questionnaire_markdown(canonical),
        answers_path(state_dir): build_answers_markdown(canonical),
        approval_path(state_dir): build_approval_markdown(canonical),
    }
    for path, text in docs.items():
        if path.exists() and not force:
            continue
        write_text(path, text)


def extract_field(text: str, name: str) -> str:
    match = re.search(rf'(?mi)^{re.escape(name)}:[ \t]*([^\r\n]*)[ \t]*$', text or '')
    return match.group(1).strip() if match else ''


def extract_field_any(text: str, names: list[str]) -> str:
    for name in names:
        value = extract_field(text, name)
        if value:
            return value
    return ''


def parse_bool(text: str) -> bool:
    lowered = (text or '').strip().lower()
    return lowered in {'y', 'yes', 'true', 'approved', '1', '예', '승인', '네'}


def normalize_status(value: str, default: str = 'pending') -> str:
    lowered = (value or '').strip().lower()
    return STATUS_ALIASES.get(lowered, default)


def extract_section_items(text: str, heading: str) -> list[str]:
    pattern = re.compile(rf'(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)')
    match = pattern.search(text or '')
    if not match:
        return []
    items: list[str] = []
    for raw in match.group(1).splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith('- '):
            value = stripped[2:].strip()
        else:
            value = stripped
        lowered = value.lower()
        if lowered.startswith(PLACEHOLDER_PREFIXES) or value.startswith(('대기 중', '작성 필요')):
            continue
        items.append(value)
    return items


def extract_section_items_any(text: str, headings: list[str]) -> list[str]:
    for heading in headings:
        items = extract_section_items(text, heading)
        if items:
            return items
    return []


def load_intake_status(state_dir: Path) -> dict[str, Any]:
    approval_text = read_text(approval_path(state_dir))
    config_mode = read_config_mode(state_dir)
    mode = canonical_mode(extract_field_any(approval_text, FIELD_ALIASES['mode']) or config_mode)
    status_value = normalize_status(extract_field_any(approval_text, FIELD_ALIASES['status']) or 'pending')
    approved = parse_bool(extract_field_any(approval_text, FIELD_ALIASES['approved'])) and status_value in {'approved', 'locked', 'complete'}
    missing: list[str] = []
    if not questionnaire_path(state_dir).exists():
        missing.append('질문지 파일이 없습니다')
    if not answers_path(state_dir).exists():
        missing.append('답변 기록 파일이 없습니다')
    if not approval_path(state_dir).exists():
        missing.append('승인 문서가 없습니다')
    if not approved:
        missing.append('승인이 완료되지 않았습니다')

    lock_summary: list[str] = []
    for label, headings in LOCK_SECTION_ALIASES:
        items = extract_section_items_any(approval_text, headings)
        if not items:
            continue
        for item in items[:2]:
            lock_summary.append(f'- {label}: {item}')

    return {
        'mode': mode,
        'status': status_value,
        'approved': approved,
        'approvedBy': extract_field_any(approval_text, FIELD_ALIASES['approved_by']),
        'approvedAt': extract_field_any(approval_text, FIELD_ALIASES['approved_at']),
        'questionnaireExists': questionnaire_path(state_dir).exists(),
        'answersExists': answers_path(state_dir).exists(),
        'approvalExists': approval_path(state_dir).exists(),
        'missing': missing,
        'lockSummary': lock_summary,
    }


def intake_gate_message(status: dict[str, Any]) -> str:
    if status.get('approved'):
        return '인테이크 승인이 완료되었습니다.'
    missing = ', '.join(status.get('missing', [])[:3]) or '승인이 완료되지 않았습니다'
    return f'첫 seed 실행 전까지 `.codex-loop/intake/APPROVAL.md`를 승인 상태로 잠그고, 모드에 맞는 인테이크 Q&A를 완료하세요 ({missing}).'


def command_init(root: Path, mode: str, force: bool) -> int:
    state_dir = state_dir_from(root)
    state_dir.mkdir(parents=True, exist_ok=True)
    canonical = canonical_mode(mode or read_config_mode(state_dir))
    write_config_mode(state_dir, canonical)
    ensure_intake_files(state_dir, canonical, force=force)
    print(f'Summit 인테이크 문서를 `{canonical}` 모드로 초기화했습니다: {intake_dir_from(state_dir)}')
    print('다음 단계:')
    print('  1. 요청자와 Q&A를 진행하고 최종 답변을 `.codex-loop/intake/ANSWERS.md`에 적습니다.')
    print('  2. 승인된 목표, 산출물, 증거 기준을 `.codex-loop/intake/APPROVAL.md`에 잠급니다.')
    print('  3. 실제 승인 후 `승인: 예`와 `상태: 승인`으로 변경합니다.')
    print('  4. `python3 scripts/context_engine.py refresh --source intake`로 컨텍스트를 갱신합니다.')
    return 0


def command_status(root: Path, as_json: bool) -> int:
    state_dir = state_dir_from(root)
    status = load_intake_status(state_dir)
    payload = {
        'mode': status['mode'],
        'status': status['status'],
        'approved': status['approved'],
        'approvedBy': status['approvedBy'],
        'approvedAt': status['approvedAt'],
        'missing': status['missing'],
        'lockSummary': status['lockSummary'],
        'nextStep': intake_gate_message(status),
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
    if payload['lockSummary']:
        print('확정 요약:')
        for item in payload['lockSummary']:
            print(item)
    print(f"다음 단계: {payload['nextStep']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='SummitHarness 인테이크 / Q&A 게이트를 초기화하고 상태를 확인합니다.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    init_cmd = subparsers.add_parser('init', help='모드별 인테이크 질문지와 승인 문서를 생성하거나 새로 고칩니다')
    init_cmd.add_argument('--mode', default='', help='proposal | prd | implementation | product-ui')
    init_cmd.add_argument('--force', action='store_true', help='기존 인테이크 파일을 덮어씁니다')
    init_cmd.add_argument('--root', default='.', help='프로젝트 루트')

    status_cmd = subparsers.add_parser('status', help='첫 seed 실행 기준으로 인테이크 승인 상태를 보여줍니다')
    status_cmd.add_argument('--root', default='.', help='프로젝트 루트')
    status_cmd.add_argument('--json', action='store_true', help='상태를 JSON으로 출력합니다')

    args = parser.parse_args()
    root = Path(getattr(args, 'root', '.')).expanduser().resolve()
    if args.command == 'init':
        return command_init(root, args.mode, args.force)
    if args.command == 'status':
        return command_status(root, args.json)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

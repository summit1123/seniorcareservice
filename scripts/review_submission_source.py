#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PLACEHOLDER_PATTERNS = [
    r'\bTODO\b',
    r'\bTBD\b',
    r'\bFIXME\b',
    r'\bReplace\b',
    r'작성해주세요',
    r'추후 작성',
    r'lorem ipsum',
]
ASSISTANT_TONE_PATTERNS = [
    r'본 문서는',
    r'이 문서는',
    r'이 페이지는',
    r'보여줍니다',
    r'설명합니다',
    r'다음과 같습니다',
    r'this document',
    r'this page',
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


def review_root(root: Path) -> Path:
    return root / '.codex-loop' / 'artifacts' / 'source-review'


def slugify_stem(name: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-')
    return slug or 'document'


def extract_preset(design_text: str) -> str:
    match = re.search(r'(?mi)^Preset:\s*([A-Za-z0-9_-]+)\s*$', design_text or '')
    return match.group(1).strip().lower() if match else 'document-editorial'


def extract_reference_pack(design_text: str) -> str:
    match = re.search(r'(?mi)^Reference-Pack:\s*([A-Za-z0-9_-]+)\s*$', design_text or '')
    return match.group(1).strip().lower() if match else ''


def load_reference_pack(root: Path, name: str) -> str:
    if not name:
        return ''
    return read_text(root / '.codex-loop' / 'design' / 'reference-packs' / f'{name}.md')


def canonical_mode(mode: str) -> str:
    lowered = (mode or '').strip().lower()
    if lowered in {'proposal', 'submission', 'planning', 'contest', 'deck'}:
        return 'proposal'
    if lowered in {'prd', 'spec'}:
        return 'prd'
    if lowered in {'product-ui', 'ui', 'ux', 'design'}:
        return 'product-ui'
    return 'implementation'


def detect_mode(root: Path, explicit_mode: str | None) -> str:
    if explicit_mode:
        return canonical_mode(explicit_mode)
    config_path = root / '.codex-loop' / 'config.json'
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding='utf-8'))
            return canonical_mode(str(payload.get('loop', {}).get('mode', 'implementation')))
        except Exception:
            pass
    return 'proposal'


def first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('# '):
            return stripped[2:].strip()
    return ''


def section_headings(text: str) -> list[str]:
    return [line.strip()[3:].strip() for line in text.splitlines() if line.strip().startswith('## ')]


def table_count(text: str) -> int:
    count = 0
    lines = text.splitlines()
    pattern = r'\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?'
    for index in range(len(lines) - 1):
        if '|' in lines[index] and re.fullmatch(pattern, lines[index + 1].strip()):
            count += 1
    return count


def word_count(text: str) -> int:
    words = re.findall(r'[A-Za-z0-9가-힣]+', text)
    return len(words)


def detect_patterns(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            hits.append(pattern)
    return hits


def concept_coverage(text: str) -> dict[str, bool]:
    lowered = text.lower()
    checks = {
        'problem': ['문제', '배경', '리스크', 'problem'],
        'solution': ['해결', '솔루션', '구조', 'solution'],
        'feasibility': ['실현', '근거', 'proof', '데모', 'feasibility'],
        'business': ['사업', '수익', '도입', 'buyer', 'business'],
        'impact': ['효과', '기대', '활용', 'impact', 'effect'],
    }
    return {key: any(token in lowered for token in tokens) for key, tokens in checks.items()}


def build_review(root: Path, source_path: Path, mode: str, design_path: Path) -> dict[str, Any]:
    path = source_path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    design_text = read_text(design_path)
    text = read_text(path)
    title = first_heading(text)
    sections = section_headings(text)
    words = word_count(text)
    tables = table_count(text)
    placeholder_hits = detect_patterns(text, PLACEHOLDER_PATTERNS)
    assistant_hits = detect_patterns(text, ASSISTANT_TONE_PATTERNS)
    coverage = concept_coverage(text)
    mode_name = canonical_mode(mode)
    preset = extract_preset(design_text)
    reference_pack = extract_reference_pack(design_text)
    reference_pack_text = load_reference_pack(root, reference_pack)
    image_refs = text.count('![')
    link_refs = len(re.findall(r'\[[^\]]+\]\([^)]+\)', text))

    blockers: list[str] = []
    warnings: list[str] = []
    next_actions: list[str] = []

    if path.suffix.lower() != '.md':
        blockers.append('원고 게이트는 source of truth로 Markdown 문서를 기대합니다.')
    if not title:
        blockers.append('원고에 단일 H1 제목이 없습니다.')
    if placeholder_hits:
        blockers.append('원고에 placeholder 또는 템플릿 문구가 그대로 남아 있습니다.')
    if not design_text:
        warnings.append('디자인 계약 문서가 없습니다. 레이아웃 판단 기준을 유지하려면 `.codex-loop/design/DESIGN.md`를 추가하세요.')
    if reference_pack and not reference_pack_text:
        warnings.append(f'선택한 레퍼런스 팩 `{reference_pack}`을 `.codex-loop/design/reference-packs/`에서 찾지 못했습니다.')
    if assistant_hits:
        warnings.append('원고에 아직 AI 보조자처럼 설명하는 말투가 남아 있습니다. 심사위원이 읽는 문장으로 다시 써야 합니다.')

    if mode_name == 'proposal':
        if words < 600:
            blockers.append('제안서 원고의 실질 내용이 부족합니다. 레이아웃보다 먼저 내용 밀도를 보강해야 합니다.')
        elif words < 1000:
            warnings.append('제안서 원고가 아직 가볍습니다. 근거, 비교표, 운영 디테일을 더 보강해야 합니다.')
        if len(sections) < 5:
            blockers.append('제안서에는 문제 정의, 해결 방안, 실현 가능성, 사업화 경로, 기대 효과를 나누는 구조화된 섹션이 더 필요합니다.')
        if tables < 1:
            blockers.append('제안서에는 실제 비교표 또는 구조 표가 최소 1개 이상 필요합니다.')
        if sum(1 for value in coverage.values() if value) < 4:
            warnings.append('제안서에서 실현 가능성, 사업화 경로, 기대 효과 같은 핵심 서사 블록이 하나 이상 비어 있을 수 있습니다.')
        if preset != 'document-editorial':
            warnings.append('제안서 모드는 보통 `document-editorial` 프리셋을 사용해야 합니다.')
        if not reference_pack:
            warnings.append('제안서 모드에서는 시각 방향을 명확히 하기 위해 레퍼런스 팩을 고르는 편이 좋습니다.')
        if link_refs < 1:
            warnings.append('심사 신뢰도를 위해 근거 링크나 출처 표기를 보강하는 편이 좋습니다.')
    elif mode_name == 'prd':
        if words < 500:
            blockers.append('PRD 원고가 너무 짧아 실제 실행 기준으로 삼기 어렵습니다.')
        if len(sections) < 5:
            blockers.append('PRD에는 사용자, 범위, 요구사항, 제약사항, 수용 기준 섹션이 필요합니다.')
        lowered = text.lower()
        for keyword, label in [('user', 'users'), ('requirement', 'requirements'), ('acceptance', 'acceptance criteria')]:
            if keyword not in lowered and label not in lowered and label.replace(' ', '') not in lowered:
                warnings.append(f'PRD에 `{label}` 섹션이 명시적으로 없을 수 있습니다.')
    elif mode_name == 'product-ui':
        if preset != 'product-ops':
            warnings.append('Product UI 모드는 보통 `product-ops` 프리셋을 사용해야 합니다.')
        if not reference_pack:
            warnings.append('Product UI 모드에서는 시각 다듬기를 시작하기 전에 레퍼런스 팩을 먼저 정해야 합니다.')
        if image_refs < 1 and 'assets/' not in text and 'registry' not in text.lower():
            blockers.append('Product UI 원고에는 실제 asset, 스크린샷, 승인된 시각 입력이 포함되어야 합니다.')
        if len(sections) < 4:
            warnings.append('Product UI 원고에는 플로우, 화면 구조, asset, 검증 섹션이 더 분명해야 합니다.')
    else:
        if words < 250:
            warnings.append('구현 모드 보조 문서가 아직 너무 짧습니다. 코드를 진실 원본으로 두되, supporting docs는 더 정리해야 합니다.')

    if blockers:
        next_actions.append('PDF보다 먼저 Markdown 원고 자체를 수정해야 합니다.')
    if mode_name == 'proposal':
        next_actions.append('원고 리뷰를 통과한 뒤 `python3 scripts/render_markdown_submission.py`를 실행합니다.')
    next_actions.append('Ralph가 최신 source of truth를 보도록 컨텍스트 패킷을 갱신합니다.')

    preview_lines = [line.rstrip() for line in text.splitlines()[:40] if line.strip()]

    return {
        'generatedAt': now_iso(),
        'projectRoot': str(root),
        'mode': mode_name,
        'file': {
            'path': str(path),
            'name': path.name,
            'extension': path.suffix.lower(),
        },
        'design': {
            'path': str(design_path.resolve()),
            'preset': preset,
            'referencePack': reference_pack,
            'referencePackLoaded': bool(reference_pack_text),
            'present': bool(design_text),
        },
        'stats': {
            'wordCount': words,
            'sectionCount': len(sections),
            'tableCount': tables,
            'imageRefs': image_refs,
            'linkRefs': link_refs,
        },
        'structure': {
            'title': title,
            'sections': sections,
            'conceptCoverage': coverage,
        },
        'preview': '\n'.join(preview_lines),
        'blockers': blockers,
        'warnings': warnings,
        'nextActions': next_actions,
    }


def render_review(review: dict[str, Any]) -> str:
    lines = [
        '# 제출 원고 점검 결과',
        '',
        f"- 생성 시각: {review['generatedAt']}",
        f"- 모드: {review['mode']}",
        f"- 파일: {review['file']['name']}",
        f"- 디자인 프리셋: {review['design']['preset']}",
        f"- 레퍼런스 팩: {review['design'].get('referencePack') or '없음'}",
        f"- 글자 수: {review['stats']['wordCount']}",
        f"- 섹션 수: {review['stats']['sectionCount']}",
        f"- 표 수: {review['stats']['tableCount']}",
        '',
        '## 차단 이슈',
        *([f'- {item}' for item in review.get('blockers', [])] or ['- 없음']),
        '',
        '## 경고',
        *([f'- {item}' for item in review.get('warnings', [])] or ['- 없음']),
        '',
        '## 다음 조치 제안',
        *([f'- {item}' for item in review.get('nextActions', [])] or ['- 없음']),
        '',
        '## 미리보기',
    ]
    preview = review.get('preview', '')
    if preview:
        lines.extend(['```text', preview, '```'])
    else:
        lines.append('- 미리보기 텍스트가 없습니다.')
    lines.append('')
    return '\n'.join(lines)


def write_review_files(root: Path, review: dict[str, Any]) -> tuple[Path, Path]:
    name = slugify_stem(Path(review['file']['name']).stem)
    out_dir = review_root(root)
    json_path = out_dir / f'{name}-review.json'
    md_path = out_dir / f'{name}-review.md'
    write_json(json_path, review)
    write_text(md_path, render_review(review))
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description='렌더링이나 최종 제출 패키징 전에 Markdown 원고를 점검합니다.')
    parser.add_argument('source', nargs='?', default='docs/submissions/proposal.md', help='점검할 Markdown 원고 파일')
    parser.add_argument('--mode', help='문서 모드를 직접 지정')
    parser.add_argument('--design', default='.codex-loop/design/DESIGN.md', help='디자인 계약 파일')
    parser.add_argument('--stdout-only', action='store_true', help='산출물 파일 대신 리뷰 결과를 stdout으로 출력')
    args = parser.parse_args()

    root = project_root()
    source_path = (root / args.source).resolve()
    design_path = (root / args.design).resolve()
    mode = detect_mode(root, args.mode)
    review = build_review(root, source_path, mode, design_path)

    if args.stdout_only:
        print(render_review(review))
    else:
        json_path, md_path = write_review_files(root, review)
        print(f'Wrote source review to {json_path}')
        print(f'Wrote source review report to {md_path}')
        print(render_review(review))

    return 2 if review.get('blockers') else 0


if __name__ == '__main__':
    raise SystemExit(main())

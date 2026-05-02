#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_TOOLS = ['git', 'python3', 'codex']
OPTIONAL_TOOLS = ['node', 'npm', 'pnpm', 'bun', 'docker', 'ffmpeg', 'pdfinfo', 'pdftotext', 'pdftoppm']
OPTIONAL_ENV = ['OPENAI_API_KEY']
CHROME_PATHS = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def project_root() -> Path:
    return Path.cwd().resolve()


def state_dir(root: Path) -> Path:
    return root / '.codex-loop'


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def tool_status(name: str) -> dict[str, Any]:
    binary = shutil.which(name)
    version = None
    if binary:
        try:
            result = subprocess.run([name, '--version'], capture_output=True, text=True, timeout=5)
            output = (result.stdout or result.stderr).strip()
            version = output.splitlines()[0] if output else None
        except Exception:
            version = None
    return {'name': name, 'present': bool(binary), 'path': binary, 'version': version}


def browser_status() -> dict[str, Any]:
    env_value = os.environ.get('CHROME_BIN')
    candidates = [env_value, *CHROME_PATHS]
    for alias in ['google-chrome', 'chromium', 'chromium-browser', 'chrome']:
        found = shutil.which(alias)
        if found:
            candidates.append(found)
    for item in candidates:
        if not item:
            continue
        if os.path.isabs(item) and Path(item).exists():
            return {'name': 'chrome', 'present': True, 'path': item, 'version': None}
        found = shutil.which(item)
        if found:
            return {'name': 'chrome', 'present': True, 'path': found, 'version': None}
    return {'name': 'chrome', 'present': False, 'path': None, 'version': None}


def config_flags() -> dict[str, Any]:
    config_path = Path.home() / '.codex' / 'config.toml'
    hooks_path = Path.home() / '.codex' / 'hooks.json'
    text = config_path.read_text(encoding='utf-8') if config_path.exists() else ''
    hooks_text = hooks_path.read_text(encoding='utf-8') if hooks_path.exists() else ''
    return {
        'configPath': str(config_path),
        'hooksPath': str(hooks_path),
        'configExists': config_path.exists(),
        'hooksExists': hooks_path.exists(),
        'codexHooksEnabled': bool(re.search(r'(?m)^codex_hooks\s*=\s*true\s*$', text)),
        'rmcpClientEnabled': bool(re.search(r'(?m)^rmcp_client\s*=\s*true\s*$', text)),
        'figmaMcpMentioned': 'figma' in text.lower(),
        'stopDispatcherInstalled': 'stop_hook_dispatch.py' in hooks_text,
    }


def detect_workspace(root: Path) -> dict[str, Any]:
    return {
        'gitRepo': (root / '.git').exists() or subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], cwd=root, capture_output=True, text=True).returncode == 0,
        'packageJson': (root / 'package.json').exists(),
        'pnpmLock': (root / 'pnpm-lock.yaml').exists(),
        'npmLock': (root / 'package-lock.json').exists(),
        'bunLock': (root / 'bun.lock').exists() or (root / 'bun.lockb').exists(),
        'pythonProject': (root / 'pyproject.toml').exists(),
    }


def build_report(root: Path) -> dict[str, Any]:
    required = [tool_status(name) for name in REQUIRED_TOOLS]
    optional = [tool_status(name) for name in OPTIONAL_TOOLS]
    chrome = browser_status()
    config = config_flags()
    workspace = detect_workspace(root)
    env_checks = {name: bool(os.environ.get(name)) for name in OPTIONAL_ENV}

    blockers: list[str] = []
    warnings: list[str] = []

    for item in required:
        if not item['present']:
            blockers.append(f"Required tool missing: {item['name']}")

    if not workspace['gitRepo']:
        warnings.append('This workspace does not appear to be inside a Git repository.')
    if workspace['packageJson'] and not any(item['present'] for item in optional if item['name'] in {'node', 'npm', 'pnpm', 'bun'}):
        blockers.append('Node-based workspace detected but no Node toolchain was found.')
    if not config['configExists']:
        warnings.append('~/.codex/config.toml was not found.')
    if config['configExists'] and not config['codexHooksEnabled']:
        blockers.append('codex_hooks is not enabled in ~/.codex/config.toml.')
    if config['hooksExists'] and not config['stopDispatcherInstalled']:
        warnings.append('Global Stop hook dispatcher for SummitHarness is not installed.')
    if not config['rmcpClientEnabled']:
        warnings.append('rmcp_client is not enabled. Remote MCP flows like hosted Figma may need it.')
    if not config['figmaMcpMentioned']:
        warnings.append('No Figma MCP configuration was detected in ~/.codex/config.toml.')
    if not env_checks['OPENAI_API_KEY']:
        warnings.append('OPENAI_API_KEY is not set. Image or video generation workflows will be unavailable.')
    if not any(item['present'] for item in optional if item['name'] == 'ffmpeg'):
        warnings.append('ffmpeg is missing. Video-to-GIF or post-processing steps may be limited.')
    if not chrome['present']:
        warnings.append('Chrome or Chromium is missing. Markdown-to-PDF rendering will be unavailable until CHROME_BIN or a supported browser is installed.')
    if not any(item['present'] for item in optional if item['name'] == 'pdftoppm'):
        warnings.append('pdftoppm is missing. Visual PDF page rendering checks will be limited.')
    if not any(item['present'] for item in optional if item['name'] == 'pdfinfo'):
        warnings.append('pdfinfo is missing. Attachment metadata checks will be limited.')

    return {
        'timestamp': now_iso(),
        'projectRoot': str(root),
        'blockers': blockers,
        'warnings': warnings,
        'requiredTools': required,
        'optionalTools': optional,
        'chrome': chrome,
        'env': env_checks,
        'config': config,
        'workspace': workspace,
    }


def render_report(status: dict[str, Any]) -> str:
    def tool_line(item: dict[str, Any]) -> str:
        state = 'ok' if item['present'] else 'missing'
        version = f" - {item['version']}" if item.get('version') else ''
        return f"- {item['name']}: {state}{version}"

    blockers = [f'- {item}' for item in status['blockers']] or ['- 없음']
    warnings = [f'- {item}' for item in status['warnings']] or ['- 없음']
    lines = [
        '# 사전 점검 리포트',
        '',
        f"- 생성 시각: {status['timestamp']}",
        f"- 프로젝트 루트: {status['projectRoot']}",
        '',
        '## 차단 이슈',
        *blockers,
        '',
        '## 경고',
        *warnings,
        '',
        '## 필수 도구',
        *(tool_line(item) for item in status['requiredTools']),
        '',
        '## 선택 도구',
        *(tool_line(item) for item in status['optionalTools']),
        '',
        '## 렌더링 브라우저',
        f"- chrome: {'정상' if status['chrome']['present'] else '누락'}",
        f"- 경로: {status['chrome']['path'] or '찾지 못함'}",
        '',
        '## 환경 변수',
        *(f"- {name}: {'설정됨' if enabled else '누락'}" for name, enabled in status['env'].items()),
        '',
        '## Codex 설정',
        f"- codex_hooks: {'활성화' if status['config']['codexHooksEnabled'] else '비활성화'}",
        f"- rmcp_client: {'활성화' if status['config']['rmcpClientEnabled'] else '비활성화'}",
        f"- figma MCP 힌트 감지: {'예' if status['config']['figmaMcpMentioned'] else '아니오'}",
        f"- Stop dispatcher 설치 여부: {'예' if status['config']['stopDispatcherInstalled'] else '아니오'}",
        '',
        '## 워크스페이스 감지',
        *(f"- {key}: {'예' if value else '아니오'}" for key, value in status['workspace'].items()),
        '',
    ]
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='SummitHarness 사전 점검을 실행합니다.')
    parser.add_argument('command', nargs='?', default='run', choices=['run'])
    parser.parse_args()

    root = project_root()
    report_root = state_dir(root) / 'preflight'
    status = build_report(root)
    write_json(report_root / 'status.json', status)
    write_text(report_root / 'REPORT.md', render_report(status))

    print(f"사전 점검 상태를 저장했습니다: {report_root / 'status.json'}")
    print(f"사전 점검 리포트를 저장했습니다: {report_root / 'REPORT.md'}")
    if status['blockers']:
        print('차단 이슈가 발견되었습니다:')
        for item in status['blockers']:
            print(f'- {item}')
        return 2
    print('차단 이슈 없이 사전 점검을 통과했습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

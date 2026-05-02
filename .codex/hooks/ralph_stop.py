#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROMISE_TAG_RE = re.compile(r"<promise>\s*([A-Z]+)(?::(.*?))?\s*</promise>", re.IGNORECASE | re.DOTALL)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")


def read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def first_promise_tag(text: str) -> tuple[str, str] | None:
    match = PROMISE_TAG_RE.search(text or "")
    if not match:
        return None
    kind = match.group(1).upper()
    detail = " ".join((match.group(2) or "").split())
    return kind, detail


def normalize_expected_completion(text: str) -> tuple[str, str] | None:
    text = (text or "").strip()
    if not text:
        return None
    tagged = first_promise_tag(text)
    if tagged:
        return tagged
    if ":" in text:
        left, right = text.split(":", 1)
        return left.strip().upper(), right.strip()
    return text.upper(), ""


def completion_matches(message: str, expected: str) -> bool:
    actual = first_promise_tag(message)
    wanted = normalize_expected_completion(expected)
    if not actual or not wanted:
        return False
    return actual[0] == wanted[0] and actual[1] == wanted[1]


def all_tasks_complete(root: Path) -> bool:
    tasks_path = root / ".codex-loop" / "tasks.json"
    if not tasks_path.exists():
        return False
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        return False
    return all(str(task.get("status", "")).lower() in {"done", "completed", "complete", "skipped"} for task in tasks)


def build_continuation_prompt(state: dict[str, Any]) -> str:
    max_iterations = state.get("maxIterations")
    max_text = "unbounded" if not max_iterations else str(max_iterations)
    completion = state.get("completionPromise") or "<promise>COMPLETE</promise>"
    original_prompt = (state.get("prompt") or "").strip()
    iteration = int(state.get("currentIteration", 0))
    return "\n".join(
        [
            original_prompt,
            "",
            f"Ralph stop-hook continuation {iteration}/{max_text}.",
            f"Keep iterating until you can honestly emit {completion}.",
            "If you are blocked, emit <promise>BLOCKED:reason</promise>.",
            "If a real human decision is required, emit <promise>DECIDE:question</promise>.",
        ]
    ).strip()


def refresh_context(root: Path, source: str) -> None:
    script = root / "scripts" / "context_engine.py"
    if not script.exists():
        return
    subprocess.run(
        [sys.executable, str(script), "refresh", "--source", source],
        cwd=root,
        capture_output=True,
        text=True,
    )


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def state_path(root: Path) -> Path:
    return root / ".codex-loop" / "ralph-loop.json"


def hook_log_path(root: Path) -> Path:
    return root / ".codex-loop" / "logs" / "ralph-hook.log"


def main() -> int:
    root = project_root()
    state_file = state_path(root)
    state = load_json(state_file)
    if not state.get("active"):
        print("{}")
        return 0

    event = read_event()
    message = event.get("last_assistant_message") or ""
    promise = first_promise_tag(message)
    state["updatedAt"] = now_iso()
    state["lastAssistantMessage"] = message[-12000:] if message else ""
    state["lastStopEvent"] = {
        "turnId": event.get("turn_id"),
        "stopHookActive": bool(event.get("stop_hook_active")),
        "capturedAt": state["updatedAt"],
    }

    if completion_matches(message, str(state.get("completionPromise") or "")):
        if state.get("requireTaskCompletion") and not all_tasks_complete(root):
            append_log(hook_log_path(root), f"[{state['updatedAt']}] rejected completion because tasks remain open")
        else:
            state["active"] = False
            state["status"] = "complete"
            state["completedAt"] = state["updatedAt"]
            write_json(state_file, state)
            append_log(hook_log_path(root), f"[{state['updatedAt']}] complete")
            refresh_context(root, "local-stop-hook-complete")
            print("{}")
            return 0

    if promise and promise[0] in {"BLOCKED", "DECIDE"}:
        state["active"] = False
        state["status"] = promise[0].lower()
        state["stoppedAt"] = state["updatedAt"]
        state["stopReason"] = promise[1]
        write_json(state_file, state)
        append_log(hook_log_path(root), f"[{state['updatedAt']}] stop {promise[0]} {promise[1]}".rstrip())
        refresh_context(root, f"local-stop-hook-{promise[0].lower()}")
        print("{}")
        return 0

    max_iterations = int(state.get("maxIterations", 0) or 0)
    current_iteration = int(state.get("currentIteration", 0) or 0)
    if max_iterations and current_iteration >= max_iterations:
        state["active"] = False
        state["status"] = "max_iterations"
        state["stoppedAt"] = state["updatedAt"]
        write_json(state_file, state)
        append_log(hook_log_path(root), f"[{state['updatedAt']}] stop max_iterations")
        refresh_context(root, "local-stop-hook-max-iterations")
        print("{}")
        return 0

    state["currentIteration"] = current_iteration + 1
    continuation = build_continuation_prompt(state)
    state["lastContinuationPrompt"] = continuation
    write_json(state_file, state)
    append_log(hook_log_path(root), f"[{state['updatedAt']}] continue iteration={state['currentIteration']}")
    refresh_context(root, "local-stop-hook-continue")
    print(json.dumps({"decision": "block", "reason": continuation}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

---
description: Start a Stop-hook Ralph loop in the current project. Usage: /ralph-loop "<task>" --completion-promise "<promise>COMPLETE</promise>" --max-iterations 20
---

# /ralph-loop

Start the hook-native Ralph loop in this repository.

## Arguments

- The task prompt is required.
- `--completion-promise "<text>"` is optional. Default: `<promise>COMPLETE</promise>`
- `--max-iterations <n>` is optional. Default: `20`

## Workflow

1. Parse `$ARGUMENTS`.
2. If the task prompt is missing, ask the user for it and stop.
3. Confirm this repo is bootstrapped for Codex Ralph loop. If `scripts/ralph_session.py` is missing, run the bootstrap flow first.
4. Run `python3 scripts/ralph_session.py start ...` with the parsed task prompt, completion promise, and max iterations.
5. Tell the user the loop is armed.
6. Then immediately begin the task itself from the same prompt so the Stop hook can keep continuing it after each attempted exit.

## Notes

- The Stop hook will keep feeding the task back until the completion promise appears, the loop is cancelled, or the iteration limit is reached.
- If the user wants to stop the loop, use `/cancel-ralph`.

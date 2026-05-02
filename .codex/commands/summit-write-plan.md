---
description: Turn the current brief into a project-specific SummitHarness task graph.
---

# /summit-write-plan

1. Confirm `.codex-loop/prd/PRD.md` and `.codex-loop/prd/SUMMARY.md` reflect the current goal.
2. Replace the bootstrap template task graph in `.codex-loop/tasks.json` and `.codex-loop/tasks/TASK-*.json` with a real project plan.
3. Prefer a Superpowers-style shape when it fits: brainstorm/spec lock -> execution plan -> implementation slices -> verification.
4. Keep the graph small enough to execute, usually 3 to 7 tasks.
5. Give each task explicit deliverables, acceptance criteria, and real dependencies.
6. Run `python3 scripts/context_engine.py refresh --source plan` and summarize the new next step.

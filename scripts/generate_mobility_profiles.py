#!/usr/bin/env python3
"""Offline generation of agent mobility profiles (Option C).

Reasoning step in front of the deterministic GAIP engine: an LLM agent reads
each senior's life context and reasons out a realistic 14-month mobility profile
(named living zones, per-person change month + trigger, rationale). Profiles are
generated ONCE and cached (committed) so the demo stays deterministic; the
engine then expands + scores them blind.

Usage:
    OPENAI_API_KEY=... python3 scripts/generate_mobility_profiles.py
    # options: --limit N (first N people), --model gpt-4o, --out PATH,
    #          --seed N, --only p03,p07 (specific person_ids)

Reads OPENAI_API_KEY from the environment (loads .env if python-dotenv present).
Model defaults to $MOBILITY_AGENT_MODEL or "gpt-4o".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gaip_simulation.mobility_agent import (  # noqa: E402
    MobilityProfileError,
    generate_mobility_profile,
)
from src.gaip_simulation.personas import build_person_roster  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "fixtures" / "mobility_profiles.json"
DEFAULT_MODEL = os.environ.get("MOBILITY_AGENT_MODEL", "gpt-4o")
DEFAULT_SEED = 26_071_406


def _load_dotenv() -> None:
    """Best-effort load of .env (no hard dependency on python-dotenv)."""

    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="generate only the first N people")
    parser.add_argument("--only", type=str, default=None, help="comma-separated person_ids to (re)generate")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    _load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set (put it in .env or the environment).", file=sys.stderr)
        return 2

    from src.llm.openai_client import OpenAIClient

    client = OpenAIClient(model=args.model, timeout_seconds=args.timeout, max_retries=args.max_retries)

    roster = build_person_roster(args.seed)
    only_ids = {p.strip() for p in args.only.split(",")} if args.only else None
    if only_ids:
        targets = [p for p in roster if p["person_id"] in only_ids]
    elif args.limit:
        targets = roster[: args.limit]
    else:
        targets = roster

    # merge into any existing cache so --only / --limit are incremental
    existing: dict[str, dict] = {}
    if args.out.exists():
        try:
            payload = json.loads(args.out.read_text(encoding="utf-8"))
            existing = {row["person_id"]: row for row in payload.get("profiles", [])}
        except (json.JSONDecodeError, KeyError, TypeError):
            existing = {}

    print(f"Generating {len(targets)} mobility profiles with model={args.model} …", file=sys.stderr)
    failures: list[str] = []
    for index, person in enumerate(targets, start=1):
        # Transient-error resilience: the Responses API returns occasional 5xx /
        # rate limits over a 60-call batch, so retry the whole person with backoff.
        profile = None
        last_exc: Exception | None = None
        for network_attempt in range(4):
            try:
                profile = generate_mobility_profile(person, client, max_attempts=args.max_retries)
                break
            except MobilityProfileError as exc:
                last_exc = exc  # model produced invalid structure repeatedly — one more batch retry
            except Exception as exc:  # noqa: BLE001 - transient API/network error, back off + retry
                last_exc = exc
            time.sleep(min(8.0, 1.5 * (2**network_attempt)))
        if profile is None:
            failures.append(person["person_id"])
            print(f"  [{index}/{len(targets)}] {person['person_id']} FAILED: {last_exc}", file=sys.stderr)
            continue
        existing[person["person_id"]] = profile
        zones = profile["zones"]
        change = profile.get("change_month")
        print(
            f"  [{index}/{len(targets)}] {person['person_id']} {person['designed_type']:22s} "
            f"zones={len(zones)} change_month={change} — {profile['reasoning_ko'][:42]}",
            file=sys.stderr,
        )

    ordered = [existing[p["person_id"]] for p in roster if p["person_id"] in existing]
    out_payload = {
        "schema": "masil_gaip_mobility_profiles_v1",
        "seed": args.seed,
        "model": args.model,
        "count": len(ordered),
        "profiles": ordered,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(ordered)} profiles → {args.out}", file=sys.stderr)
    if failures:
        print(f"FAILURES ({len(failures)}): {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# TODO(LABEL_DIVERSITY_RULE): 다음 프로필 재생성 시 프롬프트에 아래 규칙을 포함할 것.
# \n라벨 다양성 규칙(LABEL_DIVERSITY_RULE): 존 이름은 사람마다 서로 다르게 지어라. 이미 사용된 라벨 목록이 주어지면 그 목록의 이름을 재사용하지 마라. 전형적인 한 가지 이름(예: 새마을시장)으로 수렴하지 말 것.

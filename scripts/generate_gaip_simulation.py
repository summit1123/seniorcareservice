#!/usr/bin/env python3
"""Generate the deterministic FourSure · Masil GAIP simulation bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.gaip_simulation import DEFAULT_SEED, write_gaip_simulation_bundle


DEFAULT_OUTPUT = ROOT / "data" / "fixtures" / "gaip_simulation_bundle.json"
DEFAULT_RAW_EVENTS_OUTPUT = ROOT / "data" / "fixtures" / "gaip_visit_events.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-events-output", type=Path, default=DEFAULT_RAW_EVENTS_OUTPUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = write_gaip_simulation_bundle(
        args.output,
        seed=args.seed,
        raw_events_path=args.raw_events_output,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = {
        "output": str(path),
        "schema_version": payload["metadata"]["schema_version"],
        "driver_count": payload["cohort"]["driver_count"],
        "trip_count": payload["trip_visit_summary"]["trip_count"],
        "raw_visit_events": payload["metadata"]["source_artifacts"]["raw_visit_events"],
        "validation_status": payload["validation_results"]["result_status"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["validation_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

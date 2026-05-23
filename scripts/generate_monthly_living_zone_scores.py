#!/usr/bin/env python3
"""Generate rolling monthly living-zone snapshots and annual score artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.monthly_living_zone import (
    DEFAULT_CANDIDATE_RULES_INPUT,
    DEFAULT_EVENTS_INPUT,
    DEFAULT_PROFILE_INPUT,
    DEFAULT_SCORE_OUTPUT,
    DEFAULT_SNAPSHOT_OUTPUT,
    DEFAULT_TRIP_INPUT,
    build_monthly_living_zone_outputs,
    write_json,
    write_monthly_outputs,
)
from src.product.annual_scoring_engine import (
    DEFAULT_ANNUAL_SCORE_OUTPUT,
    build_annual_score_table,
    build_annual_scoring_manifest,
    write_annual_score_table,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate monthly living-zone and annual score outputs.")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILE_INPUT), help="Annual profile fixture JSON")
    parser.add_argument("--trips", default=str(DEFAULT_TRIP_INPUT), help="Annual trip log CSV")
    parser.add_argument("--events", default=str(DEFAULT_EVENTS_INPUT), help="Monthly scenario event JSON")
    parser.add_argument("--candidate-rules", default=str(DEFAULT_CANDIDATE_RULES_INPUT), help="Selected policy JSON")
    parser.add_argument("--monthly-snapshots", default=str(DEFAULT_SNAPSHOT_OUTPUT), help="Monthly snapshot JSON output")
    parser.add_argument("--monthly-scores", default=str(DEFAULT_SCORE_OUTPUT), help="Monthly score CSV output")
    parser.add_argument("--annual-scores", default=str(DEFAULT_ANNUAL_SCORE_OUTPUT), help="Annual score CSV output")
    args = parser.parse_args(argv)

    monthly_snapshots, monthly_score_rows = build_monthly_living_zone_outputs(
        profile_input=Path(args.profiles),
        trip_input=Path(args.trips),
        events_input=Path(args.events),
        candidate_rules_input=Path(args.candidate_rules),
    )
    write_monthly_outputs(
        monthly_snapshots,
        monthly_score_rows,
        snapshot_output=Path(args.monthly_snapshots),
        score_output=Path(args.monthly_scores),
    )
    annual_rows = build_annual_score_table(
        monthly_score_input=Path(args.monthly_scores),
        profile_input=Path(args.profiles),
        candidate_rules_input=Path(args.candidate_rules),
    )
    write_annual_score_table(annual_rows, Path(args.annual_scores))
    manifest = build_annual_scoring_manifest(
        annual_rows,
        monthly_score_input=Path(args.monthly_scores),
        monthly_snapshot_input=Path(args.monthly_snapshots),
        annual_score_output=Path(args.annual_scores),
    )
    manifest_path = Path(args.annual_scores).with_suffix(".manifest.json")
    write_json(manifest_path, manifest)

    print(f"wrote {monthly_snapshots['snapshot_count']} monthly snapshots to {args.monthly_snapshots}")
    print(f"wrote {len(monthly_score_rows)} monthly score rows to {args.monthly_scores}")
    print(f"wrote {len(annual_rows)} annual score rows to {args.annual_scores}")
    print(json.dumps(manifest["score_summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


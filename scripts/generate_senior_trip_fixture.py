#!/usr/bin/env python3
"""Generate Senior Safe Mileage synthetic trip-log fixtures."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.ai_simulation_agent import main


if __name__ == "__main__":
    raise SystemExit(main())

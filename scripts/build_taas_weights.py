#!/usr/bin/env python3
"""Build TAAS behavior weights from the raw stt CSV."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.taas_weights import main


if __name__ == "__main__":
    raise SystemExit(main())

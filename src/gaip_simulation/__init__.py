"""Deterministic GAIP simulation primitives for the Masil product studio.

This package is intentionally isolated from the domestic competition fixture.
It provides a synthetic, reproducible international-extension sandbox without
changing the domestic source-of-truth artifacts.
"""

from .engine import (
    DEFAULT_SEED,
    ENVIRONMENTS,
    PERSONA_TYPES,
    build_gaip_simulation_bundle,
    classify_month,
    pricing_sandbox,
    write_gaip_simulation_bundle,
)

__all__ = [
    "DEFAULT_SEED",
    "ENVIRONMENTS",
    "PERSONA_TYPES",
    "build_gaip_simulation_bundle",
    "classify_month",
    "pricing_sandbox",
    "write_gaip_simulation_bundle",
]

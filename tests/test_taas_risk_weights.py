"""TAAS 표 → 위험 유형 가중치 유도가 표와 수식대로인지 독립 재계산으로 검증."""

from __future__ import annotations

import csv
import unittest

from src.gaip_simulation.taas_risk_weights import (
    RISK_TYPE_WEIGHTS_BASE,
    RISK_TYPE_WEIGHTS_OUTER_NIGHT,
    TAAS_RISK_WEIGHT_PROVENANCE,
    TAAS_WEIGHT_TABLE_PATH,
    derive_risk_type_weights,
)


def _latest_row() -> dict[str, str]:
    with TAAS_WEIGHT_TABLE_PATH.open(encoding="utf-8", newline="") as csvfile:
        rows = list(csv.DictReader(csvfile))
    return max(rows, key=lambda row: int(row["year"]))


class TaasRiskWeightDerivationTest(unittest.TestCase):
    def test_base_weights_match_independent_recomputation(self) -> None:
        row = _latest_row()
        speeding_share = (
            float(row["speeding_weight"])
            if int(row["speeding_weight_available"])
            else float(row["speeding_weight_reference_2010_2020"])
        )
        hard_brake = float(row["safety_distance_weight"])
        speeding = speeding_share + float(row["signal_violation_weight"])
        sudden_accel = float(row["centerline_violation_weight"])
        total = hard_brake + speeding + sudden_accel

        self.assertAlmostEqual(
            RISK_TYPE_WEIGHTS_BASE["hard_brake"], hard_brake / total, places=4
        )
        self.assertAlmostEqual(
            RISK_TYPE_WEIGHTS_BASE["speeding"], speeding / total, places=4
        )
        self.assertAlmostEqual(
            RISK_TYPE_WEIGHTS_BASE["sudden_accel"], sudden_accel / total, places=4
        )
        self.assertAlmostEqual(sum(RISK_TYPE_WEIGHTS_BASE.values()), 1.0, places=3)

    def test_outer_night_weight_uses_share_times_fatality(self) -> None:
        row = _latest_row()
        expected_night = min(
            0.85,
            float(row["night_accident_share"]) * float(row["night_fatality_weight"]),
        )
        self.assertAlmostEqual(
            RISK_TYPE_WEIGHTS_OUTER_NIGHT["night_outer"], expected_night, places=4
        )
        self.assertAlmostEqual(
            sum(RISK_TYPE_WEIGHTS_OUTER_NIGHT.values()), 1.0, places=3
        )
        self.assertEqual(
            set(RISK_TYPE_WEIGHTS_OUTER_NIGHT), {"night_outer", "hard_brake", "speeding"}
        )

    def test_speeding_fallback_flag_is_declared_in_provenance(self) -> None:
        row = _latest_row()
        inputs = TAAS_RISK_WEIGHT_PROVENANCE["inputs"]
        self.assertEqual(
            inputs["speeding_share_is_2010_2020_reference"],
            not int(row["speeding_weight_available"]),
        )
        self.assertEqual(TAAS_RISK_WEIGHT_PROVENANCE["year_used"], int(row["year"]))
        self.assertEqual(
            TAAS_RISK_WEIGHT_PROVENANCE["role"],
            "type_breakdown_display_only_decisions_unaffected",
        )

    def test_derivation_is_deterministic(self) -> None:
        base_again, outer_again, _ = derive_risk_type_weights()
        self.assertEqual(base_again, RISK_TYPE_WEIGHTS_BASE)
        self.assertEqual(outer_again, RISK_TYPE_WEIGHTS_OUTER_NIGHT)


if __name__ == "__main__":
    unittest.main()

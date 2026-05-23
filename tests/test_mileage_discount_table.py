from __future__ import annotations

import inspect
import unittest

from src.product import mileage_discount_table
from src.product.mileage_discount_table import (
    PERSONAL_BUSINESS,
    PERSONAL_PASSENGER_EV_HYDROGEN,
    PERSONAL_PASSENGER_GENERAL,
    load_mileage_discount_table,
    lookup_existing_mileage_discount,
)


class TestMileageDiscountTable(unittest.TestCase):
    def test_loads_all_samsungfire_mileage_tiers_and_vehicle_classes(self) -> None:
        table = load_mileage_discount_table()

        self.assertEqual(table.schema_version, "samsungfire-mileage-discount-table/v2026-04-11")
        self.assertEqual(table.max_discount_mileage_km, 15000)
        self.assertEqual(len(table.tiers), 15)
        self.assertEqual(
            set(table.vehicle_class_ids),
            {
                PERSONAL_PASSENGER_GENERAL,
                PERSONAL_PASSENGER_EV_HYDROGEN,
                PERSONAL_BUSINESS,
            },
        )
        self.assertEqual(table.tiers[0].max_annual_mileage_km, 1000)
        self.assertEqual(table.tiers[-1].max_annual_mileage_km, 15000)

    def test_personal_general_three_thousand_km_discount_is_twenty_eight_pct(self) -> None:
        result = lookup_existing_mileage_discount(
            annual_mileage_km=3000,
            vehicle_class=PERSONAL_PASSENGER_GENERAL,
        )

        self.assertEqual(result.discount_rate_pct, 28.0)
        self.assertEqual(result.matched_tier_label, "3천km 이하")
        self.assertEqual(result.input_fields, ("annual_mileage_km", "vehicle_class"))
        self.assertTrue(result.eligible_for_discount)

    def test_lookup_uses_only_annual_mileage_and_vehicle_class(self) -> None:
        ev_result = lookup_existing_mileage_discount(15000, PERSONAL_PASSENGER_EV_HYDROGEN)
        business_result = lookup_existing_mileage_discount(15000, PERSONAL_BUSINESS)
        over_limit = lookup_existing_mileage_discount(15000.01, PERSONAL_PASSENGER_GENERAL)

        self.assertEqual(ev_result.discount_rate_pct, 1.0)
        self.assertEqual(business_result.discount_rate_pct, 3.0)
        self.assertEqual(over_limit.discount_rate_pct, 0.0)
        self.assertFalse(over_limit.eligible_for_discount)
        self.assertIsNone(over_limit.matched_max_annual_mileage_km)

    def test_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            lookup_existing_mileage_discount(-1, PERSONAL_PASSENGER_GENERAL)
        with self.assertRaises(ValueError):
            lookup_existing_mileage_discount(3000, "unknown_vehicle_class")

    def test_source_contract_explicitly_excludes_monthly_rate_derivations(self) -> None:
        source = inspect.getsource(mileage_discount_table.lookup_existing_mileage_discount)

        self.assertIn("CAGR", source)
        self.assertIn("월복리", source)
        self.assertIn("월별 할인율", source)


if __name__ == "__main__":
    unittest.main()

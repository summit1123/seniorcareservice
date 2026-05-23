"""Annual mileage discount lookup for the existing Samsung Fire baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


MILEAGE_DISCOUNT_TABLE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fixtures" / "mileage_discount_table.json"
)

PERSONAL_PASSENGER_GENERAL = "personal_passenger_general"
PERSONAL_PASSENGER_EV_HYDROGEN = "personal_passenger_ev_hydrogen"
PERSONAL_BUSINESS = "personal_business"


@dataclass(frozen=True)
class VehicleClass:
    id: str
    label: str


@dataclass(frozen=True)
class MileageDiscountTier:
    label: str
    max_annual_mileage_km: int
    discount_rate_pct: dict[str, float]


@dataclass(frozen=True)
class MileageDiscountLookupResult:
    annual_mileage_km: float
    vehicle_class: str
    vehicle_class_label: str
    discount_rate_pct: float
    matched_tier_label: str
    matched_max_annual_mileage_km: int | None
    eligible_for_discount: bool
    table_id: str
    source_url: str
    input_fields: tuple[str, str] = ("annual_mileage_km", "vehicle_class")

    def to_dict(self) -> dict[str, Any]:
        return {
            "annual_mileage_km": self.annual_mileage_km,
            "vehicle_class": self.vehicle_class,
            "vehicle_class_label": self.vehicle_class_label,
            "discount_rate_pct": self.discount_rate_pct,
            "matched_tier_label": self.matched_tier_label,
            "matched_max_annual_mileage_km": self.matched_max_annual_mileage_km,
            "eligible_for_discount": self.eligible_for_discount,
            "table_id": self.table_id,
            "source_url": self.source_url,
            "input_fields": list(self.input_fields),
        }


@dataclass(frozen=True)
class MileageDiscountTable:
    schema_version: str
    table_id: str
    source_url: str
    source_title: str
    retrieved_at: str
    effective_note: str
    vehicle_classes: tuple[VehicleClass, ...]
    tiers: tuple[MileageDiscountTier, ...]
    out_of_range_label: str
    out_of_range_discount_rate_pct: float

    @property
    def vehicle_class_ids(self) -> tuple[str, ...]:
        return tuple(vehicle_class.id for vehicle_class in self.vehicle_classes)

    @property
    def max_discount_mileage_km(self) -> int:
        return max(tier.max_annual_mileage_km for tier in self.tiers)

    def lookup(self, annual_mileage_km: float, vehicle_class: str) -> MileageDiscountLookupResult:
        mileage = _validate_annual_mileage(annual_mileage_km)
        vehicle = self._vehicle_class(vehicle_class)
        for tier in self.tiers:
            if mileage <= tier.max_annual_mileage_km:
                return MileageDiscountLookupResult(
                    annual_mileage_km=mileage,
                    vehicle_class=vehicle.id,
                    vehicle_class_label=vehicle.label,
                    discount_rate_pct=round(float(tier.discount_rate_pct[vehicle.id]), 2),
                    matched_tier_label=tier.label,
                    matched_max_annual_mileage_km=tier.max_annual_mileage_km,
                    eligible_for_discount=True,
                    table_id=self.table_id,
                    source_url=self.source_url,
                )
        return MileageDiscountLookupResult(
            annual_mileage_km=mileage,
            vehicle_class=vehicle.id,
            vehicle_class_label=vehicle.label,
            discount_rate_pct=round(float(self.out_of_range_discount_rate_pct), 2),
            matched_tier_label=self.out_of_range_label,
            matched_max_annual_mileage_km=None,
            eligible_for_discount=False,
            table_id=self.table_id,
            source_url=self.source_url,
        )

    def _vehicle_class(self, vehicle_class: str) -> VehicleClass:
        for candidate in self.vehicle_classes:
            if candidate.id == vehicle_class:
                return candidate
        raise ValueError(f"unknown vehicle_class: {vehicle_class}")


def lookup_existing_mileage_discount(
    annual_mileage_km: float,
    vehicle_class: str,
) -> MileageDiscountLookupResult:
    """Return the existing annual mileage discount rate for one vehicle class.

    Contract: this baseline uses only annual mileage and vehicle class. Do not
    apply CAGR, 월복리, or 월별 할인율 환산 here; monthly data belongs to the
    proposed annual-score explanation, not this existing discount lookup.
    """

    return load_mileage_discount_table().lookup(annual_mileage_km, vehicle_class)


def load_mileage_discount_table() -> MileageDiscountTable:
    return _load_mileage_discount_table(str(MILEAGE_DISCOUNT_TABLE_PATH))


@lru_cache(maxsize=None)
def _load_mileage_discount_table(path: str) -> MileageDiscountTable:
    with Path(path).open(encoding="utf-8") as file:
        payload = json.load(file)
    return _parse_table(payload)


def _parse_table(payload: dict[str, Any]) -> MileageDiscountTable:
    vehicle_classes = tuple(
        VehicleClass(id=str(row["id"]), label=str(row["label"]))
        for row in payload["vehicle_classes"]
    )
    vehicle_class_ids = {vehicle.id for vehicle in vehicle_classes}
    tiers = tuple(
        MileageDiscountTier(
            label=str(row["label"]),
            max_annual_mileage_km=int(row["max_annual_mileage_km"]),
            discount_rate_pct={
                str(vehicle_class): float(discount_rate)
                for vehicle_class, discount_rate in row["discount_rate_pct"].items()
            },
        )
        for row in payload["tiers"]
    )

    _validate_table_contract(vehicle_class_ids, tiers)
    source = payload["source"]
    out_of_range = payload["out_of_range"]
    return MileageDiscountTable(
        schema_version=str(payload["schema_version"]),
        table_id=str(payload["table_id"]),
        source_url=str(source["url"]),
        source_title=str(source["title"]),
        retrieved_at=str(source["retrieved_at"]),
        effective_note=str(source["effective_note"]),
        vehicle_classes=vehicle_classes,
        tiers=tiers,
        out_of_range_label=str(out_of_range["label"]),
        out_of_range_discount_rate_pct=float(out_of_range["discount_rate_pct"]),
    )


def _validate_table_contract(
    vehicle_class_ids: set[str],
    tiers: tuple[MileageDiscountTier, ...],
) -> None:
    if not tiers:
        raise ValueError("mileage discount table must include at least one tier")
    thresholds = [tier.max_annual_mileage_km for tier in tiers]
    if thresholds != sorted(thresholds):
        raise ValueError("mileage discount tiers must be sorted by max annual mileage")
    for tier in tiers:
        tier_vehicle_classes = set(tier.discount_rate_pct)
        if tier_vehicle_classes != vehicle_class_ids:
            raise ValueError(
                f"tier {tier.label} vehicle classes do not match table contract"
            )


def _validate_annual_mileage(annual_mileage_km: float) -> float:
    mileage = float(annual_mileage_km)
    if mileage < 0:
        raise ValueError("annual_mileage_km must be non-negative")
    return round(mileage, 2)

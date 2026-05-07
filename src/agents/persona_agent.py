"""Persona Agent for senior-driver simulation templates.

The template file uses JSON-compatible YAML so the project can load it with the
standard library and avoid adding a YAML parser dependency for this fixture.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents.contracts import (
    AgentArtifact,
    AgentExecutionResult,
    AgentInputPayload,
    AgentMetadata,
    AgentOutputPayload,
    AgentRole,
    AgentStatus,
    ArtifactType,
    utc_now_iso,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH = ROOT / "data" / "fixtures" / "persona_templates.yaml"
DEFAULT_CUSTOMER_PATH = ROOT / "data" / "fixtures" / "senior_customers.json"
DEFAULT_PARAMETER_PATH = ROOT / "data" / "fixtures" / "customer_driving_parameters.json"

EXPECTED_PERSONA_TYPES = {
    "stable_local_low_mileage",
    "stable_outer_safe",
    "recent_outer_risk_change",
    "in_zone_risky_low_mileage",
    "medical_visit_pattern",
    "irregular_family_support",
}

REQUIRED_PERSONA_FIELDS = {
    "persona_type",
    "display_name_ko",
    "product_role",
    "driving_behavior",
    "risk_traits",
    "care_context",
    "ground_truth",
    "scenario_variants",
}

REQUIRED_BEHAVIOR_FIELDS = {
    "annualized_mileage_band_km",
    "baseline_trip_count_range",
    "recent_trip_count_range",
    "primary_zones",
    "typical_destinations",
    "outer_trip_ratio_baseline",
    "outer_trip_ratio_recent",
    "night_drive_ratio_baseline",
    "night_drive_ratio_recent",
    "risk_event_rate_per_100km_baseline",
    "risk_event_rate_per_100km_recent",
}

REQUIRED_CUSTOMER_FIELDS = {
    "customer_id",
    "driver_id",
    "persona_type",
    "scenario_id",
    "scenario_variant",
    "expected_care_decision",
    "expected_reason_codes",
    "living_zone_seed",
}

REQUIRED_PATTERN_FIELDS = {
    "customer_id",
    "persona_type",
    "scenario_id",
    "scenario_variant",
    "observation_period",
    "annualized_mileage_target_km",
    "trip_count",
    "distance_km_per_trip_range",
    "zone_mix",
    "night_drive_ratio",
    "risk_event_rate_per_100km",
    "risk_event_mix",
    "time_window_weights",
    "destination_weights",
    "route_variability",
    "pattern_change_expectation",
}


@dataclass(frozen=True)
class PersonaProfile:
    persona_type: str
    display_name_ko: str
    product_role: str
    driving_behavior: dict[str, Any]
    risk_traits: list[str]
    care_context: dict[str, Any]
    ground_truth: dict[str, Any]
    scenario_variants: list[str]

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "PersonaProfile":
        return cls(
            persona_type=str(row["persona_type"]),
            display_name_ko=str(row["display_name_ko"]),
            product_role=str(row["product_role"]),
            driving_behavior=dict(row["driving_behavior"]),
            risk_traits=[str(value) for value in row["risk_traits"]],
            care_context=dict(row["care_context"]),
            ground_truth=dict(row["ground_truth"]),
            scenario_variants=[str(value) for value in row["scenario_variants"]],
        )


@dataclass(frozen=True)
class CustomerIdentity:
    customer_id: str
    driver_id: str
    persona_type: str
    scenario_id: str
    scenario_variant: str
    expected_care_decision: str
    expected_reason_codes: list[str]
    living_zone_seed: dict[str, Any]
    persona_profile: PersonaProfile

    @classmethod
    def from_dict(cls, row: dict[str, Any], profiles: dict[str, PersonaProfile]) -> "CustomerIdentity":
        persona_type = str(row["persona_type"])
        return cls(
            customer_id=str(row["customer_id"]),
            driver_id=str(row["driver_id"]),
            persona_type=persona_type,
            scenario_id=str(row["scenario_id"]),
            scenario_variant=str(row["scenario_variant"]),
            expected_care_decision=str(row["expected_care_decision"]),
            expected_reason_codes=[str(value) for value in row["expected_reason_codes"]],
            living_zone_seed=dict(row["living_zone_seed"]),
            persona_profile=profiles[persona_type],
        )


@dataclass(frozen=True)
class CustomerDrivingPattern:
    customer_id: str
    persona_type: str
    scenario_id: str
    scenario_variant: str
    observation_period: dict[str, Any]
    annualized_mileage_target_km: float
    trip_count: dict[str, int]
    distance_km_per_trip_range: dict[str, list[float]]
    zone_mix: dict[str, dict[str, float]]
    night_drive_ratio: dict[str, float]
    risk_event_rate_per_100km: dict[str, float]
    risk_event_mix: dict[str, float]
    time_window_weights: dict[str, dict[str, float]]
    destination_weights: dict[str, float]
    route_variability: str
    pattern_change_expectation: dict[str, float]

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "CustomerDrivingPattern":
        return cls(
            customer_id=str(row["customer_id"]),
            persona_type=str(row["persona_type"]),
            scenario_id=str(row["scenario_id"]),
            scenario_variant=str(row["scenario_variant"]),
            observation_period=dict(row["observation_period"]),
            annualized_mileage_target_km=float(row["annualized_mileage_target_km"]),
            trip_count={key: int(value) for key, value in row["trip_count"].items()},
            distance_km_per_trip_range={
                key: [float(item) for item in value] for key, value in row["distance_km_per_trip_range"].items()
            },
            zone_mix={key: {zone: float(ratio) for zone, ratio in value.items()} for key, value in row["zone_mix"].items()},
            night_drive_ratio={key: float(value) for key, value in row["night_drive_ratio"].items()},
            risk_event_rate_per_100km={key: float(value) for key, value in row["risk_event_rate_per_100km"].items()},
            risk_event_mix={key: float(value) for key, value in row["risk_event_mix"].items()},
            time_window_weights={
                key: {window: float(weight) for window, weight in value.items()}
                for key, value in row["time_window_weights"].items()
            },
            destination_weights={key: float(value) for key, value in row["destination_weights"].items()},
            route_variability=str(row["route_variability"]),
            pattern_change_expectation={key: float(value) for key, value in row["pattern_change_expectation"].items()},
        )


class PersonaAgent:
    """Loads and validates persona templates and synthetic customer identities."""

    metadata = AgentMetadata(
        agent_id="persona_agent",
        role=AgentRole.PERSONA,
        display_name="Persona Agent",
        description="Defines six senior driver personas and edge cases.",
        produces=("persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"),
    )

    def __init__(
        self,
        template_path: str | Path = DEFAULT_TEMPLATE_PATH,
        customer_path: str | Path = DEFAULT_CUSTOMER_PATH,
        parameter_path: str | Path = DEFAULT_PARAMETER_PATH,
    ) -> None:
        self.template_path = Path(template_path)
        self.customer_path = Path(customer_path)
        self.parameter_path = Path(parameter_path)

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        """Validate persona fixtures and return the shared agent contract result."""
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            profiles = self.load_profiles()
            identities = self.load_customer_identities()
            patterns = self.load_customer_driving_patterns()
            persona_counts = {
                persona_type: sum(1 for identity in identities if identity.persona_type == persona_type)
                for persona_type in sorted(EXPECTED_PERSONA_TYPES)
            }
            risk_change_personas = sorted(
                profile.persona_type
                for profile in profiles
                if profile.ground_truth.get("risk_change_target") is True
            )
            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="persona_templates.yaml",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_fixture_path(self.template_path),
                        rows=len(profiles),
                        summary={
                            "persona_count": len(profiles),
                            "customer_count_per_persona": 5,
                            "risk_change_personas": risk_change_personas,
                        },
                    ),
                    AgentArtifact(
                        artifact_id="senior_customers.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_fixture_path(self.customer_path),
                        rows=len(identities),
                        summary={
                            "customer_count": len(identities),
                            "persona_customer_counts": persona_counts,
                        },
                    ),
                    AgentArtifact(
                        artifact_id="customer_driving_parameters.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_fixture_path(self.parameter_path),
                        rows=len(patterns),
                        summary={"driving_pattern_count": len(patterns)},
                    ),
                ),
                metrics={
                    "persona_count": len(profiles),
                    "customer_count": len(identities),
                    "driving_pattern_count": len(patterns),
                    "risk_change_target_customer_count": persona_counts.get("recent_outer_risk_change", 0),
                },
                validation={
                    "passed": True,
                    "expected_persona_types": sorted(EXPECTED_PERSONA_TYPES),
                    "persona_customer_counts": persona_counts,
                },
                reason_codes=("PERSONA_FIXTURE_VALIDATED", "SIX_PERSONAS_FIVE_CUSTOMERS_EACH"),
                messages=("persona templates, customer identities, and driving parameters validated",),
            )
            return AgentExecutionResult(
                run_id=payload.run_id,
                metadata=self.metadata,
                status=AgentStatus.SUCCEEDED,
                input_payload=payload,
                output_payload=output,
                started_at=started_at,
                completed_at=utc_now_iso(),
                duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
            )
        except Exception as exc:
            return AgentExecutionResult(
                run_id=payload.run_id,
                metadata=self.metadata,
                status=AgentStatus.FAILED,
                input_payload=payload,
                started_at=started_at,
                completed_at=utc_now_iso(),
                duration_ms=max(0, int((perf_counter() - start_time) * 1000)),
                errors=(f"{exc.__class__.__name__}: {exc}",),
            )

    def load_template(self) -> dict[str, Any]:
        with self.template_path.open(encoding="utf-8") as file:
            return json.load(file)

    def load_profiles(self) -> list[PersonaProfile]:
        template = self.load_template()
        self.validate_template(template)
        return [PersonaProfile.from_dict(persona) for persona in template["personas"]]

    def load_customer_fixture(self) -> dict[str, Any]:
        with self.customer_path.open(encoding="utf-8") as file:
            return json.load(file)

    def load_customer_identities(self) -> list[CustomerIdentity]:
        profiles = {profile.persona_type: profile for profile in self.load_profiles()}
        fixture = self.load_customer_fixture()
        self.validate_customer_fixture(fixture, profiles)
        return [CustomerIdentity.from_dict(customer, profiles) for customer in fixture["customers"]]

    def load_driving_parameter_fixture(self) -> dict[str, Any]:
        with self.parameter_path.open(encoding="utf-8") as file:
            return json.load(file)

    def load_customer_driving_patterns(self) -> list[CustomerDrivingPattern]:
        profiles = {profile.persona_type: profile for profile in self.load_profiles()}
        identities = self.load_customer_identities()
        fixture = self.load_driving_parameter_fixture()
        self.validate_driving_parameter_fixture(fixture, identities, profiles)
        return [CustomerDrivingPattern.from_dict(pattern) for pattern in fixture["parameters"]]

    def validate_template(self, template: dict[str, Any]) -> None:
        personas = template.get("personas")
        if not isinstance(personas, list):
            raise ValueError("personas must be a list")

        persona_types = {str(persona.get("persona_type")) for persona in personas}
        if persona_types != EXPECTED_PERSONA_TYPES:
            missing = sorted(EXPECTED_PERSONA_TYPES - persona_types)
            extra = sorted(persona_types - EXPECTED_PERSONA_TYPES)
            raise ValueError(f"persona_type mismatch; missing={missing}, extra={extra}")

        if int(template.get("customer_count_per_persona", 0)) != 5:
            raise ValueError("customer_count_per_persona must be 5")

        observation_period = template.get("observation_period", {})
        if observation_period.get("baseline_days") != 60 or observation_period.get("recent_days") != 30:
            raise ValueError("observation_period must be baseline 60 days and recent 30 days")

        risk_change_targets = 0
        for persona in personas:
            self._validate_persona(persona)
            if persona["ground_truth"].get("risk_change_target") is True:
                risk_change_targets += 1

        if risk_change_targets != 1:
            raise ValueError("exactly one persona type must be the risk_change_target group")

    def validate_customer_fixture(
        self,
        fixture: dict[str, Any],
        profiles: dict[str, PersonaProfile] | None = None,
    ) -> None:
        if profiles is None:
            profiles = {profile.persona_type: profile for profile in self.load_profiles()}

        customers = fixture.get("customers")
        if not isinstance(customers, list):
            raise ValueError("customers must be a list")
        if len(customers) != 30:
            raise ValueError("customers must define exactly 30 synthetic identities")

        seen_customer_ids: set[str] = set()
        seen_driver_ids: set[str] = set()
        persona_counts = {persona_type: 0 for persona_type in EXPECTED_PERSONA_TYPES}
        variants_by_persona: dict[str, set[str]] = {persona_type: set() for persona_type in EXPECTED_PERSONA_TYPES}

        for customer in customers:
            self._validate_customer(customer, profiles)
            customer_id = str(customer["customer_id"])
            driver_id = str(customer["driver_id"])
            persona_type = str(customer["persona_type"])

            if customer_id in seen_customer_ids:
                raise ValueError(f"duplicate customer_id: {customer_id}")
            if driver_id in seen_driver_ids:
                raise ValueError(f"duplicate driver_id: {driver_id}")

            seen_customer_ids.add(customer_id)
            seen_driver_ids.add(driver_id)
            persona_counts[persona_type] += 1
            variants_by_persona[persona_type].add(str(customer["scenario_variant"]))

        invalid_counts = {persona: count for persona, count in persona_counts.items() if count != 5}
        if invalid_counts:
            raise ValueError(f"each persona must define five customers; invalid_counts={invalid_counts}")

        for persona_type, profile in profiles.items():
            expected_variants = set(profile.scenario_variants)
            if variants_by_persona[persona_type] != expected_variants:
                raise ValueError(
                    f"{persona_type} customer variants mismatch; "
                    f"expected={sorted(expected_variants)}, actual={sorted(variants_by_persona[persona_type])}"
                )

    def validate_driving_parameter_fixture(
        self,
        fixture: dict[str, Any],
        identities: list[CustomerIdentity] | None = None,
        profiles: dict[str, PersonaProfile] | None = None,
    ) -> None:
        if profiles is None:
            profiles = {profile.persona_type: profile for profile in self.load_profiles()}
        if identities is None:
            identities = self.load_customer_identities()

        patterns = fixture.get("parameters")
        if not isinstance(patterns, list):
            raise ValueError("parameters must be a list")
        if len(patterns) != 30:
            raise ValueError("parameters must define exactly 30 customer driving patterns")

        identities_by_customer = {identity.customer_id: identity for identity in identities}
        seen_customer_ids: set[str] = set()
        for pattern in patterns:
            self._validate_driving_pattern(pattern, identities_by_customer, profiles)
            customer_id = str(pattern["customer_id"])
            if customer_id in seen_customer_ids:
                raise ValueError(f"duplicate customer driving parameters: {customer_id}")
            seen_customer_ids.add(customer_id)

        missing = sorted(set(identities_by_customer) - seen_customer_ids)
        extra = sorted(seen_customer_ids - set(identities_by_customer))
        if missing or extra:
            raise ValueError(f"driving parameter customer mismatch; missing={missing}, extra={extra}")

    def _validate_persona(self, persona: dict[str, Any]) -> None:
        missing = REQUIRED_PERSONA_FIELDS - set(persona)
        if missing:
            raise ValueError(f"{persona.get('persona_type', '<unknown>')} missing fields: {sorted(missing)}")

        behavior = persona["driving_behavior"]
        missing_behavior = REQUIRED_BEHAVIOR_FIELDS - set(behavior)
        if missing_behavior:
            raise ValueError(f"{persona['persona_type']} missing behavior fields: {sorted(missing_behavior)}")

        if len(persona["risk_traits"]) < 4:
            raise ValueError(f"{persona['persona_type']} must define at least four risk traits")
        if len(persona["scenario_variants"]) != 5:
            raise ValueError(f"{persona['persona_type']} must define five scenario variants")

        care_context = persona["care_context"]
        if care_context.get("expected_care_decision") not in {"favorable", "standard", "preventive_care"}:
            raise ValueError(f"{persona['persona_type']} has invalid expected_care_decision")

        reason_codes = persona["ground_truth"].get("expected_reason_codes", [])
        if len(reason_codes) < 3:
            raise ValueError(f"{persona['persona_type']} must define at least three expected reason codes")
        if persona["ground_truth"].get("expected_care_decision") != care_context["expected_care_decision"]:
            raise ValueError(f"{persona['persona_type']} ground_truth expected_care_decision must match care_context")
        if not isinstance(persona["ground_truth"].get("risk_change_target"), bool):
            raise ValueError(f"{persona['persona_type']} ground_truth risk_change_target must be boolean")

    def _validate_customer(self, customer: dict[str, Any], profiles: dict[str, PersonaProfile]) -> None:
        missing = REQUIRED_CUSTOMER_FIELDS - set(customer)
        if missing:
            raise ValueError(f"{customer.get('customer_id', '<unknown>')} missing fields: {sorted(missing)}")

        customer_id = str(customer["customer_id"])
        driver_id = str(customer["driver_id"])
        persona_type = str(customer["persona_type"])
        if persona_type not in profiles:
            raise ValueError(f"{customer_id} has unknown persona_type: {persona_type}")
        if not customer_id.startswith("cust_"):
            raise ValueError(f"{customer_id} must use cust_### format")
        if not driver_id.startswith("driver_"):
            raise ValueError(f"{customer_id} driver_id must use driver_### format")

        profile = profiles[persona_type]
        if customer["scenario_variant"] not in profile.scenario_variants:
            raise ValueError(f"{customer_id} scenario_variant is not defined on {persona_type}")
        if customer["expected_care_decision"] != profile.care_context["expected_care_decision"]:
            raise ValueError(f"{customer_id} expected_care_decision must match persona profile")
        if set(customer["expected_reason_codes"]) != set(profile.ground_truth["expected_reason_codes"]):
            raise ValueError(f"{customer_id} expected_reason_codes must match persona profile")

        living_zone_seed = customer["living_zone_seed"]
        for field in ("center_gps_x", "center_gps_y", "jitter_m"):
            if field not in living_zone_seed:
                raise ValueError(f"{customer_id} living_zone_seed missing {field}")
        if not 126.70 <= float(living_zone_seed["center_gps_x"]) <= 127.30:
            raise ValueError(f"{customer_id} center_gps_x outside synthetic fixture range")
        if not 37.35 <= float(living_zone_seed["center_gps_y"]) <= 37.75:
            raise ValueError(f"{customer_id} center_gps_y outside synthetic fixture range")
        if int(living_zone_seed["jitter_m"]) <= 0:
            raise ValueError(f"{customer_id} jitter_m must be positive")

    def _validate_driving_pattern(
        self,
        pattern: dict[str, Any],
        identities_by_customer: dict[str, CustomerIdentity],
        profiles: dict[str, PersonaProfile],
    ) -> None:
        missing = REQUIRED_PATTERN_FIELDS - set(pattern)
        if missing:
            raise ValueError(f"{pattern.get('customer_id', '<unknown>')} missing pattern fields: {sorted(missing)}")

        customer_id = str(pattern["customer_id"])
        if customer_id not in identities_by_customer:
            raise ValueError(f"{customer_id} does not exist in senior_customers fixture")

        identity = identities_by_customer[customer_id]
        for field in ("persona_type", "scenario_id", "scenario_variant"):
            if pattern[field] != getattr(identity, field):
                raise ValueError(f"{customer_id} {field} must match senior_customers fixture")

        profile = profiles[str(pattern["persona_type"])]
        behavior = profile.driving_behavior
        observation_period = pattern["observation_period"]
        if observation_period.get("baseline_days") != 60 or observation_period.get("recent_days") != 30:
            raise ValueError(f"{customer_id} observation_period must be baseline 60 days and recent 30 days")

        self._assert_in_range(
            customer_id,
            "annualized_mileage_target_km",
            float(pattern["annualized_mileage_target_km"]),
            behavior["annualized_mileage_band_km"],
        )
        for period, template_key in (
            ("baseline", "baseline_trip_count_range"),
            ("recent", "recent_trip_count_range"),
        ):
            self._assert_in_range(customer_id, f"{period}_trip_count", int(pattern["trip_count"][period]), behavior[template_key])
            self._assert_in_range(
                customer_id,
                f"{period}_outer_trip_ratio",
                float(pattern["zone_mix"][period]["outer"]),
                behavior[f"outer_trip_ratio_{period}"],
            )
            self._assert_in_range(
                customer_id,
                f"{period}_night_drive_ratio",
                float(pattern["night_drive_ratio"][period]),
                behavior[f"night_drive_ratio_{period}"],
            )
            self._assert_in_range(
                customer_id,
                f"{period}_risk_event_rate_per_100km",
                float(pattern["risk_event_rate_per_100km"][period]),
                behavior[f"risk_event_rate_per_100km_{period}"],
            )
            self._assert_ratio_map(customer_id, f"{period}_zone_mix", pattern["zone_mix"][period], {"core", "buffer", "outer"})
            self._assert_ratio_map(
                customer_id,
                f"{period}_time_window_weights",
                pattern["time_window_weights"][period],
                {"morning", "afternoon", "evening", "night"},
            )
            distance_range = pattern["distance_km_per_trip_range"][period]
            if len(distance_range) != 2 or float(distance_range[0]) <= 0 or float(distance_range[0]) > float(distance_range[1]):
                raise ValueError(f"{customer_id} {period} distance_km_per_trip_range is invalid")

        self._assert_ratio_map(
            customer_id,
            "risk_event_mix",
            pattern["risk_event_mix"],
            {"speeding", "harsh_accel", "harsh_brake", "sharp_turn"},
        )
        if not set(pattern["destination_weights"]).issubset(set(behavior["typical_destinations"])):
            raise ValueError(f"{customer_id} destination_weights must use persona typical_destinations")
        self._assert_ratio_map(customer_id, "destination_weights", pattern["destination_weights"], set(pattern["destination_weights"]))
        if pattern["route_variability"] not in {"low", "medium", "high"}:
            raise ValueError(f"{customer_id} route_variability must be low, medium, or high")

    def _assert_in_range(self, customer_id: str, field: str, value: float, bounds: list[float]) -> None:
        lower, upper = float(bounds[0]), float(bounds[1])
        if not lower <= value <= upper:
            raise ValueError(f"{customer_id} {field}={value} outside range [{lower}, {upper}]")

    def _assert_ratio_map(self, customer_id: str, field: str, value: dict[str, Any], expected_keys: set[str]) -> None:
        if set(value) != expected_keys:
            raise ValueError(f"{customer_id} {field} keys must be {sorted(expected_keys)}")
        total = sum(float(ratio) for ratio in value.values())
        if any(float(ratio) < 0 for ratio in value.values()) or abs(total - 1.0) > 0.01:
            raise ValueError(f"{customer_id} {field} ratios must be non-negative and sum to 1.0")


def _relative_fixture_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate senior driver persona templates.")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE_PATH), help="Path to persona_templates.yaml")
    parser.add_argument("--customers", default=str(DEFAULT_CUSTOMER_PATH), help="Path to senior_customers.json")
    parser.add_argument("--parameters", default=str(DEFAULT_PARAMETER_PATH), help="Path to customer_driving_parameters.json")
    args = parser.parse_args(argv)

    agent = PersonaAgent(args.template, args.customers, args.parameters)
    profiles = agent.load_profiles()
    identities = agent.load_customer_identities()
    patterns = agent.load_customer_driving_patterns()
    print(f"persona templates: {args.template}")
    print(f"customer identities: {args.customers}")
    print(f"customer driving parameters: {args.parameters}")
    print(f"persona_count: {len(profiles)}")
    print(f"customer_count: {len(identities)}")
    print(f"driving_pattern_count: {len(patterns)}")
    for profile in profiles:
        decision = profile.care_context["expected_care_decision"]
        count = sum(1 for identity in identities if identity.persona_type == profile.persona_type)
        pattern_count = sum(1 for pattern in patterns if pattern.persona_type == profile.persona_type)
        print(
            f"- {profile.persona_type}: {profile.display_name_ko} / "
            f"customers={count} / patterns={pattern_count} / expected={decision}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Scenario Agent for customer-level 30-day trip generation rules."""

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
from src.agents.persona_agent import (
    CustomerDrivingPattern,
    CustomerIdentity,
    PersonaAgent,
    PersonaProfile,
    EXPECTED_PERSONA_TYPES,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_OUTPUT = ROOT / "data" / "fixtures" / "scenario_config.json"
SCHEMA_VERSION = "senior-scenario-config/v1"


@dataclass(frozen=True)
class ScenarioRule:
    customer_id: str
    persona_type: str
    scenario_id: str
    scenario_variant: str
    observation_period: dict[str, int]
    baseline_driving_pattern: dict[str, Any]
    recent_30_day_rule: dict[str, Any]
    expected_recent_behavior_change: dict[str, Any]
    ground_truth: dict[str, Any]


class ScenarioAgent:
    """Builds explicit scenario rules from persona and customer fixtures."""

    metadata = AgentMetadata(
        agent_id="scenario_agent",
        role=AgentRole.SCENARIO,
        display_name="Scenario Agent",
        description="Builds 60-day baseline and 30-day recent behavior-change scenarios.",
        consumes=("persona_templates.yaml", "senior_customers.json", "customer_driving_parameters.json"),
        produces=("scenario_config.json",),
    )

    def __init__(self, persona_agent: PersonaAgent | None = None) -> None:
        self.persona_agent = persona_agent or PersonaAgent()

    def run(self, payload: AgentInputPayload) -> AgentExecutionResult:
        """Generate scenario_config and return the shared agent contract result."""
        started_at = utc_now_iso()
        start_time = perf_counter()
        try:
            payload.validate(self.metadata)
            output_path = Path(str(payload.parameters.get("output_path", DEFAULT_SCENARIO_OUTPUT)))
            config = self.write_config(output_path)
            rules = config["customer_scenario_rules"]
            persona_counts = {
                persona_type: sum(1 for rule in rules if rule["persona_type"] == persona_type)
                for persona_type in sorted(EXPECTED_PERSONA_TYPES)
            }
            risk_change_count = sum(
                1
                for rule in rules
                if rule["expected_recent_behavior_change"]["risk_change_target"] is True
            )
            output = AgentOutputPayload(
                run_id=payload.run_id,
                agent_id=self.metadata.agent_id,
                output_artifacts=(
                    AgentArtifact(
                        artifact_id="scenario_config.json",
                        artifact_type=ArtifactType.JSON,
                        path=_relative_fixture_path(output_path),
                        rows=len(rules),
                        summary={
                            "customer_scenario_rule_count": len(rules),
                            "persona_customer_counts": persona_counts,
                            "risk_change_target_customer_count": risk_change_count,
                            "observation_period": config["observation_period"],
                        },
                    ),
                ),
                metrics={
                    "customer_scenario_rule_count": len(rules),
                    "persona_count": len(persona_counts),
                    "risk_change_target_customer_count": risk_change_count,
                    "baseline_days": config["observation_period"]["baseline_days"],
                    "recent_days": config["observation_period"]["recent_days"],
                },
                validation={
                    "passed": True,
                    "persona_customer_counts": persona_counts,
                    "risk_change_target_persona": "recent_outer_risk_change",
                    "observation_period": config["observation_period"],
                },
                reason_codes=("SCENARIO_CONFIG_VALIDATED", "BASELINE_60_RECENT_30_DEFINED"),
                messages=("scenario_config generated and validated",),
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

    def build_config(self) -> dict[str, Any]:
        profiles = {profile.persona_type: profile for profile in self.persona_agent.load_profiles()}
        identities = self.persona_agent.load_customer_identities()
        patterns = self.persona_agent.load_customer_driving_patterns()
        identities_by_customer = {identity.customer_id: identity for identity in identities}

        scenario_rules = [
            self.build_rule(identities_by_customer[pattern.customer_id], pattern, profiles[pattern.persona_type])
            for pattern in patterns
        ]
        config = {
            "schema_version": SCHEMA_VERSION,
            "simulation_seed": int(self.persona_agent.load_template()["simulation_seed"]),
            "source_persona_template": str(self.persona_agent.template_path.relative_to(ROOT)),
            "source_customer_fixture": str(self.persona_agent.customer_path.relative_to(ROOT)),
            "source_parameter_fixture": str(self.persona_agent.parameter_path.relative_to(ROOT)),
            "customer_count": len(scenario_rules),
            "customer_count_per_persona": 5,
            "observation_period": {"baseline_days": 60, "recent_days": 30},
            "persona_generation_rules": self.build_persona_generation_rules(profiles),
            "customer_scenario_rules": [self.rule_to_dict(rule) for rule in scenario_rules],
        }
        self.validate_config(config)
        return config

    def build_persona_generation_rules(self, profiles: dict[str, PersonaProfile]) -> dict[str, Any]:
        rules: dict[str, Any] = {}
        for persona_type, profile in sorted(profiles.items()):
            behavior = profile.driving_behavior
            rules[persona_type] = {
                "display_name_ko": profile.display_name_ko,
                "product_role": profile.product_role,
                "baseline_60_day_rule": {
                    "trip_count_range": behavior["baseline_trip_count_range"],
                    "outer_trip_ratio_range": behavior["outer_trip_ratio_baseline"],
                    "night_drive_ratio_range": behavior["night_drive_ratio_baseline"],
                    "risk_event_rate_per_100km_range": behavior["risk_event_rate_per_100km_baseline"],
                    "primary_zones": behavior["primary_zones"],
                    "typical_destinations": behavior["typical_destinations"],
                },
                "recent_30_day_rule": {
                    "trip_count_range": behavior["recent_trip_count_range"],
                    "outer_trip_ratio_range": behavior["outer_trip_ratio_recent"],
                    "night_drive_ratio_range": behavior["night_drive_ratio_recent"],
                    "risk_event_rate_per_100km_range": behavior["risk_event_rate_per_100km_recent"],
                },
                "expected_care_decision": profile.care_context["expected_care_decision"],
                "risk_change_target": bool(profile.ground_truth["risk_change_target"]),
                "expected_reason_codes": profile.ground_truth["expected_reason_codes"],
            }
        return rules

    def build_rule(
        self,
        identity: CustomerIdentity,
        pattern: CustomerDrivingPattern,
        profile: PersonaProfile,
    ) -> ScenarioRule:
        baseline = {
            "trip_count": pattern.trip_count["baseline"],
            "distance_km_per_trip_range": pattern.distance_km_per_trip_range["baseline"],
            "zone_mix": pattern.zone_mix["baseline"],
            "night_drive_ratio": pattern.night_drive_ratio["baseline"],
            "risk_event_rate_per_100km": pattern.risk_event_rate_per_100km["baseline"],
            "time_window_weights": pattern.time_window_weights["baseline"],
            "destination_weights": pattern.destination_weights,
            "route_variability": pattern.route_variability,
        }
        recent = {
            "trip_count": pattern.trip_count["recent"],
            "distance_km_per_trip_range": pattern.distance_km_per_trip_range["recent"],
            "zone_mix": pattern.zone_mix["recent"],
            "night_drive_ratio": pattern.night_drive_ratio["recent"],
            "risk_event_rate_per_100km": pattern.risk_event_rate_per_100km["recent"],
            "time_window_weights": pattern.time_window_weights["recent"],
        }
        expected_change = {
            "outer_ratio_delta": pattern.pattern_change_expectation["outer_ratio_delta"],
            "night_ratio_delta": pattern.pattern_change_expectation["night_ratio_delta"],
            "risk_rate_delta_per_100km": pattern.pattern_change_expectation["risk_rate_delta_per_100km"],
            "risk_change_target": bool(profile.ground_truth["risk_change_target"]),
            "expected_care_decision": identity.expected_care_decision,
            "expected_reason_codes": identity.expected_reason_codes,
        }
        return ScenarioRule(
            customer_id=identity.customer_id,
            persona_type=identity.persona_type,
            scenario_id=identity.scenario_id,
            scenario_variant=identity.scenario_variant,
            observation_period={
                "baseline_days": int(pattern.observation_period["baseline_days"]),
                "recent_days": int(pattern.observation_period["recent_days"]),
            },
            baseline_driving_pattern=baseline,
            recent_30_day_rule=recent,
            expected_recent_behavior_change=expected_change,
            ground_truth={
                "risk_change_target": bool(profile.ground_truth["risk_change_target"]),
                "expected_care_decision": identity.expected_care_decision,
                "expected_reason_codes": profile.ground_truth["expected_reason_codes"],
            },
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        rules = config.get("customer_scenario_rules", [])
        if len(rules) != 30:
            raise ValueError("scenario_config must define exactly 30 customer scenario rules")
        if config.get("observation_period") != {"baseline_days": 60, "recent_days": 30}:
            raise ValueError("scenario_config observation_period must be baseline 60 days and recent 30 days")

        persona_counts: dict[str, int] = {}
        risk_change_customers = 0
        for rule in rules:
            persona_type = str(rule["persona_type"])
            persona_counts[persona_type] = persona_counts.get(persona_type, 0) + 1
            if rule["observation_period"] != {"baseline_days": 60, "recent_days": 30}:
                raise ValueError(f"{rule['customer_id']} observation_period must be 60+30 days")
            for field in ("baseline_driving_pattern", "recent_30_day_rule", "expected_recent_behavior_change"):
                if not rule.get(field):
                    raise ValueError(f"{rule['customer_id']} missing {field}")

            change = rule["expected_recent_behavior_change"]
            baseline = rule["baseline_driving_pattern"]
            recent = rule["recent_30_day_rule"]
            self._assert_delta_matches(rule["customer_id"], "outer_ratio_delta", recent["zone_mix"]["outer"] - baseline["zone_mix"]["outer"], change)
            self._assert_delta_matches(
                rule["customer_id"],
                "night_ratio_delta",
                recent["night_drive_ratio"] - baseline["night_drive_ratio"],
                change,
            )
            self._assert_delta_matches(
                rule["customer_id"],
                "risk_rate_delta_per_100km",
                recent["risk_event_rate_per_100km"] - baseline["risk_event_rate_per_100km"],
                change,
            )
            if change["risk_change_target"]:
                risk_change_customers += 1

        invalid_counts = {persona: count for persona, count in persona_counts.items() if count != 5}
        if invalid_counts or len(persona_counts) != 6:
            raise ValueError(f"scenario_config must define six personas with five customers each; invalid={invalid_counts}")
        if risk_change_customers != 5:
            raise ValueError("scenario_config must define five risk-change target customers")

    def write_config(self, output_path: str | Path = DEFAULT_SCENARIO_OUTPUT) -> dict[str, Any]:
        config = self.build_config()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return config

    def rule_to_dict(self, rule: ScenarioRule) -> dict[str, Any]:
        return {
            "customer_id": rule.customer_id,
            "persona_type": rule.persona_type,
            "scenario_id": rule.scenario_id,
            "scenario_variant": rule.scenario_variant,
            "observation_period": rule.observation_period,
            "baseline_driving_pattern": rule.baseline_driving_pattern,
            "recent_30_day_rule": rule.recent_30_day_rule,
            "expected_recent_behavior_change": rule.expected_recent_behavior_change,
            "ground_truth": rule.ground_truth,
        }

    def _assert_delta_matches(self, customer_id: str, field: str, actual_delta: float, change: dict[str, Any]) -> None:
        expected_delta = float(change[field])
        if round(actual_delta, 4) != round(expected_delta, 4):
            raise ValueError(
                f"{customer_id} {field} mismatch; "
                f"expected={round(expected_delta, 4)}, actual={round(actual_delta, 4)}"
            )


def _relative_fixture_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build senior driver scenario_config fixture.")
    parser.add_argument("--output", default=str(DEFAULT_SCENARIO_OUTPUT), help="Scenario config JSON output path")
    args = parser.parse_args(argv)

    agent = ScenarioAgent()
    config = agent.write_config(args.output)
    print(f"wrote {len(config['customer_scenario_rules'])} customer scenario rules to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

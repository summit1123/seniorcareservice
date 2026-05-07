"""Agent definitions for Senior Safe Mileage product exploration."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "ABComparison": "src.agents.contracts",
    "AGENT_REGISTRY": "src.agents.orchestrator",
    "AGENT_VALIDATION_PIPELINE_SCHEMA_VERSION": "src.agents.contracts",
    "AISimulationAgent": "src.agents.ai_simulation_agent",
    "AgentArtifact": "src.agents.contracts",
    "AgentExecutionResult": "src.agents.contracts",
    "AgentInputPayload": "src.agents.contracts",
    "AgentMetadata": "src.agents.contracts",
    "AgentOutputPayload": "src.agents.contracts",
    "AgentRegistry": "src.agents.orchestrator",
    "AgentRole": "src.agents.contracts",
    "AgentStatus": "src.agents.contracts",
    "AgentValidationCheckResult": "src.agents.contracts",
    "AgentValidationPipelineResult": "src.agents.contracts",
    "AgentValidationSummary": "src.agents.contracts",
    "ConsistencyCheckAgent": "src.agents.consistency_check_agent",
    "CriticAgent": "src.agents.critic_agent",
    "CustomerDecisionSnapshot": "src.agents.contracts",
    "EvaluationAgent": "src.agents.evaluation_agent",
    "ObservationPeriod": "src.agents.contracts",
    "OrchestratorSpec": "src.agents.orchestrator",
    "OrchestratorStep": "src.agents.orchestrator",
    "PolicyCandidate": "src.agents.contracts",
    "PolicySearchAgent": "src.agents.policy_search_agent",
    "ReportAgent": "src.agents.report_agent",
    "ScenarioAgent": "src.agents.scenario_agent",
    "SeniorMileageAgent": "src.agents.contracts",
    "StructuredOutputEnvelope": "src.agents.structured_outputs",
    "UI_DASHBOARD_BUNDLE_SCHEMA": "src.agents.structured_outputs",
    "build_default_agent_map": "src.agents.orchestrator",
    "build_orchestrator_spec": "src.agents.orchestrator",
    "build_pipeline_steps": "src.agents.orchestrator",
    "build_ui_dashboard_bundle": "src.agents.structured_outputs",
    "execute_agent_pipeline": "src.agents.orchestrator",
    "execute_default_agent_pipeline": "src.agents.orchestrator",
    "load_structured_json": "src.agents.structured_outputs",
    "validate_agent_validation_pipeline_result": "src.agents.contracts",
    "validate_critic_review": "src.agents.structured_outputs",
    "validate_customer_decision_snapshot": "src.agents.contracts",
    "validate_evaluation_view_model": "src.agents.structured_outputs",
    "validate_report_view_model": "src.agents.structured_outputs",
    "validate_ui_dashboard_bundle": "src.agents.structured_outputs",
    "write_structured_json": "src.agents.structured_outputs",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    """Load exported agent helpers lazily.

    This avoids importing an executable submodule while ``python -m`` is still
    preparing to run it.
    """

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value

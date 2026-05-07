"""Local webapp views for Senior Safe Mileage."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "build_customer_decision_view_model": "src.webapp.customer_decision_app",
    "build_validation_api_response": "src.webapp.customer_decision_app",
    "load_dashboard_bundle": "src.webapp.customer_decision_app",
    "render_customer_decision_page": "src.webapp.customer_decision_app",
    "render_webapp_page": "src.webapp.customer_decision_app",
    "get_validation_pipeline_check": "src.webapp.validation_pipeline_service",
    "load_validation_pipeline_result": "src.webapp.validation_pipeline_service",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    """Load exported webapp helpers lazily.

    This keeps ``python -m src.webapp.customer_decision_app`` from importing the
    target module through the package initializer before runpy executes it.
    """

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value

"""Shared LLM client utilities for Senior Safe Mileage agents."""

from src.llm.openai_client import (
    OpenAIClient,
    OpenAIClientAuthenticationError,
    OpenAIClientAPIError,
    OpenAIClientConfigurationError,
    OpenAIClientError,
    OpenAIClientNetworkError,
    OpenAIClientRateLimitError,
    OpenAIClientTimeoutError,
    OpenAIReportRequest,
    OpenAIReportResponse,
)

__all__ = [
    "OpenAIClient",
    "OpenAIClientAuthenticationError",
    "OpenAIClientAPIError",
    "OpenAIClientConfigurationError",
    "OpenAIClientError",
    "OpenAIClientNetworkError",
    "OpenAIClientRateLimitError",
    "OpenAIClientTimeoutError",
    "OpenAIReportRequest",
    "OpenAIReportResponse",
]

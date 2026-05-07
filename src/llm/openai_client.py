"""Central OpenAI API wrapper for insurer-staff report generation.

The wrapper keeps network policy in one place: timeout, retry budget, and
exception conversion.  Agents should depend on this module instead of importing
the OpenAI SDK directly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from time import sleep as default_sleep
from typing import Any, Callable, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRIES = 1
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAIClientError(RuntimeError):
    """Base exception raised by the shared OpenAI wrapper."""


class OpenAIClientConfigurationError(OpenAIClientError):
    """Raised when the OpenAI SDK or API key is not configured."""


class OpenAIClientAuthenticationError(OpenAIClientError):
    """Raised when OpenAI authentication or authorization fails."""


class OpenAIClientTimeoutError(OpenAIClientError):
    """Raised after a timeout exceeds the configured retry budget."""


class OpenAIClientNetworkError(OpenAIClientError):
    """Raised when the OpenAI request fails at the network transport layer."""


class OpenAIClientRateLimitError(OpenAIClientError):
    """Raised after a rate limit response exceeds the retry budget."""


class OpenAIClientAPIError(OpenAIClientError):
    """Raised for non-timeout, non-rate-limit OpenAI API failures."""


class _ResponsesTransport(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """Create a response using OpenAI-compatible keyword arguments."""


@dataclass(frozen=True)
class OpenAIReportRequest:
    """Privacy-filtered request payload for insurer-staff LLM reports."""

    system_prompt: str
    user_prompt: str
    request_features: dict[str, Any]
    purpose: str = "insurer_staff_report"


@dataclass(frozen=True)
class OpenAIReportResponse:
    """Normalized OpenAI response returned to report agents."""

    text: str
    model: str
    attempts: int
    raw_response: Any | None = None


class OpenAIClient:
    """Small Responses API client with centralized timeout and retry handling."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: _ResponsesTransport | None = None,
        sleep: Callable[[float], None] = default_sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self._transport = transport
        self._sleep = sleep

    def generate_insurer_report(self, request: OpenAIReportRequest) -> OpenAIReportResponse:
        """Generate a report from already privacy-filtered summary features."""

        from src.agents.contracts import validate_privacy_filtered_features

        validate_privacy_filtered_features(request.request_features)
        input_payload = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": request.system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": request.user_prompt,
                    },
                    {
                        "type": "input_text",
                        "text": f"privacy_filtered_features={request.request_features!r}",
                    },
                ],
            },
        ]
        return self.create_text_response(input_payload, purpose=request.purpose)

    def create_text_response(self, input_payload: Any, *, purpose: str) -> OpenAIReportResponse:
        """Call OpenAI Responses API and normalize retries and exceptions."""

        transport = self._transport or self._build_default_transport()
        attempts = 0
        last_exc: BaseException | None = None
        for attempt_index in range(self.max_retries + 1):
            attempts = attempt_index + 1
            try:
                response = transport.create(
                    model=self.model,
                    input=input_payload,
                    timeout=self.timeout_seconds,
                    metadata={"purpose": purpose},
                )
                return OpenAIReportResponse(
                    text=_extract_response_text(response),
                    model=self.model,
                    attempts=attempts,
                    raw_response=response,
                )
            except Exception as exc:
                converted = _convert_openai_exception(exc)
                if not _is_retryable(converted) or attempt_index >= self.max_retries:
                    raise converted from exc
                last_exc = converted
                self._sleep(min(2.0, 0.25 * (2**attempt_index)))
        if last_exc is not None:
            raise last_exc
        raise OpenAIClientAPIError("OpenAI request failed before an attempt was made")

    def _build_default_transport(self) -> _ResponsesTransport:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise OpenAIClientConfigurationError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            return _UrllibResponsesTransport(api_key=api_key)
        client = OpenAI(api_key=api_key, timeout=self.timeout_seconds, max_retries=0)
        return client.responses


class _UrllibResponsesTransport:
    """Minimal Responses API transport used when the OpenAI SDK is unavailable."""

    def __init__(self, *, api_key: str, endpoint: str = OPENAI_RESPONSES_URL) -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    def create(self, **kwargs: Any) -> dict[str, Any]:
        timeout = float(kwargs.pop("timeout", DEFAULT_TIMEOUT_SECONDS))
        payload = {
            "model": kwargs["model"],
            "input": kwargs["input"],
        }
        if kwargs.get("metadata"):
            payload["metadata"] = kwargs["metadata"]
        request = urllib_request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = f"OpenAI HTTP {exc.code}: {_openai_error_message(body)}"
            if exc.code == 401:
                raise OpenAIClientAuthenticationError(message) from exc
            if exc.code == 429:
                raise OpenAIClientRateLimitError(message) from exc
            raise OpenAIClientAPIError(message) from exc
        except urllib_error.URLError as exc:
            raise OpenAIClientNetworkError(str(exc.reason)) from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise OpenAIClientAPIError("OpenAI response was not valid JSON") from exc


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    if isinstance(response, dict):
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        text = response.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        output_text = _extract_text_from_responses_output(response.get("output"))
        if output_text:
            return output_text
        raise OpenAIClientAPIError("OpenAI response did not include text")
    text = str(response).strip()
    if text:
        return text
    raise OpenAIClientAPIError("OpenAI response did not include text")


def _extract_text_from_responses_output(output: Any) -> str:
    fragments: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for content_item in content:
                    if isinstance(content_item, dict):
                        text = content_item.get("text")
                        if isinstance(text, str) and text.strip():
                            fragments.append(text.strip())
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())
    return "\n".join(fragments).strip()


def _openai_error_message(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return body.strip()


def _convert_openai_exception(exc: BaseException) -> OpenAIClientError:
    name = exc.__class__.__name__.lower()
    message = str(exc) or exc.__class__.__name__
    if "timeout" in name or "timed out" in message.lower():
        return OpenAIClientTimeoutError(message)
    if (
        "authentication" in name
        or "auth" in name
        or "unauthorized" in message.lower()
        or "invalid api key" in message.lower()
        or "401" in message
    ):
        return OpenAIClientAuthenticationError(message)
    if (
        "connection" in name
        or "network" in name
        or "connection" in message.lower()
        or "network" in message.lower()
    ):
        return OpenAIClientNetworkError(message)
    if "ratelimit" in name or "rate_limit" in name or "rate limit" in message.lower():
        return OpenAIClientRateLimitError(message)
    if isinstance(exc, OpenAIClientError):
        return exc
    return OpenAIClientAPIError(message)


def _is_retryable(exc: OpenAIClientError) -> bool:
    return isinstance(exc, (OpenAIClientTimeoutError, OpenAIClientRateLimitError))

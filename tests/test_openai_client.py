from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.llm.openai_client import (
    OpenAIClient,
    OpenAIClientAuthenticationError,
    OpenAIClientAPIError,
    OpenAIClientConfigurationError,
    OpenAIClientNetworkError,
    OpenAIClientRateLimitError,
    OpenAIClientTimeoutError,
    OpenAIReportRequest,
)


class FakeTransport:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeTimeoutError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeAuthenticationError(Exception):
    pass


class FakeNetworkError(Exception):
    pass


class TestOpenAIClient(unittest.TestCase):
    def test_create_text_response_applies_timeout_and_retry_limit(self) -> None:
        transport = FakeTransport(
            [
                FakeTimeoutError("request timeout"),
                {"output_text": "보험사 직원용 요약"},
            ]
        )
        sleep_calls: list[float] = []
        client = OpenAIClient(
            model="test-model",
            timeout_seconds=3.5,
            max_retries=1,
            transport=transport,
            sleep=sleep_calls.append,
        )

        response = client.create_text_response([{"role": "user", "content": "hello"}], purpose="unit_test")

        self.assertEqual(response.text, "보험사 직원용 요약")
        self.assertEqual(response.model, "test-model")
        self.assertEqual(response.attempts, 2)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0]["timeout"], 3.5)
        self.assertEqual(transport.calls[0]["metadata"], {"purpose": "unit_test"})
        self.assertEqual(sleep_calls, [0.25])

    def test_timeout_exception_is_converted_after_retry_budget(self) -> None:
        transport = FakeTransport(
            [
                FakeTimeoutError("request timeout"),
                FakeTimeoutError("request timeout"),
            ]
        )
        client = OpenAIClient(max_retries=1, transport=transport, sleep=lambda _: None)

        with self.assertRaises(OpenAIClientTimeoutError):
            client.create_text_response("payload", purpose="timeout_test")

        self.assertEqual(len(transport.calls), 2)

    def test_rate_limit_exception_is_converted_and_retried(self) -> None:
        transport = FakeTransport([FakeRateLimitError("rate limit exceeded")])
        client = OpenAIClient(max_retries=0, transport=transport, sleep=lambda _: None)

        with self.assertRaises(OpenAIClientRateLimitError):
            client.create_text_response("payload", purpose="rate_limit_test")

    def test_non_retryable_api_exception_is_not_retried(self) -> None:
        transport = FakeTransport([RuntimeError("bad request")])
        client = OpenAIClient(max_retries=3, transport=transport, sleep=lambda _: None)

        with self.assertRaises(OpenAIClientAPIError):
            client.create_text_response("payload", purpose="api_error_test")

        self.assertEqual(len(transport.calls), 1)

    def test_authentication_exception_is_converted_without_retry(self) -> None:
        transport = FakeTransport([FakeAuthenticationError("401 invalid api key")])
        client = OpenAIClient(max_retries=3, transport=transport, sleep=lambda _: None)

        with self.assertRaises(OpenAIClientAuthenticationError):
            client.create_text_response("payload", purpose="auth_error_test")

        self.assertEqual(len(transport.calls), 1)

    def test_network_exception_is_converted_without_retry(self) -> None:
        transport = FakeTransport([FakeNetworkError("network connection failed")])
        client = OpenAIClient(max_retries=3, transport=transport, sleep=lambda _: None)

        with self.assertRaises(OpenAIClientNetworkError):
            client.create_text_response("payload", purpose="network_error_test")

        self.assertEqual(len(transport.calls), 1)

    def test_response_without_text_is_parsing_error(self) -> None:
        transport = FakeTransport([{"output": []}])
        client = OpenAIClient(max_retries=0, transport=transport, sleep=lambda _: None)

        with self.assertRaisesRegex(OpenAIClientAPIError, "did not include text"):
            client.create_text_response("payload", purpose="parsing_error_test")

    def test_extracts_text_from_responses_api_output_shape(self) -> None:
        transport = FakeTransport(
            [
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "실제 Responses API 요약"},
                            ],
                        }
                    ]
                }
            ]
        )
        client = OpenAIClient(max_retries=0, transport=transport, sleep=lambda _: None)

        response = client.create_text_response("payload", purpose="responses_shape_test")

        self.assertEqual(response.text, "실제 Responses API 요약")

    def test_generate_insurer_report_rejects_forbidden_request_features(self) -> None:
        client = OpenAIClient(transport=FakeTransport([{"output_text": "unused"}]))
        request = OpenAIReportRequest(
            system_prompt="system",
            user_prompt="user",
            request_features={"customer_id": "cust_011", "risk_change_score": 91.2},
        )

        with self.assertRaisesRegex(ValueError, "forbidden external API fields"):
            client.generate_insurer_report(request)

    def test_default_transport_requires_api_key(self) -> None:
        client = OpenAIClient()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(OpenAIClientConfigurationError, "OPENAI_API_KEY"):
                client.create_text_response("payload", purpose="configuration_test")


if __name__ == "__main__":
    unittest.main()

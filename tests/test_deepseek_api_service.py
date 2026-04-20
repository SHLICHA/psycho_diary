"""Unit tests for DeepSeek API service failure payloads."""

import asyncio

import aiohttp

from bot.services.deepseek_api import DeepSeekAPIService


class TestDeepSeekAPIServiceFailurePayloads:
    def test_build_failure_payload_timeout(self):
        service = DeepSeekAPIService()

        payload = service._build_failure_payload(asyncio.TimeoutError(), "")

        assert payload["success"] is False
        assert payload["error"] == "timeout"
        assert "ожидания" in payload["message"]

    def test_build_failure_payload_parse_failure(self):
        service = DeepSeekAPIService()

        payload = service._build_failure_payload(ValueError("bad json"), "raw")

        assert payload["success"] is False
        assert payload["error"] == "response_parse_failed"
        assert "Не удалось обработать ответ AI" in payload["message"]
        assert payload["raw_response"] == "raw"

    def test_build_failure_payload_upstream_unavailable(self):
        service = DeepSeekAPIService()

        payload = service._build_failure_payload(aiohttp.ClientError("network"), "")

        assert payload["success"] is False
        assert payload["error"] == "upstream_unavailable"

    def test_build_failure_payload_request_failed_default(self):
        service = DeepSeekAPIService()

        payload = service._build_failure_payload(RuntimeError("boom"), "")

        assert payload["success"] is False
        assert payload["error"] == "request_failed"
        assert payload["message"] == "boom"

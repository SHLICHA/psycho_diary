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


class TestExtractJsonFromRawText:
    """Тесты вспомогательного метода _extract_json_from_raw_text."""

    def setup_method(self):
        self.service = DeepSeekAPIService()

    def test_extracts_json_object_from_plain_text(self):
        text = 'Вот ответ: {"key": "value", "num": 42} — конец.'
        result = self.service._extract_json_from_raw_text(text)
        assert result == {"key": "value", "num": 42}

    def test_extracts_json_array_from_plain_text(self):
        text = 'Список: [1, 2, 3] готово.'
        result = self.service._extract_json_from_raw_text(text)
        assert result == [1, 2, 3]

    def test_returns_none_for_invalid_json(self):
        text = "Здесь нет JSON вообще."
        result = self.service._extract_json_from_raw_text(text)
        assert result is None

    def test_handles_nested_json(self):
        text = 'Result: {"cleaned_items": [{"value": "тест", "weight": 0.5}]}'
        result = self.service._extract_json_from_raw_text(text)
        assert result is not None
        assert "cleaned_items" in result

    def test_extracts_first_json_object(self):
        text = 'Объект: {"a": 1} и ещё: {"b": 2}'
        result = self.service._extract_json_from_raw_text(text)
        assert result == {"a": 1}


class TestParseAnalysisResponseFallback:
    """Тесты fallback-поведения парсера при неполном/мусорном ответе."""

    def setup_method(self):
        self.service = DeepSeekAPIService()

    def test_parse_plain_json(self):
        text = '{"cleaned_items": []}'
        result = asyncio.run(self.service._parse_analysis_response(text, 'ru'))
        assert result == {"cleaned_items": []}

    def test_parse_fenced_json_block(self):
        text = '```json\n{"cleaned_items": [{"value": "тест"}]}\n```'
        result = asyncio.run(self.service._parse_analysis_response(text, 'ru'))
        assert "cleaned_items" in result

    def test_parse_fenced_block_with_trailing_garbage(self):
        text = '```json\n{"key": "value"}  trailing text\n```'
        # Блок не парсится напрямую из-за мусора, парсер падает на fallback _extract_json_from_raw_text,
        # который находит первый балансированный JSON-объект — только полные данные, без обрезки.
        result = asyncio.run(self.service._parse_analysis_response(text, 'ru'))
        assert result == {"key": "value"}

    def test_parse_json_embedded_in_text(self):
        text = 'Вот результат: {"cleaned_items": []} — готово.'
        result = asyncio.run(self.service._parse_analysis_response(text, 'ru'))
        assert result == {"cleaned_items": []}

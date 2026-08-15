"""Тесты промпта и параметров therapy chat."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from diary.services.therapy_chat_service import TherapyChatService
from prompts.templates.therapy_chat_prompt import THERAPY_CHAT_PROMPT


class TestTherapyChatPrompt:
    def test_ru_prompt_has_length_limit_and_full_example(self):
        prompt = THERAPY_CHAT_PROMPT['ru']
        assert '2500' in prompt
        assert '2–4 коротких абзаца' in prompt
        assert 'is_valid = false' in prompt
        assert 'на «ты»' in prompt
        assert 'непринуждённый' in prompt
        assert 'день уже выжал тебя' in prompt
        assert 'что сильнее давит' in prompt

    def test_en_prompt_has_length_limit_and_full_example(self):
        prompt = THERAPY_CHAT_PROMPT['en']
        assert '2500' in prompt
        assert '2–4 short paragraphs' in prompt
        assert 'is_valid = false' in prompt
        assert 'casual and simple' in prompt
        assert 'day already drained you' in prompt


@pytest.mark.asyncio
async def test_therapy_chat_uses_warmer_generation_params(mocker):
    user = MagicMock()
    user.id = 1
    user.telegram_id = 123
    user.language = 'ru'
    user.compressed_psych_profile = {'psych_summary': 'test'}
    user.aget_profile_data = AsyncMock(
        return_value={
            'first_name': 'Test',
            'awareness_level': 1,
            'is_premium': False,
            'entries_count': 0,
        }
    )

    mock_api = mocker.patch(
        'diary.services.therapy_chat_service.deepseek_api_service.send_prompt_and_parse',
        new=AsyncMock(
            return_value={
                'success': True,
                'result': {'is_valid': True, 'response_text': 'ok'},
            }
        ),
    )
    mocker.patch(
        'diary.services.therapy_chat_service.get_prompt',
        return_value='prompt',
    )

    result = await TherapyChatService.process_user_message(
        user=user,
        user_message_text='Мне тревожно',
        current_history=[],
    )

    assert result['success'] is True
    mock_api.assert_awaited_once()
    kwargs = mock_api.await_args.kwargs
    assert kwargs['temperature'] == 0.7
    assert kwargs['max_tokens'] == 900

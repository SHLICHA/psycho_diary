from types import SimpleNamespace

import pytest

from bot.presenters.diary_presenter import (
    build_analysis_result_payload,
    build_analysis_error_payload,
    build_new_entry_validation_failure_view,
    build_new_entry_success_text,
    build_clarification_questions_view,
    build_entry_saved_view,
)


def test_build_analysis_result_payload_success_shape():
    analysis = SimpleNamespace(mood_score=8, comment='ok', recommendation='go on')
    payload = build_analysis_result_payload({
        'analysis': analysis,
        'formatted_message_ai': 'final text',
    })

    assert payload['success'] is True
    assert payload['result']['mood_score'] == 8
    assert payload['result']['comment'] == 'ok'
    assert payload['result']['recommendation'] == 'go on'
    assert payload['result']['analysis'] == 'final text'


def test_build_analysis_error_payload_defaults():
    payload = build_analysis_error_payload('boom')

    assert payload == {
        'success': False,
        'error': 'service_error',
        'message': 'boom',
    }


def test_build_analysis_error_payload_custom_error_type():
    payload = build_analysis_error_payload('timeout', error_type='timeout')

    assert payload['success'] is False
    assert payload['error'] == 'timeout'
    assert payload['message'] == 'timeout'


def test_build_new_entry_validation_failure_view_with_formatted_message():
    view = build_new_entry_validation_failure_view(
        {'formatted_message_ai': 'custom fail text'},
        language='ru',
    )

    assert view['text'] == 'custom fail text'
    assert view['reply_markup'].inline_keyboard[0][0].callback_data == 'new_entry'
    assert view['reply_markup'].inline_keyboard[1][0].callback_data == 'main_menu'


def test_build_new_entry_validation_failure_view_with_validation_comment():
    view = build_new_entry_validation_failure_view(
        {'validation_comment_ai': 'need more details'},
        language='ru',
    )

    assert 'не прошла валидацию' in view['text']
    assert 'need more details' in view['text']


def test_build_new_entry_success_text_includes_task_and_rewards():
    analysis = SimpleNamespace(mood_score=7, comment='c', recommendation='r')
    task = SimpleNamespace(title='T', description='D' * 10)

    text = build_new_entry_success_text(
        analysis_obj=analysis,
        suggested_task_obj=task,
        streak_bonus_info={'awarded': True, 'rewards': [(3, 5), (7, 10)]},
        language='ru',
    )

    assert '🎯' in text
    assert 'Поздравляем' in text


def test_build_new_entry_success_text_without_task_or_rewards():
    analysis = SimpleNamespace(mood_score=5, comment='c', recommendation='r')

    text = build_new_entry_success_text(
        analysis_obj=analysis,
        suggested_task_obj=None,
        streak_bonus_info={},
        language='ru',
    )

    assert isinstance(text, str)
    assert len(text) > 0


def test_build_clarification_questions_view_contains_numbered_questions():
    view = build_clarification_questions_view(
        ["Q1?", "Q2?"],
        language='ru',
    )

    assert '1. Q1?' in view['text']
    assert '2. Q2?' in view['text']
    assert view['reply_markup'].inline_keyboard[0][0].callback_data == 'main_menu'


@pytest.mark.asyncio
async def test_build_entry_saved_view_with_analysis(mocker):
    analysis = SimpleNamespace(mood_score=8, comment='ok', recommendation='keep going')
    entry = object()
    user = object()
    keyboard = object()

    mocker.patch(
        'diary.services.diary_display_service.diary_display_service.build_entry_result_keyboard',
        new=mocker.AsyncMock(return_value=keyboard),
    )

    view = await build_entry_saved_view(
        entry=entry,
        analysis=analysis,
        user=user,
        language='ru',
    )

    assert view['reply_markup'] is keyboard
    assert view['should_clear_state'] is True
    assert isinstance(view['text'], str)
    assert len(view['text']) > 0


@pytest.mark.asyncio
async def test_build_entry_saved_view_without_analysis():
    view = await build_entry_saved_view(
        entry=object(),
        analysis=None,
        user=object(),
        language='ru',
    )

    assert view['should_clear_state'] is True
    assert view['reply_markup'].inline_keyboard[0][0].callback_data == 'main_menu'
    assert isinstance(view['text'], str)

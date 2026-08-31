"""Тесты разметки all_entries для инкрементального анализа."""

import pytest

from bot.services.diary_service import DiaryService


@pytest.mark.asyncio
async def test_get_combined_entry_text_marks_last_as_new(mocker):
    service = DiaryService()
    entries = [
        mocker.Mock(text="тост на проводы"),
        mocker.Mock(text="идём в кино"),
    ]
    mocker.patch.object(
        service,
        'get_user_entries_for_date',
        new=mocker.AsyncMock(return_value=entries),
    )

    combined = await service.get_combined_entry_text(
        user=mocker.Mock(telegram_id=1),
        target_date=mocker.Mock(),
        mark_last_as_new=True,
        language='ru',
    )

    assert 'Запись 1:\nтост на проводы' in combined
    assert 'Запись 2 (новая):\nидём в кино' in combined


@pytest.mark.asyncio
async def test_get_combined_entry_text_without_new_marker(mocker):
    service = DiaryService()
    entries = [
        mocker.Mock(text="первая"),
        mocker.Mock(text="вторая"),
    ]

    combined = await service.get_combined_entry_text(
        user=mocker.Mock(telegram_id=1),
        target_date=mocker.Mock(),
        entries_list=entries,
        mark_last_as_new=False,
        language='en',
    )

    assert 'Entry 1:\nпервая' in combined
    assert 'Entry 2:\nвторая' in combined
    assert '(new)' not in combined

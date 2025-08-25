# tests/test_diary_handlers.py
"""
Тесты для обработчиков diary.py, включая инкрементальный анализ.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from django.test import TestCase
from django.utils import timezone
from asgiref.sync import sync_to_async
from datetime import datetime, date
import pytz

from aiogram import Dispatcher
from aiogram.types import Message, User as TgUser, Chat, Voice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage, EditMessageText

# Импортируем тестируемые компоненты
from bot.handlers.diary import (
    process_any_entry,
    _get_or_update_combined_entry,
    _perform_analysis,
    _handle_analysis_result,
    _get_user_profile_data,
    _get_user_local_datetime
)
from bot.states.diary_states import DiaryStates
from diary.models import DiaryEntry, CombinedDiaryEntry, PsychoAnalysis
from users.models import User
from bot.services.deepseek_api import DeepSeekAPIService


# Используем фикстуры pytest-django
@pytest.mark.django_db
class TestDiaryHandlers(TestCase):
    """Тесты для обработчиков diary.py."""

    def setUp(self):
        """Настройка тестового окружения."""
        # Создаем тестового пользователя Django
        self.django_user = User.objects.create(
            telegram_id=123456789,
            username="testuser",
            language='ru',
            timezone='Europe/Moscow'
        )
        # Создаем объект aiogram User
        self.tg_user = TgUser(id=self.django_user.telegram_id, is_bot=False, first_name="Test", username="testuser")
        self.chat = Chat(id=self.django_user.telegram_id, type="private")
        self.language = self.django_user.language

    def _create_message(self, text=None, voice=None):
        """Создание тестового сообщения."""
        msg = Message(
            message_id=1,
            date=timezone.now(),
            chat=self.chat,
            from_user=self.tg_user,
            text=text,
        )
        if voice:
            msg.voice = voice
        return msg

    @patch('bot.handlers.diary.deepseek_api_service')
    @patch('bot.handlers.diary.daily_state_service')
    @patch('bot.handlers.diary.diary_service')
    async def test_process_any_entry_first_text_entry(self, mock_diary_service, mock_daily_state_service, mock_deepseek_service):
        """Тест process_any_entry для первой текстовой записи дня."""
        # --- Подготовка ---
        # Мокаем FSMContext
        storage = MemoryStorage()
        fsm_context = FSMContext(storage=storage, key=("test", "test"))

        # Мокаем diary_service.create_text_entry
        mock_entry = AsyncMock(spec=DiaryEntry)
        mock_entry.id = 10
        mock_entry.entry_date = date.today()
        mock_diary_service.create_text_entry.return_value = mock_entry

        # Мокаем daily_state_service.get_daily_state -> None (первая запись)
        mock_daily_state_service.get_daily_state.return_value = None
        # Мокаем daily_state_service.create_daily_state_from_entry
        mock_combined_entry = AsyncMock(spec=CombinedDiaryEntry)
        mock_combined_entry.id = 20
        mock_daily_state_service.create_daily_state_from_entry.return_value = mock_combined_entry

        # Мокаем deepseek_api_service.analyze_text_with_profile (ожидаем вызов этого метода)
        mock_analysis_result = {
            'success': True,
            'result': {
                'mood_score': 7,
                'comment': 'Хорошее настроение',
                'recommendation': 'Продолжайте в том же духе',
                'analysis': 'Текст содержит позитив.',
                'needs_clarification': False,
                'suggested_task': None
            },
            'api_response': {'status': 200}
        }
        mock_deepseek_service.analyze_text_with_profile.return_value = mock_analysis_result

        # Мокаем diary_service.create_initial_analysis
        mock_psycho_analysis = AsyncMock(spec=PsychoAnalysis)
        mock_psycho_analysis.id = 30
        mock_diary_service.create_initial_analysis.return_value = mock_psycho_analysis

        # Мокаем daily_state_service.update_daily_state
        mock_daily_state_service.update_daily_state.return_value = True

        # Создаем тестовое текстовое сообщение
        test_text = "Это моя первая запись сегодня!"
        message = self._create_message(text=test_text)

        # --- Выполнение ---
        # Создаем мок для Message.answer, чтобы проверить отправку сообщения об обработке
        with patch.object(message, 'answer', new=AsyncMock()) as mock_answer:
            # Создаем мок для Message.bot.get_file и Message.bot.download_file для голоса (не используется, но патчим для полноты)
            with patch.object(message.bot, 'get_file', new=AsyncMock()), \
                 patch.object(message.bot, 'download_file', new=AsyncMock()):
                await process_any_entry(message, fsm_context, self.django_user, self.language)

        # --- Проверки ---
        # 1. Проверяем, что была создана текстовая запись
        mock_diary_service.create_text_entry.assert_awaited_once_with(
            user=self.django_user,
            text=test_text,
            language=self.language,
            entry_datetime=ANY # Проверяем, что дата передана, но не конкретное значение
        )

        # 2. Проверяем, что был запрос на получение CombinedDiaryEntry
        mock_daily_state_service.get_daily_state.assert_awaited_once_with(self.django_user, mock_entry.entry_date)

        # 3. Проверяем, что был создан новый CombinedDiaryEntry
        mock_daily_state_service.create_daily_state_from_entry.assert_awaited_once_with(mock_entry)

        # 4. Проверяем, что был вызван analyze_text_with_profile (так как это первая запись)
        profile_data = await _get_user_profile_data(self.django_user, self.language)
        mock_deepseek_service.analyze_text_with_profile.assert_awaited_once_with(
            text=test_text,
            user_profile=profile_data,
            language=self.language
        )

        # 5. Проверяем, что был создан PsychoAnalysis
        expected_analysis_data = mock_analysis_result['result']
        mock_diary_service.create_initial_analysis.assert_awaited_once_with(
            entry=mock_entry,
            mood_score=expected_analysis_data['mood_score'],
            comment=expected_analysis_data['comment'],
            recommendation=expected_analysis_data['recommendation'],
            analysis_text=expected_analysis_data['analysis'],
            api_response=mock_analysis_result['api_response']
        )

        # 6. Проверяем, что было обновлено состояние дня
        mock_daily_state_service.update_daily_state.assert_awaited_once_with(
            mock_combined_entry, expected_analysis_data['analysis'] # Предполагаем, что сохраняется analysis_text
        )

        # 7. Проверяем, что состояние FSM очищено
        current_state = await fsm_context.get_state()
        assert current_state is None

        # 8. Проверяем, что было отправлено сообщение об обработке, а затем финальный результат
        # (Точное тестирование редактирования сообщений сложнее без мока status_message)
        # Но мы можем проверить, что message.answer был вызван (для status_message)
        assert mock_answer.await_count >= 1 # Должно быть хотя бы одно сообщение

    @patch('bot.handlers.diary.deepseek_api_service')
    @patch('bot.handlers.diary.daily_state_service')
    @patch('bot.handlers.diary.diary_service')
    @patch('bot.handlers.diary.yandex_speechkit_service')
    async def test_process_any_entry_subsequent_voice_entry(self, mock_speechkit_service, mock_diary_service, mock_daily_state_service, mock_deepseek_service):
        """Тест process_any_entry для последующей голосовой записи дня."""
        # --- Подготовка ---
        storage = MemoryStorage()
        fsm_context = FSMContext(storage=storage, key=("test", "test"))

        # Мокаем diary_service.create_voice_entry
        mock_entry = AsyncMock(spec=DiaryEntry)
        mock_entry.id = 11
        mock_entry.entry_date = date.today()
        mock_diary_service.create_voice_entry.return_value = mock_entry

        # Мокаем daily_state_service.get_daily_state -> CombinedDiaryEntry (не первая запись)
        mock_combined_entry = AsyncMock(spec=CombinedDiaryEntry)
        mock_combined_entry.id = 21
        mock_combined_entry.ai_state_data = "Предыдущее состояние: настроение 6"
        mock_daily_state_service.get_daily_state.return_value = mock_combined_entry

        # Мокаем daily_state_service.update_daily_state_text_and_count
        mock_daily_state_service.update_daily_state_text_and_count.return_value = True

        # Мокаем diary_service.get_combined_entry_text
        mock_diary_service.get_combined_entry_text.return_value = "Объединенный текст"
        # Мокаем diary_service.get_user_entries_for_date
        mock_diary_service.get_user_entries_for_date.return_value = [mock_entry] # 1 запись

        # Мокаем yandex_speechkit_service.recognize_voice
        mock_recognition_result = {
            'success': True,
            'result': 'Распознанный текст из голоса',
        }
        mock_speechkit_service.recognize_voice.return_value = mock_recognition_result

        # Мокаем deepseek_api_service.punctuate_and_format_text
        mock_punctuation_result = {
            'success': True,
            'result': 'Отформатированный текст из голоса',
        }
        mock_deepseek_service.punctuate_and_format_text.return_value = mock_punctuation_result

        # Мокаем deepseek_api_service.analyze_text_with_previous_state (ожидаем вызов этого метода)
        mock_analysis_result = {
            'success': True,
            'result': {
                'mood_score': 8,
                'comment': 'Настроение улучшилось',
                'recommendation': 'Говорите больше о хороших вещах',
                'analysis': 'Новая запись показывает улучшение.',
                'needs_clarification': False,
                'suggested_task': None
            },
            'api_response': {'status': 200}
        }
        mock_deepseek_service.analyze_text_with_previous_state.return_value = mock_analysis_result

        # Мокаем diary_service.create_initial_analysis
        mock_psycho_analysis = AsyncMock(spec=PsychoAnalysis)
        mock_psycho_analysis.id = 31
        mock_diary_service.create_initial_analysis.return_value = mock_psycho_analysis

        # Мокаем daily_state_service.update_daily_state
        mock_daily_state_service.update_daily_state.return_value = True

        # Создаем тестовое голосовое сообщение
        test_voice = Voice(file_id="voice_file_id_123", duration=10, mime_type="audio/ogg")
        message = self._create_message(voice=test_voice)

        # --- Выполнение ---
        with patch.object(message, 'answer', new=AsyncMock()) as mock_answer:
            with patch.object(message.bot, 'get_file', new=AsyncMock()) as mock_get_file, \
                 patch.object(message.bot, 'download_file', new=AsyncMock()) as mock_download_file:
                
                # Настраиваем моки для скачивания файла
                mock_file_mock = AsyncMock()
                mock_file_mock.file_path = "path/to/voice.ogg"
                mock_get_file.return_value = mock_file_mock
                mock_download_file.return_value.read.return_value = b"fake_voice_data"

                await process_any_entry(message, fsm_context, self.django_user, self.language)

        # --- Проверки ---
        # 1. Проверяем, что была создана голосовая запись
        mock_diary_service.create_voice_entry.assert_awaited_once()
        call_args = mock_diary_service.create_voice_entry.await_args
        assert call_args.kwargs['user'] == self.django_user
        assert call_args.kwargs['voice_file_id'] == "voice_file_id_123"
        assert call_args.kwargs['duration'] == 10
        assert call_args.kwargs['recognized_text'] == 'Отформатированный текст из голоса' # После постобработки
        assert call_args.kwargs['language'] == self.language

        # 2. Проверяем, что был запрос на получение CombinedDiaryEntry
        mock_daily_state_service.get_daily_state.assert_awaited_once_with(self.django_user, mock_entry.entry_date)

        # 3. Проверяем, что текст и счетчик были обновлены (так как это не первая запись)
        mock_daily_state_service.update_daily_state_text_and_count.assert_awaited_once()

        # 4. Проверяем, что был вызван analyze_text_with_previous_state
        profile_data = await _get_user_profile_data(self.django_user, self.language)
        mock_deepseek_service.analyze_text_with_previous_state.assert_awaited_once_with(
            previous_state_context=mock_combined_entry.ai_state_data,
            new_text='Отформатированный текст из голоса',
            user_profile=profile_data,
            language=self.language
        )

        # 5. Проверяем, что был создан PsychoAnalysis
        expected_analysis_data = mock_analysis_result['result']
        mock_diary_service.create_initial_analysis.assert_awaited_once_with(
            entry=mock_entry,
            mood_score=expected_analysis_data['mood_score'],
            comment=expected_analysis_data['comment'],
            recommendation=expected_analysis_data['recommendation'],
            analysis_text=expected_analysis_data['analysis'],
            api_response=mock_analysis_result['api_response']
        )

        # 6. Проверяем, что было обновлено состояние дня
        mock_daily_state_service.update_daily_state.assert_awaited_once_with(
            mock_combined_entry, expected_analysis_data['analysis']
        )

        # 7. Проверяем, что состояние FSM очищено
        current_state = await fsm_context.get_state()
        assert current_state is None

    @patch('bot.handlers.diary.deepseek_api_service')
    async def test_perform_analysis_first_entry(self, mock_deepseek_service):
        """Тест _perform_analysis для первой записи."""
        is_first = True
        combined_entry = None # Не используется для первой записи
        text = "Тестовый текст"
        profile = {"username": "test"}
        lang = "ru"

        mock_result = {"success": True, "result": {"mood_score": 5}}
        mock_deepseek_service.analyze_text_with_profile.return_value = mock_result

        result = await _perform_analysis(is_first, combined_entry, text, profile, lang)

        mock_deepseek_service.analyze_text_with_profile.assert_awaited_once_with(
            text=text, user_profile=profile, language=lang
        )
        assert result == mock_result

    @patch('bot.handlers.diary.deepseek_api_service')
    async def test_perform_analysis_subsequent_entry(self, mock_deepseek_service):
        """Тест _perform_analysis для последующей записи."""
        is_first = False
        mock_combined_entry = AsyncMock()
        mock_combined_entry.ai_state_data = "Старое состояние"
        text = "Новый текст"
        profile = {"username": "test"}
        lang = "ru"

        mock_result = {"success": True, "result": {"mood_score": 7}}
        mock_deepseek_service.analyze_text_with_previous_state.return_value = mock_result

        result = await _perform_analysis(is_first, mock_combined_entry, text, profile, lang)

        mock_deepseek_service.analyze_text_with_previous_state.assert_awaited_once_with(
            previous_state_context=mock_combined_entry.ai_state_data,
            new_text=text,
            user_profile=profile,
            language=lang
        )
        assert result == mock_result

    @patch('bot.handlers.diary.deepseek_api_service')
    async def test_perform_analysis_subsequent_entry_empty_state(self, mock_deepseek_service):
        """Тест _perform_analysis для последующей записи с пустым состоянием."""
        is_first = False
        mock_combined_entry = AsyncMock()
        mock_combined_entry.ai_state_data = "" # Пустое состояние
        text = "Новый текст"
        profile = {"username": "test"}
        lang = "ru"

        mock_result = {"success": True, "result": {"mood_score": 6}}
        # Ожидаем вызов analyze_text_with_profile как fallback
        mock_deepseek_service.analyze_text_with_profile.return_value = mock_result

        result = await _perform_analysis(is_first, mock_combined_entry, text, profile, lang)

        mock_deepseek_service.analyze_text_with_profile.assert_awaited_once_with(
            text=text, user_profile=profile, language=lang
        )
        assert result == mock_result

    @patch('bot.handlers.diary.diary_service')
    @patch('bot.handlers.diary.daily_state_service')
    async def test_handle_analysis_result_clarification(self, mock_daily_state_service, mock_diary_service):
        """Тест _handle_analysis_result при необходимости уточнений."""
        # --- Подготовка ---
        mock_entry = AsyncMock()
        mock_entry.id = 99
        analysis_result = {
            'success': True,
            'result': {
                'needs_clarification': True,
                'clarification_questions': ['Вопрос 1?', 'Вопрос 2?']
            }
        }
        # Создаем мок для status_message
        mock_status_message = AsyncMock()
        language = 'ru'
        # Мокаем FSMContext
        storage = MemoryStorage()
        fsm_context = FSMContext(storage=storage, key=("test", "test"))
        user = self.django_user

        # --- Выполнение ---
        # patch внутри async функции требует особого подхода
        with patch('bot.handlers.diary.get_cancel_keyboard', return_value=MagicMock()) as mock_get_kb, \
             patch('bot.handlers.diary.get_message', return_value="Нужно уточнение:\n\n") as mock_get_msg:
            await _handle_analysis_result(mock_entry, analysis_result, mock_status_message, language, fsm_context, user)

        # --- Проверки ---
        # 1. Проверяем, что состояние FSM установлено в asking_clarifying_questions
        current_state = await fsm_context.get_state()
        assert current_state == DiaryStates.asking_clarifying_questions

        # 2. Проверяем, что данные состояния обновлены
        state_data = await fsm_context.get_data()
        assert state_data.get('clarifying_entry_id') == mock_entry.id
        assert state_data.get('clarification_questions') == analysis_result['result']['clarification_questions']

        # 3. Проверяем, что сообщение отредактировано с вопросами
        mock_status_message.edit_text.assert_awaited_once()
        edit_call_args = mock_status_message.edit_text.await_args
        assert "Нужно уточнение" in edit_call_args.args[0]
        assert "Вопрос 1?" in edit_call_args.args[0]
        assert "Вопрос 2?" in edit_call_args.args[0]

    # Тесты для вспомогательных функций
    def test_get_user_profile_data(self):
        """Тест _get_user_profile_data."""
        profile_data = asyncio.run(_get_user_profile_data(self.django_user, self.language))
        assert profile_data['username'] == self.django_user.username
        assert profile_data['first_name'] == self.django_user.first_name
        assert profile_data['language'] == self.django_user.language
        assert profile_data['awareness_level'] == self.django_user.awareness_level

    def test_get_user_local_datetime(self):
        """Тест _get_user_local_datetime."""
        local_dt = asyncio.run(_get_user_local_datetime(self.django_user))
        assert isinstance(local_dt, datetime)
        assert str(local_dt.tzinfo) == self.django_user.timezone # pytz.timezone возвращает объект с именем зоны


# Дополнительные тесты можно добавить для:
# - process_any_entry с ошибками (API, БД)
# - _handle_analysis_result без уточнений и с созданием PsychoAnalysis
# - _handle_analysis_result с suggested_task
# - _get_or_update_combined_entry
# - Обработки ошибок в _handle_analysis_result (например, исключения при создании PsychoAnalysis)
"""
Handlers для помощи и поддержки
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from messages import get_message
from bot.keyboards import (
    get_help_keyboard,
    get_help_section_keyboard,
    get_back_keyboard,
)
from bot.states.feedback_states import FeedbackStates
from bot.decorators.analytics_decorator import log_user_activity

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "help")
@router.message(Command("help"))
@log_user_activity('help_open')
async def show_help(event, language: str = 'ru'):
    try:
        help_msg = get_message('help_main_text', language=language)
        keyboard = get_help_keyboard(language)
        if isinstance(event, Message):
            await event.answer(
                help_msg,
                reply_markup=keyboard
            )
        else:
            await event.message.edit_text(
                help_msg,
                reply_markup=keyboard
            )
            await event.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ: {e}", exc_info=True)
        if isinstance(event, CallbackQuery):
            await event.answer("Ошибка при показе помощи")
        elif isinstance(event, Message):
            await event.answer("Ошибка при показе помощи")

@router.callback_query(F.data == "help_faq")
@log_user_activity('help_open', metadata_extra={'context': 'FAQ'})
async def show_faq(callback: CallbackQuery, language: str = 'ru'):
    try:
        faq_msg = get_message('help_faq_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            faq_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ FAQ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе FAQ")

@router.callback_query(F.data == "help_how_to_start")
@log_user_activity('help_open', metadata_extra={'context': 'Как начать'})
async def show_how_to_start(callback: CallbackQuery, language: str = 'ru'):
    try:
        how_to_start_msg = get_message('help_how_to_start_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            how_to_start_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО НАЧАЛУ РАБОТЫ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по началу работы")

@router.callback_query(F.data == "help_writing_entries")
@log_user_activity('help_open', metadata_extra={'context': 'Написание записей'})
async def show_writing_entries_help(callback: CallbackQuery, language: str = 'ru'):
    try:
        writing_entries_msg = get_message('help_writing_entries_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            writing_entries_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО НАПИСАНИЮ ЗАПИСЕЙ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по написанию записей")

@router.callback_query(F.data == "help_tasks")
@log_user_activity('help_open', metadata_extra={'context': 'Задания'})
async def show_tasks_help(callback: CallbackQuery, language: str = 'ru'):
    try:
        tasks_help_msg = get_message('help_tasks_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            tasks_help_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ЗАДАНИЯМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по заданиям")

@router.callback_query(F.data == "help_privacy")
@log_user_activity('help_open', metadata_extra={'context': 'Приватность'})
async def show_privacy_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по приватности"""
    try:
        privacy_help_msg = get_message('help_privacy_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            privacy_help_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ПРИВАТНОСТИ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по приватности")

@router.callback_query(F.data == "help_contact")
@log_user_activity('help_open', metadata_extra={'context': 'Контакты'})
async def show_contact_help(callback: CallbackQuery, language: str = 'ru'):
    """Контактная помощь"""
    try:
        contact_help_msg = get_message('help_contact_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            contact_help_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ КОНТАКТНОЙ ПОМОЩИ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе контактной помощи")

@router.callback_query(F.data == "help_subscription_and_tokens")
@log_user_activity('help_open', metadata_extra={'context': 'Подписка и токены'})
async def show_subscription_and_tokens_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по подписке и токенам"""
    try:
        subscription_help_msg = get_message('help_subscription_and_tokens_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            subscription_help_msg,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ПОДПИСКЕ И ТОКЕНАМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по подписке и токенам")

@router.callback_query(F.data == "help_guide")
@log_user_activity('help_open', metadata_extra={'context': 'Руководство'})
async def show_guide_menu(callback: CallbackQuery, language: str = 'ru'):
    """Показывает подменю руководства"""
    try:
        guide_msg = get_message('help_guide_text', language=language)
        # Импортируем новую клавиатуру
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            guide_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОДМЕНЮ РУКОВОДСТВА: {e}", exc_info=True)
        await callback.answer("Ошибка при показе подменю руководства")

@router.callback_query(F.data == "help_guide_writing_entries")
async def show_guide_writing_entries(callback: CallbackQuery, language: str = 'ru'):
    """Показывает руководство по написанию записей"""
    try:
        writing_entries_msg = get_message('help_writing_entries_text', language=language) # Используем существующий текст
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard # Клавиатура возврата к подменю руководства
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            writing_entries_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ РУКОВОДСТВА ПО НАПИСАНИЮ ЗАПИСЕЙ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе руководства по написанию записей")

@router.callback_query(F.data == "help_referral_program")
@log_user_activity('help_open', metadata_extra={'context': 'Реферальная программа'})
async def show_referral_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по реферальной программе"""
    try:
        referral_help_msg = get_message('help_referral_program_text', language=language)
        # Используем клавиатуру для отдельных разделов помощи
        from bot.keyboards.help_keyboard import get_help_section_keyboard
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            referral_help_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО РЕФЕРАЛЬНОЙ ПРОГРАММЕ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по реферальной программе")


@router.callback_query(F.data == "help_account_merge")
@log_user_activity('help_open', metadata_extra={'context': 'Объединение аккаунтов'})
async def show_account_merge_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по объединению аккаунтов Telegram/MAX."""
    try:
        merge_help_msg = get_message('help_account_merge_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(merge_help_msg, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе помощи по объединению аккаунтов: {e}", exc_info=True)
        await callback.answer("Ошибка при показе раздела")


@router.callback_query(F.data == "help_support")
@log_user_activity('help_open', metadata_extra={'context': 'Техподдержка'})
async def help_support_callback(callback: CallbackQuery, state: FSMContext, language: str = 'ru'):
    """Кнопка техподдержки — тот же сценарий, что /feedback и /support."""
    try:
        await callback.message.answer(
            get_message('feedback', language),
            reply_markup=get_back_keyboard(language),
        )
        await state.set_state(FeedbackStates.waiting_message)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запуске техподдержки из помощи: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language), show_alert=True)


@router.callback_query(F.data == "help_guide_tasks")
@log_user_activity('help_open', metadata_extra={'context': 'Руководство: задания'})
async def show_guide_tasks(callback: CallbackQuery, language: str = 'ru'):
    """Показывает руководство по заданиям"""
    try:
        tasks_help_msg = get_message('help_tasks_text', language=language) # Используем существующий текст
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            tasks_help_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ РУКОВОДСТВА ПО ЗАДАНИЯМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе руководства по заданиям")

@router.callback_query(F.data == "help_guide_progress")
@log_user_activity('help_open', metadata_extra={'context': 'Прогресс'})
async def show_guide_progress(callback: CallbackQuery, language: str = 'ru'):
    """Показывает руководство по прогрессу"""
    try:
        progress_help_msg = get_message('help_progress_text', language=language) # Используем существующий текст
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            progress_help_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ РУКОВОДСТВА ПО ПРОГРЕССУ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе руководства по прогрессу")

@router.callback_query(F.data == "help_guide_profile")
@log_user_activity('help_open', metadata_extra={'context': 'Профиль'})
async def show_guide_profile(callback: CallbackQuery, language: str = 'ru'):
    """Показывает руководство по профилю"""
    try:
        profile_help_msg = get_message('help_profile_text', language=language) # Используем существующий текст
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            profile_help_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ РУКОВОДСТВА ПО ПРОФИЛЮ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе руководства по профилю")

@router.callback_query(F.data == "help_guide_settings")
@log_user_activity('help_open', metadata_extra={'context': 'Настройки'})
async def show_guide_settings(callback: CallbackQuery, language: str = 'ru'):
    """Показывает руководство по настройкам"""
    try:
        settings_help_msg = get_message('help_settings_text', language=language) # Используем существующий текст
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            settings_help_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ РУКОВОДСТВА ПО НАСТРОЙКАМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе руководства по настройкам")

@router.callback_query(F.data == "help_guide_therapy_chat")
@log_user_activity('help_open', metadata_extra={'context': 'Чат'})
async def show_guide_therapy_chat(callback: CallbackQuery, language: str = 'ru'):
    """Показывает руководство по чату с психологом"""
    try:
        chat_help_msg = get_message('help_therapy_chat_text', language=language) # Используем существующий текст
        from bot.keyboards.help_keyboard import get_help_guide_section_keyboard
        keyboard = get_help_guide_section_keyboard(language)
        await callback.message.edit_text(
            chat_help_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ РУКОВОДСТВА ПО ЧАТУ С ПСИХОЛОГОМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе руководства по чату с психологом")

@router.callback_query(F.data == "help_back_to_main")
async def back_to_main_help(callback: CallbackQuery, language: str):
    """Возврат к основной помощи"""
    try:
        help_msg = get_message('help_text', language=language)
        await callback.message.edit_text(
            help_msg,
            reply_markup=get_help_keyboard(language)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при возврате к основной помощи: {e}")
        await callback.answer(get_message('error_generic', language=language))


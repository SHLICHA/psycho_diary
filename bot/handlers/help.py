"""
Handlers для помощи и поддержки
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from messages import get_message
from bot.keyboards import (
    get_help_keyboard,
    get_help_section_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "help")
@router.message(Command("help"))
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

#TODO сообщения для en. Объединить?
@router.callback_query(F.data == "help_faq")
async def show_faq(callback: CallbackQuery, language: str = 'ru'):
    try:
        faq_msg = get_message('help_faq_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            faq_msg,
            reply_markup=keyboard
        )
        await callback.answer("FAQ показан")
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ FAQ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе FAQ")

#TODO сообщения для en. Объединить?
@router.callback_query(F.data == "help_how_to_start")
async def show_how_to_start(callback: CallbackQuery, language: str = 'ru'):
    try:
        how_to_start_msg = get_message('help_how_to_start_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            how_to_start_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по началу работы показана")
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО НАЧАЛУ РАБОТЫ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по началу работы")

#TODO сообщения для en. Объединить?
@router.callback_query(F.data == "help_writing_entries")
async def show_writing_entries_help(callback: CallbackQuery, language: str = 'ru'):
    try:
        writing_entries_msg = get_message('help_writing_entries_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            writing_entries_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по написанию записей показана")
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО НАПИСАНИЮ ЗАПИСЕЙ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по написанию записей")

#TODO сообщения для en. Объединить?
@router.callback_query(F.data == "help_tasks")
async def show_tasks_help(callback: CallbackQuery, language: str = 'ru'):
    try:
        tasks_help_msg = get_message('help_tasks_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            tasks_help_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по заданиям показана")
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ЗАДАНИЯМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по заданиям")

#TODO сообщения для en. Объединить?
@router.callback_query(F.data == "help_privacy")
async def show_privacy_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по приватности"""
    try:
        privacy_help_msg = get_message('help_privacy_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            privacy_help_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по приватности показана")
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ПРИВАТНОСТИ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по приватности")

#TODO сообщения для en. Объединить? Нужен?
@router.callback_query(F.data == "help_contact")
async def show_contact_help(callback: CallbackQuery, language: str = 'ru'):
    """Контактная помощь"""
    try:
        # ИЗМЕНЕН КЛЮЧ - добавлен _text
        contact_help_msg = get_message('help_contact_text', language=language)
        keyboard = get_help_section_keyboard(language)
        await callback.message.edit_text(
            contact_help_msg,
            reply_markup=keyboard
        )
        await callback.answer("Контактная помощь показана")
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ КОНТАКТНОЙ ПОМОЩИ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе контактной помощи")

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

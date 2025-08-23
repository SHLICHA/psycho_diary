"""
Handlers для помощи и поддержки
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from messages import get_message
from bot.keyboards.help_keyboard import (
    get_help_keyboard,
    get_help_section_keyboard
)

# Создаем роутер для этого модуля
router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "help")
@router.message(Command("help"))
async def show_help(event, language: str = 'ru'):
    """Показ помощи"""
    logger.info(f"=== НАЧАЛО ПОКАЗА ПОМОЩИ ===")
    logger.info(f"Пользователь ID: {event.from_user.id}")
    logger.info(f"Язык: {language}")
    logger.info(f"Тип события: {type(event).__name__}")
    
    try:
        # Используем правильный ключ с _text
        help_msg = get_message('help_main_text', language=language)
        logger.info(f"Основное сообщение помощи получено, длина: {len(help_msg)} символов")
        
        keyboard = get_help_keyboard(language)
        logger.info(f"Основная клавиатура помощи создана, кнопок: {len(keyboard.inline_keyboard)}")
        
        # Определяем тип события
        if isinstance(event, Message):
            # Для команды /help
            logger.info("Отправка помощи через команду...")
            await event.answer(
                help_msg,
                reply_markup=keyboard
            )
            logger.info("Помощь успешно отправлена через команду")
        else:
            # Для callback
            logger.info("Отправка помощи через callback...")
            await event.message.edit_text(
                help_msg,
                reply_markup=keyboard
            )
            await event.answer()
            logger.info("Помощь успешно отправлена через callback")
        
        logger.info("=== ПОМОЩЬ УСПЕШНО ПОКАЗАНА ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ: {e}", exc_info=True)
        if isinstance(event, CallbackQuery):
            await event.answer("Ошибка при показе помощи")
        elif isinstance(event, Message):
            await event.answer("Ошибка при показе помощи")

@router.callback_query(F.data == "help_faq")
async def show_faq(callback: CallbackQuery, language: str = 'ru'):
    """Показ FAQ"""
    logger.info(f"=== ПОКАЗ FAQ ===")
    logger.info(f"Пользователь ID: {callback.from_user.id}")
    logger.info(f"Язык: {language}")
    
    try:
        # ИЗМЕНЕН КЛЮЧ
        faq_msg = get_message('help_faq_text', language=language)
        logger.info(f"Сообщение FAQ получено, длина: {len(faq_msg)} символов")
        
        keyboard = get_help_section_keyboard(language)
        logger.info(f"Клавиатура раздела создана")
        
        await callback.message.edit_text(
            faq_msg,
            reply_markup=keyboard
        )
        await callback.answer("FAQ показан")
        logger.info("=== FAQ УСПЕШНО ПОКАЗАН ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ FAQ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе FAQ")

@router.callback_query(F.data == "help_how_to_start")
async def show_how_to_start(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по началу работы"""
    logger.info(f"=== ПОКАЗ ПОМОЩИ ПО НАЧАЛУ РАБОТЫ ===")
    logger.info(f"Пользователь ID: {callback.from_user.id}")
    logger.info(f"Язык: {language}")
    
    try:
        # ИЗМЕНЕН КЛЮЧ
        how_to_start_msg = get_message('help_how_to_start_text', language=language)
        logger.info(f"Сообщение помощи по началу работы получено, длина: {len(how_to_start_msg)} символов")
        
        keyboard = get_help_section_keyboard(language)
        logger.info(f"Клавиатура раздела создана")
        
        await callback.message.edit_text(
            how_to_start_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по началу работы показана")
        logger.info("=== ПОМОЩЬ ПО НАЧАЛУ РАБОТЫ УСПЕШНО ПОКАЗАНА ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО НАЧАЛУ РАБОТЫ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по началу работы")

@router.callback_query(F.data == "help_writing_entries")
async def show_writing_entries_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по написанию записей"""
    logger.info(f"=== ПОКАЗ ПОМОЩИ ПО НАПИСАНИЮ ЗАПИСЕЙ ===")
    logger.info(f"Пользователь ID: {callback.from_user.id}")
    logger.info(f"Язык: {language}")
    
    try:
        # ИЗМЕНЕН КЛЮЧ - добавлен _text
        writing_entries_msg = get_message('help_writing_entries_text', language=language)
        logger.info(f"Сообщение помощи по написанию записей получено, длина: {len(writing_entries_msg)} символов")
        
        keyboard = get_help_section_keyboard(language)
        logger.info(f"Клавиатура раздела создана")
        
        await callback.message.edit_text(
            writing_entries_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по написанию записей показана")
        logger.info("=== ПОМОЩЬ ПО НАПИСАНИЮ ЗАПИСЕЙ УСПЕШНО ПОКАЗАНА ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО НАПИСАНИЮ ЗАПИСЕЙ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по написанию записей")

@router.callback_query(F.data == "help_tasks")
async def show_tasks_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по заданиям"""
    logger.info(f"=== ПОКАЗ ПОМОЩИ ПО ЗАДАНИЯМ ===")
    logger.info(f"Пользователь ID: {callback.from_user.id}")
    logger.info(f"Язык: {language}")
    
    try:
        # ИЗМЕНЕН КЛЮЧ - добавлен _text
        tasks_help_msg = get_message('help_tasks_text', language=language)
        logger.info(f"Сообщение помощи по заданиям получено, длина: {len(tasks_help_msg)} символов")
        
        keyboard = get_help_section_keyboard(language)
        logger.info(f"Клавиатура раздела создана")
        
        await callback.message.edit_text(
            tasks_help_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по заданиям показана")
        logger.info("=== ПОМОЩЬ ПО ЗАДАНИЯМ УСПЕШНО ПОКАЗАНА ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ЗАДАНИЯМ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по заданиям")

@router.callback_query(F.data == "help_privacy")
async def show_privacy_help(callback: CallbackQuery, language: str = 'ru'):
    """Помощь по приватности"""
    logger.info(f"=== ПОКАЗ ПОМОЩИ ПО ПРИВАТНОСТИ ===")
    logger.info(f"Пользователь ID: {callback.from_user.id}")
    logger.info(f"Язык: {language}")
    
    try:
        # ИЗМЕНЕН КЛЮЧ - добавлен _text
        privacy_help_msg = get_message('help_privacy_text', language=language)
        logger.info(f"Сообщение помощи по приватности получено, длина: {len(privacy_help_msg)} символов")
        
        keyboard = get_help_section_keyboard(language)
        logger.info(f"Клавиатура раздела создана")
        
        await callback.message.edit_text(
            privacy_help_msg,
            reply_markup=keyboard
        )
        await callback.answer("Помощь по приватности показана")
        logger.info("=== ПОМОЩЬ ПО ПРИВАТНОСТИ УСПЕШНО ПОКАЗАНА ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ ПОМОЩИ ПО ПРИВАТНОСТИ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе помощи по приватности")

@router.callback_query(F.data == "help_contact")
async def show_contact_help(callback: CallbackQuery, language: str = 'ru'):
    """Контактная помощь"""
    logger.info(f"=== ПОКАЗ КОНТАКТНОЙ ПОМОЩИ ===")
    logger.info(f"Пользователь ID: {callback.from_user.id}")
    logger.info(f"Язык: {language}")
    
    try:
        # ИЗМЕНЕН КЛЮЧ - добавлен _text
        contact_help_msg = get_message('help_contact_text', language=language)
        logger.info(f"Контактное сообщение помощи получено, длина: {len(contact_help_msg)} символов")
        
        keyboard = get_help_section_keyboard(language)
        logger.info(f"Клавиатура раздела создана")
        
        await callback.message.edit_text(
            contact_help_msg,
            reply_markup=keyboard
        )
        await callback.answer("Контактная помощь показана")
        logger.info("=== КОНТАКТНАЯ ПОМОЩЬ УСПЕШНО ПОКАЗАНА ===")
        
    except Exception as e:
        logger.error(f"!!! ОШИБКА ПРИ ПОКАЗЕ КОНТАКТНОЙ ПОМОЩИ: {e}", exc_info=True)
        await callback.answer("Ошибка при показе контактной помощи")

@router.callback_query(F.data == "help_back_to_main")
async def back_to_main_help(callback: CallbackQuery, language: str):
    """Возврат к основной помощи"""
    logger.info(f"Возврат к основной помощи для пользователя {callback.from_user.id}")
    
    try:
        help_msg = get_message('help_text', language=language)
        
        await callback.message.edit_text(
            help_msg,
            reply_markup=get_help_keyboard(language)
        )
        await callback.answer()
        logger.info("Возврат к основной помощи")
        
    except Exception as e:
        logger.error(f"Ошибка при возврате к основной помощи: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: CallbackQuery, user, language: str):
    """Возврат к списку заданий"""
    logger.info(f"Возврат к списку заданий для пользователя {callback.from_user.id}")
    
    try:
        # Получаем активные задания пользователя
        from bot.services.task_service import task_service
        active_tasks = await task_service.get_user_active_tasks(user)
        
        if active_tasks:
            # Показываем первое активное задание с пагинацией
            first_task = active_tasks[0]
            
            from messages import get_message
            task_msg = get_message(
                'task_assigned',
                language,
                title=first_task.title,
                description=first_task.description
            )
            
            # Проверяем, отличается ли новое сообщение от текущего
            if callback.message.text != task_msg:
                # ИСПРАВЛЕНО: используем клавиатуру с пагинацией
                from bot.keyboards.tasks_keyboard import get_task_pagination_keyboard
                await callback.message.edit_text(
                    task_msg,
                    reply_markup=get_task_pagination_keyboard(
                        task_id=first_task.id,
                        current_index=0,
                        total_tasks=len(active_tasks),
                        language=language
                    )
                )
                logger.info(f"Показано первое задание из {len(active_tasks)}")
            else:
                logger.info("Сообщение не изменилось, обновляем только клавиатуру")
                try:
                    # Если сообщение такое же, обновляем только клавиатуру
                    from bot.keyboards.tasks_keyboard import get_task_pagination_keyboard
                    await callback.message.edit_reply_markup(
                        reply_markup=get_task_pagination_keyboard(
                            task_id=first_task.id,
                            current_index=0,
                            total_tasks=len(active_tasks),
                            language=language
                        )
                    )
                except Exception as keyboard_error:
                    logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                    # Если не удалось обновить клавиатуру, отправляем новое сообщение
                    from bot.keyboards.tasks_keyboard import get_task_pagination_keyboard
                    await callback.message.edit_text(
                        task_msg,
                        reply_markup=get_task_pagination_keyboard(
                            task_id=first_task.id,
                            current_index=0,
                            total_tasks=len(active_tasks),
                            language=language
                        )
                    )
        else:
            # Нет активных заданий
            from messages import get_message
            no_task_msg = get_message('task_no_active', language)
            
            # Проверяем, отличается ли новое сообщение от текущего
            if callback.message.text != no_task_msg:
                from bot.keyboards.main_menu import get_back_keyboard
                await callback.message.edit_text(
                    no_task_msg,
                    reply_markup=get_back_keyboard(language)
                )
            else:
                try:
                    from bot.keyboards.main_menu import get_back_keyboard
                    await callback.message.edit_reply_markup(
                        reply_markup=get_back_keyboard(language)
                    )
                except Exception as keyboard_error:
                    logger.warning(f"Не удалось обновить клавиатуру: {keyboard_error}")
                    # Если не удалось обновить клавиатуру, отправляем новое сообщение
                    from bot.keyboards.main_menu import get_back_keyboard
                    await callback.message.edit_text(
                        no_task_msg,
                        reply_markup=get_back_keyboard(language)
                    )
            
            logger.info("Нет активных заданий")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку заданий: {e}")
        from messages import get_message
        await callback.answer(get_message('error_generic', language))
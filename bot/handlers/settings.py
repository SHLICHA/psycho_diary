"""
Handlers для работы с настройками
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from messages import get_message, get_button_text
from bot.states.settings_states import SettingsStates
from bot.keyboards.help_keyboard import get_help_keyboard
from bot.keyboards.settings_keyboard import (
    get_settings_keyboard,
    get_language_selection_keyboard,
    get_premium_keyboard,
)
from bot.keyboards import get_back_keyboard, get_main_menu_keyboard, get_common_timezones_keyboard, get_timezone_selection_method_keyboard
from bot.utils.state_manager import state_manager

# Создаем роутер для этого модуля
router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery, user, language: str):
    """Показ настроек"""
    logger.info(f"Показ настроек для пользователя {callback.from_user.id}")
    
    try:
        settings_msg = get_message('settings_menu', language=language)
        
        await callback.message.edit_text(
            settings_msg,
            reply_markup=get_settings_keyboard(user, language)
        )
        await callback.answer()
        logger.info("Показаны настройки пользователя")
        
    except Exception as e:
        logger.error(f"Ошибка при показе настроек: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_change_language")
async def change_language(callback: CallbackQuery, state: FSMContext, language: str):
    """Изменение языка"""
    logger.info(f"Изменение языка для пользователя {callback.from_user.id}")
    
    try:
        # Устанавливаем состояние ожидания выбора языка
        await state_manager.set_state(state, SettingsStates.waiting_for_language_choice)
        
        language_msg = get_message('settings_menu', language=language)
        
        await callback.message.edit_text(
            language_msg,
            reply_markup=get_language_selection_keyboard(language)
        )
        await callback.answer()
        logger.info("Показан выбор языка")
        
    except Exception as e:
        logger.error(f"Ошибка при показе выбора языка: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("set_language:"))
async def set_language(callback: CallbackQuery, user, state: FSMContext, language: str):
    """Установка языка"""
    logger.info(f"Установка языка для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем язык из callback_data
        new_language = callback.data.split(":")[1]
        logger.info(f"Установка языка: {new_language}")
        
        # Проверяем, поддерживается ли язык
        supported_languages = ['ru', 'en']
        if new_language not in supported_languages:
            logger.warning(f"Неподдерживаемый язык: {new_language}")
            await callback.answer(get_message('error_generic', language=language))
            return
        
        # Обновляем язык пользователя в базе данных
        user.language = new_language
        await user.asave(update_fields=['language'])
        logger.info(f"Язык пользователя обновлен на: {new_language}")
        
        # Очищаем состояние
        await state_manager.clear_state(state)
        
        # Отправляем сообщение об успешной смене языка
        success_msg = get_message('language_changed', language=new_language)
        
        # Проверяем, отличается ли новое сообщение от текущего
        if callback.message.text != success_msg:
            await callback.message.edit_text(
                success_msg,
                reply_markup=get_settings_keyboard(user, new_language)
            )
        else:
            # Если сообщение такое же, просто обновляем клавиатуру
            try:
                await callback.message.edit_reply_markup(
                    reply_markup=get_settings_keyboard(user, new_language)
                )
            except Exception as e:
                logger.warning(f"Не удалось обновить клавиатуру: {e}")
                # Если не удалось обновить клавиатуру, отправляем новое сообщение
                await callback.message.edit_text(
                    success_msg,
                    reply_markup=get_settings_keyboard(user, new_language)
                )
        
        await callback.answer()
        logger.info("Язык успешно изменен")
        
    except Exception as e:
        logger.error(f"Ошибка при установке языка: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_toggle_notifications")
async def toggle_notifications(callback: CallbackQuery, user, language: str):
    """Переключение уведомлений"""
    logger.info(f"Переключение уведомлений для пользователя {callback.from_user.id}")
    
    try:
        # Получаем текущее состояние уведомлений
        current_state = user.notifications_enabled
        logger.info(f"Текущее состояние уведомлений: {current_state}")
        
        # Переключаем состояние
        new_state = not current_state
        user.notifications_enabled = new_state
        
        # Сохраняем изменения в базе данных
        await user.asave(update_fields=['notifications_enabled'])
        logger.info(f"Новое состояние уведомлений: {new_state} (сохранено в БД)")
        
        # Формируем сообщение
        if new_state:
            toggle_msg = get_message('notifications_enabled', language=language)
        else:
            toggle_msg = get_message('notifications_disabled', language=language)
        
        await callback.answer(toggle_msg)
        
        # Создаем новую клавиатуру с обновленным состоянием
        new_keyboard = get_settings_keyboard(user, language)
        
        # Проверяем, отличается ли новая клавиатура от текущей
        # Всегда обновляем клавиатуру, так как состояние изменилось
        try:
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
            logger.info("Клавиатура уведомлений успешно обновлена")
        except Exception as e:
            logger.warning(f"Не удалось обновить клавиатуру напрямую: {e}")
            # Если не удалось обновить клавиатуру, отправляем новое сообщение
            settings_msg = get_message('settings_menu', language=language)
            await callback.message.edit_text(
                settings_msg,
                reply_markup=new_keyboard
            )
            logger.info("Клавиатура уведомлений обновлена через новое сообщение")
        
    except Exception as e:
        logger.error(f"Ошибка при переключении уведомлений: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_toggle_auto_analysis")
async def toggle_auto_analysis(callback: CallbackQuery, user, language: str):
    """Переключение автоанализа"""
    logger.info(f"Переключение автоанализа для пользователя {callback.from_user.id}")
    
    try:
        # Получаем текущее состояние автоанализа
        current_state = user.auto_analysis_enabled
        logger.info(f"Текущее состояние автоанализа: {current_state}")
        
        # Переключаем состояние
        new_state = not current_state
        user.auto_analysis_enabled = new_state
        
        # Сохраняем изменения в базе данных
        await user.asave(update_fields=['auto_analysis_enabled'])
        logger.info(f"Новое состояние автоанализа: {new_state} (сохранено в БД)")
        
        # Формируем сообщение
        if new_state:
            toggle_msg = get_message('settings_auto_analysis', language=language).format(
                status=get_message('status_enabled', language=language)
            )
        else:
            toggle_msg = get_message('settings_auto_analysis', language=language).format(
                status=get_message('status_disabled', language=language)
            )
        
        await callback.answer(toggle_msg)
        
        # Создаем новую клавиатуру с обновленным состоянием
        new_keyboard = get_settings_keyboard(user, language)
        
        # Проверяем, отличается ли новая клавиатура от текущей
        # Всегда обновляем клавиатуру, так как состояние изменилось
        try:
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
            logger.info("Клавиатура автоанализа успешно обновлена")
        except Exception as e:
            logger.warning(f"Не удалось обновить клавиатуру напрямую: {e}")
            # Если не удалось обновить клавиатуру, отправляем новое сообщение
            settings_msg = get_message('settings_menu', language=language)
            await callback.message.edit_text(
                settings_msg,
                reply_markup=new_keyboard
            )
            logger.info("Клавиатура автоанализа обновлена через новое сообщение")
        
    except Exception as e:
        logger.error(f"Ошибка при переключении автоанализа: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_premium")
async def show_premium(callback: CallbackQuery, user, language: str):
    """Показ премиум функций"""
    logger.info(f"Показ премиум функций для пользователя {callback.from_user.id}")
    
    try:
        if user.is_premium:
            # Пользователь уже имеет премиум
            premium_msg = get_message('settings_premium', language=language).format(
                status=get_message('status_enabled', language=language)
            )
        else:
            # Пользователь не имеет премиум
            premium_msg = get_message('premium_benefits', language=language)
        
        await callback.message.edit_text(
            premium_msg,
            reply_markup=get_premium_keyboard(language)
        )
        await callback.answer()
        logger.info("Показаны премиум функции")
        
    except Exception as e:
        logger.error(f"Ошибка при показе премиум функций: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "premium_subscribe")
async def premium_subscribe(callback: CallbackQuery, user, language: str):
    """Подписка на премиум"""
    logger.info(f"Подписка на премиум для пользователя {callback.from_user.id}")
    
    try:
        # Здесь будет логика подписки на премиум
        # Пока заглушка
        
        subscribe_msg = "💳 Для подписки на премиум функции свяжитесь с администратором"
        
        await callback.message.edit_text(
            subscribe_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
        logger.info("Показана информация о подписке")
        
    except Exception as e:
        logger.error(f"Ошибка при подписке на премиум: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "premium_trial")
async def premium_trial(callback: CallbackQuery, user, language: str):
    """Пробный период премиум"""
    logger.info(f"Пробный период премиум для пользователя {callback.from_user.id}")
    
    try:
        # Здесь будет логика пробного периода
        # Пока заглушка
        
        trial_msg = "🎁 Пробный период премиум функций активирован на 7 дней!"
        
        # Обновляем статус пользователя (в реальной реализации)
        # user.is_premium = True
        # await user.asave(update_fields=['is_premium'])
        
        await callback.message.edit_text(
            trial_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
        logger.info("Активирован пробный период")
        
    except Exception as e:
        logger.error(f"Ошибка при активации пробного периода: {e}")
        await callback.answer(get_message('error_generic', language=language))

# ==================== ВСПОМОГАТЕЛЬНЫЕ HANDLERS ====================

@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery, language: str):
    """Показ помощи"""
    logger.info(f"Показ помощи для пользователя {callback.from_user.id}")
    
    try:
        help_msg = get_message('help_text', language=language)
        
        await callback.message.edit_text(
            help_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
        logger.info("Показана помощь")
        
    except Exception as e:
        logger.error(f"Ошибка при показе помощи: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "user_profile")
async def show_user_profile(callback: CallbackQuery, user, language: str):
    """Показ профиля пользователя"""
    logger.info(f"Показ профиля для пользователя {callback.from_user.id}")
    
    try:
        # Создаем сообщение с профилем пользователя
        from datetime import datetime
        
        profile_msg = f"""👤 <b>Ваш профиль</b>

🆔 <b>ID:</b> {user.telegram_id}
📝 <b>Имя пользователя:</b> @{user.username if user.username else 'Не указан'}
👤 <b>Имя:</b> {user.first_name if user.first_name else 'Не указано'}
👥 <b>Фамилия:</b> {user.last_name if user.last_name else 'Не указана'}
🌍 <b>Язык:</b> {'Русский' if user.language == 'ru' else 'English'}
🔔 <b>Уведомления:</b> {'Включены' if user.notifications_enabled else 'Выключены'}
📈 <b>Автоанализ:</b> {'Включен' if user.auto_analysis_enabled else 'Выключен'}
👑 <b>Премиум:</b> {'Да' if user.is_premium else 'Нет'}
📊 <b>Уровень осознанности:</b> {user.awareness_level}/10
📅 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Не указана'}
📝 <b>Последняя запись:</b> {user.last_entry.strftime('%d.%m.%Y %H:%M') if user.last_entry else 'Нет записей'}
"""
        
        await callback.message.edit_text(
            profile_msg,
            reply_markup=get_back_keyboard(language)
        )
        await callback.answer()
        logger.info("Показан профиль пользователя")
        
    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "settings_change_timezone")
async def change_timezone(callback: CallbackQuery, user, language: str):
    """Начало изменения часового пояса"""
    logger.info(f"Начало изменения часового пояса для пользователя {callback.from_user.id}")
    
    try:
        # Формируем сообщение с предложением способа выбора
        timezone_msg = get_message('ask_timezone_selection', language, current_timezone=user.timezone)
        
        # Получаем клавиатуру выбора способа
        from bot.keyboards.settings_keyboard import get_timezone_selection_method_keyboard
        reply_markup = get_timezone_selection_method_keyboard(language, user.timezone)
        
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
        logger.info("Показаны варианты выбора часового пояса")
        
    except Exception as e:
        logger.error(f"Ошибка при показе вариантов выбора часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "timezone_select_from_list")
async def select_timezone_from_list(callback: CallbackQuery, user, language: str):
    """Выбор часового пояса из списка"""
    logger.info(f"Выбор часового пояса из списка для пользователя {callback.from_user.id}")
    
    try:
        # Формируем сообщение со списком
        timezone_msg = get_message('select_timezone_title', language, current_timezone=user.timezone)
        
        # Получаем клавиатуру со списком
        reply_markup = get_common_timezones_keyboard(language, user.timezone)
        
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        await callback.answer()
        logger.info("Показан список популярных часовых поясов")
        
    except Exception as e:
        logger.error(f"Ошибка при показе списка часовых поясов: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data == "timezone_enter_manually")
async def enter_timezone_manually(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Ввод часового пояса вручную"""
    logger.info(f"Ввод часового пояса вручную для пользователя {callback.from_user.id}")
    
    try:
        # Формируем сообщение с просьбой ввести пояс
        timezone_msg = get_message('ask_enter_custom_timezone', language, current_timezone=user.timezone)
        
        # Получаем клавиатуру "Назад"
        from bot.keyboards import get_back_keyboard
        reply_markup = get_back_keyboard(language)
        
        await callback.message.edit_text(
            timezone_msg,
            reply_markup=reply_markup
        )
        
        # Устанавливаем состояние ожидания ввода
        from bot.states.settings_states import SettingsStates
        await state_manager.set_state(state, SettingsStates.waiting_for_timezone_input)
        
        await callback.answer()
        logger.info("Запрошено ручное введение часового пояса, установлено состояние")
        
    except Exception as e:
        logger.error(f"Ошибка при запросе ручного введения часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language))

@router.callback_query(F.data.startswith("set_timezone:"))
async def set_timezone(callback: CallbackQuery, user, language: str):
    """Установка выбранного часового пояса"""
    logger.info(f"Установка часового пояса для пользователя {callback.from_user.id}")
    
    try:
        # Извлекаем часовой пояс из callback_data
        new_timezone_str = callback.data.split(":", 1)[1] # Разделяем только по первому ':'
        logger.info(f"Попытка установки часового пояса: {new_timezone_str}")
        
        # Валидируем и нормализуем часовой пояс
        import pytz
        try:
            # Пробуем создать объект пояса, чтобы убедиться, что он существует
            tz_obj = pytz.timezone(new_timezone_str)
            # Получаем каноническое имя (если оно отличается)
            canonical_tz_name = str(tz_obj)
            logger.info(f"Часовой пояс '{new_timezone_str}' валиден, каноническое имя: {canonical_tz_name}")
            
            # Обновляем часовой пояс пользователя в базе данных
            user.timezone = canonical_tz_name
            await user.asave(update_fields=['timezone'])
            logger.info(f"Часовой пояс пользователя обновлен на: {canonical_tz_name}")
            
            # Формируем сообщение об успехе
            success_msg = get_message('timezone_changed', language, timezone=canonical_tz_name)
            
            # Возвращаемся в меню настроек с обновленной клавиатурой
            settings_msg = get_message('settings_menu', language=language)
            from bot.keyboards.settings_keyboard import get_settings_keyboard
            reply_markup = get_settings_keyboard(user, language)
            
            await callback.message.edit_text(
                settings_msg,
                reply_markup=reply_markup
            )
            await callback.answer(success_msg) # Показываем сообщение как уведомление
            logger.info("Часовой пояс успешно изменен и показаны настройки")
            
        except pytz.UnknownTimeZoneError:
            logger.error(f"Неизвестный часовой пояс: {new_timezone_str}")
            error_msg = get_message('error_unknown_timezone', language)
            await callback.answer(error_msg, show_alert=True)
            return
            
    except Exception as e:
        logger.error(f"Ошибка при установке часового пояса: {e}")
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

# Обработчик для текстовых сообщений в состоянии SettingsStates.waiting_for_timezone_input
@router.message(SettingsStates.waiting_for_timezone_input)
async def process_timezone_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ручного ввода часового пояса"""
    logger.info(f"Обработка ручного ввода часового пояса от пользователя {message.from_user.id}")
    
    try:
        # Получаем введенный текст
        input_text = message.text.strip()
        logger.info(f"Введенный текст часового пояса: {input_text}")
        
        # Проверяем, не является ли это командой "Назад" или подобной
        if input_text.lower() in ['назад', 'back', '/start', '/menu']:
            # Очищаем состояние и возвращаем в меню настроек
            await state_manager.clear_state(state)
            from bot.keyboards.settings_keyboard import get_settings_keyboard
            settings_msg = get_message('settings_menu', language=language)
            await message.answer(
                settings_msg,
                reply_markup=get_settings_keyboard(user, language)
            )
            logger.info("Пользователь отменил ввод часового пояса и вернулся в настройки")
            return
        
        # Валидируем введенный текст
        import pytz
        import re
        
        # Простая проверка формата Region/City
        if not re.match(r"^[a-zA-Z]+/[a-zA-Z_]+$", input_text):
            logger.warning(f"Неверный формат часового пояса: {input_text}")
            error_msg = get_message('error_invalid_timezone', language)
            await message.answer(error_msg)
            # Возвращаем запрос на ввод
            timezone_msg = get_message('ask_enter_custom_timezone', language, current_timezone=user.timezone)
            from bot.keyboards import get_back_keyboard
            await message.answer(timezone_msg, reply_markup=get_back_keyboard(language))
            return
        
        try:
            # Пробуем создать объект пояса
            tz_obj = pytz.timezone(input_text)
            canonical_tz_name = str(tz_obj)
            logger.info(f"Введенный часовой пояс '{input_text}' валиден, каноническое имя: {canonical_tz_name}")
            
            # Обновляем часовой пояс пользователя
            user.timezone = canonical_tz_name
            await user.asave(update_fields=['timezone'])
            logger.info(f"Часовой пояс пользователя обновлен на: {canonical_tz_name}")
            
            # Очищаем состояние
            await state_manager.clear_state(state)
            
            # Формируем сообщение об успехе
            success_msg = get_message('timezone_changed', language, timezone=canonical_tz_name)
            await message.answer(success_msg)
            
            # Показываем меню настроек с обновленной клавиатурой
            settings_msg = get_message('settings_menu', language=language)
            from bot.keyboards.settings_keyboard import get_settings_keyboard
            await message.answer(
                settings_msg,
                reply_markup=get_settings_keyboard(user, language)
            )
            logger.info("Часовой пояс успешно изменен через ручной ввод")
            
        except pytz.UnknownTimeZoneError:
            logger.error(f"Неизвестный введенный часовой пояс: {input_text}")
            error_msg = get_message('error_unknown_timezone', language)
            await message.answer(error_msg)
            # Возвращаем запрос на ввод
            timezone_msg = get_message('ask_enter_custom_timezone', language, current_timezone=user.timezone)
            from bot.keyboards import get_back_keyboard
            await message.answer(timezone_msg, reply_markup=get_back_keyboard(language))
            return
            
    except Exception as e:
        logger.error(f"Ошибка при обработке ручного ввода часового пояса: {e}")
        await message.answer(get_message('error_generic', language=language))
        # Очищаем состояние в случае ошибки
        await state_manager.clear_state(state)
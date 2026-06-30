# /home/shlicha/psycho_diary/bot/handlers/broadcast_handlers.py
"""
Хендлеры для рассылки сообщений администратором
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# --- НОВОЕ: Импортируем BufferedInputFile ---
from aiogram.types import BufferedInputFile
# --- КОНЕЦ НОВОГО ---
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async
from collections import Counter # Добавляем импорт Counter для подсчёта часовых поясов

from messages import get_message, get_button_text
from diary.models import DiaryEntry, AnalysisRating
from users.models import User, Payment
from core.services.admin_service import admin_service
from core.services.base_service import BaseService

# --- НОВОЕ: Импортируем функции для генерации графиков ---
from bot.utils.activity_chart import generate_activity_chart_image, generate_hourly_activity_chart_image
# --- КОНЕЦ НОВОГО ---

router = Router()
logger = logging.getLogger(__name__)

class BroadcastStates(StatesGroup):
    waiting_broadcast_type = State()
    waiting_broadcast_message = State()


@router.message(Command("broadcast"))
async def broadcast_handler(message: Message, state: FSMContext):
    if not admin_service.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
    await state.set_state(BroadcastStates.waiting_broadcast_type)
    await message.answer(
        get_message('broadcast_select_type', language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_button_text('broadcast_important_btn', language),
                    callback_data="broadcast_important"
                ),
                InlineKeyboardButton(
                    text=get_button_text('broadcast_regular_btn', language),
                    callback_data="broadcast_regular"
                )
            ],
            [InlineKeyboardButton(
                text=get_button_text('broadcast_cancel_btn', language),
                callback_data="cancel_broadcast"
            )]
        ])
    )

@router.callback_query(F.data.startswith("broadcast_"), BroadcastStates.waiting_broadcast_type)
async def set_broadcast_type(callback: CallbackQuery, state: FSMContext):
    try:
        language = getattr(callback.from_user, 'language_code', 'ru') or 'ru'
        is_important = callback.data == "broadcast_important"
        await state.update_data(is_important=is_important)
        await state.set_state(BroadcastStates.waiting_broadcast_message)
        broadcast_type_text = get_message(
            'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
            language
        )
        await callback.message.edit_text(
            get_message('broadcast_enter_message', language, broadcast_type=broadcast_type_text),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=get_button_text('broadcast_cancel_btn', language),
                    callback_data="cancel_broadcast"
                )]
            ])
        )
    except Exception as e:
        logger.error(f"Error setting broadcast type: {e}")
        await callback.answer(get_message('broadcast_error', language), show_alert=True)
    finally:
        await callback.answer()

@router.message(BroadcastStates.waiting_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext, bot):
    data = await state.get_data()
    is_important = data.get('is_important', False)
    try:
        users = await admin_service.get_users_for_broadcast(is_important)
        result = await admin_service.send_broadcast_message(bot, users, message.text, is_important)

        language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
        await message.answer(
            get_message(
                'broadcast_success',
                language,
                broadcast_type=get_message(
                    'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
                    language
                ),
                success=result['success'],
                failed=result['failed']
            )
        )
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
        await message.answer(get_message('broadcast_error', language))
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    try:
        language = getattr(callback.from_user, 'language_code', 'ru') or 'ru'
        await callback.message.edit_text(get_message('broadcast_cancelled', language))
        await state.clear()
    except Exception as e:
        logger.error(f"Error canceling broadcast: {e}")
        language = getattr(callback.from_user, 'language_code', 'ru') or 'ru'
        await callback.answer(get_message('broadcast_failed_cancel', language), show_alert=True)
    finally:
        await callback.answer()

@router.message(Command("stats"))
async def cmd_admin_stats(message: Message):
    """
    Отправляет администратору сводную статистику.
    """
    if not admin_service.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для просмотра статистики.")
        return
    try:
        stats = await admin_service.get_admin_stats()
        response = f"""
📊 <b>Статистика приложения</b> (на {timezone.now().strftime('%d.%m.%Y %H:%M')})

<b>👥Пользователи:</b>
• Всего (активных в системе): {stats['total_users']}
• 🟢Активных (незаблокированных): {stats['active_users']}
• 🟢Активных за последние 7 дней: {stats['active_users_last_7_days']}
• 🔴Заблокировано: {stats['blocked_users']}
• 💳С активной подпиской: {stats['premium_users']}
• 💎С токенами: {stats['users_with_tokens']}
• 📈С включённым автоанализом: {stats['users_with_auto_analysis_enabled']}
• 🎓Завершили онбординг: {stats['users_completed_onboarding']}
• ✍️Сделали хотя бы одну запись: {stats['users_with_entries']}

<b>Платежи (успешные):</b>
• 💎Подписки (30 дней): {stats['subscriptions_30_count']} шт.
• 💎Подписки (год): {stats['subscriptions_year_count']} шт.
• 💰Токены (10 шт.): {stats['tokens_10_count']} шт.
• 💰Токены (50 шт.): {stats['tokens_50_count']} шт.
• 💰Токены (100 шт.): {stats['tokens_100_count']} шт.
• 💰Токены (200 шт.): {stats['tokens_200_count']} шт.
• 💰Токены (500 шт.): {stats['tokens_500_count']} шт.
• 💰Токены (кастом): {stats['custom_tokens_count']} шт.

<b>Записи:</b>
• Всего (от незаблокированных пользователей): {stats['total_entries']}
• "Настоящие": {stats['real_entries']}
• Восстановленные: {stats['recovered_entries']}

"""

        # --- НОВОЕ: Добавляем статистику по оценкам анализов ---
        response += f"<b>Оценки анализов:</b>\n"
        response += f"• Всего оценок: {stats['total_ratings']}\n"
        for i in range(1, 6):
            star_emoji = "⭐" * i
            count = stats['rating_distribution'].get(i, 0)
            response += f"• {star_emoji}: {count} шт.\n"
        # --- КОНЕЦ НОВОГО ---

        # --- НОВОЕ: Добавляем статистику по часовым поясам ---
        if stats['top_timezones']:
            response += "\n<b>Топ 10 часовых поясов:</b>\n"
            for tz, count in stats['top_timezones']:
                # Экранируем символы, которые могут мешать HTML-парсингу, если tz содержит их
                # Однако, обычно идентификаторы часовых поясов (например, Europe/Moscow) не требуют экранирования в HTML
                # Если есть сомнения, можно использовать html.escape(tz), импортировав html
                response += f"• {tz}: {count} пользоват.\n"
        else:
            response += "\n<b>Часовые пояса:</b>\nНет данных или все пользователи используют UTC.\n"
        # --- КОНЕЦ НОВОГО ---

        await message.answer(response, parse_mode='HTML')

        # --- НОВОЕ: Отправляем графики активности ---
        # Получаем администратора для передачи его часового пояса
        admin_user = await BaseService.get_user_by_telegram_id(message.from_user.id)
        if not admin_user:
            await message.answer("❌ Администратор не найден в базе данных.")
            return
        try:
            activity_chart_img = await generate_activity_chart_image(admin_user, days=30) # График за 30 дней
            # --- ОБЕРТЫВАЕМ BytesIO в BufferedInputFile ---
            input_file = BufferedInputFile(activity_chart_img.getvalue(), filename="activity_chart.png")
            await message.answer_photo(photo=input_file, caption="📈 Активность пользователей по дням (по времени администратора)")
        except Exception as chart_error:
            logger.error(f"Ошибка генерации графика активности по дням: {chart_error}")
            await message.answer("❌ Ошибка при генерации графика активности по дням.")

        try:
            hourly_activity_chart_img = await generate_hourly_activity_chart_image(admin_user, days=30) # График по часам за 30 дней
            # --- ОБЕРТЫВАЕМ BytesIO в BufferedInputFile ---
            input_file_hourly = BufferedInputFile(hourly_activity_chart_img.getvalue(), filename="hourly_activity_chart.png")
            await message.answer_photo(photo=input_file_hourly, caption="⏰ Активность пользователей по часам (по времени администратора)")
        except Exception as hourly_chart_error:
            logger.error(f"Ошибка генерации почасового графика активности: {hourly_chart_error}")
            await message.answer("❌ Ошибка при генерации почасового графика активности.")
        # --- КОНЕЦ НОВОГО ---

    except Exception as e:
        logger.error(f"Ошибка при сборе статистики администратора: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сборе статистики.")

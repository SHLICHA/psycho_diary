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
from diary.models import DiaryEntry, AnalysisRating # Импортируем AnalysisRating
from users.models import User, Payment

# --- НОВОЕ: Импортируем функции для генерации графиков ---
from bot.utils.activity_chart import generate_activity_chart_image, generate_hourly_activity_chart_image
# --- КОНЕЦ НОВОГО ---

router = Router()
logger = logging.getLogger(__name__)

class BroadcastStates(StatesGroup):
    waiting_broadcast_type = State()
    waiting_broadcast_message = State()

def is_admin(telegram_id: int) -> bool:
    dev_chat_id_str = settings.DEVELOPER_CHAT_ID
    if not dev_chat_id_str:
        return False
    try:
        dev_chat_id = int(dev_chat_id_str)
        return telegram_id == dev_chat_id
    except (ValueError, TypeError):
        return False

@router.message(Command("broadcast"))
async def broadcast_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
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
        if is_important:
            users = await sync_to_async(list)(
                User.objects.filter(
                    is_blocked=False,
                    deletion_status='active',
                    deleted_at__isnull=True
                ).values_list('telegram_id', 'language')
            )
        else:
            users = await sync_to_async(list)(
                User.objects.filter(
                    is_blocked=False,
                    deletion_status='active',
                    deleted_at__isnull=True,
                    notifications_enabled=True
                ).values_list('telegram_id', 'language')
            )

        success = 0
        failed = 0
        for user_id, user_lang in users:
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=get_button_text('btn_main_menu', user_lang),
                        callback_data="main_menu"
                    )]
                ])
                await bot.send_message(
                    chat_id=user_id,
                    text=f"{'🔴 ' if is_important else '🔵 '}{get_message('broadcast_prefix', user_lang)}\n\n{message.text}",
                    reply_markup=kb
                )
                success += 1
            except Exception as e:
                if "bot was blocked" in str(e).lower():
                    await User.mark_blocked(user_id)
                failed += 1

        language = getattr(message.from_user, 'language_code', 'ru') or 'ru'
        await message.answer(
            get_message(
                'broadcast_success',
                language,
                broadcast_type=get_message(
                    'broadcast_type_selected_important' if is_important else 'broadcast_type_selected_regular',
                    language
                ),
                success=success,
                failed=failed
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

async def get_admin_stats():
    """
    Асинхронная функция для сбора статистики администратора.
    Возвращает словарь с метриками.
    """
    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)
    stats = {}
    active_in_system_users = User.objects.filter(deletion_status='active', is_superuser=False)
    stats['total_users'] = await active_in_system_users.acount()
    active_users_query = active_in_system_users.filter(is_blocked=False)
    stats['active_users'] = await active_users_query.acount()
    stats['active_users_last_7_days'] = await active_users_query.filter(
        last_activity__gte=seven_days_ago
    ).acount()
    stats['blocked_users'] = await active_in_system_users.filter(is_blocked=True).acount()
    @sync_to_async
    def count_premium_users():
        users_qs = active_users_query
        count = 0
        for user in users_qs.iterator():
            if user.is_premium_active():
                count += 1
        return count
    stats['premium_users'] = await count_premium_users()
    stats['users_with_tokens'] = await active_users_query.filter(token_balance__gt=0).acount()
    stats['users_with_auto_analysis_enabled'] = await active_users_query.filter(auto_analysis_enabled=True).acount()
    stats['users_completed_onboarding'] = await active_users_query.filter(is_onboarding_completed=True).acount()
    user_ids_with_entries = await DiaryEntry.objects.filter(
        user__in=active_users_query
    ).values_list('user_id', flat=True).distinct().acount()
    stats['users_with_entries'] = user_ids_with_entries
    @sync_to_async
    def get_timezones_list():
        return list(active_users_query.values_list('timezone', flat=True))
    timezones_list = await get_timezones_list()
    timezone_counts = Counter(timezones_list)
    top_timezones = timezone_counts.most_common(10)
    stats['top_timezones'] = top_timezones
    all_ratings = AnalysisRating.objects.all()
    stats['total_ratings'] = await all_ratings.acount()
    @sync_to_async
    def get_rating_counts():
        from django.db.models import Count
        rating_counts = all_ratings.values('rating').annotate(count=Count('rating')).order_by('rating')
        counts = {i: 0 for i in range(1, 6)}
        for item in rating_counts:
            counts[item['rating']] = item['count']
        return counts
    stats['rating_distribution'] = await get_rating_counts()
    successful_payments = Payment.objects.filter(status='succeeded')
    stats['subscriptions_30_count'] = await successful_payments.filter(payment_type='subscription_month').acount()
    stats['subscriptions_year_count'] = await successful_payments.filter(payment_type='subscription_year').acount()
    stats['tokens_10_count'] = await successful_payments.filter(payment_type='tokens_10').acount()
    stats['tokens_50_count'] = await successful_payments.filter(payment_type='tokens_50').acount()
    stats['tokens_100_count'] = await successful_payments.filter(payment_type='tokens_100').acount()
    stats['tokens_200_count'] = await successful_payments.filter(payment_type='tokens_200').acount()
    stats['tokens_500_count'] = await successful_payments.filter(payment_type='tokens_500').acount()
    stats['custom_tokens_count'] = await successful_payments.filter(payment_type='tokens_custom').acount()
    user_active_ids = await sync_to_async(list)(active_users_query.values_list('id', flat=True))
    total_entries_query = DiaryEntry.objects.filter(user_id__in=user_active_ids)
    stats['total_entries'] = await total_entries_query.acount()
    stats['real_entries'] = await total_entries_query.filter(is_recovered_streak=False).acount()
    stats['recovered_entries'] = await total_entries_query.filter(is_recovered_streak=True).acount()
    return stats

@router.message(Command("stats"))
async def cmd_admin_stats(message: Message):
    """
    Отправляет администратору сводную статистику.
    """
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для просмотра статистики.")
        return
    try:
        stats = await get_admin_stats()
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
        admin_user = await User.objects.aget(telegram_id=message.from_user.id)
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

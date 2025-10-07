# bot/utils/diary_utils.py
import logging
from typing import Dict, Any, List, Tuple
from asgiref.sync import sync_to_async
from datetime import date, datetime, timedelta
import pytz
from django.utils import timezone

from diary.models import DiaryEntry
from users.models import User, TokenTransaction
from messages.messages_utils import get_message # Импортируем get_message здесь, так как она используется

logger = logging.getLogger(__name__)

def get_user_streaks(user):
    """
    Подсчитывает текущую и максимальную серию дней с записями для пользователя.
    """
    try:
        import pytz
        user_timezone_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_timezone_str)
        now = datetime.now(user_tz)
        today = now.date()
        # Получаем все даты, когда пользователь делал записи
        entry_dates = DiaryEntry.objects.filter(
            user=user
        ).order_by('-created_at').distinct().values_list('created_at', flat=True)
        # Преобразуем в даты в часовом поясе пользователя
        user_entry_dates = []
        for dt in entry_dates:
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            user_entry_dates.append(dt.astimezone(user_tz).date())
        # Убираем дубликаты и сортируем по убыванию
        unique_dates = sorted(set(user_entry_dates), reverse=True)
        if not unique_dates:
            return 0, 0
        # Подсчитываем текущую серию
        current_streak = 0
        current_date = today
        for entry_date in unique_dates:
            if entry_date == current_date:
                current_streak += 1
                current_date -= timedelta(days=1)
            elif entry_date < current_date:
                break
        # Подсчитываем максимальную серию
        max_streak = 0
        current_run = 0
        prev_date = None
        for entry_date in sorted(set(user_entry_dates)):
            if prev_date is None:
                current_run = 1
            elif entry_date == prev_date + timedelta(days=1):
                current_run += 1
            else:
                max_streak = max(max_streak, current_run)
                current_run = 1
            prev_date = entry_date
        max_streak = max(max_streak, current_run)
        return current_streak, max_streak
    except Exception as e:
        logger.error(f"Ошибка при подсчете серий пользователя {user.telegram_id}: {e}")
        return 0, 0

async def check_and_award_streak_bonus(user: User) -> Dict[str, Any]:
    """
    Проверяет текущую серию пользователя и начисляет токены за вехи (7, 30, 365 дней подряд).
    Возвращает словарь с информацией о начислениях.
    """
    logger.debug(f"[Streak Bonus] Проверка наград за серию для пользователя {user.telegram_id}")
    try:
        current_streak, max_streak = await sync_to_async(get_user_streaks)(user)
        logger.debug(f"[Streak Bonus] Текущая серия для {user.telegram_id}: {current_streak}, Максимальная: {max_streak}")
    except Exception as e:
        logger.error(f"[Streak Bonus] Ошибка при получении серии для пользователя {user.telegram_id}: {e}")
        return {"awarded": False, "error": str(e)}

    if current_streak <= 0:
        logger.debug(f"[Streak Bonus] Текущая серия пользователя {user.telegram_id} <= 0, наград не начисляется.")
        return {"awarded": False}
    try:
        user_db = await User.objects.aget(telegram_id=user.telegram_id)
        last_7 = user_db.last_streak_reward_7
        last_30 = user_db.last_streak_reward_30
        last_365 = user_db.last_streak_reward_365
        logger.debug(f"[Streak Bonus] Последние награды для {user.telegram_id}: 7={last_7}, 30={last_30}, 365={last_365}")
    except User.DoesNotExist:
        logger.error(f"[Streak Bonus] Пользователь с telegram_id {user.telegram_id} не найден в БД при проверке награды за серию.")
        return {"awarded": False, "error": "user_not_found"}
    rewards_awarded: List[Tuple[int, int]] = []
    updated_fields = []
    if current_streak >= last_7 + 7 and current_streak % 7 == 0:
        tokens_to_award = 3
        transaction_description = f"Награда за {current_streak} дней подряд ведения дневника"
        try:
            await sync_to_async(TokenTransaction.create_and_update_balance)(
                user=user_db,
                amount=tokens_to_award,
                transaction_type='streak_bonus',
                description=transaction_description
            )
            rewards_awarded.append((current_streak, tokens_to_award))
            user_db.last_streak_reward_7 = current_streak
            updated_fields.append('last_streak_reward_7')
            logger.info(f"[Streak Bonus] Награда за {current_streak} дней подряд начислена пользователю {user.telegram_id}: {tokens_to_award} токенов.")
        except Exception as e:
            logger.error(f"[Streak Bonus] Ошибка при начислении награды за {current_streak} дней: {e}")
    if current_streak >= last_30 + 30 and current_streak % 30 == 0:
        tokens_to_award = 20
        transaction_description = f"Награда за {current_streak} дней подряд ведения дневника"
        try:
            await sync_to_async(TokenTransaction.create_and_update_balance)(
                user=user_db,
                amount=tokens_to_award,
                transaction_type='streak_bonus',
                description=transaction_description
            )
            rewards_awarded.append((current_streak, tokens_to_award))
            user_db.last_streak_reward_30 = current_streak
            updated_fields.append('last_streak_reward_30')
            logger.info(f"[Streak Bonus] Награда за {current_streak} дней под ряд начислена пользователю {user.telegram_id}: {tokens_to_award} токенов.")
        except Exception as e:
            logger.error(f"[Streak Bonus] Ошибка при начислении награды за {current_streak} дней: {e}")
    if current_streak >= last_365 + 365 and current_streak % 365 == 0:
        tokens_to_award = 1000
        transaction_description = f"Награда за {current_streak} дней под ряд ведения дневника"
        try:
            await sync_to_async(TokenTransaction.create_and_update_balance)(
                user=user_db,
                amount=tokens_to_award,
                transaction_type='streak_bonus',
                description=transaction_description
            )
            rewards_awarded.append((current_streak, tokens_to_award))
            user_db.last_streak_reward_365 = current_streak
            updated_fields.append('last_streak_reward_365')
            logger.info(f"[Streak Bonus] Награда за {current_streak} дней под ряд начислена пользователю {user.telegram_id}: {tokens_to_award} токенов.")
        except Exception as e:
            logger.error(f"[Streak Bonus] Ошибка при начислении награды за {current_streak} дней: {e}")
    if updated_fields:
        try:
            await sync_to_async(user_db.save)(update_fields=updated_fields)
            logger.debug(f"[Streak Bonus] Поля наград обновлены для пользователя {user_db.telegram_id}: {updated_fields}")
        except Exception as e:
            logger.error(f"[Streak Bonus] Ошибка при обновлении полей наград пользователя {user_db.telegram_id}: {e}")
    total_tokens = sum(tokens for _, tokens in rewards_awarded)
    if rewards_awarded:
        logger.debug(f"[Streak Bonus] Награды начислены для {user.telegram_id}: {rewards_awarded}, Всего токенов: {total_tokens}")
        return {
            "awarded": True,
            "rewards": rewards_awarded,
            "total_tokens_awarded": total_tokens
        }
    else:
        logger.debug(f"[Streak Bonus] Наград не начислено для {user.telegram_id}.")
        return {"awarded": False}
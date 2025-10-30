import logging
from typing import Dict, Any, List, Tuple, Optional
from asgiref.sync import sync_to_async
from datetime import date
import pytz
from django.utils import timezone

from diary.models import DiaryEntry
from users.models import User, TokenTransaction
from messages.messages_utils import get_message

logger = logging.getLogger(__name__)

async def get_user_streaks(user):
    """
    Подсчитывает текущую и максимальную серию дней с записями для пользователя.
    Учитывает ВСЕ записи, включая is_recovered_streak=True.
    """
    try:
        import pytz
        from asgiref.sync import sync_to_async
        from datetime import datetime, timedelta, date
        import logging

        logger = logging.getLogger(__name__)

        user_timezone_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_timezone_str)
        now = datetime.now(user_tz)
        today = now.date()
        @sync_to_async
        def get_entry_dates_sync():
            entry_dates_qs = DiaryEntry.objects.filter(
                user=user,
            ).order_by('created_at').distinct().values_list('created_at', flat=True)
            return list(entry_dates_qs)
        entry_dates = await get_entry_dates_sync()
        user_entry_dates = set()
        for dt in entry_dates:
            if dt is None:
                continue
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                user_entry_dates.add(dt.astimezone(user_tz).date())
            elif isinstance(dt, date):
                user_entry_dates.add(dt)
            else:
                logger.warning(f"get_user_streaks: Неожиданный тип даты: {type(dt)}, значение: {dt}")

        sorted_dates = sorted(user_entry_dates)

        if not sorted_dates:
            return 0, 0
        current_streak = 0
        current_date = today
        for entry_date in sorted(user_entry_dates, reverse=True):
            if entry_date == current_date:
                current_streak += 1
                current_date -= timedelta(days=1)
            elif entry_date < current_date:
                break
        max_streak = 0
        current_run = 0
        prev_date = None
        for entry_date in sorted_dates:
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
        current_streak, max_streak = await get_user_streaks(user)
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
    
async def get_recoverable_gap_info(user: User) -> Optional[List[date]]:
    """
    Проверяет, можно ли восстановить пропущенные дни в серии.
    Восстановление возможно только для 1 или 2 последовательных пропущенных дней,
    которые идут сразу после существующей записи X и <= yesterday (вчера).
    Сегодняшний день не учитывается.

    Args:
        user: Пользователь.

    Returns:
        List[date] с датами, которые можно восстановить, или None, если восстановление невозможно.
    """
    logger.debug(f"[get_recoverable_gap_info] Проверка восстановления серии для пользователя {user.telegram_id}")
    try:
        import pytz
        from asgiref.sync import sync_to_async
        from datetime import datetime, timedelta, date

        user_timezone_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_timezone_str)
        now = datetime.now(user_tz)
        today = now.date()
        yesterday = today - timedelta(days=1)

        # --- ОБНОВЛЕНИЕ: Обернуть в sync_to_async ---
        @sync_to_async
        def get_all_entry_dates_sync():
            entry_dates_qs = DiaryEntry.objects.filter(user=user).order_by('created_at').distinct().values_list('created_at', flat=True)
            return list(entry_dates_qs)

        entry_dates = await get_all_entry_dates_sync()
        # ---

        user_all_entry_dates = set()
        for dt in entry_dates:
            if dt is None:
                continue
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                user_all_entry_dates.add(dt.astimezone(user_tz).date())
            elif isinstance(dt, date):
                user_all_entry_dates.add(dt)

        # Исключаем сегодняшний день
        user_all_entry_dates.discard(today)

        sorted_dates = sorted(user_all_entry_dates)

        if not sorted_dates:
            logger.debug("[get_recoverable_gap_info] Нет записей (без учета сегодняшнего дня).")
            return None

        # Ищем интервал [start_gap, end_gap] сразу после существующей записи
        # где длина интервала 1 или 2, и end_gap <= yesterday
        for i in range(len(sorted_dates)):
            date_before_gap = sorted_dates[i]
            # Проверяем дни после date_before_gap до yesterday
            gap_start = date_before_gap + timedelta(days=1)
            if gap_start > yesterday:
                # Если день после записи уже за вчера, пропускаем
                continue

            # Найдем конец потенциального пропуска
            current_check_date = gap_start
            gap_dates = []
            while current_check_date <= yesterday and current_check_date not in user_all_entry_dates:
                gap_dates.append(current_check_date)
                if len(gap_dates) > 2:
                    # Пропуск слишком длинный
                    break
                current_check_date += timedelta(days=1)

            # Проверяем длину пропуска
            if 1 <= len(gap_dates) <= 2:
                # Пропуск подходит
                logger.debug(f"[get_recoverable_gap_info] Найден пропуск после {date_before_gap} для восстановления: {gap_dates}")
                return gap_dates
            # Если длина > 2 или == 0, идём к следующей дате записи

        logger.debug("[get_recoverable_gap_info] Не найдено подходящего пропуска для восстановления.")
        return None

    except Exception as e:
        logger.error(f"[get_recoverable_gap_info] Ошибка при проверке восстановления серии для {user.telegram_id}: {e}", exc_info=True)
        return None
    
async def attempt_restore_streak(user: User, target_date: date, cost_tokens: int = 10) -> Dict[str, Any]:
    """
    Пытается восстановить серию, создав "восстановленную" запись за указанный день.

    Args:
        user: Пользователь.
        target_date: Дата, за которую создается запись.
        cost_tokens: Количество токенов для списания (по умолчанию 10).

    Returns:
        Dict с результатом операции:
        - success (bool): Успешность.
        - message_key (str): Ключ сообщения для пользователя.
        - message_kwargs (dict): Параметры для форматирования сообщения.
        - updated_date (Optional[date]): Дата, за которую была создана запись (если успех).
    """
    logger.debug(f"[attempt_restore_streak] Попытка восстановления для {user.telegram_id} за {target_date}, стоимость: {cost_tokens}")

    # 1. Проверить, возможно ли восстановление для target_date
    recoverable_dates = await get_recoverable_gap_info(user)
    logger.debug(f"[attempt_restore_streak] Возможные даты для восстановления: {recoverable_dates}")

    if not recoverable_dates or target_date not in recoverable_dates:
        logger.warning(f"[attempt_restore_streak] {target_date} не входит в список возможных для восстановления.")
        return {
            "success": False,
            "message_key": "restore_streak_unavailable",
            "message_kwargs": {},
            "updated_date": None
        }

    # 2. Проверить баланс
    if user.token_balance < cost_tokens:
        logger.info(f"[attempt_restore_streak] Недостаточно токенов у {user.telegram_id} для восстановления. Требуется: {cost_tokens}, доступно: {user.token_balance}")
        return {
            "success": False,
            "message_key": "restore_streak_no_tokens",
            "message_kwargs": {"tokens_cost": cost_tokens},
            "updated_date": None
        }

    try:
        # 3. Создать "восстановленную" запись
        # Используем асинхронную сессию или sync_to_async для создания
        from asgiref.sync import sync_to_async
        from diary.models import DiaryEntry
        import pytz
        from datetime import datetime

        user_timezone_str = user.timezone if user.timezone else 'UTC'
        user_tz = pytz.timezone(user_timezone_str)

        # Создаем datetime для начала дня в часовом поясе пользователя
        naive_datetime = datetime.combine(target_date, datetime.min.time())
        localized_datetime = user_tz.localize(naive_datetime)
        # Преобразуем в UTC для хранения
        utc_datetime = localized_datetime.astimezone(pytz.utc)

        @sync_to_async
        def create_and_update_entry():
            entry = DiaryEntry.objects.create(
                user=user,
                text="Запись создана для восстановления серии", # Дефолтный текст
                # created_at НЕ указываем, пусть Django поставит текущее время при создании
                language=user.language,
                word_count=5, # Дефолтное количество слов
                is_recovered_streak=True, # Устанавливаем флаг
                # Остальные поля остаются по умолчанию
            )
            # Теперь обновляем created_at на нужное значение
            entry.created_at = utc_datetime
            entry.save(update_fields=['created_at']) # Сохраняем только поле created_at
            return entry

        new_entry = await create_and_update_entry()
        logger.info(f"[attempt_restore_streak] Создана восстановленная запись ID {new_entry.id} для {user.telegram_id} за {target_date}")

        # --- ЛОГИРОВАНИЕ ДЛЯ ПРОВЕРКИ ---
        try:
            entry_date_prop = new_entry.entry_date
            logger.info(f"[attempt_restore_streak] entry_date восстановленной записи (ID {new_entry.id}): {entry_date_prop}")
            logger.info(f"[attempt_restore_streak] created_at восстановленной записи (ID {new_entry.id}): {new_entry.created_at}")
            logger.info(f"[attempt_restore_streak] timezone пользователя {user.telegram_id}: {user.timezone}")
        except Exception as prop_error:
            logger.error(f"[attempt_restore_streak] Ошибка при получении entry_date: {prop_error}")
        # ---

        # 4. Списать токены
        from users.models import TokenTransaction
        @sync_to_async
        def create_transaction_and_update_balance():
            TokenTransaction.create_and_update_balance(
                user=user,
                amount=-cost_tokens, # Отрицательное значение для списания
                transaction_type='streak_restore',
                description=f'Восстановление серии за {target_date}'
            )
        await create_transaction_and_update_balance()
        logger.info(f"[attempt_restore_streak] Списано {cost_tokens} токенов за восстановление серии для {user.telegram_id}")

        return {
            "success": True,
            "message_key": "restore_streak_success",
            "message_kwargs": {"date": target_date.strftime("%d.%m.%Y")},
            "updated_date": target_date
        }

    except Exception as e:
        logger.error(f"[attempt_restore_streak] Критическая ошибка при восстановлении серии для {user.telegram_id}: {e}", exc_info=True)
        # В случае ошибки, возможно, стоит откатить создание записи и возвратить токены.
        # Пока просто возвращаем ошибку.
        return {
            "success": False,
            "message_key": "restore_streak_unavailable", # Или специальное сообщение об ошибке
            "message_kwargs": {},
            "updated_date": None
        }
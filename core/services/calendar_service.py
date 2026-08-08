# /core/services/calendar_service.py
"""
Сервис для работы с календарём.
Универсальный сервис: работает и для бота, и для API.

Отвечается за:
- Навигацию по месяцам (предыдущий/следующий)
- Обновление позиции календаря пользователя
- Получение локальной даты пользователя
"""

import logging
from datetime import date, datetime
from typing import Optional, Tuple, Dict, Any

import pytz
from django.utils import timezone

from users.models import User

logger = logging.getLogger(__name__)


class CalendarService:
    """Сервис для работы с календарём."""

    def calculate_prev_month(self, year: int, month: int) -> Tuple[int, int]:
        """
        Вычисляет предыдущий месяц.

        Args:
            year: Текущий год.
            month: Текущий месяц (1-12).

        Returns:
            Tuple[int, int]: (год, месяц) предыдущего месяца.
        """
        prev_month = month - 1
        prev_year = year
        if prev_month < 1:
            prev_month = 12
            prev_year = year - 1
        return prev_year, prev_month

    def calculate_next_month(self, year: int, month: int) -> Tuple[int, int]:
        """
        Вычисляет следующий месяц.

        Args:
            year: Текущий год.
            month: Текущий месяц (1-12).

        Returns:
            Tuple[int, int]: (год, месяц) следующего месяца.
        """
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year = year + 1
        return next_year, next_month

    def get_user_local_date(self, user: User) -> date:
        """
        Получает локальную дату пользователя.

        Args:
            user: Пользователь.

        Returns:
            date: Локальная дата пользователя.
        """
        return user.get_local_datetime().date()

    def get_user_local_datetime(self, user: User) -> datetime:
        """
        Получает локальное время пользователя.

        Args:
            user: Пользователь.

        Returns:
            datetime: Локальное время пользователя.
        """
        return user.get_local_datetime()

    async def update_user_calendar_position(
        self, user: User, year: int, month: int
    ) -> User:
        """
        Обновляет позицию календаря пользователя в БД.

        Args:
            user: Пользователь.
            year: Год для установки.
            month: Месяц для установки.

        Returns:
            User: Обновлённый пользователь.
        """
        user.current_calendar_year = year
        user.current_calendar_month = month
        await user.asave(update_fields=['current_calendar_year', 'current_calendar_month'])
        logger.debug(f"Позиция календаря пользователя {user.telegram_id} обновлена: {year}-{month:02d}")
        return user

    def get_target_date_from_callback(self, year: int, month: int, day: int = 1) -> date:
        """
        Создаёт дату из компонентов callback.

        Args:
            year: Год.
            month: Месяц.
            day: День (по умолчанию 1).

        Returns:
            date: Целевая дата.
        """
        return date(year, month, day)

    def is_same_month(self, date1: date, year: int, month: int) -> bool:
        """
        Проверяет, совпадает ли месяц даты с указанным.

        Args:
            date1: Дата для проверки.
            year: Год для сравнения.
            month: Месяц для сравнения.

        Returns:
            bool: True если месяцы совпадают.
        """
        return date1.year == year and date1.month == month

    def is_same_year(self, date1: date, year: int) -> bool:
        """
        Проверяет, совпадает ли год даты с указанным.

        Args:
            date1: Дата для проверки.
            year: Год для сравнения.

        Returns:
            bool: True если годы совпадают.
        """
        return date1.year == year

    def resolve_calendar_anchor_day(self, user_local_date: date, year: int) -> int:
        """
        Определяет день-якорь для календаря января при выборе года.

        Если выбран текущий год и локальный месяц пользователя — январь,
        используется текущий день; иначе — 1-е число.
        """
        if self.is_same_year(user_local_date, year) and user_local_date.month == 1:
            return user_local_date.day
        return 1

    async def build_year_selected_calendar_view(
        self,
        user: User,
        year: int,
        language: str,
    ) -> Dict[str, Any]:
        """Payload экрана календаря после выбора года (январь + навигация)."""
        from bot.keyboards import get_month_calendar_with_navigation
        from messages import get_message

        user_local_date = self.get_user_local_date(user)
        anchor_day = self.resolve_calendar_anchor_day(user_local_date, year)
        return {
            'success': True,
            'text': get_message('archive_menu', language),
            'reply_markup': await get_month_calendar_with_navigation(
                user, year, 1, anchor_day, language
            ),
            'year': year,
            'anchor_day': anchor_day,
        }


calendar_service = CalendarService()

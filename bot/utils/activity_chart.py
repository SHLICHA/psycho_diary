# bot/utils/activity_chart.py

import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
from asgiref.sync import sync_to_async
from django.db.models import Count, Q
from django.utils import timezone
from diary.models import UserActivity
import pytz
import logging
from users.models import User

logger = logging.getLogger(__name__)

async def generate_activity_chart_image(admin_user, days=7) -> io.BytesIO:
    """
    Генерирует изображение с графиком активности пользователей за последние N дней.
    Время событий переводится в часовой пояс администратора (admin_user).
    Возвращает BytesIO с изображением в формате PNG.
    """
    admin_tz_str = admin_user.timezone or 'UTC'
    try:
        admin_tz = pytz.timezone(admin_tz_str)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Неверный часовой пояс {admin_tz_str} для администратора {admin_user.id}, используем UTC.")
        admin_tz = pytz.UTC

    # Вычисляем диапазон дат (последние N дней)
    now_admin = datetime.now(admin_tz)
    end_datetime = now_admin.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_datetime = now_admin.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

    # Получаем данные из UserActivity за этот период
    @sync_to_async
    def get_data_sync():
        # Фильтруем активность, переводим timestamp в часовой пояс администратора и группируем по дню
        # timezone.now() возвращает время в UTC, поэтому timestamp также в UTC
        # Мы конвертируем его в часовой пояс администратора
        activities = UserActivity.objects.filter(
            timestamp__gte=start_datetime.astimezone(pytz.utc), # Переводим в UTC для фильтрации
            timestamp__lte=end_datetime.astimezone(pytz.utc)
        ).annotate(
            # Создаём поле 'day' в часовом поясе администратора
            # Это позволяет корректно группировать по календарным дням администратора
            day_in_admin_tz=timezone.now().astimezone(admin_tz).date() # Это не сработает напрямую в annotate
        )

        # Более надёжный способ: получаем все записи и обрабатываем в Python
        all_activities = list(activities.select_related('user').order_by('timestamp'))
        activity_counts_by_day = {}
        for activity in all_activities:
            # Переводим timestamp в часовой пояс администратора
            localized_time = activity.timestamp.astimezone(admin_tz)
            day_key = localized_time.date()
            activity_counts_by_day[day_key] = activity_counts_by_day.get(day_key, 0) + 1

        # Сортируем по дате
        sorted_items = sorted(activity_counts_by_day.items())
        return sorted_items

    # АЛЬТЕРНАТИВНЫЙ ПОДХОД (предпочтительный для БД с большим количеством записей):
    # Используем Django ORM с raw SQL или extra для манипуляции с датой в часовом поясе
    # Однако, это может быть менее переносимо между СУБД.
    # Более переносимый способ - получить сырые временные метки и обработать в Python.

    # ПОЭТАПНО:
    # 1. Получаем все активности за период (в UTC)
    @sync_to_async
    def fetch_activities_raw():
        return list(
            UserActivity.objects.filter(
                timestamp__gte=start_datetime.astimezone(pytz.utc),
                timestamp__lte=end_datetime.astimezone(pytz.utc)
            ).select_related('user').values_list('timestamp', flat=True).order_by('timestamp')
        )

    try:
        raw_timestamps = await fetch_activities_raw()
    except Exception as e:
        logger.error(f"Ошибка при получении временных меток активности: {e}")
        raw_timestamps = []

    # 2. Конвертируем в дни по часовому поясу администратора и подсчитываем
    activity_counts_by_day = {}
    for ts_utc in raw_timestamps:
        localized_time = ts_utc.astimezone(admin_tz)
        day_key = localized_time.date()
        activity_counts_by_day[day_key] = activity_counts_by_day.get(day_key, 0) + 1

    # 3. Подготовка данных для matplotlib (сортировка)
    if activity_counts_by_day:
        sorted_items = sorted(activity_counts_by_day.items())
        dates, counts = zip(*sorted_items)
    else:
        dates, counts = [], []

    # Подготовка данных для matplotlib
    if not dates:
        # Создаем изображение с надписью "Нет данных"
        fig, ax = plt.subplots(figsize=(12, 6)) # Указываем размер
        ax.text(0.5, 0.5, 'Нет данных активности за период', horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, fontsize=14)
        ax.set_title("Активность пользователей (по времени администратора)", fontsize=16)
        ax.set_xlabel("Дата", fontsize=12)
        ax.set_ylabel("Количество событий", fontsize=12)
        ax.grid(True)
    else:
        fig, ax = plt.subplots(figsize=(12, 6)) # Указываем размер
        ax.bar(dates, counts, width=0.8, label='Количество событий', color='skyblue', edgecolor='navy', linewidth=0.5)
        ax.set_title("Активность пользователей (по времени администратора)", fontsize=16)
        ax.set_xlabel("Дата", fontsize=12)
        ax.set_ylabel("Количество событий", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.legend(fontsize=10)
        plt.xticks(rotation=45, fontsize=10) # Повернуть метки дат
        plt.yticks(fontsize=10)
        plt.tight_layout() # Улучшить отступы

    # Сохраняем в BytesIO
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150) # Увеличим DPI для лучшего качества
    img_buffer.seek(0)
    plt.close(fig) # Обязательно закрыть фигуру, чтобы освободить память
    return img_buffer

async def generate_hourly_activity_chart_image(admin_user, days=7) -> io.BytesIO:
    """
    Генерирует изображение с графиком активности пользователей по часам за последние N дней.
    Время событий переводится в часовой пояс администратора (admin_user).
    Показывает, в какие часы дня наблюдается наибольшая активность.
    Возвращает BytesIO с изображением в формате PNG.
    """
    admin_tz_str = admin_user.timezone or 'UTC'
    try:
        admin_tz = pytz.timezone(admin_tz_str)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Неверный часовой пояс {admin_tz_str} для администратора {admin_user.id}, используем UTC.")
        admin_tz = pytz.UTC

    # Вычисляем диапазон дат (последние N дней)
    now_admin = datetime.now(admin_tz)
    end_datetime = now_admin.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_datetime = now_admin.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

    # Получаем временные метки активности за период
    @sync_to_async
    def fetch_activities_raw():
        return list(
            UserActivity.objects.filter(
                timestamp__gte=start_datetime.astimezone(pytz.utc),
                timestamp__lte=end_datetime.astimezone(pytz.utc)
            ).values_list('timestamp', flat=True).order_by('timestamp')
        )

    try:
        raw_timestamps = await fetch_activities_raw()
    except Exception as e:
        logger.error(f"Ошибка при получении временных меток активности для почасового графика: {e}")
        raw_timestamps = []

    # Подсчитываем количество активностей по часам (0-23) в часовом поясе администратора
    hourly_counts = [0] * 24  # Список для 24 часов
    for ts_utc in raw_timestamps:
        localized_time = ts_utc.astimezone(admin_tz)
        hour = localized_time.hour
        hourly_counts[hour] += 1

    # Подготовка данных для matplotlib
    hours = list(range(24))
    counts = hourly_counts

    fig, ax = plt.subplots(figsize=(14, 6)) # Указываем размер
    ax.bar(hours, counts, width=0.8, label='Количество событий', color='lightcoral', edgecolor='darkred', linewidth=0.5)
    ax.set_title("Активность пользователей по часам (по времени администратора)", fontsize=16)
    ax.set_xlabel("Час дня", fontsize=12)
    ax.set_ylabel("Количество событий", fontsize=12)
    ax.set_xticks(hours) # Устанавливаем метки на каждый час
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(fontsize=10)
    plt.xticks(fontsize=10) # Уменьшаем размер шрифта меток часов, если нужно
    plt.yticks(fontsize=10)
    plt.tight_layout() # Улучшить отступы

    # Сохраняем в BytesIO
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150) # Увеличим DPI для лучшего качества
    img_buffer.seek(0)
    plt.close(fig) # Обязательно закрыть фигуру, чтобы освободить память
    return img_buffer

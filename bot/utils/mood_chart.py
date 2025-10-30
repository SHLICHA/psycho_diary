# bot/charts/mood_chart.py

import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
from asgiref.sync import sync_to_async
from django.db.models import Q
from diary.models import CombinedDiaryEntry
import pytz
import logging

logger = logging.getLogger(__name__)

async def generate_mood_chart_image(user, days=7) -> io.BytesIO:
    """
    Генерирует изображение с графиком среднего настроения за последние N дней.
    Возвращает BytesIO с изображением в формате PNG.
    """
    user_tz_str = user.timezone or 'UTC'
    try:
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Неверный часовой пояс {user_tz_str} для пользователя {user.id}, используем UTC.")
        user_tz = pytz.UTC
    now_user = datetime.now(user_tz)
    end_date = now_user.date()
    start_date = end_date - timedelta(days=days - 1)
    @sync_to_async
    def get_data_sync():
        entries = CombinedDiaryEntry.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        return [(entry.date, entry.average_mood_score) for entry in entries if entry.average_mood_score > 0]

    try:
        mood_data = await get_data_sync()
    except Exception as e:
        logger.error(f"Ошибка при получении данных для графика настроения: {e}")
        mood_data = []
    if not mood_data:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'Нет данных за период', horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, fontsize=14)
        ax.set_title("Динамика настроения", fontsize=16)
        ax.set_xlabel("Дата", fontsize=12)
        ax.set_ylabel("Настроение", fontsize=12)
        ax.set_ylim(0, 10)
        ax.grid(True)
    else:
        dates, scores = zip(*mood_data)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(dates, scores, marker='o', linestyle='-', linewidth=2, markersize=6, label='Среднее настроение')
        ax.set_title("Динамика настроения", fontsize=16)
        ax.set_xlabel("Дата", fontsize=12)
        ax.set_ylabel("Настроение (среднее)", fontsize=12)
        ax.set_ylim(0, 10)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.legend(fontsize=10)
        plt.xticks(rotation=45, fontsize=10)
        plt.yticks(fontsize=10)
        plt.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    img_buffer.seek(0)
    plt.close(fig)
    return img_buffer

# bot/utils/task_impact_chart.py
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
from datetime import datetime, timedelta
from asgiref.sync import sync_to_async
from django.db.models import Q
from diary.models import TaskCompletionAnalysis, TherapyTask
import pytz
import logging
from collections import defaultdict # Импортируем для агрегации

logger = logging.getLogger(__name__)

async def generate_task_impact_chart_image(user, days=30, language='ru') -> io.BytesIO:
    """
    Генерирует изображение с графиком влияния выполненных заданий на настроение
    и их сложности за последние N дней.
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
        # Получаем TaskCompletionAnalysis, связанные с выполненными заданиями пользователя
        # за указанный период.
        # Используем completion__created_at для определения даты выполнения.
        # Используем select_related для уменьшения количества запросов к базе данных.
        analyses = TaskCompletionAnalysis.objects.filter(
            completion__task__user=user,
            completion__task__status='completed', # Только выполненные задания
            completion__created_at__date__gte=start_date, # Дата выполнения >= start_date
            completion__created_at__date__lte=end_date,   # Дата выполнения <= end_date
        ).select_related('completion__task').order_by('completion__created_at')

        # Собираем данные и агрегируем по дням
        daily_data = defaultdict(list)
        complexity_map = {'low': 1, 'medium': 2, 'high': 3}

        for analysis in analyses:
            task = analysis.completion.task
            # Используем дату выполнения (completion.created_at) как ось X
            exec_date = analysis.completion.created_at.date()
            mood_impact = analysis.mood_impact_score # Может быть None
            complexity_str = task.complexity # 'low', 'medium', 'high'
            complexity_num = complexity_map.get(complexity_str, 2) # По умолчанию 'medium' (2)

            # Если mood_impact_score отсутствует, используем 0
            mood_impact = mood_impact if mood_impact is not None else 0

            daily_data[exec_date].append({'mood_impact': mood_impact, 'complexity': complexity_num})

        # Агрегируем данные по дням
        aggregated_dates = []
        aggregated_mood_impacts = []
        aggregated_complexities = []

        for date, entries in sorted(daily_data.items()):
            aggregated_dates.append(date)
            # Усредняем mood_impact за день
            avg_mood_impact = sum(e['mood_impact'] for e in entries) / len(entries)
            aggregated_mood_impacts.append(avg_mood_impact)
            # Усредняем complexity за день (округляем до ближайшего уровня)
            avg_complexity = sum(e['complexity'] for e in entries) / len(entries)
            # Округляем до ближайшего целого (1, 2 или 3)
            rounded_avg_complexity = round(avg_complexity)
            # Ограничиваем в пределах 1-3
            final_complexity = max(1, min(3, rounded_avg_complexity))
            aggregated_complexities.append(final_complexity)

        return aggregated_dates, aggregated_mood_impacts, aggregated_complexities

    try:
        dates, mood_impacts, complexities_numeric = await get_data_sync()
    except Exception as e:
        logger.error(f"Ошибка при получении данных для графика влияния заданий: {e}")
        dates = []
        mood_impacts = []
        complexities_numeric = []

    # --- Генерация графика ---
    fig, ax1 = plt.subplots(figsize=(10, 6))

    if not dates:
        # Если нет данных, отображаем сообщение
        ax1.text(0.5, 0.5, 'Нет данных для отображения' if language == 'ru' else 'No data to display',
                horizontalalignment='center', verticalalignment='center',
                transform=ax1.transAxes, fontsize=14)
        ax1.set_title('График влияния заданий' if language == 'ru' else 'Task Impact Chart')
        ax1.axis('off') # Скрыть оси, если нет данных
    else:
        # Определение цветов
        color_mood = 'tab:blue'
        color_complexity = 'tab:red'

        # Ось Y для влияния на настроение
        ax1.set_xlabel('Дата выполнения задания')
        ax1.set_ylabel('Среднее влияние на настроение', color=color_mood)
        ax1.plot(dates, mood_impacts, color=color_mood, marker='o', label='Среднее влияние на настроение', linestyle='-', linewidth=2, markersize=6)
        ax1.tick_params(axis='y', labelcolor=color_mood)
        # Устанавливаем диапазон для оси Y влияния настроения (например, от -5 до 5)
        min_y_mood = min(min(mood_impacts, default=0) - 1, -5)
        max_y_mood = max(max(mood_impacts, default=0) + 1, 5)
        ax1.set_ylim(min_y_mood, max_y_mood)
        ax1.grid(True, linestyle='--', alpha=0.6)

        # Вторая ось Y для сложности
        ax2 = ax1.twinx()
        ax2.set_ylabel('Средняя сложность задания', color=color_complexity)
        ax2.plot(dates, complexities_numeric, color=color_complexity, marker='s', label='Средняя сложность задания', linestyle='--', linewidth=2, markersize=6)
        ax2.tick_params(axis='y', labelcolor=color_complexity)
        ax2.set_ylim(0.5, 3.5) # Устанавливаем лимиты для сложности (1-3)
        ax2.set_yticks([1, 2, 3])
        y_labels = ['Низкая', 'Средняя', 'Высокая'] if language == 'ru' else ['Low', 'Medium', 'High']
        ax2.set_yticklabels(y_labels)

        # Форматирование оси X (даты)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        # Показывать дату каждые N дней, в зависимости от общего количества точек или периода
        # Устанавливаем locator, чтобы избежать переполнения тиками
        if len(dates) <= 1: # Если только одна точка
             ax1.xaxis.set_major_locator(mdates.DayLocator()) # Показываем только её
        else:
             # Показываем примерно 7-10 делений на оси X
             interval = max(1, len(dates) // 10)
             ax1.xaxis.set_major_locator(mdates.DayLocator(interval=interval))

        plt.xticks(rotation=45)

        # Заголовок
        ax1.set_title('Среднее влияние и сложность заданий' if language == 'ru' else 'Avg. Task Impact and Complexity')

        # Легенда
        # Объединяем линии из обеих осей в одну легенду
        lines_1, labels_1 = ax1.get_legend_handles_labels()
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left')

    # Сохраняем график в байтовый буфер
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close(fig) # ВАЖНО: закрываем фигуру для освобождения памяти
    return img_buffer

from diary.tasks.scheduler_tasks import (
    schedule_daily_analyses,
    perform_scheduled_daily_analysis,
    # Если у вас есть другие задачи в scheduler_tasks.py, импортируйте их тоже сюда
)
from diary.tasks.reminder_tasks import (
    send_entry_reminders
)
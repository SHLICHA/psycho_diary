import os
from celery import Celery

# Установите модуль настроек Django по умолчанию
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# Загрузка конфигурации из settings.py с префиксом CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматическое обнаружение задач в приложениях
app.autodiscover_tasks(packages=['core', 'diary', 'diary.tasks'])


# === РЕШЕНИЕ ПРОБЛЕМЫ С ЗАКРЫТЫМИ СОЕДИНЕНИЯМИ ===
from celery.signals import task_prerun, task_postrun
from django.db import close_old_connections

@task_prerun.connect
def celery_task_prerun(*args, **kwargs):
    """Закрываем старые соединения с БД перед выполнением задачи"""
    close_old_connections()

@task_postrun.connect
def celery_task_postrun(*args, **kwargs):
    """Закрываем соединения после выполнения задачи (на всякий случай)"""
    close_old_connections()


# === Опционально: отладочная задача ===
@app.task(bind=True)
def debug_task(self):
    request_info = self.request
    if request_info.args or request_info.kwargs or any(v for k, v in request_info.items() if k not in ['args', 'kwargs']):
        print(f'Request: {request_info!r}')
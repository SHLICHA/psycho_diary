import os
from celery import Celery

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(packages=['core', 'diary', 'diary.tasks'])


# === КРИТИЧЕСКИ ВАЖНО: закрытие соединений с БД в Celery ===
from celery.signals import task_prerun, task_postrun
from django.db import close_old_connections

@task_prerun.connect
def celery_task_prerun(*args, **kwargs):
    close_old_connections()

@task_postrun.connect
def celery_task_postrun(*args, **kwargs):
    close_old_connections()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
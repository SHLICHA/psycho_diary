import os
from celery import Celery

# Установите модуль настроек Django по умолчанию для программы 'celery'.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# Используя строку здесь означает, что воркер не должен сериализовать
# объект конфигурации дочернему процессу.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Загрузите определения задач из всех зарегистрированных приложений Django.
app.autodiscover_tasks(packages=['core', 'diary', 'diary.tasks'])

# (Опционально) Для мониторинга состояния воркеров
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

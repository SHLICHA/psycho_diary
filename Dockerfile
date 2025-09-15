# /home/shlicha/psycho_diary/Dockerfile
FROM python:3.10-slim

# Аргументы для сборки
ARG DEBIAN_FRONTEND=noninteractive

# Установка переменных окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Установка зависимостей системы
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        libpq-dev \
        ffmpeg \
        netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование requirements.txt и установка зависимостей Python
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всего приложения
COPY . /app/

# Создание каталогов для статики и медиа (для Nginx, если понадобится)
RUN mkdir -p /app/staticfiles && mkdir -p /app/media

# Команда по умолчанию (ее нужно будет переопределить при запуске контейнера)
# Например, для запуска бота: python manage.py runbot
# Для запуска веб-сервера: python manage.py runserver 0.0.0.0:8000 или gunicorn
CMD ["python", "manage.py", "--help"]

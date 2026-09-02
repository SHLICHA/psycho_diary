# /home/shlicha/psycho_diary/Dockerfile
FROM python:3.10-slim

# Аргументы для сборки
ARG DEBIAN_FRONTEND=noninteractive

# Установка переменных окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Устойчивость к медленному/нестабильному доступу к PyPI при сборке
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_RETRIES=10
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV SENTENCE_TRANSFORMERS_MODEL_NAME=ai-forever/sbert_large_nlu_ru
ENV SENTENCE_TRANSFORMERS_DEVICE=cpu
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface/transformers

# Установка зависимостей системы
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        libpq-dev \
        ffmpeg \
        netcat-traditional \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app
RUN mkdir -p /app/.cache/sentence-transformers /app/.cache/huggingface/transformers

# Копирование requirements.txt и установка зависимостей Python
COPY ./requirements.txt /app/requirements.txt
RUN pip install --upgrade pip

# Удаляем конфликтующие строки до установки (typing_extensions ставим явно с aiogram)
RUN sed -i '/cryptography==46.0.2/d' /app/requirements.txt \
    && sed -i '/python-docx==1.2.0/d' /app/requirements.txt

COPY ./requirements-ml.txt /app/requirements-ml.txt

# aiogram первым (typing-extensions~=4.7.1), затем остальное и ML-стек
RUN pip install --no-cache-dir "typing-extensions==4.7.1" aiogram==3.1.1 \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-ml.txt \
    && pip install --no-cache-dir python-docx==1.2.0 \
    && pip install --no-cache-dir --force-reinstall cryptography==46.0.2 \
    && pip install --no-cache-dir --force-reinstall "typing-extensions==4.7.1"

# Копирование всего приложения
COPY . /app/

# CA Минцифры → system trust store (нужно для TLS к platform-api2.max.ru)
RUN certs_installed=0; \
    for cert in \
        /app/russian_trusted_sub_ca_2024_pem.crt \
        /app/russian_trusted_root_ca_pem.crt \
        /app/russian_trusted_sub_ca_pem.crt \
        /app/russian_trusted_sub_ca_gost_2025_pem.crt \
        /app/russian_trusted_root_ca_gost_2025_pem.crt; do \
        if [ -f "$cert" ]; then \
            cp "$cert" "/usr/local/share/ca-certificates/$(basename "$cert")"; \
            certs_installed=1; \
        fi; \
    done; \
    if [ "$certs_installed" = "1" ]; then \
        update-ca-certificates; \
    fi

# Создание каталогов для статики и медиа (для Nginx, если понадобится)
RUN mkdir -p /app/staticfiles && mkdir -p /app/media

# Команда по умолчанию (ее нужно будет переопределить при запуске контейнера)
# Например, для запуска бота: python manage.py runbot
# Для запуска веб-сервера: python manage.py runserver 0.0.0.0:8000 или gunicorn
CMD ["python", "manage.py", "--help"]

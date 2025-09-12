# /home/shlicha/psycho_diary/bot/services/yandex_object_storage.py
import os
import uuid
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class YandexObjectStorageService:
    def __init__(self):
        self.bucket_name = os.getenv('YANDEX_STORAGE_BUCKET_NAME')
        self.access_key_id = os.getenv('YANDEX_STORAGE_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('YANDEX_STORAGE_SECRET_ACCESS_KEY')
        self.region = os.getenv('YANDEX_STORAGE_REGION', 'ru-central1')
        self.endpoint_url = os.getenv('YANDEX_STORAGE_ENDPOINT', 'https://storage.yandexcloud.net')

        if not all([self.bucket_name, self.access_key_id, self.secret_access_key]):
            raise ValueError("Не настроены параметры подключения к Yandex Object Storage")

        # Инициализируем клиент boto3
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region
        )
        logger.info("YandexObjectStorageService инициализирован")

    def generate_unique_filename(self, original_filename: str, prefix: str = "audio") -> str:
        """
        Генерирует уникальное имя файла для загрузки.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique_id = uuid.uuid4().hex[:8]
        name, ext = os.path.splitext(original_filename)
        # Если расширение отсутствует, добавим ogg для голосовых
        if not ext:
            ext = ".ogg"
        return f"{prefix}/{timestamp}_{unique_id}{ext}"

    async def upload_audio_file(self, file_bytes: bytes, original_filename: str) -> str:
        """
        Загружает аудиофайл в Object Storage и возвращает его HTTPS URI.
        
        Args:
            file_bytes: Байты аудиофайла.
            original_filename: Оригинальное имя файла (для генерации уникального имени).
            
        Returns:
            str: HTTPS URI загруженного файла.
            
        Raises:
            Exception: В случае ошибки загрузки.
        """
        try:
            key = self.generate_unique_filename(original_filename)
            
            logger.info(f"Начинается загрузка файла {key} в бакет {self.bucket_name}")
            
            # Загрузка файла
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_bytes,
                # Можно добавить метаданные
                Metadata={
                    'uploaded_at': datetime.now().isoformat(),
                }
            )
            
            # Генерируем HTTPS URL для SpeechKit
            # SpeechKit Long Running Recognition API требует HTTPS URL объекта в Object Storage
            file_uri = f"https://storage.yandexcloud.net/{self.bucket_name}/{key}"
            logger.info(f"Файл успешно загружен. URI: {file_uri}")
            
            return file_uri
            
        except ClientError as e:
            logger.error(f"Ошибка клиента boto3 при загрузке файла: {e}")
            raise Exception(f"Ошибка загрузки в Object Storage: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при загрузке файла: {e}")
            raise Exception(f"Ошибка загрузки в Object Storage: {e}")

    # Опционально: метод для генерации подписанного URL (если понадобится)
    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """
        Генерирует подписанный URL для временного доступа к файлу.
        """
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expiration
            )
            return presigned_url
        except ClientError as e:
            logger.error(f"Ошибка при генерации подписанного URL: {e}")
            return None

# Глобальный экземпляр сервиса
yandex_storage_service = YandexObjectStorageService()
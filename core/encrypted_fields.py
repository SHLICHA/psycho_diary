# psycho_diary/core/encrypted_fields.py

import json
import logging
import base64
from typing import Any, Optional, Union, Tuple

from cryptography.fernet import Fernet, InvalidToken
from django.core import exceptions
from django.db import models
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)

def get_fernet_instance():
    """Получает экземпляр Fernet из настроек Django."""
    key = getattr(settings, 'CRYPTOGRAPHY_KEY', None)
    if not key:
        raise exceptions.ImproperlyConfigured(
            "Для использования зашифрованных полей необходимо указать CRYPTOGRAPHY_KEY в settings.py"
        )
    if isinstance(key, str):
        key = key.encode('utf-8')
    return Fernet(key)

def is_raw_value_encrypted(raw_value: Union[str, bytes, None]) -> Tuple[bool, str]:
    """
    Проверяет, является ли сырое значение из БД уже зашифрованным.
    """
    if raw_value is None or raw_value == "":
        return True, "Пустое значение"

    fernet_instance = get_fernet_instance()
    
    try:
        if isinstance(raw_value, bytes):
            # Пробуем дешифровать байты
            fernet_instance.decrypt(raw_value)
            return True, "Байтовое значение успешно дешифровано"
            
        elif isinstance(raw_value, str):
            # Эвристика 1: Проверяем типичный префикс зашифрованных данных Fernet
            if raw_value.startswith('gAAAA'):
                return True, "Строка начинается с префикса Fernet"
                
            # Эвристика 2: Проверяем длину (зашифрованные данные обычно длинные)
            if len(raw_value) > 100 and ' ' not in raw_value:
                return True, "Длинная строка без пробелов - вероятно зашифрована"
            
            # Эвристика 3: Пробуем декодировать как base64 и дешифровать
            try:
                decoded_bytes = base64.b64decode(raw_value)
                # Проверяем, что декодированные данные имеют разумный размер
                if 10 <= len(decoded_bytes) <= 1000:
                    fernet_instance.decrypt(decoded_bytes)
                    return True, "Base64 строка успешно дешифрована"
            except (base64.binascii.Error, ValueError):
                pass
                
            # Эвристика 4: Пробуем дешифровать как обычную строку
            try:
                fernet_instance.decrypt(raw_value.encode('utf-8'))
                return True, "Строка успешно дешифрована"
            except InvalidToken:
                return False, "Строка не является зашифрованными данными"
                
        return False, f"Неподдерживаемый тип: {type(raw_value)}"
        
    except InvalidToken:
        return False, "Неверный токен"
    except Exception as e:
        logger.debug(f"Ошибка проверки шифрования: {e}")
        return False, f"Ошибка: {e}"

class EncryptedFieldMixin:
    """Миксин для шифрования/дешифрования полей модели."""
    
    def get_prep_value(self, value):
        """
        Шифрует значение перед сохранением в БД.
        Возвращает base64 строку.
        """
        if value is None or value == "":
            return value

        fernet_instance = get_fernet_instance()
        
        # Сериализуем нестроковые значения в JSON
        if not isinstance(value, str):
            value = json.dumps(value, cls=DjangoJSONEncoder)
        
        # Шифруем
        value_bytes = value.encode('utf-8')
        encrypted_bytes = fernet_instance.encrypt(value_bytes)
        
        # Конвертируем байты в base64 строку
        return base64.b64encode(encrypted_bytes).decode('ascii')

    def from_db_value(self, value, expression, connection):
        """Дешифрует значение при загрузке из БД."""
        return self._decrypt_value(value)

    def _decrypt_value(self, value):
        """Внутренний метод дешифровки, который можно вызывать явно."""
        if value is None or value == "":
            return value
            
        fernet_instance = get_fernet_instance()
        
        try:
            if isinstance(value, bytes):
                decrypted_bytes = fernet_instance.decrypt(value)
            elif isinstance(value, str):
                try:
                    decoded_bytes = base64.b64decode(value)
                    decrypted_bytes = fernet_instance.decrypt(decoded_bytes)
                except (base64.binascii.Error, ValueError):
                    try:
                        decrypted_bytes = fernet_instance.decrypt(value.encode('utf-8'))
                    except InvalidToken:
                        logger.warning(f"Не удалось дешифровать: {value[:50]}...")
                        return value
            else:
                return value

            # Декодируем в строку
            decrypted_str = decrypted_bytes.decode('utf-8')
            
            # Для JSONField пытаемся десериализовать
            if isinstance(self, models.JSONField):
                try:
                    return json.loads(decrypted_str)
                except json.JSONDecodeError:
                    return decrypted_str
            
            # Для текстовых полей возвращаем строку
            return decrypted_str

        except Exception as e:
            logger.error(f"Ошибка дешифровки: {e}")
            return value

    def contribute_to_class(self, cls, name, **kwargs):
        """Добавляем дескриптор для автоматического дешифрования при доступе к полю."""
        super().contribute_to_class(cls, name, **kwargs)
        
        # Создаем дескриптор для автоматического дешифрования
        class EncryptedFieldDescriptor:
            def __init__(self, field):
                self.field = field
                self.attname = field.attname
            
            def __get__(self, instance, owner):
                if instance is None:
                    return self
                
                # Получаем значение из instance.__dict__
                value = instance.__dict__.get(self.attname)
                
                # Если значение зашифровано (начинается с типичного префикса Fernet), дешифруем
                if value and isinstance(value, str) and (
                    value.startswith('gAAAA') or 
                    len(value) > 50  # Эвристика: зашифрованные данные обычно длинные
                ):
                    try:
                        decrypted_value = self.field._decrypt_value(value)
                        # Сохраняем дешифрованное значение обратно в instance.__dict__
                        instance.__dict__[self.attname] = decrypted_value
                        return decrypted_value
                    except Exception as e:
                        logger.error(f"Ошибка автоматического дешифрования поля {self.attname}: {e}")
                
                return value
            
            def __set__(self, instance, value):
                instance.__dict__[self.attname] = value
        
        # Заменяем стандартный дескриптор на наш
        setattr(cls, self.name, EncryptedFieldDescriptor(self))

class EncryptedCharField(EncryptedFieldMixin, models.CharField):
    """Зашифрованное CharField."""
    pass

class EncryptedTextField(EncryptedFieldMixin, models.TextField):
    """Зашифрованное TextField."""
    pass

class EncryptedEmailField(EncryptedFieldMixin, models.EmailField):
    """Зашифрованное EmailField."""
    pass

class EncryptedJSONField(EncryptedFieldMixin, models.JSONField):
    """Зашифрованное JSONField."""
    
    def from_db_value(self, value, expression, connection):
        result = super().from_db_value(value, expression, connection)
        # Дополнительная обработка для JSON
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return result
        return result
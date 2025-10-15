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
    Надежно проверяет, является ли сырое значение из БД уже зашифрованным.
    """
    if raw_value is None or raw_value == "":
        return True, "Пустое значение"

    fernet_instance = get_fernet_instance()
    
    # Импортируем base64 здесь, чтобы избежать ошибки
    import base64
    
    # Эвристика 1: Проверяем типичный префикс зашифрованных данных Fernet
    if isinstance(raw_value, str) and raw_value.startswith('gAAAA'):
        return True, "Строка начинается с префикса Fernet"
    
    # Эвристика 2: Проверяем длину и структуру (зашифрованные данные обычно длинные без пробелов)
    if isinstance(raw_value, str) and len(raw_value) > 50 and ' ' not in raw_value:
        # Дополнительно проверяем, что это валидный base64
        try:
            base64.b64decode(raw_value)
            return True, "Длинная base64 строка без пробелов - вероятно зашифрована"
        except:
            pass
    
    try:
        if isinstance(raw_value, bytes):
            # Пробуем дешифровать байты
            fernet_instance.decrypt(raw_value)
            return True, "Байтовое значение успешно дешифровано"
            
        elif isinstance(raw_value, str):
            # Пробуем декодировать как base64 и дешифровать
            try:
                decoded_bytes = base64.b64decode(raw_value)
                fernet_instance.decrypt(decoded_bytes)
                return True, "Base64 строка успешно дешифрована"
            except (base64.binascii.Error, ValueError):
                # Не base64, пробуем дешифровать как обычную строку
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
        result = base64.b64encode(encrypted_bytes).decode('ascii')
        return result

    def get_db_prep_lookup(self, lookup_type, value, connection, prepared=False):
        """
        Подготавливает значение для поиска (фильтрации), шифруя его.
        Работает только для lookup_type 'exact' и 'iexact'.
        """
        if lookup_type in ('exact', 'iexact'):
            encrypted_value = self.get_prep_value(value)
            prepared_encrypted_value = connection.ops.get_db_prep_value(
                encrypted_value, connection, prepared=False
            )
            return (prepared_encrypted_value,)
        else:
            logger.warning(f"[EncryptedFieldMixin] Lookup '{lookup_type}' is not supported for EncryptedFieldMixin.")
            raise NotImplementedError(
                f"Lookup '{lookup_type}' is not supported for EncryptedFieldMixin."
            )

    def from_db_value(self, value, expression, connection):
        """Дешифрует значение при загрузке из БД."""
        return self._decrypt_value(value)

    def _decrypt_value(self, value):
        """Внутренний метод дешифровки с улучшенной проверкой."""
        if value is None or value == "":
            return value
            
        # Сначала проверяем, нужно ли вообще дешифровать это значение
        if not self._should_decrypt_value(value):
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
                        # Если не удалось дешифровать, вероятно это обычный текст
                        logger.debug(f"Не удалось дешифровать значение (вероятно обычный текст): {value[:50]}...")
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
            logger.debug(f"Ошибка дешифровки (вероятно обычный текст): {e}")
            return value

    def _should_decrypt_value(self, value):
        """
        Определяет, нужно ли пытаться дешифровать значение.
        Возвращает True только для явно зашифрованных данных.
        """
        if value is None or value == "":
            return False
            
        # Для байтов - всегда пробуем дешифровать
        if isinstance(value, bytes):
            return True
            
        # Для строк проверяем признаки зашифрованных данных
        if isinstance(value, str):
            # Признак 1: Начинается с типичного префикса Fernet
            if value.startswith('gAAAA'):
                return True
                
            # Признак 2: Длинная строка без пробелов (возможно base64)
            if len(value) > 50 and ' ' not in value:
                import base64
                try:
                    # Проверяем, что это валидный base64
                    base64.b64decode(value)
                    return True
                except:
                    return False
                    
            # Признак 3: Содержит только base64 символы
            import base64
            try:
                base64.b64decode(value)
                return True
            except:
                pass
                
        # Во всех остальных случаях - не дешифруем
        return False

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
                
                # Дешифруем только если значение явно зашифровано
                if value and self.field._should_decrypt_value(value):
                    try:
                        decrypted_value = self.field._decrypt_value(value)
                        # Сохраняем дешифрованное значение обратно в instance.__dict__
                        instance.__dict__[self.attname] = decrypted_value
                        return decrypted_value
                    except Exception as e:
                        logger.debug(f"Ошибка автоматического дешифрования поля {self.attname}: {e}")
                
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
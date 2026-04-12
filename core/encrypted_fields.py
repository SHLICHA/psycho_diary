# psycho_diary/core/encrypted_fields.py
"""
Универсальные зашифрованные поля для Django моделей.

Все поля используют EncryptedFieldMixin для единой логики шифрования.
Поддерживаемые типы: CharField, TextField, EmailField, JSONField.

Использование:
    # Старый стиль (обратная совместимость):
    from core.encrypted_fields import EncryptedCharField, EncryptedTextField

    # Новый стиль (рекомендуется):
    from core.encrypted_fields import EncryptedField
    field = EncryptedField(max_length=200, field_type='char')
"""

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

# Кэш Fernet instance
_fernet_cache = None


def get_fernet_instance():
    """Получает экземпляр Fernet из настроек Django (с кэшированием)."""
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache

    key = getattr(settings, 'CRYPTOGRAPHY_KEY', None)
    if not key:
        raise exceptions.ImproperlyConfigured(
            "Для использования зашифрованных полей необходимо указать CRYPTOGRAPHY_KEY в settings.py"
        )
    if isinstance(key, str):
        key = key.encode('utf-8')
    _fernet_cache = Fernet(key)
    return _fernet_cache


def is_raw_value_encrypted(raw_value: Union[str, bytes, None]) -> Tuple[bool, str]:
    """
    Надежно проверяет, является ли сырое значение из БД уже зашифрованным.
    """
    if raw_value is None or raw_value == "":
        return True, "Пустое значение"

    fernet_instance = get_fernet_instance()

    if isinstance(raw_value, str) and raw_value.startswith('gAAAA'):
        return True, "Строка начинается с префикса Fernet"

    if isinstance(raw_value, str) and len(raw_value) > 50 and ' ' not in raw_value:
        try:
            base64.b64decode(raw_value)
            return True, "Длинная base64 строка без пробелов"
        except Exception:
            pass

    try:
        if isinstance(raw_value, bytes):
            fernet_instance.decrypt(raw_value)
            return True, "Байтовое значение успешно дешифровано"
        elif isinstance(raw_value, str):
            try:
                decoded_bytes = base64.b64decode(raw_value)
                fernet_instance.decrypt(decoded_bytes)
                return True, "Base64 строка успешно дешифрована"
            except (base64.binascii.Error, ValueError):
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
        """Шифрует значение перед сохранением в БД. Возвращает base64 строку."""
        if value is None or value == "":
            return value

        fernet_instance = get_fernet_instance()

        if not isinstance(value, str):
            value = json.dumps(value, cls=DjangoJSONEncoder)

        value_bytes = value.encode('utf-8')
        encrypted_bytes = fernet_instance.encrypt(value_bytes)
        return base64.b64encode(encrypted_bytes).decode('ascii')

    def get_db_prep_lookup(self, lookup_type, value, connection, prepared=False):
        """Подготавливает значение для поиска (фильтрации), шифруя его."""
        if lookup_type in ('exact', 'iexact'):
            encrypted_value = self.get_prep_value(value)
            prepared_encrypted_value = connection.ops.get_db_prep_value(
                encrypted_value, connection, prepared=False
            )
            return (prepared_encrypted_value,)
        else:
            logger.warning(f"[EncryptedFieldMixin] Lookup '{lookup_type}' is not supported.")
            raise NotImplementedError(
                f"Lookup '{lookup_type}' is not supported for EncryptedFieldMixin."
            )

    def from_db_value(self, value, expression, connection):
        """Дешифрует значение при загрузке из БД."""
        return self._decrypt_value(value)

    def _is_encrypted(self, value):
        """Определяет, зашифровано ли значение."""
        if value is None or value == "":
            return False
        if isinstance(value, bytes):
            return True
        if isinstance(value, str):
            if value.startswith('gAAAA'):
                return True
            if len(value) > 50 and ' ' not in value:
                try:
                    base64.b64decode(value)
                    return True
                except Exception:
                    return False
                try:
                    base64.b64decode(value)
                    return True
                except Exception:
                    pass
        return False

    def _decrypt_value(self, value):
        """Внутренний метод дешифровки."""
        if value is None or value == "":
            return value

        if not self._is_encrypted(value):
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
                        logger.debug(f"Не удалось дешифровать: {value[:50]}...")
                        return value
            else:
                return value

            decrypted_str = decrypted_bytes.decode('utf-8')

            if isinstance(self, models.JSONField):
                try:
                    return json.loads(decrypted_str)
                except json.JSONDecodeError:
                    return decrypted_str

            return decrypted_str
        except Exception as e:
            logger.debug(f"Ошибка дешифровки: {e}")
            return value

    def contribute_to_class(self, cls, name, **kwargs):
        """Добавляем дескриптор для автоматического дешифрования."""
        super().contribute_to_class(cls, name, **kwargs)

        class EncryptedFieldDescriptor:
            def __init__(self, field):
                self.field = field
                self.attname = field.attname

            def __get__(self, instance, owner):
                if instance is None:
                    return self
                value = instance.__dict__.get(self.attname)
                if value and self.field._is_encrypted(value):
                    try:
                        decrypted_value = self.field._decrypt_value(value)
                        instance.__dict__[self.attname] = decrypted_value
                        return decrypted_value
                    except Exception as e:
                        logger.debug(f"Ошибка авто-дешифрования {self.attname}: {e}")
                return value

            def __set__(self, instance, value):
                instance.__dict__[self.attname] = value

        setattr(cls, self.name, EncryptedFieldDescriptor(self))


# =============================================
# Унифицированное EncryptedField (рекомендуемый)
# =============================================

def EncryptedField(field_type='text', max_length=None, **kwargs):
    """
    Фабрика зашифрованных полей.

    Args:
        field_type: Тип поля ('char', 'text', 'email', 'json').
        max_length: Максимальная длина (для CharField).
        **kwargs: Дополнительные аргументы для поля.

    Returns:
        Зашифрованное поле Django.

    Примеры:
        EncryptedField(field_type='char', max_length=200)
        EncryptedField(field_type='json', default=dict)
        EncryptedField(field_type='text', blank=True)
    """
    field_map = {
        'char': models.CharField,
        'text': models.TextField,
        'email': models.EmailField,
        'json': models.JSONField,
    }

    if field_type not in field_map:
        raise ValueError(f"Неподдерживаемый тип поля: {field_type}. Допустимые: {list(field_map.keys())}")

    base_field_cls = field_map[field_type]

    field_kwargs = {}
    if field_type == 'char' and max_length:
        field_kwargs['max_length'] = max_length
    field_kwargs.update(kwargs)

    return type(
        f'Encrypted{field_type.capitalize()}Field',
        (EncryptedFieldMixin, base_field_cls),
        {}
    )(**field_kwargs)


# =============================================
# Классы для обратной совместимости
# =============================================

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
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return result
        return result

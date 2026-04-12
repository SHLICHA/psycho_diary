"""
Стандартизированный ответ от сервиса.
Унифицирует формат возврата данных во всех сервисах проекта.

Использование:
    # Успешный ответ с данными
    return ServiceResponse.ok(
        data={'entry': entry, 'analysis': analysis},
        message='Запись успешно создана'
    )

    # Успешный ответ без данных
    return ServiceResponse.ok(message='Настройки обновлены')

    # Ошибка
    return ServiceResponse.error(
        error='entry_not_found',
        message='Запись не найдена'
    )

    # Проверка в handler:
    if response.success:
        entry = response.data.get('entry')
    else:
        logger.error(f"Ошибка: {response.error} - {response.message}")
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List


@dataclass
class ServiceResponse:
    """Стандартизированный ответ от сервиса."""

    success: bool
    """True если операция выполнена успешно."""

    data: Optional[Any] = None
    """Полезные данные (словарь, объект, список и т.д.)."""

    error: Optional[str] = None
    """Код ошибки для логирования и обработки (например 'entry_not_found')."""

    message: Optional[str] = None
    """Текст сообщения для пользователя или логирования."""

    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    """Дополнительные метаданные (счётчики, флаги, пагинация и т.д.)."""

    @classmethod
    def ok(cls, data=None, message=None, **kwargs):
        """
        Создаёт успешный ответ.

        Args:
            data: Полезные данные.
            message: Сообщение об успехе.
            **kwargs: Дополнительные поля для metadata.

        Returns:
            ServiceResponse: Успешный ответ.
        """
        metadata = kwargs if kwargs else {}
        return cls(success=True, data=data, message=message, metadata=metadata)

    @classmethod
    def fail(cls, error: str, message=None, data=None, **kwargs):
        """
        Создаёт ответ с ошибкой.

        Args:
            error: Код ошибки (например 'entry_not_found').
            message: Текст сообщения об ошибке.
            data: Опциональные данные (например частично полученные).
            **kwargs: Дополнительные поля для metadata.

        Returns:
            ServiceResponse: Ответ с ошибкой.
        """
        metadata = kwargs if kwargs else {}
        return cls(success=False, error=error, message=message, data=data, metadata=metadata)

    # Алиас для обратной совместимости
    @classmethod
    def make_error(cls, error: str, message=None, data=None, **kwargs):
        """Алиас для fail() — для тех, кто привык вызывать error()."""
        return cls.fail(error=error, message=message, data=data, **kwargs)

    def is_error(self) -> bool:
        """Проверяет, является ли ответ ошибкой."""
        return not self.success

    def has_data(self) -> bool:
        """Проверяет, есть ли полезные данные."""
        return self.data is not None

    def get(self, key: str, default=None):
        """
        Удобное получение значения из data (если data — словарь).

        Args:
            key: Ключ для получения.
            default: Значение по умолчанию.

        Returns:
            Значение из data или default.
        """
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

    def __bool__(self):
        """ServiceResponse считается truthy если success=True."""
        return self.success


class ServiceResponseList:
    """
    Контейнер для списка ответов от сервисов.
    Удобно для батч-операций и агрегации результатов.
    """

    def __init__(self):
        self.responses: List[ServiceResponse] = []
        self.total_count: int = 0
        self.success_count: int = 0
        self.error_count: int = 0

    def add(self, response: ServiceResponse):
        """Добавляет ответ и обновляет счётчики."""
        self.responses.append(response)
        self.total_count += 1
        if response.success:
            self.success_count += 1
        else:
            self.error_count += 1

    @property
    def all_success(self) -> bool:
        """Все ли операции успешны."""
        return self.error_count == 0

    @property
    def errors(self) -> List[ServiceResponse]:
        """Список ответов с ошибками."""
        return [r for r in self.responses if not r.success]

    @property
    def successes(self) -> List[ServiceResponse]:
        """Список успешных ответов."""
        return [r for r in self.responses if r.success]

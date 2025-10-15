# /home/shlicha/psycho_diary/bot/utils/html_sanitizer.py
"""
Утилиты для санитизации HTML-разметки в сообщениях от ИИ.
"""

import logging
from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)

def sanitize_html(text: str, allowed_tags: set = None) -> str:
    """
    Санитизирует HTML-разметку в строке, удаляя или балансируя теги.
    Позволяет только определённые теги.

    Args:
        text (str): Входной текст с потенциально небезопасной разметкой.
        allowed_tags (set, optional): Множество разрешённых тегов. 
                                      По умолчанию {'b', 'i', 'u', 'em', 'strong'}.

    Returns:
        str: Очищенный текст с безопасной HTML-разметкой.
    """
    if allowed_tags is None:
        allowed_tags = {'b', 'i', 'u', 'em', 'strong'}

    try:
        # Создаём объект BeautifulSoup с 'lxml' парсером (быстрее и надёжнее для HTML)
        # Если lxml не установлен, можно использовать 'html.parser'
        soup = BeautifulSoup(text, 'html.parser') # Используем html.parser, он встроен и подходит для простых задач

        # Рекурсивно обходим все элементы (теги) в дереве
        for tag in soup.find_all(True): # find_all(True) находит все теги
            if tag.name not in allowed_tags:
                # Если тег не в списке разрешённых, заменяем его содержимым (unwrap)
                # unwrap() удаляет тег, оставляя его содержимое внутри родительского элемента
                tag.unwrap()
            # BeautifulSoup автоматически балансирует теги при парсинге и рендеринге
            # Например, <b>text<i></b></i> станет <b>text</b><i></i>
            # Но если теги в allowed_tags, они останутся, и их баланс будет корректным

        # Получаем очищенный HTML как строку
        sanitized_html = str(soup)
        logger.debug(f"HTML санитизирован. Разрешённые теги: {allowed_tags}.")
        return sanitized_html
    except Exception as e:
        logger.error(f"Ошибка при санитизации HTML: {e}. Возвращаем оригинальный текст.")
        # В случае любой ошибки санитизации (например, если BeautifulSoup не установлен)
        # возвращаем оригинальный текст, чтобы не ломать основной функционал.
        # Telegram сам обработает неправильный HTML, убрав его.
        return text

def strip_html(text: str) -> str:
    """
    Полностью удаляет HTML-теги из строки.

    Args:
        text (str): Входной текст с HTML-тегами.

    Returns:
        str: Текст без HTML-тегов.
    """
    try:
        soup = BeautifulSoup(text, 'html.parser')
        # get_text() извлекает текст, удаляя все теги
        stripped_text = soup.get_text()
        logger.debug("HTML-теги удалены.")
        return stripped_text
    except Exception as e:
        logger.error(f"Ошибка при удалении HTML: {e}. Возвращаем оригинальный текст.")
        return text
    
def sanitize_html_in_dict_or_string(obj, allowed_tags: set = None) -> any:
    """
    Рекурсивно обходит словарь или список и санитизирует HTML в строковых значениях.
    Если передан просто строкой, обрабатывает её.

    Args:
        obj (any): Словарь, список или строка для обработки.
        allowed_tags (set, optional): Множество разрешённых тегов.

    Returns:
        any: Объект той же структуры, но с санитизированной разметкой в строках.
    """
    if allowed_tags is None:
        allowed_tags = {'b', 'i', 'u', 'em', 'strong'}

    if isinstance(obj, str):
        # Санитизируем строку
        return sanitize_html(obj, allowed_tags=allowed_tags)
    elif isinstance(obj, dict):
        # Рекурсивно обрабатываем значения словаря
        return {key: sanitize_html_in_dict_or_string(value, allowed_tags) for key, value in obj.items()}
    elif isinstance(obj, list):
        # Рекурсивно обрабатываем элементы списка
        return [sanitize_html_in_dict_or_string(item, allowed_tags) for item in obj]
    else:
        # Возвращаем объект как есть, если он не строка, словарь или список
        return obj
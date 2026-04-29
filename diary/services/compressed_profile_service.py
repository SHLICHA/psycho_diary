"""
Сервис для генерации сжатого психологического профиля пользователя.

Использует heuristic-подход (без AI) для сжатия существующих
полей профиля в компактный формат, пригодный для LITE-анализов.

Структура compressed_psych_profile:
{
    "psych_summary": "Краткое описание личности (5-7 предложений)",
    "core_patterns": ["паттерн 1", "паттерн 2", ...],
    "emotional_style": "1 предложение об эмоциональном стиле",
    "main_triggers": ["триггер 1", ...],
    "coping_style": "1 предложение о стиле совладания",
    "current_focus": "текущий фокус внимания"
}
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Константы ────────────────────────────────────────────────────────

MAX_PATTERNS = 5          # Максимальное кол-во core_patterns
MAX_TRIGGERS = 5          # Максимальное кол-во main_triggers
MAX_SUMMARY_CHARS = 500   # Максимальная длина psych_summary
MIN_FIELDS_FOR_PROFILE = 1  # Мин. заполненных полей для генерации


# ─── Сервис ───────────────────────────────────────────────────────────

class CompressedProfileService:
    """
    Генерирует compressed_psych_profile из текущих полей User.

    Безопасен:
    - Только чтение из существующих полей
    - Запись только в compressed_psych_profile
    - Не удаляет и не модифицирует исходные данные
    - Обрабатывает отсутствующие поля gracefully
    """

    def generate_for_user(self, user) -> Optional[dict]:
        """
        Основной метод. Генерирует compressed профиль из полей User.

        Args:
            user: объект User (sync или async)

        Returns:
            dict с compressed профилем или None если данных недостаточно.
        """
        # Проверяем, достаточно ли данных
        filled_count = self._count_filled_fields(user)
        if filled_count < MIN_FIELDS_FOR_PROFILE:
            logger.debug(
                f"[CompressedProfile] User {user.telegram_id}: "
                f"недостаточно данных ({filled_count} полей), пропускаем"
            )
            return None

        psych_summary = self._build_psych_summary(user)
        core_patterns = self._extract_core_patterns(user)
        emotional_style = self._infer_emotional_style(user)
        main_triggers = self._extract_main_triggers(user)
        coping_style = self._infer_coping_style(user)
        current_focus = self._get_current_focus(user)

        result = {
            "psych_summary": psych_summary,
            "core_patterns": core_patterns,
            "emotional_style": emotional_style,
            "main_triggers": main_triggers,
            "coping_style": coping_style,
            "current_focus": current_focus,
        }

        logger.debug(
            f"[CompressedProfile] User {user.telegram_id}: "
            f"профиль сгенерирован (summary={len(psych_summary)} симв., "
            f"patterns={len(core_patterns)}, triggers={len(main_triggers)})"
        )
        return result

    # ─── Внутренние методы ────────────────────────────────────────────

    def _count_filled_fields(self, user) -> int:
        """Считает сколько профильных полей заполнено."""
        fields = [
            'personality_description',
            'personality_traits',
            'life_facts',
            'hobbies',
            'core_values',
            'triggers',
            'strengths',
            'areas_for_growth',
            'personality_insights',
            'practical_patterns',
            'aspirations',
        ]
        count = 0
        for field_name in fields:
            value = getattr(user, field_name, None)
            if value:
                if isinstance(value, (list, dict)) and len(value) > 0:
                    count += 1
                elif isinstance(value, str) and value.strip():
                    count += 1
        return count

    def _get_list_field(self, user, field_name: str) -> list:
        """Безопасно получает список из поля пользователя."""
        value = getattr(user, field_name, None)
        if isinstance(value, list):
            return value
        return []

    def _get_dict_field(self, user, field_name: str) -> dict:
        """Безопасно получает dict из поля пользователя."""
        value = getattr(user, field_name, None)
        if isinstance(value, dict):
            return value
        return {}

    def _get_text_field(self, user, field_name: str) -> str:
        """Безопасно получает текст из поля пользователя."""
        value = getattr(user, field_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    def _build_psych_summary(self, user) -> str:
        """
        Строит psych_summary из personality_description и ключевых полей.

        Если есть personality_description — берём его (обрезая).
        Если нет — собираем из traits, facts, values.
        """
        description = self._get_text_field(user, 'personality_description')
        if description:
            # Обрезаем до MAX_SUMMARY_CHARS по границе предложения/слова
            if len(description) <= MAX_SUMMARY_CHARS:
                return description
            truncated = description[:MAX_SUMMARY_CHARS]
            # Находим последнюю точку/запятую для красивого обрезания
            for sep in ['. ', '…', ', ']:
                last_sep = truncated.rfind(sep)
                if last_sep > MAX_SUMMARY_CHARS * 0.5:
                    return truncated[:last_sep + 1].strip()
            # Если не нашли — обрезаем по слову
            last_space = truncated.rfind(' ')
            if last_space > 0:
                return truncated[:last_space] + '…'
            return truncated + '…'

        # Нет description — собираем из полей
        parts = []

        # Черты характера
        traits = self._get_dict_field(user, 'personality_traits')
        if traits:
            top_traits = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:3]
            trait_names = [name for name, _ in top_traits]
            if trait_names:
                parts.append(f"Черты: {', '.join(trait_names)}.")

        # Факты о жизни
        facts = self._get_list_field(user, 'life_facts')
        if facts:
            parts.append(f"Факты: {', '.join(facts[:3])}.")

        # Ценности
        values = self._get_list_field(user, 'core_values')
        if values:
            parts.append(f"Ценности: {', '.join(values[:3])}.")

        if parts:
            result = ' '.join(parts)
            if len(result) > MAX_SUMMARY_CHARS:
                result = result[:MAX_SUMMARY_CHARS - 1] + '…'
            return result

        return ""

    def _extract_core_patterns(self, user) -> list:
        """
        Извлекает core_patterns из всех полей профиля.

        Берёт топ-N элементов из traits, insights, areas_for_growth,
        объединяет и обрезает до MAX_PATTERNS.
        """
        patterns = []

        # Черты характера (top-3 по весу)
        traits = self._get_dict_field(user, 'personality_traits')
        if traits:
            sorted_traits = sorted(traits.items(), key=lambda x: x[1], reverse=True)
            for name, weight in sorted_traits[:3]:
                if isinstance(weight, (int, float)) and weight > 0.5:
                    patterns.append(name)
                elif isinstance(weight, str):
                    patterns.append(name)  # строковые черты тоже берём

        # Глубинные инсайты
        insights = self._get_dict_field(user, 'personality_insights')
        if insights:
            for key, val in list(insights.items())[:2]:
                if isinstance(val, str) and val.strip():
                    patterns.append(val.strip())
                elif isinstance(val, dict) and val.get('text'):
                    patterns.append(val['text'])

        # Зоны роста
        areas = self._get_list_field(user, 'areas_for_growth')
        if areas:
            for item in areas[:2]:
                if isinstance(item, str) and item.strip():
                    patterns.append(item.strip())

        # Убираем дубликаты сохраняя порядок
        seen = set()
        unique_patterns = []
        for p in patterns:
            p_lower = p.lower()
            if p_lower not in seen and len(p) > 2:
                seen.add(p_lower)
                unique_patterns.append(p)

        return unique_patterns[:MAX_PATTERNS]

    def _infer_emotional_style(self, user) -> str:
        """
        Выводит эмоциональный стиль из триггеров, черт и зон роста.

        Эвристика на основе комбинаций полей.
        """
        triggers = self._get_list_field(user, 'triggers')
        traits = self._get_dict_field(user, 'personality_traits')
        areas = self._get_list_field(user, 'areas_for_growth')
        strengths = self._get_list_field(user, 'strengths')

        # Если данных мало — возвращаем общее описание
        has_triggers = len(triggers) > 0
        has_traits = len(traits) > 0
        has_areas = len(areas) > 0

        if not has_triggers and not has_traits and not has_areas:
            # Попробуем из description
            desc = self._get_text_field(user, 'personality_description').lower()
            if not desc:
                return ""

            # Простой анализ по ключевым словам
            emotional_words = [
                ('тревож', 'склонен к тревожности'),
                ('спокой', 'спокойный, уравновешенный тип'),
                ('эмоц', 'эмоционально отзывчивый'),
                ('сдержан', 'сдержанный в проявлениях эмоций'),
                ('радост', 'склонен к позитивному восприятию'),
                ('раздражен', 'склонен к раздражительности'),
                ('устал', 'склонен к быстрой утомляемости'),
                ('чувствител', 'высокочувствительный'),
            ]
            for word, style in emotional_words:
                if word in desc:
                    return style
            return "эмоциональный стиль требует дальнейшего наблюдения"

        # Анализируем триггеры
        trigger_words = set()
        for t in triggers:
            if isinstance(t, str):
                trigger_words.add(t.lower())
            elif isinstance(t, dict):
                val = t.get('value', t.get('text', ''))
                if isinstance(val, str):
                    trigger_words.add(val.lower())

        # Определяем паттерн по триггерам
        negative_triggers = {
            'критик', 'осужден', 'конфликт', 'агресс',
            'давлен', 'контрол', 'игнор', 'отвержен',
            'предатель', 'обман', 'страх', 'паник',
        }
        social_triggers = {
            'обществ', 'толп', 'выступлен', 'знаком',
            'публичн', 'люд', 'коллектив',
        }
        internal_triggers = {
            'самокрит', 'перфекцион', 'сомнен', 'вин',
            'стыд', 'неполноцен', 'одиноч',
        }

        has_neg = bool(trigger_words & negative_triggers)
        has_social = bool(trigger_words & social_triggers)
        has_internal = bool(trigger_words & internal_triggers)

        if has_neg and has_internal:
            return "склонен к внутреннему напряжению и самокритике"
        elif has_neg and has_social:
            return "испытывает напряжение в социальных ситуациях"
        elif has_internal:
            return "склонен к самоанализу и внутренним переживаниям"
        elif has_neg:
            return "чувствителен к внешним угрозам и давлению"

        # Анализируем зоны роста
        area_words = set()
        for a in areas:
            if isinstance(a, str):
                area_words.add(a.lower())

        growth_indicators = {
            'уверен': 'работает над уверенностью в себе',
            'тревож': 'учится справляться с тревожностью',
            'эмоц': 'развивает эмоциональную регуляцию',
            'границ': 'учится выстраивать личные границы',
            'принят': 'работает над принятием себя',
        }
        for word, style in growth_indicators.items():
            for area in area_words:
                if word in area:
                    return style

        # Если ничего не подошло — обобщаем из доступных данных
        if triggers:
            trigger_list = [t if isinstance(t, str) else str(t) for t in triggers[:3]]
            return f"триггеры: {', '.join(trigger_list)}"

        if traits:
            top_trait = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:2]
            trait_names = [name for name, _ in top_trait]
            return f"основные черты: {', '.join(trait_names)}"

        return ""

    def _extract_main_triggers(self, user) -> list:
        """
        Извлекает основные триггеры из поля triggers.

        Берёт до MAX_TRIGGERS, убирает дубликаты.
        """
        triggers_raw = self._get_list_field(user, 'triggers')
        result = []

        for item in triggers_raw:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
            elif isinstance(item, dict):
                val = item.get('value', item.get('text', ''))
                if isinstance(val, str) and val.strip():
                    result.append(val.strip())

        # Убираем дубликаты
        seen = set()
        unique = []
        for t in result:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                unique.append(t)

        return unique[:MAX_TRIGGERS]

    def _infer_coping_style(self, user) -> str:
        """
        Выводит стиль совладания из зон роста, сильных сторон и описания.
        """
        areas = self._get_list_field(user, 'areas_for_growth')
        strengths = self._get_list_field(user, 'strengths')
        desc = self._get_text_field(user, 'personality_description').lower()

        # Если есть сильные стороны — это ресурс coping
        strength_words = set()
        for s in strengths:
            if isinstance(s, str):
                strength_words.add(s.lower())

        # Определяем ресурсный стиль
        coping_resources = {
            'рефлекси': 'рефлексия и самоанализ',
            'осознан': 'осознанность и медитация',
            'спорт': 'физическая активность',
            'творчеств': 'творчество',
            'общен': 'общение и социальная поддержка',
            'чтен': 'чтение и самообразование',
            'юмор': 'чувство юмора',
            'планирован': 'планирование и организация',
            'анализ': 'анализ и логика',
            'помощ': 'обращение за поддержкой',
        }

        found_resources = []
        for word, resource in coping_resources.items():
            for strength in strength_words:
                if word in strength:
                    found_resources.append(resource)
                    break

        # Определяем проблемный стиль из зон роста
        area_words = set()
        for a in areas:
            if isinstance(a, str):
                area_words.add(a.lower())

        coping_challenges = {
            'избега': 'избегание',
            'контрол': 'контроль',
            'подавл': 'подавление эмоций',
            'рационализа': 'рационализация',
            'тревож': 'тревожность',
            'импульсив': 'импульсивность',
            'перфекцион': 'перфекционизм',
            'самокрит': 'самокритика',
        }

        found_challenges = []
        for word, challenge in coping_challenges.items():
            for area in area_words:
                if word in area:
                    found_challenges.append(challenge)
                    break

        # Формируем вывод
        if found_resources and found_challenges:
            return f"ресурсы: {', '.join(found_resources[:2])}; вызовы: {', '.join(found_challenges[:2])}"
        elif found_resources:
            return f"основные ресурсы: {', '.join(found_resources[:2])}"
        elif found_challenges:
            return f"области работы: {', '.join(found_challenges[:2])}"

        # Fallback: анализ по description
        if desc:
            fallback_patterns = {
                'избега': 'склонен к избеганию',
                'стараюсь не': 'склонен к избеганию',
                'предпочитаю один': 'предпочитает уединение для восстановления',
                'стараюсь справ': 'старается справляться самостоятельно',
                'пытаюсь поня': 'склонен к рефлексии и анализу',
                'думаю о': 'склонен к размышлениям',
                'медита': 'использует медитацию/осознанность',
                'спорт': 'использует физическую активность',
            }
            for word, style in fallback_patterns.items():
                if word in desc:
                    return style

        return ""

    def _get_current_focus(self, user) -> str:
        """
        Определяет текущий фокус внимания пользователя.

        На основе фактов жизни, стремлений, зон роста.
        """
        facts = self._get_list_field(user, 'life_facts')
        aspirations = self._get_list_field(user, 'aspirations')
        areas = self._get_list_field(user, 'areas_for_growth')

        # Берём самый свежий/актуальный элемент
        # Приоритет: стремления → факты → зоны роста
        if aspirations:
            item = aspirations[0]
            if isinstance(item, str) and item.strip():
                return item.strip()
            elif isinstance(item, dict):
                val = item.get('value', item.get('text', ''))
                if isinstance(val, str) and val.strip():
                    return val.strip()

        if facts:
            item = facts[-1]  # Последний добавленный факт — самый свежий
            if isinstance(item, str) and item.strip():
                return item.strip()
            elif isinstance(item, dict):
                val = item.get('value', item.get('text', ''))
                if isinstance(val, str) and val.strip():
                    return val.strip()

        if areas:
            item = areas[0]
            if isinstance(item, str) and item.strip():
                return item.strip()

        return ""

    async def save_for_user_async(self, user, profile_data: dict) -> bool:
        """
        Сохраняет compressed профиль в пользователя (async).

        Args:
            user: объект User
            profile_data: dict с compressed профилем

        Returns:
            True если сохранено, False если данные не валидны.
        """
        if not profile_data or not isinstance(profile_data, dict):
            logger.warning(f"[CompressedProfile] User {user.telegram_id}: невалидные данные для сохранения")
            return False

        # Валидация структуры
        required_keys = {
            'psych_summary', 'core_patterns', 'emotional_style',
            'main_triggers', 'coping_style', 'current_focus'
        }
        missing = required_keys - set(profile_data.keys())
        if missing:
            logger.warning(
                f"[CompressedProfile] User {user.telegram_id}: "
                f"отсутствуют ключи: {missing}"
            )
            return False

        try:
            from django.db import transaction

            @sync_to_async
            def _do_save():
                with transaction.atomic():
                    user.compressed_psych_profile = profile_data
                    user.save(update_fields=['compressed_psych_profile'])

            await _do_save()
            # Обновляем и оригинальный объект
            user.compressed_psych_profile = profile_data
            logger.info(
                f"[CompressedProfile] User {user.telegram_id}: "
                f"compressed_psych_profile сохранён"
            )
            return True
        except Exception as e:
            logger.error(
                f"[CompressedProfile] User {user.telegram_id}: "
                f"ошибка сохранения: {e}",
                exc_info=True
            )
            return False


# ─── Модуль-level singleton ──────────────────────────────────────────

compressed_profile_service = CompressedProfileService()


async def generate_compressed_profile_for_user(user) -> Optional[dict]:
    """
    Удобная async-функция: генерирует и сохраняет compressed профиль.

    Args:
        user: объект User

    Returns:
        dict с compressed профилем или None.
    """
    service = compressed_profile_service
    profile = service.generate_for_user(user)
    if profile:
        await service.save_for_user_async(user, profile)
    return profile

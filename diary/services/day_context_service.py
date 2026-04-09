"""
Сервис для генерации day_context_summary из DailyAnalysis.

Перепаковывает данные из DailyAnalysis + CombinedDiaryEntry
в компактный формат, пригодный для LITE-анализов.

Структура day_context_summary:
{
    "emotional_arc": "7 → 5 → 3 → 4",
    "key_topics": ["работа", "самооценка"],
    "main_conflict": "ожидания vs реальность",
    "dominant_pattern": "катастрофизация",
    "trend": "declining"
}
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Константы ────────────────────────────────────────────────────────

MAX_KEY_TOPICS = 3         # Максимальное кол-во key_topics
MAX_MOOD_SCORES_IN_ARC = 10  # Максимум оценок в emotional_arc


# ─── Сервис ───────────────────────────────────────────────────────────

class DayContextService:
    """
    Генерирует day_context_summary из DailyAnalysis / CombinedDiaryEntry.

    Безопасен:
    - Только чтение из существующих полей
    - Запись только в day_context_summary
    - Не удаляет и не модифицирует исходные данные
    - Без AI, чистая перепаковка
    """

    def generate_from_daily_analysis(self, daily_analysis) -> Optional[dict]:
        """
        Генерирует day_context_summary из DailyAnalysis.

        Args:
            daily_analysis: объект DailyAnalysis (связанный с CombinedDiaryEntry)

        Returns:
            dict с day_context_summary или None если данных нет.
        """
        if not daily_analysis:
            return None

        combined_entry = getattr(daily_analysis, 'combined_entry', None)
        if not combined_entry:
            return None

        mood_trend = getattr(daily_analysis, 'mood_trend', '') or ''
        key_themes = self._get_list_field(daily_analysis, 'key_themes')
        emotional_patterns = self._get_list_field(daily_analysis, 'emotional_patterns')
        insights = self._get_list_field(daily_analysis, 'insights')

        mood_scores = getattr(combined_entry, 'daily_mood_scores', []) or []

        emotional_arc = self._build_emotional_arc(mood_scores)
        key_topics = self._extract_key_topics(key_themes)
        main_conflict = self._infer_main_conflict(key_themes, emotional_patterns)
        dominant_pattern = self._extract_dominant_pattern(emotional_patterns, insights)
        trend = mood_trend if mood_trend else self._infer_trend(mood_scores)

        result = {
            "emotional_arc": emotional_arc,
            "key_topics": key_topics,
            "main_conflict": main_conflict,
            "dominant_pattern": dominant_pattern,
            "trend": trend,
        }

        logger.debug(
            f"[DayContext] DailyAnalysis ID {daily_analysis.pk}: "
            f"сгенерировано day_context_summary (arc={emotional_arc}, "
            f"topics={len(key_topics)}, conflict={bool(main_conflict)})"
        )
        return result

    def generate_from_combined_entry(self, combined_entry) -> Optional[dict]:
        """
        Генерирует day_context_summary из CombinedDiaryEntry без DailyAnalysis.

        Использует mood_scores, ai_state_data, analysis_result как fallback.

        Args:
            combined_entry: объект CombinedDiaryEntry

        Returns:
            dict с day_context_summary или None если данных нет.
        """
        if not combined_entry:
            return None

        mood_scores = getattr(combined_entry, 'daily_mood_scores', []) or []
        average_mood = getattr(combined_entry, 'average_mood_score', 0.0) or 0.0
        ai_state_data = getattr(combined_entry, 'ai_state_data', '') or ''
        analysis_result = getattr(combined_entry, 'analysis_result', {}) or {}

        if not mood_scores and not ai_state_data and not analysis_result:
            return None

        emotional_arc = self._build_emotional_arc(mood_scores)
        key_topics = self._extract_topics_from_analysis_result(analysis_result)
        main_conflict = ""
        dominant_pattern = ""
        trend = self._infer_trend(mood_scores)

        # Если есть ai_state_data — попробуем извлечь оттуда
        if ai_state_data:
            ai_pattern = self._extract_pattern_from_ai_state(ai_state_data)
            if ai_pattern:
                dominant_pattern = ai_pattern

        result = {
            "emotional_arc": emotional_arc,
            "key_topics": key_topics,
            "main_conflict": main_conflict,
            "dominant_pattern": dominant_pattern,
            "trend": trend,
        }

        logger.debug(
            f"[DayContext] CombinedDiaryEntry ID {combined_entry.pk}: "
            f"сгенерировано day_context_summary из fallback данных"
        )
        return result

    # ─── Внутренние методы ────────────────────────────────────────────

    def _get_list_field(self, obj, field_name: str) -> list:
        """Безопасно получает список из поля объекта."""
        value = getattr(obj, field_name, None)
        if isinstance(value, list):
            return value
        return []

    def _build_emotional_arc(self, mood_scores: list) -> str:
        """
        Строит строку эмоциональной дуги.

        Пример: "7 → 5 → 3 → 6 → 4"
        """
        if not mood_scores:
            return ""

        # Берём последние N оценок
        scores = mood_scores[-MAX_MOOD_SCORES_IN_ARC:]

        # Округляем до int
        int_scores = []
        for s in scores:
            try:
                int_scores.append(int(round(float(s))))
            except (ValueError, TypeError):
                pass

        if not int_scores:
            return ""

        return ' → '.join(str(s) for s in int_scores)

    def _extract_key_topics(self, key_themes: list) -> list:
        """
        Извлекает ключевые темы из DailyAnalysis.key_themes.

        Поддерживает форматы:
        - ["тема 1", "тема 2"] (старый формат)
        - [{"theme": "...", "mentions": N, "significance": S}] (новый)
        """
        topics = []
        for item in key_themes:
            if isinstance(item, str) and item.strip():
                topics.append(item.strip())
            elif isinstance(item, dict):
                theme = item.get('theme', item.get('text', ''))
                if isinstance(theme, str) and theme.strip():
                    topics.append(theme.strip())

        # Убираем дубликаты сохраняя порядок
        seen = set()
        unique = []
        for t in topics:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                unique.append(t)

        return unique[:MAX_KEY_TOPICS]

    def _extract_topics_from_analysis_result(self, analysis_result: dict) -> list:
        """
        Извлекает темы из analysis_result CombinedDiaryEntry.

        analysis_result может содержать mood_score, comment, recommendation.
        """
        if not isinstance(analysis_result, dict):
            return []

        topics = []
        for key in ['key_themes', 'themes', 'topics']:
            val = analysis_result.get(key)
            if isinstance(val, list):
                topics.extend(self._extract_key_topics(val))
                break

        return topics[:MAX_KEY_TOPICS]

    def _infer_main_conflict(self, key_themes: list, emotional_patterns: list) -> str:
        """
        Выводит основной конфликт из тем и эмоций.

        Эвристика: ищет противоречивые/конфликтные элементы.
        """
        conflict_indicators = {
            'конфликт': 'внутренний конфликт',
            'проблем': 'столкновение с проблемами',
            'спор': 'конфликтная ситуация',
            'ссор': 'межличностный конфликт',
            'тревог': 'тревожность и неопределённость',
            'страх': 'страх и неуверенность',
            'сомнен': 'внутренние сомнения',
            'вин': 'чувство вины',
            'обид': 'обида и несправедливость',
            'одиноч': 'чувство одиночества',
            'устал': 'эмоциональное выгорание',
            'давлен': 'давление извне',
            'непониман': 'непонимание и разрыв коммуникации',
        }

        # Собираем все тексты для анализа
        all_texts = []
        for item in key_themes:
            if isinstance(item, str):
                all_texts.append(item.lower())
            elif isinstance(item, dict):
                val = item.get('theme', item.get('text', '')).lower()
                if val:
                    all_texts.append(val)

        for item in emotional_patterns:
            if isinstance(item, str):
                all_texts.append(item.lower())
            elif isinstance(item, dict):
                val = item.get('emotion', item.get('context', '')).lower()
                if val:
                    all_texts.append(val)

        # Ищем индикаторы конфликта
        for indicator, conflict_type in conflict_indicators.items():
            for text in all_texts:
                if indicator in text:
                    return conflict_type

        return ""

    def _extract_dominant_pattern(self, emotional_patterns: list, insights: list) -> str:
        """
        Извлекает доминирующий паттерн.

        Приоритет: первый элемент emotional_patterns → первый insight.
        """
        # Из emotional_patterns
        for item in emotional_patterns:
            if isinstance(item, str) and item.strip():
                return item.strip()
            elif isinstance(item, dict):
                # Может быть {"emotion": "...", "frequency": N, "context": "..."}
                emotion = item.get('emotion', '')
                context = item.get('context', '')
                if emotion:
                    parts = [emotion]
                    if context:
                        parts.append(context)
                    return ' — '.join(parts)

        # Из insights
        for item in insights:
            if isinstance(item, str) and item.strip():
                return item.strip()[:100]  # Обрезаем если слишком длинный
            elif isinstance(item, dict):
                text = item.get('text', '')
                if isinstance(text, str) and text.strip():
                    return text.strip()[:100]

        return ""

    def _extract_pattern_from_ai_state(self, ai_state_data: str) -> str:
        """
        Извлекает паттерн из ai_state_data (строка, может быть JSON).

        ai_state_data — текстовое поле, может содержать структурированные данные.
        """
        if not ai_state_data or len(ai_state_data) < 5:
            return ""

        # Берём первые 200 символов как краткое описание
        text = ai_state_data.strip()[:200]

        # Если это похоже на JSON — попробуем распарсить
        if text.startswith('{'):
            import json
            try:
                data = json.loads(ai_state_data)
                # Ищем паттерн в известных полях
                for key in ['dominant_pattern', 'pattern', 'dominant_emotion']:
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            except (json.JSONDecodeError, ValueError):
                pass

        # Иначе возвращаем текст как есть (обрезая)
        return text

    def _infer_trend(self, mood_scores: list) -> str:
        """
        Определяет тренд из оценок настроения.

        Возвращает: 'improving', 'declining', 'stable', 'volatile', ''
        """
        if len(mood_scores) < 2:
            return ""

        # Берём последние 5 оценок
        scores = [float(s) for s in mood_scores[-5:] if self._is_numeric(s)]
        if len(scores) < 2:
            return ""

        first_half = scores[:len(scores) // 2]
        second_half = scores[len(scores) // 2:]

        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        diff = avg_second - avg_first

        # Определяем волатильность
        max_score = max(scores)
        min_score = min(scores)
        volatility = max_score - min_score

        if volatility > 4:
            return "volatile"
        elif diff > 1.0:
            return "improving"
        elif diff < -1.0:
            return "declining"
        else:
            return "stable"

    def _is_numeric(self, value) -> bool:
        """Проверяет что значение числовое."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False


# ─── Модуль-level singleton ──────────────────────────────────────────

day_context_service = DayContextService()


async def generate_day_context_for_combined_entry(combined_entry) -> Optional[dict]:
    """
    Удобная async-функция: генерирует day_context_summary из CombinedDiaryEntry.

    Пробует сначала через DailyAnalysis, затем fallback.

    Args:
        combined_entry: объект CombinedDiaryEntry

    Returns:
        dict с day_context_summary или None.
    """
    service = day_context_service

    # Пробуем через DailyAnalysis
    daily_analysis = getattr(combined_entry, 'daily_analysis', None)
    if daily_analysis:
        result = service.generate_from_daily_analysis(daily_analysis)
        if result:
            return result

    # Fallback: из данных CombinedDiaryEntry
    return service.generate_from_combined_entry(combined_entry)

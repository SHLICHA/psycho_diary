"""
Сервис для генерации полного психологического профиля пользователя.

Генерирует human-readable профиль для отображения пользователю в web-интерфейсе.
Использует данные из полей User и результаты weekly analysis.

Структура full_psych_profile:
{
    "summary": "Общее описание личности (2-3 абзаца)",
    "traits": [{"name": "черта", "weight": 0.8, "description": "описание"}],
    "values": [{"value": "ценность", "importance": "высокая"}],
    "triggers": [{"value": "триггер", "intensity": "высокая", "description": "описание"}],
    "strengths": [{"name": "сила", "description": "описание"}],
    "growth_areas": [{"area": "зона", "description": "описание"}],
    "insights": [{"text": "инсайт", "date": "2026-01-01"}],
    "habits": [{"name": "привычка", "frequency": "часто"}],
    "skills": [{"name": "навык", "level": "высокий"}],
    "aspirations": [{"text": "стремление", "priority": "высокая"}],
    "emotional_pattern": "описание эмоционального паттерна",
    "coping_style": "описание стиля совладания",
    "last_updated": "2026-04-17"
}
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class FullProfileService:
    """
    Генерирует полный психологический профиль из полей User.
    
    Используется для:
    - Отображения профиля в web-интерфейсе
    - Еженедельного обновления профиля
    """

    def generate_for_user(self, user) -> Dict[str, Any]:
        """
        Основной метод. Генерирует полный профиль из полей User.
        
        Args:
            user: объект User (sync или async)
            
        Returns:
            dict с полным профилем для пользователя.
        """
        logger.debug(f"[FullProfile] Начало генерации для пользователя {user.telegram_id}")
        
        profile = {
            "summary": self._build_summary(user),
            "traits": self._format_traits(user),
            "values": self._format_values(user),
            "triggers": self._format_triggers(user),
            "strengths": self._format_strengths(user),
            "growth_areas": self._format_growth_areas(user),
            "insights": self._format_insights(user),
            "habits": self._format_habits(user),
            "skills": self._format_skills(user),
            "aspirations": self._format_aspirations(user),
            "emotional_pattern": self._infer_emotional_pattern(user),
            "coping_style": self._infer_coping_style(user),
            "last_updated": datetime.now().date().isoformat()
        }
        
        logger.debug(f"[FullProfile] Профиль сгенерирован для {user.telegram_id}")
        return profile

    # ─── Приватные методы ─────────────────────────────────────────────

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

    def _build_summary(self, user) -> str:
        """
        Строит общее описание личности.
        Использует personality_description или собирает из полей.
        """
        description = self._get_text_field(user, 'personality_description')
        if description:
            return description
        
        # Собираем из полей если нет description
        parts = []
        
        # Черты
        traits = self._get_dict_field(user, 'personality_traits')
        if traits:
            top = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:3]
            if top:
                parts.append(f"Основные черты: {', '.join([n for n, _ in top])}.")
        
        # Ценности
        values = self._get_list_field(user, 'core_values')
        if values:
            parts.append(f"Ценности: {', '.join(values[:3])}.")
        
        # Сильные стороны
        strengths = self._get_list_field(user, 'strengths')
        if strengths:
            parts.append(f"Сильные стороны: {', '.join(strengths[:3])}.")
        
        if parts:
            return ' '.join(parts)
        
        return "Профиль в процессе формирования. Продолжайте вести дневник для получения более точного описания."

    def _format_traits(self, user) -> List[Dict[str, Any]]:
        """Форматирует черты характера."""
        traits = self._get_dict_field(user, 'personality_traits')
        result = []
        for name, weight in traits.items():
            if isinstance(weight, (int, float)):
                level = "высокая" if weight > 0.7 else "средняя" if weight > 0.4 else "низкая"
                result.append({
                    "name": name,
                    "weight": weight,
                    "level": level,
                    "description": f"Выраженность: {int(weight * 100)}%"
                })
            elif isinstance(weight, str):
                result.append({
                    "name": name,
                    "weight": 0.5,
                    "level": "средняя",
                    "description": weight
                })
        return result

    def _format_values(self, user) -> List[Dict[str, Any]]:
        """Форматирует ценности."""
        values = self._get_list_field(user, 'core_values')
        result = []
        for v in values:
            if isinstance(v, str):
                result.append({
                    "value": v,
                    "importance": "высокая",
                    "description": "Определено на основе анализа записей"
                })
            elif isinstance(v, dict):
                result.append({
                    "value": v.get('value', v.get('text', '')),
                    "importance": v.get('importance', 'средняя'),
                    "description": v.get('description', '')
                })
        return result

    def _format_triggers(self, user) -> List[Dict[str, Any]]:
        """Форматирует триггеры."""
        triggers = self._get_list_field(user, 'triggers')
        result = []
        for t in triggers:
            if isinstance(t, str):
                result.append({
                    "value": t,
                    "intensity": "средняя",
                    "description": "Выявлен на основе анализа записей"
                })
            elif isinstance(t, dict):
                result.append({
                    "value": t.get('value', t.get('text', '')),
                    "intensity": t.get('intensity', t.get('strength', 'средняя')),
                    "description": t.get('description', '')
                })
        return result

    def _format_strengths(self, user) -> List[Dict[str, Any]]:
        """Форматирует сильные стороны."""
        strengths = self._get_list_field(user, 'strengths')
        result = []
        for s in strengths:
            if isinstance(s, str):
                result.append({
                    "name": s,
                    "description": "Подтверждено анализом записей"
                })
            elif isinstance(s, dict):
                result.append({
                    "name": s.get('name', s.get('text', '')),
                    "description": s.get('description', '')
                })
        return result

    def _format_growth_areas(self, user) -> List[Dict[str, Any]]:
        """Форматирует зоны роста."""
        areas = self._get_list_field(user, 'areas_for_growth')
        result = []
        for a in areas:
            if isinstance(a, str):
                result.append({
                    "area": a,
                    "description": "Выявлено на основе анализа"
                })
            elif isinstance(a, dict):
                result.append({
                    "area": a.get('area', a.get('text', '')),
                    "description": a.get('description', '')
                })
        return result

    def _format_insights(self, user) -> List[Dict[str, Any]]:
        """Форматирует инсайты."""
        insights = self._get_dict_field(user, 'personality_insights')
        result = []
        for key, val in insights.items():
            if isinstance(val, str):
                result.append({
                    "text": val,
                    "category": key,
                    "date": ""
                })
            elif isinstance(val, dict):
                result.append({
                    "text": val.get('text', val.get('description', '')),
                    "category": key,
                    "date": val.get('date', '')
                })
        return result

    def _format_habits(self, user) -> List[Dict[str, Any]]:
        """Форматирует привычки."""
        habits = self._get_list_field(user, 'habits')
        result = []
        for h in habits:
            if isinstance(h, str):
                result.append({
                    "name": h,
                    "frequency": "регулярно",
                    "description": "Выявлено на основе анализа записей"
                })
            elif isinstance(h, dict):
                result.append({
                    "name": h.get('name', h.get('text', '')),
                    "frequency": h.get('frequency', 'регулярно'),
                    "description": h.get('description', '')
                })
        return result

    def _format_skills(self, user) -> List[Dict[str, Any]]:
        """Форматирует навыки."""
        skills = self._get_list_field(user, 'skills')
        result = []
        for s in skills:
            if isinstance(s, str):
                result.append({
                    "name": s,
                    "level": "развитый",
                    "description": "Выявлено на основе анализа"
                })
            elif isinstance(s, dict):
                result.append({
                    "name": s.get('name', s.get('text', '')),
                    "level": s.get('level', 'развитый'),
                    "description": s.get('description', '')
                })
        return result

    def _format_aspirations(self, user) -> List[Dict[str, Any]]:
        """Форматирует стремления."""
        aspirations = self._get_list_field(user, 'aspirations')
        result = []
        for a in aspirations:
            if isinstance(a, str):
                result.append({
                    "text": a,
                    "priority": "средняя",
                    "description": "Выявлено на основе анализа"
                })
            elif isinstance(a, dict):
                result.append({
                    "text": a.get('text', a.get('value', '')),
                    "priority": a.get('priority', 'средняя'),
                    "description": a.get('description', '')
                })
        return result

    def _infer_emotional_pattern(self, user) -> str:
        """Выводит эмоциональный паттерн."""
        # Используем существующую логику из compressed_profile_service
        triggers = self._get_list_field(user, 'triggers')
        traits = self._get_dict_field(user, 'personality_traits')
        
        if not triggers and not traits:
            return "Эмоциональный паттерн формируется. Продолжайте вести дневник."
        
        # Простая эвристика
        trigger_words = set()
        for t in triggers:
            if isinstance(t, str):
                trigger_words.add(t.lower())
        
        if 'тревог' in ' '.join(trigger_words) or 'страх' in ' '.join(trigger_words):
            return "Склонность к тревожным состояниям. Важно работать с источниками беспокойства."
        elif 'раздражен' in ' '.join(trigger_words):
            return "Эмоциональная реактивность. Работа над саморегуляцией может быть полезной."
        elif 'грусть' in ' '.join(trigger_words) or 'печаль' in ' '.join(trigger_words):
            return "Склонность к меланхоличным состояниям. Поддержка и самопринятие важны."
        
        return "Эмоциональный паттерн стабильный. Продолжайте наблюдать за своим состоянием."

    def _infer_coping_style(self, user) -> str:
        """Выводит стиль совладания."""
        strengths = self._get_list_field(user, 'strengths')
        habits = self._get_list_field(user, 'habits')
        
        if not strengths and not habits:
            return "Стиль совладания формируется."
        
        # Простая эвристика
        all_items = ' '.join(strengths + habits).lower()
        
        if 'спорт' in all_items or 'физич' in all_items:
            return "Активный стиль. Предпочитает физическую активность для снятия стресса."
        elif 'анализ' in all_items or 'рефлекс' in all_items:
            return "Аналитический стиль. Склонен анализировать ситуации для поиска решений."
        elif 'творчеств' in all_items or 'музык' in all_items:
            return "Творческий стиль. Использует творчество для эмоциональной регуляции."
        elif 'социаль' in all_items or 'общен' in all_items:
            return "Социальный стиль. Предпочитает обсуждать проблемы с близкими."
        
        return "Индивидуальный стиль совладания. Продолжайте наблюдать за своими стратегиями."


# ─── Экспорт ──────────────────────────────────────────────────────────

full_profile_service = FullProfileService()


def generate_full_profile(user) -> Dict[str, Any]:
    """
    Удобная функция для генерации полного профиля.
    
    Args:
        user: объект User
        
    Returns:
        dict с полным профилем.
    """
    return full_profile_service.generate_for_user(user)
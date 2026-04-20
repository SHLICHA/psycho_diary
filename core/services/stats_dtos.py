"""
Data Transfer Objects (DTOs) for statistics API.
Used for serialization of statistics metrics to API responses.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class AICallMetrics:
    """Метрики вызовов AI."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_used: int = 0
    avg_latency_ms: float = 0.0
    retry_count: int = 0
    error_rate: float = 0.0  # percentage
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OnboardingFunnelMetrics:
    """Метрики воронки онбординга."""
    started_count: int = 0  # Users who started bot
    registered_count: int = 0  # Users who registered
    first_entry_count: int = 0  # Users who created first entry
    completed_profile_count: int = 0  # Users who completed profile
    
    # Conversion coefficients
    register_conversion: float = 0.0  # started -> registered
    first_entry_conversion: float = 0.0  # registered -> first_entry
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetentionMetrics:
    """Метрики удержания и активности."""
    daily_active_users: int = 0
    weekly_active_users: int = 0
    monthly_active_users: int = 0
    
    # Streak metrics
    users_with_active_streak: int = 0
    avg_streak_length: float = 0.0
    max_streak_length: int = 0
    users_recovered_streak: int = 0
    
    # Churn metrics
    churned_users_7d: int = 0
    returned_users_7d: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskMetrics:
    """Метрики выполнения задач."""
    total_tasks_created: int = 0
    total_tasks_completed: int = 0
    completion_rate: float = 0.0  # percentage
    avg_completion_time_hours: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntryMetrics:
    """Метрики записей в дневник."""
    total_entries: int = 0
    processed_entries: int = 0
    failed_entries: int = 0
    avg_processing_time_ms: float = 0.0
    
    entries_with_clarifications: int = 0
    avg_clarifications_per_entry: float = 0.0
    
    user_comments_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserEngagementMetrics:
    """Метрики вовлеченности пользователя."""
    avg_entries_per_user: float = 0.0
    avg_tasks_per_user: float = 0.0
    users_with_premium: int = 0
    premium_conversion_rate: float = 0.0  # percentage
    
    total_tokens_purchased: int = 0
    avg_tokens_per_user: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailyStatsSnapshot:
    """Снимок ежедневной статистики."""
    date: str  # ISO format
    dau: int  # Daily Active Users
    entries_created: int
    entries_processed: int
    tasks_completed: int
    ai_calls: int
    ai_tokens_used: int
    ai_avg_latency_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComprehensiveStatsDTO:
    """Комплексный DTO для API-выдачи всей статистики."""
    timestamp: str  # ISO format
    period: str  # "daily", "weekly", "monthly"
    
    ai_metrics: AICallMetrics = field(default_factory=AICallMetrics)
    onboarding: OnboardingFunnelMetrics = field(default_factory=OnboardingFunnelMetrics)
    retention: RetentionMetrics = field(default_factory=RetentionMetrics)
    tasks: TaskMetrics = field(default_factory=TaskMetrics)
    entries: EntryMetrics = field(default_factory=EntryMetrics)
    engagement: UserEngagementMetrics = field(default_factory=UserEngagementMetrics)
    
    daily_snapshots: List[DailyStatsSnapshot] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'period': self.period,
            'ai_metrics': self.ai_metrics.to_dict(),
            'onboarding': self.onboarding.to_dict(),
            'retention': self.retention.to_dict(),
            'tasks': self.tasks.to_dict(),
            'entries': self.entries.to_dict(),
            'engagement': self.engagement.to_dict(),
            'daily_snapshots': [s.to_dict() for s in self.daily_snapshots],
        }


@dataclass
class StatsQuery:
    """Параметры запроса статистики."""
    period: str = "daily"  # "daily", "weekly", "monthly"
    days_back: int = 7  # How many days back to look
    include_daily_snapshots: bool = False
    
    def validate(self) -> bool:
        """Validate query parameters."""
        return (
            self.period in ("daily", "weekly", "monthly")
            and 0 < self.days_back <= 365
        )

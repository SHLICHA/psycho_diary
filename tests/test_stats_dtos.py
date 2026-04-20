"""
Unit tests for Stats Service and DTOs.
"""
import pytest
from datetime import datetime, timedelta
from core.services.stats_dtos import (
    AICallMetrics, OnboardingFunnelMetrics, RetentionMetrics,
    TaskMetrics, EntryMetrics, UserEngagementMetrics,
    DailyStatsSnapshot, ComprehensiveStatsDTO, StatsQuery
)


class TestAICallMetrics:
    """Tests for AICallMetrics DTO."""
    
    def test_creation_default_values(self):
        """AICallMetrics should initialize with default values."""
        metrics = AICallMetrics()
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0
        assert metrics.total_tokens_used == 0
        assert metrics.error_rate == 0.0
    
    def test_creation_with_values(self):
        """AICallMetrics should accept custom values."""
        metrics = AICallMetrics(
            total_calls=100,
            successful_calls=95,
            failed_calls=5,
            error_rate=5.0
        )
        assert metrics.total_calls == 100
        assert metrics.successful_calls == 95
        assert metrics.failed_calls == 5
        assert metrics.error_rate == 5.0
    
    def test_to_dict(self):
        """AICallMetrics.to_dict() should return proper dictionary."""
        metrics = AICallMetrics(total_calls=50, successful_calls=45)
        data = metrics.to_dict()
        
        assert isinstance(data, dict)
        assert data['total_calls'] == 50
        assert data['successful_calls'] == 45


class TestOnboardingFunnelMetrics:
    """Tests for OnboardingFunnelMetrics DTO."""
    
    def test_conversion_calculation(self):
        """Conversion rates should be properly stored."""
        metrics = OnboardingFunnelMetrics(
            started_count=100,
            registered_count=80,
            first_entry_count=60,
            register_conversion=80.0,
            first_entry_conversion=75.0
        )
        assert metrics.register_conversion == 80.0
        assert metrics.first_entry_conversion == 75.0
    
    def test_to_dict_includes_all_fields(self):
        """to_dict() should include all fields."""
        metrics = OnboardingFunnelMetrics(
            started_count=100,
            registered_count=80,
            completed_profile_count=50
        )
        data = metrics.to_dict()
        
        assert 'started_count' in data
        assert 'registered_count' in data
        assert 'completed_profile_count' in data


class TestRetentionMetrics:
    """Tests for RetentionMetrics DTO."""
    
    def test_activity_metrics(self):
        """Activity metrics should be properly stored."""
        metrics = RetentionMetrics(
            daily_active_users=100,
            weekly_active_users=250,
            monthly_active_users=500
        )
        assert metrics.daily_active_users == 100
        assert metrics.weekly_active_users == 250
        assert metrics.monthly_active_users == 500
    
    def test_streak_metrics(self):
        """Streak metrics should be properly stored."""
        metrics = RetentionMetrics(
            users_with_active_streak=200,
            avg_streak_length=7.5,
            max_streak_length=365
        )
        assert metrics.users_with_active_streak == 200
        assert metrics.avg_streak_length == 7.5
        assert metrics.max_streak_length == 365


class TestTaskMetrics:
    """Tests for TaskMetrics DTO."""
    
    def test_completion_rate_calculation(self):
        """Completion rate should be properly stored."""
        metrics = TaskMetrics(
            total_tasks_created=100,
            total_tasks_completed=75,
            completion_rate=75.0
        )
        assert metrics.completion_rate == 75.0
    
    def test_avg_completion_time(self):
        """Average completion time should be properly stored."""
        metrics = TaskMetrics(
            avg_completion_time_hours=24.5
        )
        assert metrics.avg_completion_time_hours == 24.5


class TestEntryMetrics:
    """Tests for EntryMetrics DTO."""
    
    def test_processing_metrics(self):
        """Processing metrics should be properly stored."""
        metrics = EntryMetrics(
            total_entries=200,
            processed_entries=180,
            failed_entries=5,
            avg_processing_time_ms=1250.5
        )
        assert metrics.total_entries == 200
        assert metrics.processed_entries == 180
        assert metrics.failed_entries == 5
        assert metrics.avg_processing_time_ms == 1250.5
    
    def test_clarification_metrics(self):
        """Clarification metrics should be properly stored."""
        metrics = EntryMetrics(
            entries_with_clarifications=50,
            avg_clarifications_per_entry=2.3
        )
        assert metrics.entries_with_clarifications == 50
        assert metrics.avg_clarifications_per_entry == 2.3


class TestUserEngagementMetrics:
    """Tests for UserEngagementMetrics DTO."""
    
    def test_engagement_metrics(self):
        """Engagement metrics should be properly stored."""
        metrics = UserEngagementMetrics(
            avg_entries_per_user=5.5,
            avg_tasks_per_user=3.2,
            users_with_premium=150,
            premium_conversion_rate=15.0
        )
        assert metrics.avg_entries_per_user == 5.5
        assert metrics.avg_tasks_per_user == 3.2
        assert metrics.premium_conversion_rate == 15.0
    
    def test_token_metrics(self):
        """Token purchase metrics should be properly stored."""
        metrics = UserEngagementMetrics(
            total_tokens_purchased=5000,
            avg_tokens_per_user=50.0
        )
        assert metrics.total_tokens_purchased == 5000
        assert metrics.avg_tokens_per_user == 50.0


class TestDailyStatsSnapshot:
    """Tests for DailyStatsSnapshot DTO."""
    
    def test_creation_with_values(self):
        """DailyStatsSnapshot should store daily metrics."""
        snapshot = DailyStatsSnapshot(
            date="2026-04-19",
            dau=150,
            entries_created=500,
            entries_processed=480,
            tasks_completed=100,
            ai_calls=600,
            ai_tokens_used=50000,
            ai_avg_latency_ms=2500.0
        )
        assert snapshot.date == "2026-04-19"
        assert snapshot.dau == 150
        assert snapshot.entries_created == 500
        assert snapshot.ai_tokens_used == 50000
    
    def test_to_dict(self):
        """to_dict() should return proper dictionary."""
        snapshot = DailyStatsSnapshot(
            date="2026-04-19",
            dau=100,
            entries_created=300,
            entries_processed=280,
            tasks_completed=50,
            ai_calls=400,
            ai_tokens_used=40000,
            ai_avg_latency_ms=2000.0
        )
        data = snapshot.to_dict()
        
        assert isinstance(data, dict)
        assert data['date'] == "2026-04-19"
        assert data['dau'] == 100


class TestComprehensiveStatsDTO:
    """Tests for ComprehensiveStatsDTO."""
    
    def test_creation_with_defaults(self):
        """ComprehensiveStatsDTO should initialize with default sub-DTOs."""
        dto = ComprehensiveStatsDTO(
            timestamp="2026-04-19T10:00:00Z",
            period="daily"
        )
        assert dto.timestamp == "2026-04-19T10:00:00Z"
        assert dto.period == "daily"
        assert isinstance(dto.ai_metrics, AICallMetrics)
        assert isinstance(dto.onboarding, OnboardingFunnelMetrics)
        assert isinstance(dto.retention, RetentionMetrics)
        assert isinstance(dto.tasks, TaskMetrics)
        assert isinstance(dto.entries, EntryMetrics)
        assert isinstance(dto.engagement, UserEngagementMetrics)
    
    def test_to_dict_structure(self):
        """to_dict() should return properly structured dictionary."""
        dto = ComprehensiveStatsDTO(
            timestamp="2026-04-19T10:00:00Z",
            period="weekly"
        )
        data = dto.to_dict()
        
        assert isinstance(data, dict)
        assert data['timestamp'] == "2026-04-19T10:00:00Z"
        assert data['period'] == "weekly"
        assert 'ai_metrics' in data
        assert 'onboarding' in data
        assert 'retention' in data
        assert 'tasks' in data
        assert 'entries' in data
        assert 'engagement' in data
        assert 'daily_snapshots' in data
        assert isinstance(data['daily_snapshots'], list)
    
    def test_with_custom_metrics(self):
        """ComprehensiveStatsDTO should properly store custom metrics."""
        ai_metrics = AICallMetrics(total_calls=100, successful_calls=95)
        onboarding = OnboardingFunnelMetrics(started_count=200, registered_count=150)
        
        dto = ComprehensiveStatsDTO(
            timestamp="2026-04-19T10:00:00Z",
            period="monthly",
            ai_metrics=ai_metrics,
            onboarding=onboarding
        )
        
        data = dto.to_dict()
        assert data['ai_metrics']['total_calls'] == 100
        assert data['onboarding']['started_count'] == 200


class TestStatsQuery:
    """Tests for StatsQuery DTO."""
    
    def test_default_values(self):
        """StatsQuery should have sensible defaults."""
        query = StatsQuery()
        assert query.period == "daily"
        assert query.days_back == 7
        assert query.include_daily_snapshots is False
    
    def test_custom_values(self):
        """StatsQuery should accept custom values."""
        query = StatsQuery(
            period="monthly",
            days_back=30,
            include_daily_snapshots=True
        )
        assert query.period == "monthly"
        assert query.days_back == 30
        assert query.include_daily_snapshots is True
    
    def test_validate_valid_query(self):
        """validate() should return True for valid query."""
        query = StatsQuery(period="daily", days_back=7)
        assert query.validate() is True
        
        query = StatsQuery(period="weekly", days_back=30)
        assert query.validate() is True
        
        query = StatsQuery(period="monthly", days_back=90)
        assert query.validate() is True
    
    def test_validate_invalid_period(self):
        """validate() should return False for invalid period."""
        query = StatsQuery(period="invalid", days_back=7)
        assert query.validate() is False
    
    def test_validate_invalid_days_back(self):
        """validate() should return False for invalid days_back."""
        query = StatsQuery(period="daily", days_back=0)
        assert query.validate() is False
        
        query = StatsQuery(period="daily", days_back=366)
        assert query.validate() is False
    
    def test_validate_valid_boundary_values(self):
        """validate() should accept valid boundary values."""
        query = StatsQuery(period="daily", days_back=1)
        assert query.validate() is True
        
        query = StatsQuery(period="daily", days_back=365)
        assert query.validate() is True

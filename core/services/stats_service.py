"""
Unified statistics service for collecting and aggregating metrics.
Provides comprehensive stats for dashboards, monitoring, and API responses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from django.db.models import Count, Avg, Q, Sum, Max
from django.utils import timezone
from asgiref.sync import sync_to_async

from diary.models import (
    DiaryEntry, PsychoAnalysis, TherapyTask, TaskCompletion
)
from users.models import User, Payment
from core.services.stats_dtos import (
    AICallMetrics, OnboardingFunnelMetrics, RetentionMetrics,
    TaskMetrics, EntryMetrics, UserEngagementMetrics,
    DailyStatsSnapshot, ComprehensiveStatsDTO, StatsQuery
)

logger = logging.getLogger(__name__)


class StatsService:
    """Unified service for collecting application-level statistics."""

    @staticmethod
    async def get_ai_metrics(days_back: int = 7) -> AICallMetrics:
        """
        Collect AI call metrics from PsychoAnalysis and api_response tracking.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            AICallMetrics with aggregated data
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days_back)
            
            @sync_to_async
            def _collect_ai_metrics():
                # Query analysis records with api_response
                analyses = PsychoAnalysis.objects.filter(
                    created_at__gte=cutoff_date
                )
                
                total_calls = analyses.count()
                
                # Successful calls have api_response and processing_time set
                successful_calls = analyses.filter(
                    api_response__isnull=False,
                    processing_time__gt=0
                ).exclude(api_response={}).count()
                
                failed_calls = total_calls - successful_calls
                
                # Token usage from api_response
                total_tokens = 0
                total_latency = 0.0
                valid_latencies = 0
                
                for analysis in analyses:
                    if analysis.api_response and isinstance(analysis.api_response, dict):
                        usage = analysis.api_response.get('usage', {})
                        if isinstance(usage, dict):
                            total_tokens += usage.get('total_tokens', 0)
                        
                        # Latency tracking
                        if analysis.processing_time and analysis.processing_time > 0:
                            total_latency += analysis.processing_time * 1000  # Convert to ms
                            valid_latencies += 1
                
                avg_latency = total_latency / valid_latencies if valid_latencies > 0 else 0.0
                error_rate = (failed_calls / total_calls * 100) if total_calls > 0 else 0.0
                
                return AICallMetrics(
                    total_calls=total_calls,
                    successful_calls=successful_calls,
                    failed_calls=failed_calls,
                    total_tokens_used=total_tokens,
                    avg_latency_ms=avg_latency,
                    retry_count=0,  # Not tracked yet
                    error_rate=round(error_rate, 2)
                )
            
            return await _collect_ai_metrics()
        except Exception as e:
            logger.error(f"[StatsService] Error collecting AI metrics: {e}", exc_info=True)
            return AICallMetrics()

    @staticmethod
    async def get_onboarding_funnel(days_back: int = 7) -> OnboardingFunnelMetrics:
        """
        Calculate onboarding funnel metrics.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            OnboardingFunnelMetrics with conversion rates
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days_back)
            
            @sync_to_async
            def _collect_onboarding():
                # Count users by onboarding stage
                # Stage 1: User created (all users in this period)
                started_users = User.objects.filter(
                    date_joined__gte=cutoff_date
                ).count()
                
                # Stage 2: User has email (registered for web)
                registered_users = User.objects.filter(
                    date_joined__gte=cutoff_date,
                    email__isnull=False
                ).exclude(email='').count()
                
                # Stage 3: User created first entry
                first_entry_users = User.objects.filter(
                    date_joined__gte=cutoff_date,
                    diary_entries__isnull=False
                ).distinct().count()
                
                # Stage 4: User completed onboarding
                completed_onboarding = User.objects.filter(
                    date_joined__gte=cutoff_date,
                    is_onboarding_completed=True
                ).count()
                
                # Calculate conversions
                reg_conversion = (registered_users / started_users * 100) if started_users > 0 else 0.0
                entry_conversion = (first_entry_users / registered_users * 100) if registered_users > 0 else 0.0
                
                return OnboardingFunnelMetrics(
                    started_count=started_users,
                    registered_count=registered_users,
                    first_entry_count=first_entry_users,
                    completed_profile_count=completed_onboarding,
                    register_conversion=round(reg_conversion, 2),
                    first_entry_conversion=round(entry_conversion, 2)
                )
            
            return await _collect_onboarding()
        except Exception as e:
            logger.error(f"[StatsService] Error collecting onboarding metrics: {e}", exc_info=True)
            return OnboardingFunnelMetrics()

    @staticmethod
    async def get_retention_metrics(days_back: int = 7) -> RetentionMetrics:
        """
        Calculate retention and activity metrics.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            RetentionMetrics with DAU/WAU/MAU and streak data
        """
        try:
            now = timezone.now()
            
            @sync_to_async
            def _collect_retention():
                # Daily Active Users (last 24h)
                dau = DiaryEntry.objects.filter(
                    created_at__gte=now - timedelta(days=1)
                ).values('user_id').distinct().count()
                
                # Weekly Active Users (last 7d)
                wau = DiaryEntry.objects.filter(
                    created_at__gte=now - timedelta(days=7)
                ).values('user_id').distinct().count()
                
                # Monthly Active Users (last 30d)
                mau = DiaryEntry.objects.filter(
                    created_at__gte=now - timedelta(days=30)
                ).values('user_id').distinct().count()
                
                # Streak metrics - count users with multiple entries (proxy for active streak)
                users_with_streak = DiaryEntry.objects.filter(
                    created_at__gte=now - timedelta(days=7)
                ).values('user_id').distinct().count()
                
                # Calculate average entries per user (proxy for streak consistency)
                avg_streak = 0.0
                max_streak = 0
                if users_with_streak > 0:
                    entries_per_user = DiaryEntry.objects.filter(
                        created_at__gte=now - timedelta(days=days_back)
                    ).values('user_id').annotate(
                        count=Count('id')
                    ).aggregate(avg=Avg('count'), max=Max('count'))
                    avg_streak = float(entries_per_user.get('avg') or 0.0)
                    max_streak = entries_per_user.get('max') or 0
                
                # Users who recovered streak
                users_recovered = DiaryEntry.objects.filter(
                    is_recovered_streak=True,
                    created_at__gte=now - timedelta(days=days_back)
                ).values('user_id').distinct().count()
                
                return RetentionMetrics(
                    daily_active_users=dau,
                    weekly_active_users=wau,
                    monthly_active_users=mau,
                    users_with_active_streak=users_with_streak,
                    avg_streak_length=round(avg_streak, 2),
                    max_streak_length=max_streak,
                    users_recovered_streak=users_recovered,
                    churned_users_7d=0,  # Not tracked yet
                    returned_users_7d=0  # Not tracked yet
                )
            
            return await _collect_retention()
        except Exception as e:
            logger.error(f"[StatsService] Error collecting retention metrics: {e}", exc_info=True)
            return RetentionMetrics()

    @staticmethod
    async def get_task_metrics(days_back: int = 7) -> TaskMetrics:
        """
        Calculate task completion metrics.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            TaskMetrics with completion rates
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days_back)
            
            @sync_to_async
            def _collect_task_metrics():
                # Total tasks created
                total_tasks = TherapyTask.objects.filter(
                    assigned_at__gte=cutoff_date
                ).count()
                
                # Total tasks completed
                completed_tasks = TaskCompletion.objects.filter(
                    created_at__gte=cutoff_date
                ).count()
                
                # Completion rate
                completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0
                
                # Average completion time (from task creation to completion)
                completions = TaskCompletion.objects.filter(
                    created_at__gte=cutoff_date
                ).select_related('task')
                
                total_time = timedelta()
                completion_count = 0
                
                for completion in completions:
                    if completion.task:
                        time_diff = completion.created_at - completion.task.assigned_at
                        if time_diff.total_seconds() >= 0:
                            total_time += time_diff
                            completion_count += 1
                
                avg_completion_hours = (total_time.total_seconds() / 3600 / completion_count) if completion_count > 0 else 0.0
                
                return TaskMetrics(
                    total_tasks_created=total_tasks,
                    total_tasks_completed=completed_tasks,
                    completion_rate=round(completion_rate, 2),
                    avg_completion_time_hours=round(avg_completion_hours, 2)
                )
            
            return await _collect_task_metrics()
        except Exception as e:
            logger.error(f"[StatsService] Error collecting task metrics: {e}", exc_info=True)
            return TaskMetrics()

    @staticmethod
    async def get_entry_metrics(days_back: int = 7) -> EntryMetrics:
        """
        Calculate diary entry processing metrics.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            EntryMetrics with processing stats
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days_back)
            
            @sync_to_async
            def _collect_entry_metrics():
                entries = DiaryEntry.objects.filter(
                    created_at__gte=cutoff_date
                )
                
                total_entries = entries.count()
                processed_entries = entries.filter(is_processed=True).count()
                failed_entries = entries.filter(
                    is_processed=False,
                    processing_error__isnull=False
                ).exclude(processing_error='').count()
                
                # Average processing time
                analyses = PsychoAnalysis.objects.filter(
                    entry__created_at__gte=cutoff_date
                )
                
                proc_times = list(analyses.values_list('processing_time', flat=True))
                avg_processing_time = (sum(proc_times) / len(proc_times) * 1000) if proc_times else 0.0
                
                # Clarifications stats. Evaluate the decrypted payload because the field is encrypted.
                clarification_counts = [
                    len(entry.clarification_questions_asked or [])
                    for entry in entries
                ]
                entries_with_clarifications = sum(
                    1 for count in clarification_counts if count > 0
                )

                avg_clarifications = 0.0
                if entries_with_clarifications > 0:
                    total_clarifications = sum(clarification_counts)
                    avg_clarifications = total_clarifications / entries_with_clarifications
                
                # User comments. Evaluate decrypted values because the field is encrypted.
                user_comments = sum(
                    1 for entry in entries if bool((entry.user_comment or '').strip())
                )
                
                return EntryMetrics(
                    total_entries=total_entries,
                    processed_entries=processed_entries,
                    failed_entries=failed_entries,
                    avg_processing_time_ms=round(avg_processing_time, 2),
                    entries_with_clarifications=entries_with_clarifications,
                    avg_clarifications_per_entry=round(avg_clarifications, 2),
                    user_comments_count=user_comments
                )
            
            return await _collect_entry_metrics()
        except Exception as e:
            logger.error(f"[StatsService] Error collecting entry metrics: {e}", exc_info=True)
            return EntryMetrics()

    @staticmethod
    async def get_engagement_metrics(days_back: int = 7) -> UserEngagementMetrics:
        """
        Calculate user engagement metrics.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            UserEngagementMetrics with engagement stats
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=days_back)
            
            @sync_to_async
            def _collect_engagement():
                # Count entries and tasks per user
                active_users = User.objects.filter(
                    diary_entries__created_at__gte=cutoff_date
                ).distinct()
                
                active_user_count = active_users.count()
                
                entries_per_user = 0.0
                tasks_per_user = 0.0
                
                if active_user_count > 0:
                    total_entries = DiaryEntry.objects.filter(
                        user__in=active_users,
                        created_at__gte=cutoff_date
                    ).count()
                    entries_per_user = total_entries / active_user_count
                    
                    total_tasks = TaskCompletion.objects.filter(
                        task__user__in=active_users,
                        created_at__gte=cutoff_date
                    ).count()
                    tasks_per_user = total_tasks / active_user_count
                
                # Premium users
                premium_users = User.objects.filter(
                    is_premium=True
                ).count()
                
                total_users = User.objects.count()
                premium_rate = (premium_users / total_users * 100) if total_users > 0 else 0.0
                
                # Token purchases
                successful_payments = Payment.objects.filter(
                    status='succeeded',
                    created_at__gte=cutoff_date,
                    tokens_granted__gt=0
                )
                
                total_tokens_purchased = successful_payments.aggregate(
                    total=Sum('tokens_granted')
                )['total'] or 0
                
                avg_tokens_per_user = (total_tokens_purchased / active_user_count) if active_user_count > 0 else 0.0
                
                return UserEngagementMetrics(
                    avg_entries_per_user=round(entries_per_user, 2),
                    avg_tasks_per_user=round(tasks_per_user, 2),
                    users_with_premium=premium_users,
                    premium_conversion_rate=round(premium_rate, 2),
                    total_tokens_purchased=total_tokens_purchased,
                    avg_tokens_per_user=round(avg_tokens_per_user, 2)
                )
            
            return await _collect_engagement()
        except Exception as e:
            logger.error(f"[StatsService] Error collecting engagement metrics: {e}", exc_info=True)
            return UserEngagementMetrics()

    @classmethod
    async def get_comprehensive_stats(cls, query: StatsQuery) -> ComprehensiveStatsDTO:
        """
        Collect all statistics and return comprehensive DTO.
        
        Args:
            query: StatsQuery with parameters
            
        Returns:
            ComprehensiveStatsDTO with all aggregated data
        """
        try:
            if not query.validate():
                raise ValueError(f"Invalid stats query: {query}")
            
            # Collect all metrics in parallel
            ai_metrics = await cls.get_ai_metrics(query.days_back)
            onboarding = await cls.get_onboarding_funnel(query.days_back)
            retention = await cls.get_retention_metrics(query.days_back)
            tasks = await cls.get_task_metrics(query.days_back)
            entries = await cls.get_entry_metrics(query.days_back)
            engagement = await cls.get_engagement_metrics(query.days_back)
            
            # Build comprehensive DTO
            stats_dto = ComprehensiveStatsDTO(
                timestamp=timezone.now().isoformat(),
                period=query.period,
                ai_metrics=ai_metrics,
                onboarding=onboarding,
                retention=retention,
                tasks=tasks,
                entries=entries,
                engagement=engagement,
                daily_snapshots=[]
            )
            
            logger.debug(f"[StatsService] Comprehensive stats collected for period: {query.period}, days_back: {query.days_back}")
            return stats_dto
            
        except Exception as e:
            logger.error(f"[StatsService] Error collecting comprehensive stats: {e}", exc_info=True)
            raise


# Singleton instance
stats_service = StatsService()

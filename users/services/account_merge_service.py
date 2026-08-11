"""Атомарное объединение двух User после подтверждённого EmailMergeRequest."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

import pytz
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from users.models import (
    EmailMergeRequest,
    Feedback,
    IdentityLinkEvent,
    Payment,
    TokenTransaction,
    User,
    UserProfileHistory,
)

logger = logging.getLogger(__name__)

PROFILE_PACKAGE_FIELDS = (
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
    'personality_description',
    'compressed_psych_profile',
    'full_psych_profile',
    'awareness_level',
)

EMPTY_PROFILE_DEFAULTS: dict[str, Any] = {
    'personality_traits': {},
    'life_facts': [],
    'hobbies': [],
    'core_values': [],
    'triggers': [],
    'strengths': [],
    'areas_for_growth': [],
    'personality_insights': {},
    'practical_patterns': [],
    'aspirations': [],
    'personality_description': '',
    'compressed_psych_profile': {},
    'full_psych_profile': {},
    'awareness_level': 1,
}


@dataclass
class AccountMergeResult:
    status: str
    code: Optional[str] = None
    merge_request: Optional[EmailMergeRequest] = None
    survivor_id: Optional[int] = None
    donor_id: Optional[int] = None
    rebuild_profile: bool = False
    reanalyze_dates: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AccountMergeService:
    """Выбор survivor/donor, перенос данных, anonymize donor, пост-merge jobs."""

    PURGE_AFTER_DAYS = 30

    @classmethod
    def execute_merge(cls, merge_request: EmailMergeRequest) -> AccountMergeResult:
        if not getattr(settings, 'EMAIL_MERGE_EXECUTE_ENABLED', False):
            return AccountMergeResult(
                status='confirmed',
                code='execute_disabled',
                merge_request=merge_request,
            )

        with transaction.atomic():
            locked = (
                EmailMergeRequest.objects.select_for_update()
                .select_related('requester_user', 'target_user')
                .filter(pk=merge_request.pk)
                .first()
            )
            if locked is None:
                return AccountMergeResult(status='merge_failed', code='merge_request_not_found')

            if locked.status == 'merged':
                meta = dict(locked.metadata or {})
                return AccountMergeResult(
                    status='merged',
                    code='already_merged',
                    merge_request=locked,
                    survivor_id=meta.get('survivor_user_id'),
                    donor_id=meta.get('donor_user_id'),
                    metadata=meta,
                )

            if locked.status != 'confirmed':
                return AccountMergeResult(
                    status='merge_failed',
                    code='merge_request_not_confirmed',
                    merge_request=locked,
                )

            requester = User.objects.select_for_update().get(pk=locked.requester_user_id)
            target = User.objects.select_for_update().get(pk=locked.target_user_id)

            if requester.id == target.id:
                return cls._fail(locked, 'same_user')

            if requester.deletion_status != 'active' or target.deletion_status != 'active':
                return cls._fail(
                    locked,
                    'user_not_active',
                    extra={
                        'requester_deletion_status': requester.deletion_status,
                        'target_deletion_status': target.deletion_status,
                        'requester_user_id': requester.id,
                        'target_user_id': target.id,
                    },
                )

            survivor, donor = cls._pick_survivor_donor(requester, target)
            conflict = cls._validate_transport_union(survivor, donor)
            if conflict:
                return cls._fail(locked, conflict)

            survivor_has_profile = cls.has_profile_package(survivor)
            donor_has_profile = cls.has_profile_package(donor)
            rebuild_profile = survivor_has_profile and donor_has_profile

            counts = cls._reassign_owned_rows(survivor=survivor, donor=donor)
            reanalyze_dates = cls._resolve_day_aggregates(survivor=survivor, donor=donor)
            cls._merge_user_fields(
                survivor=survivor,
                donor=donor,
                rebuild_profile=rebuild_profile,
                survivor_had_profile=survivor_has_profile,
                donor_had_profile=donor_has_profile,
            )
            cls._anonymize_donor(donor)

            now = timezone.now()
            metadata = dict(locked.metadata or {})
            metadata.update(
                {
                    'survivor_user_id': survivor.id,
                    'donor_user_id': donor.id,
                    'merged_at': now.isoformat(),
                    'purge_after': (now + timedelta(days=cls.PURGE_AFTER_DAYS)).isoformat(),
                    'reassigned_counts': counts,
                    'rebuild_profile': rebuild_profile,
                    'reanalyze_dates': [d.isoformat() for d in reanalyze_dates],
                    'merge_execute_version': 1,
                }
            )
            locked.metadata = metadata
            locked.status = 'merged'
            if locked.confirmed_at is None:
                locked.confirmed_at = now
            locked.save(update_fields=['metadata', 'status', 'confirmed_at', 'updated_at'])

            IdentityLinkEvent.objects.create(
                user=survivor,
                actor_user=requester,
                actor_telegram_id=getattr(requester, 'telegram_id', None),
                event_type='link',
                result='success',
                source_platform=locked.source_platform or 'merge',
                source_context='email_account_merge',
                reason_code='email_merge_executed',
                metadata={
                    'merge_request_id': locked.id,
                    'survivor_user_id': survivor.id,
                    'donor_user_id': donor.id,
                },
            )

            result = AccountMergeResult(
                status='merged',
                merge_request=locked,
                survivor_id=survivor.id,
                donor_id=donor.id,
                rebuild_profile=rebuild_profile,
                reanalyze_dates=[d.isoformat() for d in reanalyze_dates],
                metadata=metadata,
            )

            transaction.on_commit(lambda: cls._schedule_post_merge_jobs(result))
            return result

    @classmethod
    async def aexecute_merge(cls, merge_request: EmailMergeRequest) -> AccountMergeResult:
        return await sync_to_async(cls.execute_merge)(merge_request)

    @classmethod
    def _fail(
        cls,
        merge_request: EmailMergeRequest,
        code: str,
        *,
        extra: dict | None = None,
    ) -> AccountMergeResult:
        metadata = dict(merge_request.metadata or {})
        metadata['merge_failed_at'] = timezone.now().isoformat()
        metadata['merge_failed_code'] = code
        if extra:
            metadata['merge_failed_details'] = extra
        merge_request.metadata = metadata
        merge_request.status = 'merge_failed'
        merge_request.save(update_fields=['metadata', 'status', 'updated_at'])
        logger.warning(
            'Account merge failed merge_request=%s code=%s details=%s',
            merge_request.id,
            code,
            extra,
        )
        return AccountMergeResult(
            status='merge_failed',
            code=code,
            merge_request=merge_request,
            metadata=metadata,
        )

    @classmethod
    def diary_entry_count(cls, user: User) -> int:
        from diary.models import DiaryEntry

        return DiaryEntry.objects.filter(user=user).count()

    @classmethod
    def _pick_survivor_donor(cls, requester: User, target: User) -> tuple[User, User]:
        req_count = cls.diary_entry_count(requester)
        tgt_count = cls.diary_entry_count(target)
        if req_count > tgt_count:
            return requester, target
        if tgt_count > req_count:
            return target, requester
        # tie → earlier created_at
        if requester.created_at <= target.created_at:
            return requester, target
        return target, requester

    @classmethod
    def _validate_transport_union(cls, survivor: User, donor: User) -> Optional[str]:
        if survivor.telegram_id and donor.telegram_id and survivor.telegram_id != donor.telegram_id:
            return 'conflicting_telegram_ids'
        if survivor.max_id and donor.max_id and survivor.max_id != donor.max_id:
            return 'conflicting_max_ids'
        return None

    @classmethod
    def _is_empty_value(cls, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False

    @classmethod
    def has_profile_package(cls, user: User) -> bool:
        for name in PROFILE_PACKAGE_FIELDS:
            value = getattr(user, name, None)
            if name == 'awareness_level':
                if isinstance(value, int) and value > 1:
                    return True
                continue
            if not cls._is_empty_value(value):
                return True
        return False

    @classmethod
    def _reassign_owned_rows(cls, *, survivor: User, donor: User) -> dict[str, int]:
        from diary.models import (
            AnalysisRating,
            DiaryEntry,
            NextEntryPrompt,
            TherapyProgress,
            TherapyTask,
            UserActivity,
            WeeklyAnalysis,
        )

        counts: dict[str, int] = {}

        def _move(model, label: str, *, unique_date_field: str | None = None):
            qs = model.objects.filter(user=donor)
            if unique_date_field:
                survivor_keys = set(
                    model.objects.filter(user=survivor).values_list(unique_date_field, flat=True)
                )
                conflict_qs = qs.filter(**{f'{unique_date_field}__in': survivor_keys})
                deleted, _ = conflict_qs.delete()
                counts[f'{label}_conflicts_deleted'] = deleted
                qs = model.objects.filter(user=donor)
            updated = qs.update(user=survivor)
            counts[label] = updated

        _move(DiaryEntry, 'diary_entries')
        _move(TherapyTask, 'therapy_tasks')
        _move(UserActivity, 'user_activities')
        _move(TherapyProgress, 'therapy_progress', unique_date_field='date')
        _move(WeeklyAnalysis, 'weekly_analyses', unique_date_field='week_start_date')
        _move(NextEntryPrompt, 'next_entry_prompts', unique_date_field='target_date')

        # AnalysisRating: unique (user, analysis)
        donor_ratings = AnalysisRating.objects.filter(user=donor)
        survivor_analysis_ids = set(
            AnalysisRating.objects.filter(user=survivor).values_list('analysis_id', flat=True)
        )
        conflict_ratings = donor_ratings.filter(analysis_id__in=survivor_analysis_ids)
        deleted_ratings, _ = conflict_ratings.delete()
        counts['analysis_ratings_conflicts_deleted'] = deleted_ratings
        counts['analysis_ratings'] = AnalysisRating.objects.filter(user=donor).update(user=survivor)

        counts['payments'] = Payment.objects.filter(user=donor).update(user=survivor)
        counts['token_transactions'] = TokenTransaction.objects.filter(user=donor).update(user=survivor)
        counts['feedbacks'] = Feedback.objects.filter(user=donor).update(user=survivor)
        counts['profile_history'] = UserProfileHistory.objects.filter(user=donor).update(user=survivor)

        # Referrals pointing at donor → survivor
        counts['invited_by_rewritten'] = User.objects.filter(invited_by=donor).update(invited_by=survivor)

        IdentityLinkEvent.objects.filter(user=donor).update(user=survivor)
        return counts

    @classmethod
    def _resolve_day_aggregates(cls, *, survivor: User, donor: User) -> list[date]:
        """Удаляет конфликтующие CombinedDiaryEntry; возвращает даты для reanalysis (последняя календарная неделя)."""
        from diary.models import CombinedDiaryEntry, DailyAnalysis, DiaryEntry

        survivor_dates = set(
            CombinedDiaryEntry.objects.filter(user=survivor).values_list('date', flat=True)
        )
        donor_cdes = list(CombinedDiaryEntry.objects.filter(user=donor))
        overlapping: set[date] = set()
        for cde in donor_cdes:
            if cde.date in survivor_dates:
                overlapping.add(cde.date)
            else:
                cde.user = survivor
                cde.save(update_fields=['user'])

        # Для overlapping: удалить оба CDE (DailyAnalysis cascade); entries уже на survivor
        if overlapping:
            cde_qs = CombinedDiaryEntry.objects.filter(user=survivor, date__in=overlapping)
            DailyAnalysis.objects.filter(combined_entry__in=cde_qs).delete()
            cde_qs.delete()
            # donor side may still have overlapping rows
            donor_overlap = CombinedDiaryEntry.objects.filter(user=donor, date__in=overlapping)
            DailyAnalysis.objects.filter(combined_entry__in=donor_overlap).delete()
            donor_overlap.delete()

        # leftover donor CDEs (race) → move or delete
        leftover = CombinedDiaryEntry.objects.filter(user=donor)
        for cde in leftover:
            if CombinedDiaryEntry.objects.filter(user=survivor, date=cde.date).exists():
                DailyAnalysis.objects.filter(combined_entry=cde).delete()
                cde.delete()
            else:
                cde.user = survivor
                cde.save(update_fields=['user'])

        week_dates = cls._last_calendar_week_dates(survivor)
        localized_dates: set[date] = set()
        for entry in DiaryEntry.objects.filter(user=survivor).only(
            'id', 'created_at', 'creator_timezone'
        ):
            try:
                tz_name = entry.creator_timezone or survivor.timezone or 'UTC'
                try:
                    entry_tz = pytz.timezone(tz_name)
                except Exception:
                    entry_tz = pytz.UTC
                created = entry.created_at
                if timezone.is_naive(created):
                    created = timezone.make_aware(created, pytz.UTC)
                local_day = created.astimezone(entry_tz).date()
                if local_day in week_dates:
                    localized_dates.add(local_day)
            except Exception:
                continue

        reanalyze = sorted((localized_dates | (overlapping & week_dates)))

        # Drop stale combined for reanalyze dates so pipeline rebuilds cleanly
        if reanalyze:
            stale = CombinedDiaryEntry.objects.filter(user=survivor, date__in=reanalyze)
            DailyAnalysis.objects.filter(combined_entry__in=stale).delete()
            stale.delete()

        return reanalyze

    @classmethod
    def _last_calendar_week_dates(cls, user: User) -> set[date]:
        """Понедельник–воскресенье текущей календарной недели в TZ пользователя."""
        try:
            tz = pytz.timezone(user.timezone or 'UTC')
        except Exception:
            tz = pytz.UTC
        local_today = timezone.now().astimezone(tz).date()
        week_start = local_today - timedelta(days=local_today.weekday())  # Monday
        return {week_start + timedelta(days=i) for i in range(7)}

    @classmethod
    def _premium_remaining_days(cls, user: User, now) -> int:
        if not user.is_premium or not user.premium_expires_at:
            return 0
        expires = user.premium_expires_at
        if timezone.is_naive(expires):
            expires = timezone.make_aware(expires, timezone.get_current_timezone())
        if expires <= now:
            return 0
        return max(0, (expires - now).days)

    @classmethod
    def _merge_user_fields(
        cls,
        *,
        survivor: User,
        donor: User,
        rebuild_profile: bool,
        survivor_had_profile: bool,
        donor_had_profile: bool,
    ) -> None:
        now = timezone.now()

        # Снять transport ids с donor до присвоения survivor (unique telegram_id).
        donor_telegram_id = donor.telegram_id
        donor_max_id = donor.max_id
        donor.telegram_id = None
        donor.max_id = None
        donor.save(update_fields=['telegram_id', 'max_id', 'updated_at'])

        if donor_telegram_id and not survivor.telegram_id:
            survivor.telegram_id = donor_telegram_id
        if donor_max_id and not survivor.max_id:
            survivor.max_id = donor_max_id

        # Email: keep survivor; if survivor empty, take donor's
        if not (survivor.email and str(survivor.email).strip()) and donor.email:
            survivor.email = donor.email

        # Tokens
        survivor.token_balance = int(survivor.token_balance or 0) + int(donor.token_balance or 0)

        # Premium: sum remaining days
        total_days = cls._premium_remaining_days(survivor, now) + cls._premium_remaining_days(donor, now)
        if total_days > 0:
            survivor.is_premium = True
            survivor.premium_expires_at = now + timedelta(days=total_days)
        else:
            survivor.is_premium = False
            survivor.premium_expires_at = None

        survivor.is_onboarding_completed = bool(
            survivor.is_onboarding_completed or donor.is_onboarding_completed
        )
        if not survivor.language and donor.language:
            survivor.language = donor.language
        if (not survivor.timezone or survivor.timezone == 'UTC') and donor.timezone:
            survivor.timezone = donor.timezone
        if survivor.date_of_birth is None and donor.date_of_birth is not None:
            survivor.date_of_birth = donor.date_of_birth
        if not survivor.first_name and donor.first_name:
            survivor.first_name = donor.first_name
        if not survivor.last_name and donor.last_name:
            survivor.last_name = donor.last_name

        survivor.last_streak_reward_7 = max(
            survivor.last_streak_reward_7 or 0, donor.last_streak_reward_7 or 0
        )
        survivor.last_streak_reward_30 = max(
            survivor.last_streak_reward_30 or 0, donor.last_streak_reward_30 or 0
        )
        survivor.last_streak_reward_365 = max(
            survivor.last_streak_reward_365 or 0, donor.last_streak_reward_365 or 0
        )

        if survivor.last_entry and donor.last_entry:
            survivor.last_entry = max(survivor.last_entry, donor.last_entry)
        elif donor.last_entry and not survivor.last_entry:
            survivor.last_entry = donor.last_entry

        if survivor.last_activity and donor.last_activity:
            survivor.last_activity = max(survivor.last_activity, donor.last_activity)
        elif donor.last_activity and not survivor.last_activity:
            survivor.last_activity = donor.last_activity

        if rebuild_profile:
            for name, default in EMPTY_PROFILE_DEFAULTS.items():
                setattr(
                    survivor,
                    name,
                    default if not isinstance(default, (dict, list)) else type(default)(),
                )
        elif donor_had_profile and not survivor_had_profile:
            for name in PROFILE_PACKAGE_FIELDS:
                setattr(survivor, name, getattr(donor, name))

        donor.email = ''
        donor.email_hash = ''
        donor.token_balance = 0
        donor.is_premium = False
        donor.premium_expires_at = None
        donor.save(
            update_fields=[
                'email',
                'email_hash',
                'token_balance',
                'is_premium',
                'premium_expires_at',
                'updated_at',
            ]
        )
        survivor.save()

    @classmethod
    def _anonymize_donor(cls, donor: User) -> None:
        now = timezone.now()
        donor.telegram_id = None
        donor.max_id = None
        donor.email = ''
        donor.email_hash = ''
        donor.referral_link = f'merged_ref_{donor.id}'
        donor.first_name = ''
        donor.last_name = ''
        donor.username = f'merged_{donor.id}'
        donor.timezone = 'UTC'
        donor.notifications_enabled = False
        donor.auto_analysis_enabled = False
        donor.is_blocked = True
        donor.deleted_at = now
        donor.deletion_status = 'anonymized'
        donor.token_balance = 0
        donor.is_premium = False
        donor.premium_expires_at = None
        for name, default in EMPTY_PROFILE_DEFAULTS.items():
            value = default if not isinstance(default, (dict, list)) else type(default)()
            setattr(donor, name, value)
        donor.save()

    @classmethod
    def _schedule_post_merge_jobs(cls, result: AccountMergeResult) -> None:
        if result.status != 'merged' or not result.survivor_id:
            return
        try:
            from diary.tasks.account_merge_tasks import (
                post_merge_rebuild_profile_task,
                post_merge_reanalyze_week_task,
            )

            if result.reanalyze_dates:
                post_merge_reanalyze_week_task.delay(result.survivor_id, result.reanalyze_dates)
            if result.rebuild_profile:
                post_merge_rebuild_profile_task.delay(result.survivor_id)
        except Exception:
            logger.exception(
                'Failed to schedule post-merge jobs for survivor=%s',
                result.survivor_id,
            )

        try:
            from bot.transports.account_merge_notifier import notify_accounts_merged

            notify_accounts_merged(
                survivor_id=result.survivor_id,
                merge_request_id=result.merge_request.id if result.merge_request else None,
            )
        except Exception:
            logger.exception('Failed to notify merge success for survivor=%s', result.survivor_id)

    @classmethod
    def purge_due_merged_users(cls, *, now=None) -> dict[str, int]:
        """Hard-delete anonymized donors from merge after PURGE_AFTER_DAYS."""
        now = now or timezone.now()
        cutoff = now - timedelta(days=cls.PURGE_AFTER_DAYS)
        qs = User.objects.filter(
            deletion_status='anonymized',
            deleted_at__lte=cutoff,
            username__startswith='merged_',
        )
        deleted = 0
        for user in qs.iterator():
            user_id = user.id
            user.delete()
            deleted += 1
            logger.info('Purged merged donor user_id=%s', user_id)
        return {'purged': deleted}

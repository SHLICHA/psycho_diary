"""
Phase A API views: settings, onboarding, therapy chat, day-by-date operations.
Thin adapters over existing services — no domain logic here.
"""

from __future__ import annotations

import logging
from datetime import datetime

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.error_utils import api_error_response
from api.serializers import APIErrorSerializer, DiaryEntrySerializer
from api.service_bridge import (
    ensure_tokens,
    from_service_dict,
    pick_keys,
    refund_tokens,
    run_async,
    serialize_entry_analysis,
    strip_transport,
)
from api.throttling import EntryMutationRateThrottle, SettingsMutationRateThrottle

logger = logging.getLogger(__name__)


def _parse_iso_date(value: str):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


class SettingsView(APIView):
    """GET/PATCH user settings via SettingsService."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == 'PATCH':
            return [SettingsMutationRateThrottle()]
        return []

    @extend_schema(
        summary='Текущие настройки',
        responses={200: OpenApiResponse(description='Настройки пользователя.'), 401: APIErrorSerializer},
        tags=['Settings'],
    )
    def get(self, request):
        from diary.services.settings_service import get_task_limit_info, get_timezone_info

        user = request.user
        task_info = run_async(get_task_limit_info(user))
        tz_info = run_async(get_timezone_info(user))
        return Response(
            {
                'language': user.language,
                'timezone': tz_info.get('current_timezone') if tz_info.get('success') else user.timezone,
                'notifications_enabled': user.notifications_enabled,
                'auto_analysis_enabled': user.auto_analysis_enabled,
                'task_limit': {
                    'current_limit': task_info.get('current_limit') if task_info.get('success') else user.max_ai_tasks_per_day,
                    'max_allowed': task_info.get('max_allowed') if task_info.get('success') else None,
                    'awareness_level': task_info.get('awareness_level') if task_info.get('success') else user.awareness_level,
                },
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary='Обновить настройки',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'language': {'type': 'string', 'enum': ['ru', 'en']},
                    'timezone': {'type': 'string'},
                    'notifications_enabled': {'type': 'boolean'},
                    'auto_analysis_enabled': {'type': 'boolean'},
                },
            }
        },
        responses={200: OpenApiResponse(description='Настройки обновлены.'), 400: APIErrorSerializer},
        tags=['Settings'],
    )
    def patch(self, request):
        from diary.services.settings_service import (
            toggle_user_auto_analysis,
            toggle_user_notifications,
            update_user_language,
            update_user_timezone,
        )

        user = request.user
        data = request.data or {}
        updated = {}

        if 'language' in data:
            result = run_async(update_user_language(user, str(data['language'])))
            if not result.get('success'):
                return api_error_response(
                    code=result.get('error') or 'language_update_failed',
                    message='Не удалось обновить язык.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            updated['language'] = result['new_language']

        if 'timezone' in data:
            result = run_async(update_user_timezone(user, str(data['timezone'])))
            if not result.get('success'):
                return api_error_response(
                    code=result.get('error') or 'timezone_update_failed',
                    message='Не удалось обновить часовой пояс.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            updated['timezone'] = result['new_timezone']

        if 'notifications_enabled' in data:
            desired = data['notifications_enabled']
            if not isinstance(desired, bool):
                return api_error_response(
                    code='invalid_value',
                    message='Поле notifications_enabled должно быть булевым.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            user.refresh_from_db(fields=['notifications_enabled'])
            if desired != user.notifications_enabled:
                result = run_async(toggle_user_notifications(user))
                if not result.get('success'):
                    return api_error_response(
                        code=result.get('error') or 'notifications_update_failed',
                        message='Не удалось обновить уведомления.',
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            updated['notifications_enabled'] = desired

        if 'auto_analysis_enabled' in data:
            desired = data['auto_analysis_enabled']
            if not isinstance(desired, bool):
                return api_error_response(
                    code='invalid_value',
                    message='Поле auto_analysis_enabled должно быть булевым.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            user.refresh_from_db(fields=['auto_analysis_enabled'])
            if desired != user.auto_analysis_enabled:
                result = run_async(toggle_user_auto_analysis(user))
                if not result.get('success'):
                    return api_error_response(
                        code=result.get('error') or 'auto_analysis_update_failed',
                        message='Не удалось обновить автоанализ.',
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            updated['auto_analysis_enabled'] = desired

        user.refresh_from_db()
        return Response(
            {
                'updated': updated,
                'language': user.language,
                'timezone': user.timezone,
                'notifications_enabled': user.notifications_enabled,
                'auto_analysis_enabled': user.auto_analysis_enabled,
            },
            status=status.HTTP_200_OK,
        )


class SettingsTaskLimitView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SettingsMutationRateThrottle]

    @extend_schema(
        summary='Изменить лимит заданий',
        request={
            'application/json': {
                'type': 'object',
                'properties': {'increment': {'type': 'integer', 'enum': [-1, 1]}},
                'required': ['increment'],
            }
        },
        responses={200: OpenApiResponse(description='Лимит обновлён.'), 400: APIErrorSerializer},
        tags=['Settings'],
    )
    def post(self, request):
        from diary.services.settings_service import update_task_limit

        increment = request.data.get('increment')
        if increment not in (-1, 1):
            return api_error_response(
                code='invalid_increment',
                message='Поле increment должно быть -1 или 1.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        result = run_async(update_task_limit(request.user, int(increment)))
        return from_service_dict(result)


class SettingsTimezoneLookupView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SettingsMutationRateThrottle]

    @extend_schema(
        summary='Поиск TZ по городу',
        request={
            'application/json': {
                'type': 'object',
                'properties': {'city_name': {'type': 'string'}},
                'required': ['city_name'],
            }
        },
        responses={200: OpenApiResponse(description='Результат поиска.'), 400: APIErrorSerializer},
        tags=['Settings'],
    )
    def post(self, request):
        from diary.services.settings_service import process_city_timezone_lookup

        city_name = (request.data.get('city_name') or '').strip()
        if not city_name:
            return api_error_response(
                code='city_name_required',
                message='Поле city_name обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = request.user.language or 'ru'
        result = run_async(process_city_timezone_lookup(city_name, language))
        return from_service_dict(result)


class SettingsTimezoneConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SettingsMutationRateThrottle]

    @extend_schema(
        summary='Подтвердить TZ по городу',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'timezone': {'type': 'string'},
                    'city': {'type': 'string'},
                    'country': {'type': 'string'},
                },
                'required': ['timezone'],
            }
        },
        responses={200: OpenApiResponse(description='TZ подтверждён.'), 400: APIErrorSerializer},
        tags=['Settings'],
    )
    def post(self, request):
        from diary.services.settings_service import confirm_timezone_by_city

        timezone_value = (request.data.get('timezone') or '').strip()
        if not timezone_value:
            return api_error_response(
                code='timezone_required',
                message='Поле timezone обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        timezone_data = {
            'timezone': timezone_value,
            'city': request.data.get('city') or '',
            'country': request.data.get('country') or '',
        }
        result = run_async(confirm_timezone_by_city(request.user, timezone_data))
        return from_service_dict(result)


class OnboardingStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Статус онбординга',
        responses={200: OpenApiResponse(description='Текущий шаг онбординга.'), 401: APIErrorSerializer},
        tags=['Onboarding'],
    )
    def get(self, request):
        from diary.services.onboarding_service import resolve_start_routing_use_case

        language = request.user.language or 'ru'
        result = run_async(
            resolve_start_routing_use_case(
                request.user,
                language,
                current_fsm_state=None,
            )
        )
        cleaned = strip_transport(result)
        return Response(
            pick_keys(
                cleaned,
                ('success', 'mode', 'text', 'current_timezone', 'reactivation_text', 'error'),
            ),
            status=status.HTTP_200_OK,
        )


class OnboardingAcceptAgreementView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SettingsMutationRateThrottle]

    @extend_schema(
        summary='Принять шаг согласия онбординга',
        request={
            'application/json': {
                'type': 'object',
                'properties': {'step': {'type': 'integer', 'enum': [1, 2]}},
                'required': ['step'],
            }
        },
        responses={200: OpenApiResponse(description='Следующий шаг.'), 400: APIErrorSerializer},
        tags=['Onboarding'],
    )
    def post(self, request):
        from messages import get_message
        from diary.services.onboarding_service import build_onboarding_timezone_prompt_view

        if request.user.is_onboarding_completed:
            return api_error_response(
                code='onboarding_already_completed',
                message='Онбординг уже завершён.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        step = request.data.get('step')
        language = request.user.language or 'ru'
        if step == 1:
            return Response(
                {
                    'success': True,
                    'mode': 'agreement_2',
                    'next': 'agreement_2',
                    'text': get_message('onboarding_project_info', language),
                },
                status=status.HTTP_200_OK,
            )
        if step == 2:
            view = run_async(
                build_onboarding_timezone_prompt_view(
                    request.user,
                    language,
                    include_info_prefix=True,
                    show_back_button=False,
                )
            )
            cleaned = strip_transport(view)
            if not cleaned.get('success'):
                return from_service_dict(cleaned)
            return Response(
                {
                    'success': True,
                    'mode': 'timezone',
                    'next': 'timezone',
                    'text': cleaned.get('text'),
                    'current_timezone': cleaned.get('current_timezone'),
                },
                status=status.HTTP_200_OK,
            )
        return api_error_response(
            code='invalid_step',
            message='Поле step должно быть 1 или 2.',
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class OnboardingTimezoneView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SettingsMutationRateThrottle]

    @extend_schema(
        summary='Установить TZ в онбординге',
        request={
            'application/json': {
                'type': 'object',
                'properties': {'timezone': {'type': 'string'}},
                'required': ['timezone'],
            }
        },
        responses={200: OpenApiResponse(description='Следующий шаг.'), 400: APIErrorSerializer},
        tags=['Onboarding'],
    )
    def post(self, request):
        from diary.services.settings_service import set_timezone_and_resolve_next_step

        timezone_value = (request.data.get('timezone') or '').strip()
        if not timezone_value:
            return api_error_response(
                code='timezone_required',
                message='Поле timezone обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = request.user.language or 'ru'
        result = run_async(
            set_timezone_and_resolve_next_step(
                request.user,
                timezone_value,
                language,
                is_onboarding=True,
            )
        )
        cleaned = strip_transport(result)
        if not cleaned.get('success'):
            return from_service_dict(cleaned)
        return Response(
            pick_keys(
                cleaned,
                ('success', 'mode', 'next', 'text', 'new_timezone', 'alert_text'),
            ),
            status=status.HTTP_200_OK,
        )


class OnboardingFirstEntryView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EntryMutationRateThrottle]

    @extend_schema(
        summary='Первая запись онбординга',
        request={
            'application/json': {
                'type': 'object',
                'properties': {'text': {'type': 'string'}},
                'required': ['text'],
            }
        },
        responses={
            201: OpenApiResponse(description='Онбординг завершён, запись создана.'),
            400: APIErrorSerializer,
        },
        tags=['Onboarding'],
    )
    def post(self, request):
        from bot.services.diary_service import diary_service
        from diary.services.onboarding_service import build_first_onboarding_entry_result_view

        text = (request.data.get('text') or '').strip()
        if not text:
            return api_error_response(
                code='text_required',
                message='Поле text обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = request.user.language or 'ru'
        response = run_async(
            diary_service.process_first_onboarding_entry_use_case(
                user=request.user,
                entry_text=text,
                language=language,
                entry_datetime=None,
            )
        )
        view = strip_transport(build_first_onboarding_entry_result_view(response, language))
        if not response.success:
            return api_error_response(
                code=response.error or 'onboarding_entry_failed',
                message=view.get('text') or response.message or 'Не удалось обработать первую запись.',
                status_code=status.HTTP_400_BAD_REQUEST,
                details=view,
            )

        data = response.data or {}
        payload = serialize_entry_analysis(data.get('entry'), data.get('analysis'))
        payload.update(
            {
                'mode': view.get('mode'),
                'text': view.get('text'),
                'mood_score': data.get('mood_score'),
                'comment': data.get('comment'),
                'recommendation': data.get('recommendation'),
                'metadata': strip_transport(response.metadata or {}),
            }
        )
        return Response(payload, status=status.HTTP_201_CREATED)


class TherapyChatWelcomeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Welcome therapy chat',
        responses={200: OpenApiResponse(description='Текст приветствия.'), 401: APIErrorSerializer},
        tags=['TherapyChat'],
    )
    def get(self, request):
        from diary.services.therapy_chat_service import TherapyChatService

        language = request.user.language or 'ru'
        view = TherapyChatService.build_therapy_chat_welcome_view(request.user, language)
        return Response(
            pick_keys(strip_transport(view), ('success', 'mode', 'text')),
            status=status.HTTP_200_OK,
        )


class TherapyChatStartView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EntryMutationRateThrottle]

    @extend_schema(
        summary='Старт therapy chat',
        responses={200: OpenApiResponse(description='Пустая история.'), 400: APIErrorSerializer},
        tags=['TherapyChat'],
    )
    def post(self, request):
        from diary.services.therapy_chat_service import TherapyChatService

        result = run_async(TherapyChatService.start_chat(request.user))
        return from_service_dict(result)


class TherapyChatMessageView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EntryMutationRateThrottle]

    @extend_schema(
        summary='Сообщение в therapy chat',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string'},
                    'history': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'role': {'type': 'string'},
                                'content': {'type': 'string'},
                            },
                        },
                    },
                },
                'required': ['text'],
            }
        },
        responses={200: OpenApiResponse(description='Ответ ИИ.'), 400: APIErrorSerializer, 402: APIErrorSerializer},
        tags=['TherapyChat'],
    )
    def post(self, request):
        from diary.services.therapy_chat_service import TherapyChatService

        text = (request.data.get('text') or '').strip()
        if not text:
            return api_error_response(
                code='text_required',
                message='Поле text обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        history = request.data.get('history') or []
        if not isinstance(history, list):
            return api_error_response(
                code='invalid_history',
                message='Поле history должно быть массивом.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        token_error = ensure_tokens(request.user, cost=1, feature_name='therapy_chat_message')
        if token_error is not None:
            return token_error

        try:
            result = run_async(
                TherapyChatService.process_user_message(
                    request.user,
                    text,
                    history,
                )
            )
        except Exception:
            refund_tokens(request.user, cost=1, feature_name='therapy_chat_message')
            raise

        if not result.get('success'):
            refund_tokens(request.user, cost=1, feature_name='therapy_chat_message')
        return from_service_dict(result)


class TherapyChatEndView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Завершить therapy chat',
        responses={200: OpenApiResponse(description='Чат завершён.'), 400: APIErrorSerializer},
        tags=['TherapyChat'],
    )
    def post(self, request):
        from diary.services.therapy_chat_service import TherapyChatService

        result = run_async(TherapyChatService.end_chat(request.user))
        return from_service_dict(result)


class DayByDateView(APIView):
    """GET/DELETE day operations by ISO date."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == 'DELETE':
            return [EntryMutationRateThrottle()]
        return []

    @extend_schema(
        summary='Записи дня по дате',
        responses={200: OpenApiResponse(description='День и записи.'), 400: APIErrorSerializer},
        tags=['Days'],
    )
    def get(self, request, entry_date: str):
        from diary.services.diary_display_service import diary_display_service

        target_date = _parse_iso_date(entry_date)
        if target_date is None:
            return api_error_response(
                code='invalid_date_format',
                message='Неверный формат даты. Используйте YYYY-MM-DD.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = request.user.language or 'ru'
        result = run_async(
            diary_display_service.build_day_entries_view(request.user, target_date, language)
        )
        cleaned = strip_transport(result)
        if cleaned.get('mode') == 'entries':
            entries = cleaned.get('entries') or []
            entry = cleaned.get('entry')
            return Response(
                {
                    'success': True,
                    'mode': 'entries',
                    'target_date': str(target_date),
                    'entry': DiaryEntrySerializer(entry).data if entry is not None else None,
                    'entries': DiaryEntrySerializer(entries, many=True).data,
                    'total': len(entries),
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                'success': cleaned.get('success', True),
                'mode': cleaned.get('mode', 'empty'),
                'target_date': str(target_date),
                'text': cleaned.get('text'),
                'error': cleaned.get('error'),
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary='Удалить все записи дня',
        responses={200: OpenApiResponse(description='День удалён.'), 400: APIErrorSerializer},
        tags=['Days'],
    )
    def delete(self, request, entry_date: str):
        from bot.services.diary_service import diary_service

        target_date = _parse_iso_date(entry_date)
        if target_date is None:
            return api_error_response(
                code='invalid_date_format',
                message='Неверный формат даты. Используйте YYYY-MM-DD.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = request.user.language or 'ru'
        result = run_async(
            diary_service.delete_entire_day_use_case(request.user, target_date, language)
        )
        cleaned = strip_transport(result)
        if not cleaned.get('success'):
            return from_service_dict(cleaned)
        return Response(
            {
                'success': True,
                'message': cleaned.get('alert_message'),
                'target_date': str(target_date),
            },
            status=status.HTTP_200_OK,
        )


class DayReanalyzeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EntryMutationRateThrottle]

    @extend_schema(
        summary='Полный переанализ дня',
        responses={
            200: OpenApiResponse(description='Анализ выполнен.'),
            400: APIErrorSerializer,
            402: APIErrorSerializer,
        },
        tags=['Days'],
    )
    def post(self, request, entry_date: str):
        from bot.services.diary_service import diary_service
        from diary.services.full_day_analysis_service import perform_full_day_analysis

        target_date = _parse_iso_date(entry_date)
        if target_date is None:
            return api_error_response(
                code='invalid_date_format',
                message='Неверный формат даты. Используйте YYYY-MM-DD.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = request.user.language or 'ru'
        prep = run_async(
            diary_service.start_full_day_reanalysis_use_case(request.user, target_date, language)
        )
        prep = strip_transport(prep)
        if prep.get('mode') == 'no_entries':
            return api_error_response(
                code='no_entries',
                message=prep.get('text') or 'Нет записей для анализа.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        token_error = ensure_tokens(request.user, cost=1, feature_name='day_reanalyze')
        if token_error is not None:
            return token_error

        try:
            analysis_result = run_async(perform_full_day_analysis(request.user, target_date))
        except Exception:
            refund_tokens(request.user, cost=1, feature_name='day_reanalyze')
            raise

        if not analysis_result.get('success'):
            refund_tokens(request.user, cost=1, feature_name='day_reanalyze')
            return api_error_response(
                code=analysis_result.get('error') or 'full_day_analysis_failed',
                message=analysis_result.get('message') or 'Не удалось выполнить анализ дня.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        daily = analysis_result.get('daily_analysis')
        return Response(
            {
                'success': True,
                'mode': 'ready',
                'target_date': str(target_date),
                'message': analysis_result.get('message'),
                'daily_analysis': {
                    'id': getattr(daily, 'id', None),
                    'overall_analysis_text': getattr(daily, 'overall_analysis_text', None),
                }
                if daily is not None
                else None,
            },
            status=status.HTTP_200_OK,
        )


class DayRatingView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EntryMutationRateThrottle]

    @extend_schema(
        summary='Оценить анализ (PsychoAnalysis)',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'analysis_id': {'type': 'integer'},
                    'rating': {'type': 'integer', 'minimum': 1, 'maximum': 5},
                },
                'required': ['analysis_id', 'rating'],
            }
        },
        responses={200: OpenApiResponse(description='Оценка сохранена.'), 400: APIErrorSerializer},
        tags=['Days'],
    )
    def post(self, request, entry_date: str):
        from diary.services.diary_display_service import diary_display_service
        from diary.models import PsychoAnalysis

        target_date = _parse_iso_date(entry_date)
        if target_date is None:
            return api_error_response(
                code='invalid_date_format',
                message='Неверный формат даты. Используйте YYYY-MM-DD.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        analysis_id = request.data.get('analysis_id')
        rating = request.data.get('rating')
        if analysis_id is None or rating is None:
            return api_error_response(
                code='analysis_id_and_rating_required',
                message='Поля analysis_id и rating обязательны.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            analysis_id = int(analysis_id)
            rating = int(rating)
        except (TypeError, ValueError):
            return api_error_response(
                code='invalid_value',
                message='analysis_id и rating должны быть целыми числами.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            analysis = PsychoAnalysis.objects.select_related('entry').get(
                id=analysis_id,
                entry__user=request.user,
            )
        except PsychoAnalysis.DoesNotExist:
            return api_error_response(
                code='not_found',
                message='Анализ не найден.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        created_date = analysis.entry.created_at.date() if analysis.entry.created_at else None
        if created_date and str(created_date) != entry_date:
            return api_error_response(
                code='analysis_date_mismatch',
                message='Анализ не относится к указанной дате.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        result = run_async(
            diary_display_service.submit_analysis_rating_use_case(analysis_id, request.user, rating)
        )
        return from_service_dict(result, default_error_code='rating_failed')

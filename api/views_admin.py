"""
Phase D API: admin feedback, DB export, admin stats.
Thin wrappers over FeedbackService / DatabaseExportService / AdminService.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from io import BytesIO

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.error_utils import api_error_response
from api.permissions import AdminDeveloperPermission
from api.serializers import APIErrorSerializer
from api.service_bridge import run_async, strip_transport
from api.throttling import AdminMutationRateThrottle

logger = logging.getLogger(__name__)


def _display_to_dict(display) -> dict:
    data = asdict(display) if hasattr(display, '__dataclass_fields__') else dict(display)
    return strip_transport(data)


class AdminFeedbackListView(APIView):
    permission_classes = [IsAuthenticated, AdminDeveloperPermission]

    @extend_schema(
        summary='Список необработанных обращений (admin)',
        parameters=[
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter('page_size', OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiResponse(description='Пагинированный список.'), 403: APIErrorSerializer},
        tags=['Admin'],
    )
    def get(self, request):
        from core.services.feedback_service import feedback_service

        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(50, max(1, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            return api_error_response(
                code='invalid_pagination',
                message='page и page_size должны быть целыми числами.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        page_data = run_async(feedback_service.get_feedbacks_with_pagination(page, page_size))
        items = []
        for fb in page_data.get('feedbacks') or []:
            display = run_async(feedback_service.format_feedback_for_display(fb, include_full_message=False))
            items.append(_display_to_dict(display))

        return Response(
            {
                'results': items,
                'total': page_data.get('total', 0),
                'page': page_data.get('page', page),
                'page_size': page_data.get('page_size', page_size),
                'has_next': page_data.get('has_next', False),
                'has_prev': page_data.get('has_prev', False),
            },
            status=status.HTTP_200_OK,
        )


class AdminFeedbackDetailView(APIView):
    permission_classes = [IsAuthenticated, AdminDeveloperPermission]

    @extend_schema(
        summary='Детали обращения (admin)',
        responses={200: OpenApiResponse(description='Обращение.'), 404: APIErrorSerializer},
        tags=['Admin'],
    )
    def get(self, request, feedback_id: int):
        from core.services.feedback_service import feedback_service

        feedback = run_async(feedback_service.get_feedback_by_id(feedback_id))
        if not feedback:
            return api_error_response(
                code='feedback_not_found',
                message='Обращение не найдено.',
                status_code=status.HTTP_404_NOT_FOUND,
            )
        display = run_async(
            feedback_service.format_feedback_for_display(feedback, include_full_message=True)
        )
        return Response({'feedback': _display_to_dict(display)}, status=status.HTTP_200_OK)


class AdminFeedbackReplyView(APIView):
    permission_classes = [IsAuthenticated, AdminDeveloperPermission]
    throttle_classes = [AdminMutationRateThrottle]

    @extend_schema(
        summary='Ответить на обращение (admin)',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'reply_text': {'type': 'string'},
                    'language': {'type': 'string'},
                },
                'required': ['reply_text'],
            }
        },
        responses={200: OpenApiResponse(description='Ответ сохранён.'), 400: APIErrorSerializer},
        tags=['Admin'],
    )
    def post(self, request, feedback_id: int):
        from core.services.feedback_service import feedback_service

        reply_text = (request.data.get('reply_text') or '').strip()
        if not reply_text:
            return api_error_response(
                code='reply_text_required',
                message='Поле reply_text обязательно.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        language = (request.data.get('language') or request.user.language or 'ru').strip()

        result = run_async(
            feedback_service.process_admin_feedback_reply_use_case(
                admin_user=request.user,
                feedback_id=feedback_id,
                reply_text=reply_text,
                language=language,
            )
        )
        cleaned = strip_transport(result)
        if not cleaned.get('success'):
            mode = cleaned.get('mode')
            http_status = status.HTTP_400_BAD_REQUEST
            if mode == 'not_found':
                http_status = status.HTTP_404_NOT_FOUND
            elif mode == 'already_processed':
                http_status = status.HTTP_409_CONFLICT
            return api_error_response(
                code=cleaned.get('error') or 'feedback_reply_failed',
                message=cleaned.get('admin_ack_text') or 'Не удалось ответить на обращение.',
                status_code=http_status,
                details=cleaned,
            )

        notify_sent = False
        notify_error = None
        notify_chat_id = cleaned.get('notify_chat_id')
        if notify_chat_id:
            try:
                from bot.utils.message_utils import send_message_to_user
                from bot.utils.state_manager import state_manager
                from users.models import User

                target = User.objects.filter(telegram_id=notify_chat_id).select_related().first()
                if target is None:
                    feedback_obj = run_async(feedback_service.get_feedback_by_id(feedback_id))
                    target = getattr(feedback_obj, 'user', None) if feedback_obj else None

                if target is not None:
                    bot = getattr(state_manager, '_bot_instance', None)

                    async def _send():
                        return await send_message_to_user(
                            bot,
                            target,
                            cleaned.get('notify_text') or reply_text,
                        )

                    notify_sent = bool(run_async(_send()))
                else:
                    notify_error = 'target_user_not_found'
            except Exception as exc:
                logger.warning('[AdminFeedbackReply] notify failed feedback_id=%s: %s', feedback_id, exc)
                notify_error = str(exc)

        # API persists even if Telegram notify failed (reply must not be lost).
        if cleaned.get('persist_reply'):
            updated = run_async(feedback_service.reply_to_feedback(feedback_id, reply_text))
            if updated is None:
                return api_error_response(
                    code='feedback_persist_failed',
                    message='Не удалось сохранить ответ в БД.',
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {
                'success': True,
                'feedback_id': feedback_id,
                'message': cleaned.get('admin_ack_text'),
                'notify_sent': notify_sent,
                'notify_error': notify_error,
            },
            status=status.HTTP_200_OK,
        )


class AdminExportView(APIView):
    permission_classes = [IsAuthenticated, AdminDeveloperPermission]
    throttle_classes = [AdminMutationRateThrottle]

    @extend_schema(
        summary='Экспорт БД в Excel (admin)',
        responses={200: OpenApiResponse(description='xlsx file'), 403: APIErrorSerializer},
        tags=['Admin'],
    )
    def post(self, request):
        from core.services.database_export_service import database_export_service

        excel_data = database_export_service.collect_all_models_data()
        output = BytesIO()
        database_export_service.write_data_to_excel(output, excel_data)
        output.seek(0)
        filename = database_export_service.generate_excel_filename()
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class AdminStatsView(APIView):
    permission_classes = [IsAuthenticated, AdminDeveloperPermission]

    @extend_schema(
        summary='Админ-статистика продукта',
        responses={200: OpenApiResponse(description='JSON stats.'), 403: APIErrorSerializer},
        tags=['Admin'],
    )
    def get(self, request):
        from core.services.admin_service import admin_service

        stats = run_async(admin_service.get_admin_stats())
        return Response({'success': True, 'stats': stats}, status=status.HTTP_200_OK)

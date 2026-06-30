"""Custom API permissions for Phase 5 hardening."""

from django.conf import settings
from rest_framework.permissions import BasePermission


class MonitoringAccessPermission(BasePermission):
	"""Restrict monitoring endpoints to privileged users when strict mode is enabled."""

	message = 'Monitoring endpoint requires privileged access.'

	def has_permission(self, request, view):
		if not getattr(request.user, 'is_authenticated', False):
			return False

		if not getattr(settings, 'MONITORING_REQUIRE_PRIVILEGED', False):
			return True

		if request.user.is_superuser or request.user.is_staff:
			return True

		privileged_user_ids = getattr(settings, 'MONITORING_PRIVILEGED_USER_IDS', []) or []
		if getattr(request.user, 'id', None) in privileged_user_ids:
			return True

		if not getattr(settings, 'MONITORING_ALLOW_LEGACY_TELEGRAM_ID', True):
			return False

		developer_chat_id = str(getattr(settings, 'DEVELOPER_CHAT_ID', '') or '').strip()
		user_telegram_id = str(getattr(request.user, 'telegram_id', '') or '').strip()

		return bool(developer_chat_id and user_telegram_id and developer_chat_id == user_telegram_id)

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

		developer_chat_id = str(getattr(settings, 'DEVELOPER_CHAT_ID', '') or '').strip()
		user_telegram_id = str(getattr(request.user, 'telegram_id', '') or '').strip()

		return bool(developer_chat_id and user_telegram_id and developer_chat_id == user_telegram_id)

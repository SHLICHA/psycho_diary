"""Custom API throttling classes for Phase 5 hardening."""

from django.core.exceptions import ImproperlyConfigured
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.settings import api_settings


class ScopedIdentityRateThrottle(SimpleRateThrottle):
    """Throttle by authenticated user when available, otherwise by client IP."""

    scope = None

    def get_rate(self):
        if not self.scope:
            return None

        rates = api_settings.DEFAULT_THROTTLE_RATES
        if not rates or self.scope not in rates:
            raise ImproperlyConfigured(
                f'No default throttle rate set for {self.scope} scope'
            )

        return rates[self.scope]

    def get_cache_key(self, request, view):
        if not self.scope:
            return None

        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }


class AuthRateThrottle(ScopedIdentityRateThrottle):
    scope = 'auth'


class LinkGenerationRateThrottle(ScopedIdentityRateThrottle):
    scope = 'link_generation'


class MonitoringRateThrottle(ScopedIdentityRateThrottle):
    scope = 'monitoring'


class MonitoringHeavyRateThrottle(ScopedIdentityRateThrottle):
    scope = 'monitoring_heavy'


class EntryMutationRateThrottle(ScopedIdentityRateThrottle):
    scope = 'entry_mutation'


class TaskMutationRateThrottle(ScopedIdentityRateThrottle):
    scope = 'task_mutation'


class RefreshRateThrottle(ScopedIdentityRateThrottle):
    scope = 'refresh'
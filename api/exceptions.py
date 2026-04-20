"""Custom exception handler for unified API error format."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .error_utils import api_error_payload


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        return Response(
            api_error_payload('internal_error', 'Internal server error'),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    status_code = response.status_code
    details = response.data

    code = 'request_failed'
    message = 'Request failed'

    if status_code == status.HTTP_400_BAD_REQUEST:
        code = 'validation_error'
        message = 'Validation failed'
    elif status_code == status.HTTP_401_UNAUTHORIZED:
        code = 'authentication_failed'
        message = 'Authentication failed'
    elif status_code == status.HTTP_403_FORBIDDEN:
        code = 'permission_denied'
        message = 'Permission denied'
    elif status_code == status.HTTP_404_NOT_FOUND:
        code = 'not_found'
        message = 'Resource not found'
    elif status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        code = 'rate_limit_exceeded'
        message = 'Rate limit exceeded'

    if isinstance(details, dict) and details.get('detail'):
        message = str(details.get('detail'))

    response.data = api_error_payload(code=code, message=message, details=details)
    return response

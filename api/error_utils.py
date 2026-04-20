"""Utilities for unified API error payloads."""

from rest_framework.response import Response


def _normalize_details(value):
    """Convert DRF/Django error details into JSON-serializable plain types."""
    if isinstance(value, dict):
        return {key: _normalize_details(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_details(item) for item in value]
    return str(value)


def api_error_payload(code: str, message: str, details=None):
    payload = {
        'error': {
            'code': code,
            'message': message,
        }
    }
    if details is not None:
        payload['error']['details'] = _normalize_details(details)
    return payload


def api_error_response(code: str, message: str, status_code: int, details=None):
    return Response(api_error_payload(code=code, message=message, details=details), status=status_code)

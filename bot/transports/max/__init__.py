"""VK MAX transport client package."""

from .client import MaxClient
from .inbound import (
	MaxNormalizedEvent,
	normalize_update,
	process_max_update,
	aprocess_max_update,
	process_merge_target_callback,
	aprocess_merge_target_callback,
)
from .preflight import collect_preflight_errors, normalize_transport_mode
from .runtime import MaxTransportCoordinator
from .state_store import MaxStateStore

__all__ = [
	'MaxClient',
	'MaxTransportCoordinator',
	'MaxStateStore',
	'MaxNormalizedEvent',
	'collect_preflight_errors',
	'normalize_transport_mode',
	'normalize_update',
	'process_max_update',
	'aprocess_max_update',
	'process_merge_target_callback',
	'aprocess_merge_target_callback',
]

"""Users services module."""

from .email_merge_service import EmailMergeService, EmailMergeConfirmationResult
from .identity_policy_service import IdentityPolicyService, EmailIdentityResolution

__all__ = [
	'EmailMergeService',
	'EmailMergeConfirmationResult',
	'IdentityPolicyService',
	'EmailIdentityResolution',
]
"""Users services module."""

from .account_merge_service import AccountMergeService, AccountMergeResult
from .email_merge_service import EmailMergeService, EmailMergeConfirmationResult
from .identity_policy_service import IdentityPolicyService, EmailIdentityResolution

__all__ = [
	'AccountMergeService',
	'AccountMergeResult',
	'EmailMergeService',
	'EmailMergeConfirmationResult',
	'IdentityPolicyService',
	'EmailIdentityResolution',
]
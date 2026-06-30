import pytest

from bot.middlewares.user_middleware import resolve_referrer_user_from_start
from users.models import User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_referral_link_generated_without_telegram_id():
    user = await User.objects.acreate(
        username='ref_web_user',
        email='ref-web@example.com',
        telegram_id=None,
    )

    assert user.referral_link
    assert user.referral_link.startswith('ref_u_')
    assert 'None' not in user.referral_link


@pytest.mark.asyncio
async def test_resolve_referrer_supports_legacy_referral_payload():
    referrer = await User.objects.acreate(
        username='ref_legacy_owner',
        email='ref-legacy-owner@example.com',
        telegram_id=555001,
        referral_link='ref_555001_legacytoken',
    )

    resolved = await resolve_referrer_user_from_start('/start ref_555001_legacytoken', current_telegram_id=555999)

    assert resolved is not None
    assert resolved.id == referrer.id


@pytest.mark.asyncio
async def test_resolve_referrer_supports_new_referral_payload():
    referrer = await User.objects.acreate(
        username='ref_new_owner',
        email='ref-new-owner@example.com',
        telegram_id=None,
    )

    resolved = await resolve_referrer_user_from_start(f'/start {referrer.referral_link}', current_telegram_id=777999)

    assert resolved is not None
    assert resolved.id == referrer.id


@pytest.mark.asyncio
async def test_resolve_referrer_blocks_self_referral_for_legacy_payload():
    await User.objects.acreate(
        username='ref_self_owner',
        email='ref-self-owner@example.com',
        telegram_id=111222,
        referral_link='ref_111222_selftoken',
    )

    resolved = await resolve_referrer_user_from_start('/start ref_111222_selftoken', current_telegram_id=111222)

    assert resolved is None

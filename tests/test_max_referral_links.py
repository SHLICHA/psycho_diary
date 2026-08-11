"""Tests for platform-aware referral links (Telegram / MAX)."""

import pytest

from diary.services.user_profile_service import get_referral_link_info
from users.models import User


pytestmark = pytest.mark.django_db


@pytest.mark.asyncio
async def test_referral_link_telegram_default(settings):
    settings.BOT_USERNAME = 'psycho_tg_bot'
    user = await User.objects.acreate(
        username='ref_tg_user',
        telegram_id=7007001,
        referral_link='ref_u_abc123',
    )
    info = await get_referral_link_info(user, 'ru', platform='telegram')
    assert info['success'] is True
    assert info['referral_link_url'] == 'https://t.me/psycho_tg_bot?start=ref_u_abc123'
    assert 'ref_u_abc123' in info['display_message']
    assert info['share_url'].startswith('https://t.me/share/url?')


@pytest.mark.asyncio
async def test_referral_link_max_platform(settings):
    settings.MAX_BOT_USERNAME = 'PsychoMaxBot'
    user = await User.objects.acreate(
        username='ref_max_user',
        max_id=8008001,
        referral_link='ref_u_maxxyz',
    )
    info = await get_referral_link_info(user, 'ru', platform='max')
    assert info['success'] is True
    assert info['referral_link_url'] == 'https://max.ru/PsychoMaxBot?start=ref_u_maxxyz'
    assert 'https://max.ru/PsychoMaxBot?start=ref_u_maxxyz' in info['display_message']
    assert info['share_url'].startswith('https://max.ru/:share?text=')


@pytest.mark.asyncio
async def test_referral_link_max_requires_username(settings):
    settings.MAX_BOT_USERNAME = ''
    user = await User.objects.acreate(
        username='ref_max_missing',
        max_id=8008002,
        referral_link='ref_u_missing',
    )
    info = await get_referral_link_info(user, 'ru', platform='max')
    assert info['success'] is False
    assert info['error'] == 'max_bot_username_missing'

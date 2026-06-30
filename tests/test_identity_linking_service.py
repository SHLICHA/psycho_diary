import pytest

from diary.services.user_service import (
    UserService,
    link_telegram_identity,
    resolve_web_link_target,
    unlink_telegram_identity,
)
from users.models import IdentityLinkEvent, User


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_resolve_web_link_target_returns_not_found_error():
    web_user, error = await resolve_web_link_target(999999, 123456)

    assert web_user is None
    assert error == 'web_user_not_found'


@pytest.mark.asyncio
async def test_resolve_web_link_target_detects_telegram_already_linked_conflict():
    web_user = await User.objects.acreate(
        username='web_owner',
        email='web-owner@example.com',
        telegram_id=None,
    )
    await User.objects.acreate(
        username='other_owner',
        email='other-owner@example.com',
        telegram_id=555123,
    )

    resolved, error = await resolve_web_link_target(web_user.id, 555123)

    assert resolved is None
    assert error == 'telegram_already_linked'

    event = await IdentityLinkEvent.objects.filter(
        event_type='link',
        result='rejected',
        reason_code='telegram_already_linked',
    ).afirst()
    assert event is not None
    assert event.user_id == web_user.id
    assert event.actor_telegram_id == 555123


@pytest.mark.asyncio
async def test_resolve_web_link_target_detects_account_already_linked_conflict():
    web_user = await User.objects.acreate(
        username='web_already_linked',
        email='web-already@example.com',
        telegram_id=111222,
    )

    resolved, error = await resolve_web_link_target(web_user.id, 333444)

    assert resolved is None
    assert error == 'account_already_linked'


@pytest.mark.asyncio
async def test_resolve_web_link_target_success_when_same_binding():
    web_user = await User.objects.acreate(
        username='same_binding',
        email='same-binding@example.com',
        telegram_id=999001,
    )

    resolved, error = await resolve_web_link_target(web_user.id, 999001)

    assert error is None
    assert resolved is not None
    assert resolved.id == web_user.id


@pytest.mark.asyncio
async def test_link_telegram_identity_is_idempotent():
    web_user = await User.objects.acreate(
        username='idempotent_user',
        email='idempotent@example.com',
        telegram_id=None,
    )

    linked = await link_telegram_identity(web_user, 777888)
    await linked.arefresh_from_db()
    assert linked.telegram_id == 777888

    linked_again = await link_telegram_identity(linked, 777888)
    await linked_again.arefresh_from_db()
    assert linked_again.telegram_id == 777888

    events = [
        event
        async for event in IdentityLinkEvent.objects.filter(
            user=web_user,
            event_type='link',
            result='success',
        ).order_by('created_at')
    ]
    assert len(events) == 2
    assert events[0].reason_code == 'link_success'
    assert events[1].reason_code == 'link_idempotent'


@pytest.mark.asyncio
async def test_unlink_telegram_identity_writes_success_and_idempotent_events():
    web_user = await User.objects.acreate(
        username='unlink_user',
        email='unlink@example.com',
        telegram_id=123321,
    )

    unlinked = await unlink_telegram_identity(web_user)
    await unlinked.arefresh_from_db()
    assert unlinked.telegram_id is None

    unlinked_again = await unlink_telegram_identity(unlinked)
    await unlinked_again.arefresh_from_db()
    assert unlinked_again.telegram_id is None

    events = [
        event
        async for event in IdentityLinkEvent.objects.filter(
            user=web_user,
            event_type='unlink',
            result='success',
        ).order_by('created_at')
    ]
    assert len(events) == 2
    assert events[0].reason_code == 'unlink_success'
    assert events[0].metadata['previous_telegram_id'] == 123321
    assert events[1].reason_code == 'unlink_idempotent'


@pytest.mark.asyncio
async def test_identity_linking_records_transport_agnostic_source_fields():
    web_user = await User.objects.acreate(
        username='max_source_user',
        email='max-source@example.com',
        telegram_id=None,
    )

    resolved, error = await UserService.resolve_web_link_target(
        web_user_id=web_user.id,
        current_telegram_id=456654,
        source_platform='max',
        source_context='max_link_callback',
    )
    assert error is None
    assert resolved is not None

    await UserService.link_telegram_identity(
        web_user=resolved,
        telegram_id=456654,
        source_platform='max',
        source_context='max_link_callback',
    )

    event = await IdentityLinkEvent.objects.filter(
        user=web_user,
        event_type='link',
        result='success',
    ).afirst()
    assert event is not None
    assert event.source_platform == 'max'
    assert event.source_context == 'max_link_callback'

"""
Тесты для base_service.py
"""
import pytest
from asgiref.sync import sync_to_async
from model_bakery import baker

from core.services.base_service import BaseService
from users.models import User


# Настройка baker для работы с Encrypted полями
from core.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedJSONField, EncryptedEmailField
baker.generators.add('core.encrypted_fields.EncryptedTextField', lambda: "Тестовый текст")
baker.generators.add('core.encrypted_fields.EncryptedCharField', lambda: "Текст")
baker.generators.add('core.encrypted_fields.EncryptedJSONField', lambda: {})
baker.generators.add('core.encrypted_fields.EncryptedEmailField', lambda: "test@test.com")


@pytest.mark.django_db(transaction=True)
class TestBaseServiceGetUserByTelegramId:
    """Тесты для get_user_by_telegram_id."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=77701, username="baseuser")

    @pytest.mark.asyncio
    async def test_get_user_existing(self, test_user):
        user = await BaseService.get_user_by_telegram_id(77701)
        assert user is not None
        assert user.telegram_id == 77701

    @pytest.mark.asyncio
    async def test_get_user_not_found(self):
        user = await BaseService.get_user_by_telegram_id(999999)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_wrong_type(self):
        user = await BaseService.get_user_by_telegram_id(-1)
        assert user is None


@pytest.mark.django_db(transaction=True)
class TestBaseServiceAsyncDbOperation:
    """Тесты для async_db_operation."""

    @pytest.fixture
    def test_user(self):
        return baker.make(User, telegram_id=77702, username="asyncopuser")

    @pytest.mark.asyncio
    async def test_async_db_operation_with_create(self):
        result = await BaseService.async_db_operation(
            User.objects.create,
            telegram_id=77703,
            username="created_via_service",
            first_name="Test",
            last_name=""
        )
        assert result is not None
        assert result.telegram_id == 77703

    @pytest.mark.asyncio
    async def test_async_db_operation_with_filter_count(self, test_user):
        def do_filter():
            return list(User.objects.filter(telegram_id=77702))
        result = await BaseService.async_db_operation(do_filter)
        assert len(result) == 1


@pytest.mark.django_db(transaction=True)
class TestBaseServiceSyncDb:
    """Тесты для sync_db декоратора."""

    @pytest.mark.asyncio
    async def test_sync_db_decorator(self):
        @BaseService.sync_db
        def get_all_users_count():
            return User.objects.count()

        count = await get_all_users_count()
        assert isinstance(count, int)
        assert count >= 0


@pytest.mark.django_db(transaction=True)
class TestBaseServiceGetQuerysetSync:
    """Тесты для get_queryset_sync."""

    @pytest.fixture
    def test_users(self):
        baker.make(User, telegram_id=77710, username="user1")
        baker.make(User, telegram_id=77711, username="user2")

    @pytest.mark.asyncio
    async def test_get_queryset_sync(self, test_users):
        from users.models import User as UserModel
        result = await BaseService.get_queryset_sync(
            lambda: list(UserModel.objects.filter(telegram_id__in=[77710, 77711]))
        )
        assert len(result) == 2

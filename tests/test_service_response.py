"""
Тесты для service_response.py
"""
import pytest

from core.service_response import ServiceResponse, ServiceResponseList


class TestServiceResponseOk:
    """Тесты для ServiceResponse.ok()."""

    def test_ok_no_args(self):
        r = ServiceResponse.ok()
        assert r.success is True
        assert r.data is None
        assert r.error is None
        assert r.message is None
        assert r.metadata == {}

    def test_ok_with_data(self):
        r = ServiceResponse.ok(data={'user_id': 42})
        assert r.success is True
        assert r.data == {'user_id': 42}
        assert r.get('user_id') == 42

    def test_ok_with_message(self):
        r = ServiceResponse.ok(message='Успешно!')
        assert r.message == 'Успешно!'

    def test_ok_with_metadata(self):
        r = ServiceResponse.ok(data={'x': 1}, count=5, status='done')
        assert r.metadata == {'count': 5, 'status': 'done'}

    def test_ok_has_data(self):
        assert ServiceResponse.ok(data={'a': 1}).has_data() is True
        assert ServiceResponse.ok().has_data() is False

    def test_ok_is_error_false(self):
        assert ServiceResponse.ok().is_error() is False


class TestServiceResponseFail:
    """Тесты для ServiceResponse.fail()."""

    def test_fail_minimal(self):
        r = ServiceResponse.fail(error='not_found')
        assert r.success is False
        assert r.error == 'not_found'
        assert r.message is None
        assert r.data is None

    def test_fail_with_message(self):
        r = ServiceResponse.fail(error='not_found', message='Запись не найдена')
        assert r.message == 'Запись не найдена'

    def test_fail_with_data(self):
        r = ServiceResponse.fail(error='partial', data={'partial': True})
        assert r.data == {'partial': True}

    def test_fail_is_error(self):
        assert ServiceResponse.fail('err').is_error() is True


class TestServiceResponseMakeError:
    """Тесты для ServiceResponse.make_error() — алиас fail()."""

    def test_make_error_is_fail(self):
        r1 = ServiceResponse.make_error(error='e', message='m')
        r2 = ServiceResponse.fail(error='e', message='m')
        assert r1.error == r2.error
        assert r1.message == r2.message
        assert r1.success == r2.success


class TestServiceResponseBool:
    """Тесты для __bool__."""

    def test_ok_is_truthy(self):
        assert bool(ServiceResponse.ok()) is True

    def test_fail_is_falsy(self):
        assert bool(ServiceResponse.fail('err')) is False


class TestServiceResponseGet:
    """Тесты для метода get()."""

    def test_get_existing_key(self):
        r = ServiceResponse.ok(data={'key': 'value'})
        assert r.get('key') == 'value'

    def test_get_missing_key_default(self):
        r = ServiceResponse.ok(data={'a': 1})
        assert r.get('b', 'default') == 'default'

    def test_get_non_dict_data(self):
        r = ServiceResponse.ok(data=[1, 2, 3])
        assert r.get('key', 'default') == 'default'


class TestServiceResponseList:
    """Тесты для ServiceResponseList."""

    def test_empty_list(self):
        lst = ServiceResponseList()
        assert lst.total_count == 0
        assert lst.success_count == 0
        assert lst.error_count == 0
        assert lst.all_success is True

    def test_all_success(self):
        lst = ServiceResponseList()
        lst.add(ServiceResponse.ok())
        lst.add(ServiceResponse.ok(data={'x': 1}))
        assert lst.total_count == 2
        assert lst.success_count == 2
        assert lst.error_count == 0
        assert lst.all_success is True

    def test_mixed(self):
        lst = ServiceResponseList()
        lst.add(ServiceResponse.ok())
        lst.add(ServiceResponse.fail('err1'))
        lst.add(ServiceResponse.fail('err2', message='Oops'))
        assert lst.total_count == 3
        assert lst.success_count == 1
        assert lst.error_count == 2
        assert lst.all_success is False

    def test_errors_property(self):
        lst = ServiceResponseList()
        lst.add(ServiceResponse.ok())
        lst.add(ServiceResponse.fail('e1'))
        lst.add(ServiceResponse.fail('e2'))
        errors = lst.errors
        assert len(errors) == 2
        assert all(not e.success for e in errors)

    def test_successes_property(self):
        lst = ServiceResponseList()
        lst.add(ServiceResponse.ok(data={'a': 1}))
        lst.add(ServiceResponse.fail('e'))
        lst.add(ServiceResponse.ok())
        successes = lst.successes
        assert len(successes) == 2
        assert all(e.success for e in successes)

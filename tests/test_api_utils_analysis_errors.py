from bot.utils.api_utils import format_api_error_for_analysis, get_api_error_message


def test_format_api_error_response_parse_failed_is_user_safe():
    analysis_result = {
        'success': False,
        'error': 'response_parse_failed',
        'message': 'Не удалось обработать ответ AI. Попробуйте позже.',
    }

    comment, recommendation, analysis_text, log_message = format_api_error_for_analysis(
        analysis_result=analysis_result,
        language='ru',
        is_final=False,
    )

    assert 'ошибка обработки ответа' in comment
    assert recommendation == 'Попробуйте позже'
    assert 'ошибки обработки ответа AI' in analysis_text
    assert 'response_parse_failed' in log_message


def test_format_api_error_upstream_unavailable_has_explicit_branch():
    analysis_result = {
        'success': False,
        'error': 'upstream_unavailable',
        'message': 'Внешний AI сервис временно недоступен',
    }

    comment, recommendation, analysis_text, log_message = format_api_error_for_analysis(
        analysis_result=analysis_result,
        language='ru',
        is_final=True,
    )

    assert 'AI сервис недоступен' in comment
    assert recommendation == 'Попробуйте позже'
    assert 'внешний AI сервис временно недоступен' in analysis_text
    assert 'upstream_unavailable' in log_message


def test_format_api_error_connection_error_aliases_upstream():
    """connection_error is an alias for upstream_unavailable at the user-facing layer."""
    result_upstream = format_api_error_for_analysis(
        {'success': False, 'error': 'upstream_unavailable', 'message': 'x'}, language='ru'
    )
    result_connection = format_api_error_for_analysis(
        {'success': False, 'error': 'connection_error', 'message': 'x'}, language='ru'
    )

    # comment and analysis_text must be identical; only log_message may differ (contains error code)
    assert result_upstream[0] == result_connection[0], "comment must match"
    assert result_upstream[2] == result_connection[2], "analysis_text must match"
    assert 'connection_error' in result_connection[3]


def test_format_api_error_context_length_exceeded_is_explicit():
    analysis_result = {
        'success': False,
        'error': 'context_length_exceeded',
        'message': 'context too long',
    }

    comment, recommendation, analysis_text, log_message = format_api_error_for_analysis(
        analysis_result=analysis_result,
        language='ru',
        is_final=False,
    )

    assert 'превышен размер контекста' in comment
    assert recommendation == 'Попробуйте позже'
    assert 'слишком большого объема запроса к AI' in analysis_text
    assert 'context_length_exceeded' in log_message


def test_get_api_error_message_supports_new_codes():
    assert get_api_error_message('response_parse_failed', 'ru') == 'Не удалось обработать ответ AI'
    assert get_api_error_message('upstream_unavailable', 'ru') == 'Внешний AI сервис временно недоступен'
    assert get_api_error_message('context_length_exceeded', 'ru') == 'Контекст запроса превышает лимит модели'
    assert get_api_error_message('request_failed', 'en') == 'Failed to complete AI service request'

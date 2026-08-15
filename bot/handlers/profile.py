"""Profile handlers (transport-only)."""
import os
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext

from messages import get_message, get_button_text
from bot.keyboards.identity_merge_keyboard import get_requester_merge_confirmation_keyboard
from bot.states.settings_states import SettingsStates
from bot.keyboards import (
    get_single_button_keyboard,
    get_account_deletion_confirmation_keyboard,
)
from bot.utils.state_manager import state_manager
from bot.decorators.analytics_decorator import log_user_activity
from bot.decorators.premium_decorator import requires_premium
from diary.services.user_profile_service import (
    get_user_profile_field,
    get_user_transaction_history,
    process_profile_field_update,
    anonymize_user_account,
    export_user_data,
    build_profile_screen_view,
    build_psychology_profile_view,
    build_edit_profile_menu_view,
    build_list_field_edit_prompt,
    build_account_deletion_menu_view,
    build_referral_link_view,
)
from diary.services.main_menu_service import build_main_menu_data
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback

router = Router()
logger = logging.getLogger(__name__)

MAX_INLINE_FIELD_LENGTH = 3000

PROFILE_FIELD_ASK_MESSAGE_KEYS = {
    'first_name': 'ask_new_name',
    'email': 'ask_new_email',
    'date_of_birth': 'ask_new_dob',
    'hobbies': 'ask_new_hobbies',
    'life_facts': 'ask_new_life_facts',
}


@router.callback_query(F.data == "user_profile")
@log_user_activity('show_profile')
async def show_user_profile(callback: CallbackQuery, user, language: str):
    """Показ основного профиля пользователя."""
    try:
        view = await build_profile_screen_view(user, user.language or language)
        await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)


@router.callback_query(F.data == "view_psychology_profile")
async def show_psychology_profile(callback: CallbackQuery, user, language: str):
    """Показ психологического профиля пользователя (только текстовое описание)."""
    try:
        view = await build_psychology_profile_view(user, language)
        await callback.message.edit_text(
            view['text'],
            reply_markup=view['reply_markup'],
            parse_mode=view.get('parse_mode') or 'HTML',
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе психологического профиля: {e}", exc_info=True)
        error_msg = get_message('error_generic', language=language)
        await callback.message.edit_text(error_msg, reply_markup=get_single_button_keyboard(language, 'user_profile', 'btn_back'))
        await callback.answer(error_msg, show_alert=True)


@router.callback_query(F.data == "view_transaction_history")
async def show_transaction_history(callback: CallbackQuery, user, language: str):
    """Показывает последние 10 транзакций и платежей пользователя."""
    try:
        history_result = await get_user_transaction_history(user, language, limit=10)

        if not history_result['success']:
            logger.error(f"Ошибка получения истории транзакций: {history_result.get('error')}")
            await callback.answer(get_message('error_generic', language=language), show_alert=True)
            return

        history_msg = history_result['message']
        keyboard = get_single_button_keyboard(language, 'user_profile', 'btn_back')

        await callback.message.edit_text(
            history_msg,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе истории транзакций: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)


@router.callback_query(F.data.startswith("view_profile_field:"))
@requires_premium(alert_message_key='feature_requires_premium')
async def show_profile_field(callback: CallbackQuery, user, language: str):
    """Показывает конкретное поле психологического профиля."""
    try:
        field_key = callback.data.split(":")[1]

        field_result = await get_user_profile_field(user, field_key, language)

        if not field_result['success']:
            error_msg = field_result.get('text', get_message('error_generic', language))
            logger.error(f"Ошибка получения поля профиля {field_key}: {field_result.get('error')}")
            await callback.answer(error_msg, show_alert=True)
            return

        field_text = field_result['text']

        back_to_psychology_button = [
            [
                InlineKeyboardButton(
                    text=get_button_text('btn_back_to_psychology', language),
                    callback_data="view_psychology_profile"
                )
            ]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=back_to_psychology_button)

        try:
            await callback.message.edit_text(
                field_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as edit_error:
            logger.warning(f"Сообщение с полем профиля слишком длинное ({len(field_text)} символов) или другая ошибка при edit_text: {edit_error}. Отправляем краткое уведомление.")
            error_notification = get_message('profile_field_too_long', language)
            await callback.message.edit_text(
                error_notification,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        await callback.answer()
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка парсинга callback_data в show_profile_field: {callback.data} - {e}")
        await callback.answer(get_message('error_generic', language), show_alert=True)
    except Exception as e:
        logger.error(f"Неожиданная ошибка при показе поля профиля {callback.data}: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language), show_alert=True)


# --- Редактирование профиля ---

@router.callback_query(F.data == "edit_profile")
async def show_edit_profile_menu(callback: CallbackQuery, user, language: str):
    """Показ меню редактирования профиля"""
    try:
        view = await build_edit_profile_menu_view(user, language)
        await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню редактирования профиля: {e}")
        await callback.answer(get_message('error_generic', language=language))


# --- Обработчики запроса новых значений ---

async def _request_new_value(callback_or_message, state: FSMContext, state_key, ask_message_key, back_callback_data, user, language: str):
    """Вспомогательная функция для запроса нового значения."""
    try:
        await state_manager.set_state(state, state_key)
        ask_msg = get_message(ask_message_key, language)
        reply_markup = get_single_button_keyboard(language, back_callback_data, 'btn_back')
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.edit_text(
                ask_msg,
                reply_markup=reply_markup
            )
            await callback_or_message.answer()
        elif isinstance(callback_or_message, Message):
            await callback_or_message.answer(
                ask_msg,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка при запросе нового значения: {e}")
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer(get_message('error_generic', language=language))
        elif isinstance(callback_or_message, Message):
            await callback_or_message.answer(get_message('error_generic', language=language))


@router.callback_query(F.data == "edit_profile_name")
async def edit_profile_name(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование имени"""
    await _request_new_value(callback, state, SettingsStates.waiting_for_name_input, 'ask_new_name', 'edit_profile', user, language)


@router.callback_query(F.data == "edit_profile_email")
async def edit_profile_email(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование email"""
    await _request_new_value(callback, state, SettingsStates.waiting_for_email_input, 'ask_new_email', 'edit_profile', user, language)


@router.callback_query(F.data == "edit_profile_dob")
async def edit_profile_dob(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование даты рождения"""
    await _request_new_value(callback, state, SettingsStates.waiting_for_date_of_birth_input, 'ask_new_dob', 'edit_profile', user, language)


@router.callback_query(F.data == "edit_profile_hobbies")
async def edit_profile_hobbies(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование увлечений"""
    try:
        view = await build_list_field_edit_prompt(
            user=user,
            field_name='hobbies',
            language=user.language or language,
            max_length=MAX_INLINE_FIELD_LENGTH,
        )
        if not view.get('success'):
            await callback.answer(get_message('error_generic', language=language))
            return
        await state_manager.set_state(state, SettingsStates.waiting_for_hobbies_input)
        await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе новых увлечений: {e}")
        await callback.answer(get_message('error_generic', language=language))


@router.callback_query(F.data == "edit_profile_life_facts")
async def edit_profile_life_facts(callback: CallbackQuery, state: FSMContext, user, language: str):
    """Редактирование фактов о жизни"""
    try:
        view = await build_list_field_edit_prompt(
            user=user,
            field_name='life_facts',
            language=user.language or language,
            max_length=MAX_INLINE_FIELD_LENGTH,
        )
        if not view.get('success'):
            await callback.answer(get_message('error_generic', language=language))
            return
        await state_manager.set_state(state, SettingsStates.waiting_for_life_facts_input)
        await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе новых фактов о жизни: {e}")
        await callback.answer(get_message('error_generic', language=language))


async def _process_field_input(message: Message, state: FSMContext, user, language: str, field_name: str, back_callback_data: str):
    """Transport-обёртка: parse input → use case → render/FSM."""
    try:
        new_value = message.text.strip()
        if new_value.lower() in ['назад', 'back', '/start', '/menu']:
            await state_manager.clear_state(state)
            await show_edit_profile_menu_callback(message, user, language)
            return

        if not new_value:
            error_msg = get_message('invalid_input', language)
            await message.answer(error_msg)
            return

        update_result = await process_profile_field_update(user, field_name, new_value)
        if not update_result['success']:
            error_code = update_result.get('error_code') or update_result.get('error')
            if error_code == 'email_confirmation_required':
                merge_request_id = update_result.get('merge_request_id')
                await message.answer(
                    get_message(
                        'merge_requester_confirmation_prompt',
                        language,
                    ),
                    reply_markup=(
                        get_requester_merge_confirmation_keyboard(merge_request_id, language)
                        if merge_request_id
                        else None
                    ),
                )
                return
            if error_code == 'email_already_exists':
                await message.answer(get_message('email_already_exists', language))
                return
            if error_code == 'target_messenger_unavailable':
                await message.answer(get_message('merge_target_messenger_unavailable', language))
                return
            if error_code in {
                'invalid_email_format',
                'invalid_date_format',
                'invalid_date_future',
                'invalid_input',
                'invalid_format',
            }:
                message_key = (
                    'invalid_date_format'
                    if error_code == 'invalid_format'
                    else error_code
                )
                await message.answer(get_message(message_key, language))
                ask_key = PROFILE_FIELD_ASK_MESSAGE_KEYS.get(field_name, f'ask_new_{field_name}')
                ask_msg = get_message(ask_key, language)
                reply_markup = get_single_button_keyboard(language, back_callback_data, 'btn_back')
                await message.answer(ask_msg, reply_markup=reply_markup)
                return

            error_msg = get_message('error_generic', language)
            logger.error(f"Ошибка обновления поля {field_name}: {update_result.get('error')}")
            await message.answer(error_msg)
            await state_manager.clear_state(state)
            return
        success_msg = get_message('profile_updated', language)
        await message.answer(success_msg)
        from diary.services.activity_service import record_user_activity

        await record_user_activity(
            user,
            'profile_updated',
            platform='telegram',
            metadata={'context': f'Обновление поля {field_name}', 'field': field_name},
        )
        await show_edit_profile_menu_callback(message, user, language)
        await state_manager.clear_state(state)
    except Exception as e:
        logger.error(f"Ошибка при обработке ввода для поля {field_name}: {e}")
        error_msg = get_message('error_generic', language)
        await message.answer(error_msg)
        await state_manager.clear_state(state)


@router.message(SettingsStates.waiting_for_name_input)
async def process_name_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода нового имени"""
    await _process_field_input(message, state, user, language, 'first_name', 'edit_profile')


@router.message(SettingsStates.waiting_for_email_input)
async def process_email_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода нового email"""
    await _process_field_input(message, state, user, language, 'email', 'edit_profile')


@router.message(SettingsStates.waiting_for_date_of_birth_input)
async def process_dob_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода новой даты рождения"""
    await _process_field_input(message, state, user, language, 'date_of_birth', 'edit_profile')


@router.message(SettingsStates.waiting_for_hobbies_input)
async def process_hobbies_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода новых увлечений"""
    await _process_field_input(message, state, user, language, 'hobbies', 'edit_profile')


@router.message(SettingsStates.waiting_for_life_facts_input)
async def process_life_facts_input(message: Message, state: FSMContext, user, language: str):
    """Обработка ввода новых фактов о жизни"""
    await _process_field_input(message, state, user, language, 'life_facts', 'edit_profile')


async def show_edit_profile_menu_callback(message_or_callback, user, language: str):
    """Показ меню редактирования профиля (callback)"""
    try:
        view = await build_edit_profile_menu_view(user, language)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(view['text'], reply_markup=view['reply_markup'])
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.edit_text(
                view['text'], reply_markup=view['reply_markup']
            )
            await message_or_callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню редактирования профиля: {e}")
        error_msg = get_message('error_generic', language)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(error_msg)
        elif isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.answer(error_msg)


# --- Удаление аккаунта ---

@router.callback_query(F.data == "delete_account")
async def show_account_deletion_menu(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Показ меню удаления аккаунта"""
    try:
        view = build_account_deletion_menu_view(user, language)
        await state_manager.set_state(state, SettingsStates.in_account_deletion_menu)
        await state_manager.update_state_data(state, balance_warning=view.get('balance_warning'))
        await callback.message.edit_text(view['text'], reply_markup=view['reply_markup'])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню удаления аккаунта: {e}")
        await callback.answer(get_message('error_generic', language=language))


@router.callback_query(F.data == "confirm_account_deletion_final")
async def confirm_account_deletion_final(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Финальное подтверждение удаления аккаунта - запрос текста подтверждения"""
    try:
        data = await state_manager.get_state_data(state)
        balance_warning = data.get('balance_warning', '')
        confirm_msg = get_message('confirm_account_deletion', language, balance_warning=balance_warning)

        success = await safe_edit_message_text(
            message=callback.message,
            text=confirm_msg,
            reply_markup=get_account_deletion_confirmation_keyboard(language)
        )

        if not success:
            logger.error(f"[confirm_account_deletion_final] Не удалось отредактировать сообщение для пользователя {user.telegram_id}")
            await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)
            return

        await state_manager.set_state(state, SettingsStates.waiting_for_deletion_confirmation_text)
        await safe_answer_callback(callback)
    except Exception as e:
        logger.error(f"Ошибка при финальном подтверждении удаления аккаунта: {e}")
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)


@router.message(SettingsStates.waiting_for_deletion_confirmation_text)
async def process_account_deletion_confirmation_text(message: Message, user, language: str, state: FSMContext):
    """Обработка ввода текста подтверждения удаления аккаунта"""
    try:
        confirmation_text = message.text.strip()
        expected_text = get_message('delete_account_btn', language)
        if confirmation_text != expected_text:
            error_msg = get_message('invalid_confirmation_text', language)
            await message.answer(error_msg)
            data = await state_manager.get_state_data(state)
            balance_warning = data.get('balance_warning', '')
            confirm_msg = get_message('confirm_account_deletion', language, balance_warning=balance_warning)
            await message.answer(confirm_msg)
            return

        result = await anonymize_user_account(user)
        if result['success']:
            success_msg = get_message('account_deletion_confirmed', language)
            await message.answer(success_msg)
            await state_manager.clear_state(state)
        else:
            error_msg = get_message('account_deletion_error', language)
            logger.error(f"Ошибка при обезличивании аккаунта {user.telegram_id}: {result.get('error')}")
            await message.answer(error_msg)
    except Exception as e:
        logger.error(f"Ошибка при обработке текста подтверждения удаления аккаунта: {e}")
        error_msg = get_message('account_deletion_error', language)
        await message.answer(error_msg)


@router.callback_query(F.data == "delete_account_cancel")
async def cancel_account_deletion(callback: CallbackQuery, user, language: str, state: FSMContext):
    """Отмена удаления аккаунта - возврат в главное меню"""
    try:
        cancel_msg = get_message('account_deletion_cancelled', language)
        success = await safe_edit_message_text(
            message=callback.message,
            text=cancel_msg,
            reply_markup=None
        )
        if not success:
            logger.warning(f"[cancel_account_deletion] Не удалось отредактировать сообщение для отмены удаления у пользователя {user.telegram_id}, возможно, оно не изменилось. Продолжаем с возвратом в главное меню.")

        await state_manager.clear_state(state)
        await asyncio.sleep(0.5)

        menu_data = await build_main_menu_data(user=user, language=language)
        main_menu_msg = menu_data['message_text']
        keyboard = menu_data['keyboard']

        success_main_menu = await safe_edit_message_text(
            message=callback.message,
            text=main_menu_msg,
            reply_markup=keyboard
        )

        if not success_main_menu:
            logger.error(f"[cancel_account_deletion] Не удалось отредактировать сообщение на главное меню для пользователя {user.telegram_id}")
            await callback.message.answer(
                text=main_menu_msg,
                reply_markup=keyboard
            )

        await safe_answer_callback(callback)

    except Exception as e:
        logger.error(f"Ошибка при отмене удаления аккаунта: {e}", exc_info=True)
        await safe_answer_callback(callback, get_message('error_generic', language), show_alert=True)

        try:
            await state_manager.clear_state(state)
            menu_data = await build_main_menu_data(user=user, language=language)
            main_menu_msg = menu_data['message_text']
            keyboard = menu_data['keyboard']
            await callback.message.answer(
                text=main_menu_msg,
                reply_markup=keyboard
            )
        except Exception as fallback_error:
            logger.error(f"Ошибка при восстановлении в отмене удаления (fallback): {fallback_error}")


@router.callback_query(F.data == "export_user_data")
@requires_premium(alert_message_key='feature_requires_premium')
async def handle_export_user_data(callback: CallbackQuery, user, language: str):
    """Обработчик экспорта данных пользователя в .docx"""
    try:
        status_msg = await callback.message.answer(get_message('export_status_preparing', language))
        export_result = await export_user_data(user)
        if not export_result['success']:
            logger.error(f"Ошибка при экспорте данных пользователя {user.telegram_id}: {export_result.get('error')}")
            await callback.message.answer(get_message('export_error', language))
            await callback.answer()
            return

        file_path = export_result['file_path']
        try:
            await status_msg.delete()
        except Exception as delete_error:
            logger.debug(f"[export_user_data_handler] status_msg delete failed: {delete_error}")
        with open(file_path, 'rb') as f:
            file_data = f.read()
        input_file = BufferedInputFile(file_data, filename='export.docx')
        await callback.message.answer_document(
            document=input_file,
            caption=get_message('export_caption', language)
        )
        try:
            os.remove(file_path)
        except Exception as remove_error:
            logger.debug(f"[export_user_data_handler] temp file remove failed: {remove_error}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при экспорте данных пользователя {user.telegram_id}: {e}", exc_info=True)
        await callback.message.answer(get_message('export_error', language))
        await callback.answer()


@router.callback_query(F.data == "get_referral_link")
@log_user_activity('referral')
async def show_referral_link(callback: CallbackQuery, user, language: str):
    """Показывает реферальную ссылку пользователя."""
    try:
        view = await build_referral_link_view(user, language)
        if not view.get('success'):
            await callback.answer(
                view.get('text') or get_message('error_generic', language),
                show_alert=True,
            )
            return
        await callback.message.edit_text(
            view['text'],
            reply_markup=view['reply_markup'],
            parse_mode="HTML",
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе реферальной ссылки: {e}", exc_info=True)
        await callback.answer(get_message('error_generic', language=language), show_alert=True)

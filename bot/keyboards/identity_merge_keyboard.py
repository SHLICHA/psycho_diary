"""Inline-клавиатуры для двустороннего подтверждения merge Telegram/MAX."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from messages import get_message


def get_requester_merge_confirmation_keyboard(merge_request_id: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура для инициатора: подтвердить запуск merge или отменить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_message('merge_btn_yes', language),
                    callback_data=f"merge_requester:yes:{merge_request_id}",
                ),
                InlineKeyboardButton(
                    text=get_message('merge_btn_no', language),
                    callback_data=f"merge_requester:no:{merge_request_id}",
                ),
            ]
        ]
    )


def get_target_merge_confirmation_keyboard(merge_request_id: int, language: str) -> InlineKeyboardMarkup:
    """Клавиатура для второго канала: подтвердить или отклонить merge."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_message('merge_btn_yes', language),
                    callback_data=f"merge_target:yes:{merge_request_id}",
                ),
                InlineKeyboardButton(
                    text=get_message('merge_btn_no', language),
                    callback_data=f"merge_target:no:{merge_request_id}",
                ),
            ]
        ]
    )

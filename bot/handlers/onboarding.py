"""
Handlers для процесса онбординга (знакомства) нового пользователя.
"""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.types import ContentType

from asgiref.sync import sync_to_async

from messages import get_message
from bot.utils.message_utils import safe_edit_message_text
from bot.utils.callback_utils import safe_answer_callback
from bot.utils.state_manager import state_manager
from users.models import User # Импортируем User для обновления onboarding_step
from bot.states.diary_states import DiaryStates

router = Router()
logger = logging.getLogger(__name__)

"""
Handlers для экспорта/импорта базы данных.
Тонкий слой routing: receive event → call service → format response → send.
"""

import logging

import pandas as pd
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from core.services.database_export_service import database_export_service

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("export_database"))
async def export_database_handler(message: Message):
    """Экспорт всей базы данных в Excel файл"""

    user_id = message.from_user.id
    if not database_export_service.is_developer(user_id):
        logger.warning(f"Попытка доступа к экспорту от пользователя {user_id}")
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return

    logger.info(f"Начало экспорта БД пользователем {user_id}")

    try:
        await message.answer("🔄 Начинаю экспорт базы данных...")

        excel_data = await sync_to_async(database_export_service.collect_all_models_data)()

        output = database_export_service.write_data_to_excel(excel_data)

        filename = database_export_service.generate_excel_filename()
        excel_file = BufferedInputFile(output.getvalue(), filename=filename)

        await message.answer_document(
            document=excel_file,
            caption="✅ База данных успешно экспортирована"
        )
        logger.info(f"Экспорт БД завершен пользователем {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при экспорте базы данных: {e}")
        await message.answer(f"❌ Ошибка при экспорте: {str(e)}")


@router.message(F.document)
async def import_database_handler(message: Message):
    """Импорт базы данных из Excel файла"""

    user_id = message.from_user.id
    if not database_export_service.is_developer(user_id):
        logger.warning(f"Попытка доступа к импорту от пользователя {user_id}")
        return

    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        return

    logger.info(f"Начало импорта БД пользователем {user_id}")

    try:
        await message.answer("🔄 Начинаю импорт базы данных...")

        file = await message.bot.download(message.document)
        file_content = file.read()

        excel_data = pd.ExcelFile(file_content)

        import_results = await sync_to_async(database_export_service.perform_import)(excel_data)

        for result in import_results:
            await message.answer(result)

        await message.answer("✅ База данных успешно импортирована!")
        logger.info(f"Импорт БД завершен пользователем {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при импорте базы данных: {e}")
        await message.answer(f"❌ Ошибка при импорте: {str(e)}")

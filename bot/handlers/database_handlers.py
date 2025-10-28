import asyncio
import logging
import pandas as pd
from io import BytesIO
from django.db import transaction
from django.conf import settings
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from asgiref.sync import sync_to_async
import pytz
from django.utils import timezone
from datetime import datetime

from users.models import User, UserProfileHistory, CityTimezone, Feedback
from diary.models import (
    DiaryEntry, PsychoAnalysis, TherapyProgress, TherapyTask, 
    TaskCompletion, TaskCompletionAnalysis, UserActivity, 
    CombinedDiaryEntry, DailyAnalysis, WeeklyAnalysis, 
    NextEntryPrompt, AnalysisRating
)

logger = logging.getLogger(__name__)

router = Router()

MODELS_ORDER = [
    User,
    CityTimezone,
    DiaryEntry,
    PsychoAnalysis,
    TherapyProgress,
    TherapyTask,
    TaskCompletion,
    TaskCompletionAnalysis,
    UserActivity,
    CombinedDiaryEntry,
    DailyAnalysis,
    WeeklyAnalysis,
    NextEntryPrompt,
    AnalysisRating,
    UserProfileHistory,
    Feedback
]

def is_developer(user_id: int) -> bool:
    """Проверка, является ли пользователь разработчиком"""
    developer_id = getattr(settings, 'DEVELOPER_CHAT_ID', None)
    if developer_id is None:
        logger.error("DEVELOPER_CHAT_ID не найден в settings")
        return False
    
    return str(user_id) == str(developer_id)

@router.message(Command("export_database"))
async def export_database_handler(message: Message):
    """Экспорт всей базы данных в Excel файл"""
    
    user_id = message.from_user.id
    if not is_developer(user_id):
        logger.warning(f"Попытка доступа к экспорту от пользователя {user_id}")
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    logger.info(f"Начало экспорта БД пользователем {user_id}")
    
    try:
        await message.answer("🔄 Начинаю экспорт базы данных...")
        output = BytesIO()
        excel_data = await _get_excel_data()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                _write_data_to_excel(writer, excel_data)
        except ImportError:
            try:
                output.seek(0)
                output.truncate(0)
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    _write_data_to_excel(writer, excel_data)
            except ImportError:
                output.seek(0)
                output.truncate(0)
                with pd.ExcelWriter(output) as writer:
                    _write_data_to_excel(writer, excel_data)
        output.seek(0)
        excel_file = BufferedInputFile(
            output.getvalue(),
            filename=f"database_backup_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        await message.answer_document(
            document=excel_file,
            caption="✅ База данных успешно экспортирована"
        )
        logger.info(f"Экспорт БД завершен пользователем {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при экспорте базы данных: {e}")
        await message.answer(f"❌ Ошибка при экспорте: {str(e)}")

@sync_to_async
def _get_excel_data():
    """Асинхронно получает все данные из БД"""
    excel_data = {}
    for model in MODELS_ORDER:
        model_name = model._meta.model_name
        queryset = model.objects.all()
        if queryset.exists():
            data = []
            for obj in queryset:
                row = {}
                for field in obj._meta.fields:
                    field_name = field.name
                    field_value = getattr(obj, field_name)
                    if field.is_relation and field_value is not None:
                        row[field_name] = field_value.id
                    elif isinstance(field_value, (list, dict)):
                        row[field_name] = str(field_value)
                    elif hasattr(field_value, 'tzinfo') and field_value.tzinfo is not None:
                        try:
                            utc_value = field_value.astimezone(pytz.utc)
                            row[field_name] = utc_value.replace(tzinfo=None)
                        except Exception as e:
                            logger.warning(f"Ошибка преобразования datetime для поля {field_name}: {e}")
                            row[field_name] = field_value
                    else:
                        row[field_name] = field_value
                data.append(row)
            
            excel_data[model_name] = data
        else:
            columns = [field.name for field in model._meta.fields]
            excel_data[model_name] = []
    return excel_data

def _write_data_to_excel(writer, excel_data):
    """Вспомогательная функция для записи данных в Excel"""
    for model in MODELS_ORDER:
        model_name = model._meta.model_name  
        if model_name in excel_data and excel_data[model_name]:
            df = pd.DataFrame(excel_data[model_name])
            for column in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[column]):
                    df[column] = pd.to_datetime(df[column], utc=False)
            df.to_excel(writer, sheet_name=model_name, index=False)
        else:
            columns = [field.name for field in model._meta.fields]
            df = pd.DataFrame(columns=columns)
            df.to_excel(writer, sheet_name=model_name, index=False)

@router.message(F.document)
async def import_database_handler(message: Message):
    """Импорт базы данных из Excel файла"""
    
    user_id = message.from_user.id
    if not is_developer(user_id):
        logger.warning(f"Попытка доступа к импорту от пользователя {user_id}")
        return
    
    # Проверяем, что это Excel файл
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        return
    
    logger.info(f"Начало импорта БД пользователем {user_id}")
    
    try:
        await message.answer("🔄 Начинаю импорт базы данных...")
        
        # Скачиваем файл
        file = await message.bot.download(message.document)
        file_content = file.read()
        
        # Читаем Excel файл
        excel_data = pd.ExcelFile(BytesIO(file_content))
        
        # Выполняем импорт и получаем результаты
        import_results = await _perform_import(excel_data)
        
        # Отправляем результаты
        for result in import_results:
            await message.answer(result)
        
        await message.answer("✅ База данных успешно импортирована!")
        logger.info(f"Импорт БД завершен пользователем {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при импорте базы данных: {e}")
        await message.answer(f"❌ Ошибка при импорте: {str(e)}")

@sync_to_async
def _perform_import(excel_data):
    """Синхронная функция для выполнения импорта, возвращает список сообщений"""
    results = []
    skipped_users = []  # Для сбора информации о пропущенных пользователях
    
    try:
        with transaction.atomic():
            for model in MODELS_ORDER:
                model_name = model._meta.model_name
                
                if model_name not in excel_data.sheet_names:
                    continue  # Просто пропускаем, не выводим сообщение
                
                # Читаем данные из листа
                df = pd.read_excel(excel_data, sheet_name=model_name)
                
                if df.empty:
                    continue  # Просто пропускаем, не выводим сообщение
                
                # Заменяем NaN значения на None
                df = df.where(pd.notnull(df), None)
                
                # Импортируем данные
                imported_count = 0
                updated_count = 0
                skipped_count = 0
                
                for index, row in df.iterrows():
                    try:
                        # Для модели User проверяем исключения
                        if model == User:
                            username = row.get('username')
                            password = row.get('password')
                            
                            # Пропускаем пользователя admin
                            if username == 'admin':
                                skipped_count += 1
                                skipped_users.append(f"admin")
                                continue
                            
                            # Пропускаем пользователей без пароля
                            if password is None or password == '':
                                skipped_count += 1
                                if username:
                                    skipped_users.append(f"{username}")
                                else:
                                    skipped_users.append(f"user_with_id_{row.get('id', 'unknown')}")
                                continue
                        
                        data = {}
                        for field in model._meta.fields:
                            field_name = field.name
                            
                            if field_name not in row:
                                continue
                                
                            value = row[field_name]
                            
                            # Пропускаем поля, которые автоматически заполняются
                            if field_name in ['id', 'created_at', 'updated_at']:
                                continue
                            
                            # Обработка ForeignKey полей
                            if field.is_relation and value is not None:
                                try:
                                    related_model = field.related_model
                                    # Пытаемся найти связанный объект
                                    if hasattr(related_model.objects, 'get'):
                                        data[field_name] = related_model.objects.get(id=int(value))
                                    else:
                                        # Если не нашли, пропускаем это поле
                                        continue
                                except (ValueError, related_model.DoesNotExist):
                                    # Если связанный объект не найден, пропускаем поле
                                    continue
                            else:
                                # Обработка datetime полей
                                if field.get_internal_type() in ['DateTimeField', 'DateField'] and value is not None:
                                    try:
                                        if pd.isna(value):
                                            data[field_name] = None
                                        elif isinstance(value, (datetime, pd.Timestamp)):
                                            # Если это datetime объект, делаем его aware (с часовым поясом)
                                            if value.tzinfo is None:
                                                # Наивный datetime - делаем aware в UTC
                                                data[field_name] = timezone.make_aware(value, timezone=timezone.utc)
                                            else:
                                                # Уже с часовым поясом - оставляем как есть
                                                data[field_name] = value
                                        elif isinstance(value, str):
                                            # Если это строка, парсим её
                                            if 'T' in value:
                                                # ISO формат
                                                parsed_dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                            else:
                                                # Простой формат даты
                                                try:
                                                    parsed_dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                                                except ValueError:
                                                    try:
                                                        parsed_dt = datetime.strptime(value, '%Y-%m-%d')
                                                    except ValueError:
                                                        # Если не удалось распарсить, оставляем как есть
                                                        data[field_name] = value
                                                        continue
                                            
                                            if parsed_dt.tzinfo is None:
                                                data[field_name] = timezone.make_aware(parsed_dt, timezone=timezone.utc)
                                            else:
                                                data[field_name] = parsed_dt
                                        else:
                                            data[field_name] = value
                                    except Exception as e:
                                        logger.warning(f"Ошибка преобразования datetime для поля {field_name}: {e}")
                                        data[field_name] = value
                                # Обработка JSON полей
                                elif field.get_internal_type() == 'JSONField' and isinstance(value, str):
                                    try:
                                        # Пытаемся преобразовать строку в JSON
                                        import ast
                                        data[field_name] = ast.literal_eval(value)
                                    except:
                                        data[field_name] = value
                                else:
                                    data[field_name] = value
                        
                        # Для модели User проверяем только last_name (обязательное поле)
                        if model == User:
                            if 'last_name' not in data or data['last_name'] is None:
                                data['last_name'] = ""  # Пустая строка вместо null
                        
                        # Пытаемся найти существующую запись по ID, если он есть
                        if 'id' in row and pd.notnull(row['id']):
                            try:
                                obj = model.objects.get(id=int(row['id']))
                                # Обновляем существующую запись
                                for key, value in data.items():
                                    setattr(obj, key, value)
                                obj.save()
                                updated_count += 1
                            except model.DoesNotExist:
                                # Создаем новую запись с указанным ID
                                data['id'] = int(row['id'])
                                model.objects.create(**data)
                                imported_count += 1
                        else:
                            # Создаем новую запись
                            model.objects.create(**data)
                            imported_count += 1
                            
                    except Exception as e:
                        logger.error(f"Ошибка при импорте строки {index} в модель {model_name}: {e}")
                        error_msg = f"❌ Ошибка при импорте {model_name} (строка {index + 2}): {str(e)}"
                        results.append(error_msg)
                        raise Exception(error_msg)
                
                # Добавляем итог по модели только если были какие-то действия
                if imported_count > 0 or updated_count > 0 or skipped_count > 0:
                    result_msg = f"✅ {model._meta.verbose_name_plural}: "
                    parts = []
                    if imported_count > 0:
                        parts.append(f"импортировано {imported_count}")
                    if updated_count > 0:
                        parts.append(f"обновлено {updated_count}")
                    if skipped_count > 0:
                        parts.append(f"пропущено {skipped_count}")
                    result_msg += ", ".join(parts)
                    results.append(result_msg)
                
    except Exception as e:
        # Добавляем ошибку в результаты
        if str(e) not in results:
            results.append(f"❌ Ошибка транзакции: {str(e)}")
        raise
    
    # Добавляем информацию о пропущенных пользователях если они есть
    if skipped_users:
        unique_skipped = list(set(skipped_users))
        if len(unique_skipped) <= 5:
            results.append(f"⏭️ Пропущенные пользователи: {', '.join(unique_skipped)}")
        else:
            results.append(f"⏭️ Пропущено {len(unique_skipped)} пользователей (включая admin)")
    
    return results
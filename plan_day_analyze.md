Этап 1: Подготовка данных и моделей

Анализ и доработка CombinedDiaryEntry:
    ✅1. Убедиться, что модель CombinedDiaryEntry подходит для хранения промежуточного "состояния дня" ИИ.
    При необходимости, добавить/уточнить поля:
    ai_state_data (или переименовать analysis_result): TextField для хранения текстового "контекста" от ИИ.
    is_analyzed: BooleanField (уже есть), указывающий, был ли день проанализирован ИИ.
    ✅2. Убедиться, что date и user используются корректно с учетом часового пояса.
    ✅(Опционально) Создание сервиса DailyStateService:
    Вынести логику работы с CombinedDiaryEntry (получение, создание, обновление состояния дня) в отдельный сервис diary/services/daily_state_service.py для лучшей модульности. (Можно начать и в diary_service, а затем вынести).

Этап 2: Рефакторинг diary_service.py

    ✅1. Разделение update_entry_analysis:
    Переименовать/разделить update_entry_analysis (и _sync версию) на два отдельных метода:
    create_initial_analysis(entry, ...): для создания нового PsychoAnalysis при первой записи дня или после редактирования.
    update_existing_analysis(analysis_obj, ...): для обновления существующего объекта PsychoAnalysis (например, после уточнений).
    ✅2. Добавление методов для работы с CombinedDiaryEntry:
    В DiaryService (или DailyStateService) добавить методы:
    ✅2.1. get_daily_state(user, date): Асинхронно получает CombinedDiaryEntry для пользователя и даты.
    ✅2.2. create_daily_state(user, date, initial_text, initial_analysis_result): Создает новый CombinedDiaryEntry с начальным состоянием.
    ✅2.3. update_daily_state(combined_entry_obj, new_ai_state_data): Обновляет существующий CombinedDiaryEntry с новым состоянием от ИИ.

Этап 3: Расширение DeepSeekAPIService
Создание нового метода API:
    ✅В bot/services/deepseek_api.py добавить метод analyze_text_with_previous_state(previous_state_context: str, new_text: str, user_profile: dict, language: str).
    ✅Реализовать логику формирования промта, как обсуждали ранее.
    ✅Убедиться, что метод возвращает структурированный ответ, включая mood_score, comment, recommendation, analysis, needs_clarification, clarification_questions и suggested_task.
    ✅Создать удобную асинхронную функцию-обертку async def analyze_text_with_previous_state(...).

Этап 4: Реализация основной логики в diary.py handlers

Изменение логики обработки новой записи (process_text_entry, process_voice_entry):
    ✅1. Прием записи: Сохранить запись стандартно (diary_service.create_text_entry/create_voice_entry).
    ✅2.Получение состояния дня: Асинхронно получить CombinedDiaryEntry для текущей даты пользователя (daily_state_service.get_daily_state).
    Выбор метода анализа:
    ✅1. Если CombinedDiaryEntry НЕ существует (первая запись дня):
    ✅1.1 Вызвать стандартный анализ с профилем: deepseek_api_service.analyze_text_with_profile(new_text, user_profile, language).
    ✅2 Если CombinedDiaryEntry существует (N>1):
    ✅2.1 Извлечь ai_state_data из CombinedDiaryEntry.
    ✅2.2 Вызвать новый метод: deepseek_api_service.analyze_text_with_previous_state(ai_state_data, new_text, user_profile, language).
Обработка результата API:
    1. Извлечь mood_score, comment, recommendation, analysis, needs_clarification, clarification_questions, suggested_task.
    2.1. Если needs_clarification: true: Перевести FSM в состояние уточнения (DiaryStates.asking_clarifying_questions), сохранить entry_id и сами вопросы. Отправить вопросы пользователю. (Эта логика частично есть).
    2.2 Если НЕ требуется уточнение:
    Создать/Обновить PsychoAnalysis: Использовать diary_service.create_initial_analysis для создания анализа новой записи.
    Обновить CombinedDiaryEntry: Использовать daily_state_service.update_daily_state (или create_daily_state для N=1), сохранив новое ai_state_data из результата API.
(Асинхронно) Обработать задание: Если suggested_task присутствует и задание за день еще не назначалось, создать новый TherapyTask.
(Асинхронно) Обновить инсайты: Использовать существующую логику (AnalysisService) для извлечения KeyPoint и UserInsight из результата API и сохранения их в БД.
Ответ пользователю: Отправить пользователю comment, recommendation, analysis из результата API.

Этап 5: Обработка уточнений

Логика уточнений (process_clarification_answers):
После получения ответов пользователя, вызвать deepseek_api_service.analyze_text_with_clarifications(...) (этот метод уже есть).
Получить финальный результат.
Создать/Обновить PsychoAnalysis: Использовать diary_service.create_initial_analysis (или новый метод для финального анализа, если будет выделен).
Обновить CombinedDiaryEntry: Использовать daily_state_service.update_daily_state, сохранив финальное ai_state_data.
(Асинхронно) Обработать задание/Инсайты: Аналогично пункту 6.
Ответ пользователю: Отправить финальный comment, recommendation, analysis.
Этап 6: Обработка редактирования записи

Изменение логики редактирования (process_entry_edit):
Обновить текст записи.
Получить весь объединенный текст за день (diary_service.get_combined_entry_text).
Вызвать стандартный анализ с профилем для объединенного текста: deepseek_api_service.analyze_text_with_profile(combined_text, user_profile, language).
Создать/Обновить PsychoAnalysis: Использовать diary_service.create_initial_analysis для обновленной записи (или отдельный метод, если анализ "главной" записи требует особого подхода).
Создать/Обновить CombinedDiaryEntry: Использовать daily_state_service.update_daily_state (или create_daily_state), сохранив новое ai_state_data из результата анализа объединенного текста.
(Асинхронно) Обработать задание/Инсайты: Аналогично.
Ответ пользователю: Отправить результат анализа объединенного текста.
Этап 7: Показ "анализа дня"

Обновление view_entry_history или создание нового обработчика:
При просмотре записей за день, добавить возможность показать ai_state_data из CombinedDiaryEntry (например, по кнопке "Анализ дня").
Этап 8: Тестирование и отладка

Тестирование: Тщательно протестировать все сценарии: первая запись, последующие записи, уточнения, редактирование, обработка заданий/инсайтов, обработка ошибок API.
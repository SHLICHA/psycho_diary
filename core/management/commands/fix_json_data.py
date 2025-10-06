# /home/shlicha/psycho_diary/core/management/commands/fix_json_data.py

import logging
from django.core.management.base import BaseCommand
from users.models import UserProfileHistory
import json

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Исправляет некорректные JSON данные в UserProfileHistory перед миграцией'

    def handle(self, *args, **options):
        self.stdout.write('Поиск и исправление некорректных JSON данных...')
        
        fixed_count = 0
        json_fields = [
            'personality_traits', 'life_facts', 'hobbies', 'core_values',
            'triggers', 'strengths', 'areas_for_growth', 'personality_insights',
            'habits', 'skills', 'aspirations', 'personality_description'
        ]
        
        for profile in UserProfileHistory.objects.all():
            needs_save = False
            
            for field_name in json_fields:
                field_value = getattr(profile, field_name)
                
                # Если поле пустое или уже корректный JSON, пропускаем
                if field_value in [None, '', 'null', 'NULL']:
                    continue
                    
                # Если это строка, пытаемся распарсить и исправить
                if isinstance(field_value, str):
                    try:
                        # Пробуем распарсить как JSON
                        parsed = json.loads(field_value)
                        setattr(profile, field_name, parsed)
                        needs_save = True
                        self.stdout.write(f'  Исправлено поле {field_name} для профиля {profile.id}')
                    except json.JSONDecodeError:
                        # Если не удалось распарсить, устанавливаем значение по умолчанию
                        if 'traits' in field_name or 'insights' in field_name:
                            setattr(profile, field_name, {})
                        else:
                            setattr(profile, field_name, [])
                        needs_save = True
                        self.stdout.write(f'  Установлено значение по умолчанию для поля {field_name} профиля {profile.id}')
            
            if needs_save:
                profile.save()
                fixed_count += 1
        
        if fixed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Успешно исправлено {fixed_count} записей UserProfileHistory')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('Некорректных JSON данных не найдено')
            )
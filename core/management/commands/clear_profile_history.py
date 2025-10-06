from django.core.management.base import BaseCommand
from users.models import UserProfileHistory

class Command(BaseCommand):
    help = 'Очищает историю профилей пользователей для успешной миграции'

    def handle(self, *args, **options):
        count = UserProfileHistory.objects.count()
        UserProfileHistory.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(f'Удалено {count} записей истории профилей')
        )
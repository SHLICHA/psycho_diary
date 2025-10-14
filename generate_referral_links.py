# /home/shlicha/psycho_diary/generate_referral_links.py

import os
import django
import sys
import secrets

# Убедитесь, что путь к вашему проекту Django в sys.path
# sys.path.append('/path/to/your/project') # Если нужно

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings') # Замените 'your_project.settings' на реальное имя модуля настроек
django.setup()

from users.models import User

def generate_missing_referral_links():
    # Найти пользователей, у которых referral_link пустой или None
    users_without_link = User.objects.filter(referral_link__isnull=True).union(
        User.objects.filter(referral_link='')
    )

    print(f"Найдено {users_without_link.count()} пользователей без реферальной ссылки.")

    for user in users_without_link:
        # Генерируем уникальную ссылку
        new_referral_link = f"ref_{user.telegram_id}_{secrets.token_urlsafe(8)}"
        user.referral_link = new_referral_link
        print(f"Генерируется ссылка для пользователя {user.telegram_id}: {new_referral_link}")

    # Сохраняем все изменения за один раз (эффективнее для большого количества пользователей)
    User.objects.bulk_update(users_without_link, ['referral_link'])

    print(f"Обновлено {len(users_without_link)} пользователей с новыми реферальными ссылками.")

if __name__ == "__main__":
    generate_missing_referral_links()

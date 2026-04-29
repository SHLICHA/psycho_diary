from django.db import migrations
from core.encrypted_fields import EncryptedJSONField


def merge_habits_and_skills(apps, schema_editor):
    """
    Data migration: объединяет habits + skills → practical_patterns для каждого User.
    habits идут первыми. Старые поля не трогаем.
    """
    User = apps.get_model('users', 'User')
    for user in User.objects.all():
        habits = user.habits or []
        skills = user.skills or []
        if not isinstance(habits, list):
            habits = []
        if not isinstance(skills, list):
            skills = []
        if habits or skills:
            user.practical_patterns = habits + skills
            user.save(update_fields=['practical_patterns'])

    UserProfileHistory = apps.get_model('users', 'UserProfileHistory')
    for snapshot in UserProfileHistory.objects.all():
        habits = snapshot.habits or []
        skills = snapshot.skills or []
        if not isinstance(habits, list):
            habits = []
        if not isinstance(skills, list):
            skills = []
        if habits or skills:
            snapshot.practical_patterns = habits + skills
            snapshot.save(update_fields=['practical_patterns'])


def reverse_merge(apps, schema_editor):
    """Обратная миграция: очищает practical_patterns."""
    User = apps.get_model('users', 'User')
    User.objects.all().update(practical_patterns=[])
    UserProfileHistory = apps.get_model('users', 'UserProfileHistory')
    UserProfileHistory.objects.all().update(practical_patterns=[])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0040_user_email_hash'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE users_user
                        ADD COLUMN IF NOT EXISTS practical_patterns TEXT DEFAULT '[]';
                        ALTER TABLE users_profile_history
                        ADD COLUMN IF NOT EXISTS practical_patterns TEXT DEFAULT '[]';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='practical_patterns',
                    field=EncryptedJSONField(blank=True, default=list, verbose_name='Привычки и навыки'),
                ),
                migrations.AddField(
                    model_name='userprofilehistory',
                    name='practical_patterns',
                    field=EncryptedJSONField(blank=True, default=list, verbose_name='Привычки и навыки'),
                ),
            ],
        ),
        migrations.RunPython(merge_habits_and_skills, reverse_code=reverse_merge),
    ]

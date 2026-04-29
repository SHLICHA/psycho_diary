from django.db import migrations

import core.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0041_add_practical_patterns'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='full_psych_profile',
            field=core.encrypted_fields.EncryptedJSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Полный психологический профиль для пользователя. '
                    'Генерируется weekly analysis. Содержит: summary, traits, values, '
                    'triggers, strengths, growth_areas, insights, practical_patterns, aspirations.'
                ),
                verbose_name='Полный психологический профиль',
            ),
        ),
    ]
# Generated manually for EmailMergeRequest status expansion

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0046_emailmergerequest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailmergerequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Ожидает подтверждения'),
                    ('confirmed', 'Подтверждено'),
                    ('merged', 'Объединено'),
                    ('merge_failed', 'Ошибка объединения'),
                    ('expired', 'Истекло'),
                    ('cancelled', 'Отменено'),
                ],
                default='pending',
                max_length=16,
                verbose_name='Статус',
            ),
        ),
    ]

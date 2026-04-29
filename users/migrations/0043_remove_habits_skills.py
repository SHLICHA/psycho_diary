from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0042_reconcile_practical_patterns'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='habits',
        ),
        migrations.RemoveField(
            model_name='user',
            name='skills',
        ),
        migrations.RemoveField(
            model_name='userprofilehistory',
            name='habits',
        ),
        migrations.RemoveField(
            model_name='userprofilehistory',
            name='skills',
        ),
    ]
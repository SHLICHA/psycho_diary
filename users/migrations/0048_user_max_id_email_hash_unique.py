# Deduplicate max_id / email_hash and enforce unique constraints.

from django.db import migrations, models


def _pick_survivor(users):
    """Prefer active users, then most recent activity/creation."""

    def sort_key(user):
        active = 1 if getattr(user, 'deletion_status', 'active') == 'active' else 0
        last_activity = user.last_activity or user.created_at
        return (active, last_activity, user.id)

    return sorted(users, key=sort_key, reverse=True)[0]


def dedupe_identity_fields(apps, schema_editor):
    User = apps.get_model('users', 'User')

    # --- max_id duplicates ---
    seen_max = set()
    for max_id in (
        User.objects.exclude(max_id__isnull=True).values_list('max_id', flat=True)
    ):
        if max_id in seen_max:
            continue
        seen_max.add(max_id)
        twins = list(User.objects.filter(max_id=max_id).order_by('id'))
        if len(twins) <= 1:
            continue
        survivor = _pick_survivor(twins)
        User.objects.filter(max_id=max_id).exclude(pk=survivor.pk).update(max_id=None)

    # --- email_hash duplicates (non-empty) ---
    seen_hash = set()
    for email_hash in (
        User.objects.exclude(email_hash__isnull=True)
        .exclude(email_hash='')
        .values_list('email_hash', flat=True)
    ):
        if email_hash in seen_hash:
            continue
        seen_hash.add(email_hash)
        twins = list(User.objects.filter(email_hash=email_hash).order_by('id'))
        if len(twins) <= 1:
            continue
        survivor = _pick_survivor(twins)
        User.objects.filter(email_hash=email_hash).exclude(pk=survivor.pk).update(
            email='',
            email_hash=None,
        )

    # Empty string → NULL so unique allows many users without email.
    User.objects.filter(email_hash='').update(email_hash=None)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0047_emailmergerequest_merged_statuses'),
    ]

    operations = [
        # Allow NULL before converting empty hashes (required for unique later).
        migrations.AlterField(
            model_name='user',
            name='email_hash',
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                null=True,
                verbose_name='Email hash (для поиска)',
            ),
        ),
        migrations.RunPython(dedupe_identity_fields, noop_reverse),
        migrations.AlterField(
            model_name='user',
            name='max_id',
            field=models.BigIntegerField(
                blank=True,
                help_text='Идентификатор пользователя в VK MAX (unique, nullable)',
                null=True,
                unique=True,
                verbose_name='MAX ID',
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='email_hash',
            field=models.CharField(
                blank=True,
                editable=False,
                help_text='SHA-256 от email в lower-case; NULL если email не задан',
                max_length=64,
                null=True,
                unique=True,
                verbose_name='Email hash (для поиска)',
            ),
        ),
    ]

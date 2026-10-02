from django.db import migrations

from users.encryption import decrypt_secret, encrypt_secret, is_encrypted


def convert_rows(apps, convert):
    """Apply `convert` to every secret allauth stores in an authenticator's data."""
    Authenticator = apps.get_model('mfa', 'Authenticator')
    for authenticator in Authenticator.objects.all():
        data = authenticator.data
        # 'secret': authenticator app; 'seed' and 'migrated_codes': recovery codes
        for name in ('secret', 'seed'):
            if name in data:
                data[name] = convert(data[name])
        if data.get('migrated_codes') is not None:
            data['migrated_codes'] = [convert(code) for code in data['migrated_codes']]
        authenticator.save(update_fields=['data'])


def encrypt_rows(apps, schema_editor):
    # Rows from before users.adapters.MFAAdapter are in cleartext
    convert_rows(apps, lambda value: value if is_encrypted(value) else encrypt_secret(value))


def decrypt_rows(apps, schema_editor):
    convert_rows(apps, lambda value: decrypt_secret(value) if is_encrypted(value) else value)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_invitation_sent_at'),
        ('mfa', '0003_authenticator_type_uniq'),
    ]

    operations = [
        migrations.RunPython(encrypt_rows, decrypt_rows),
    ]

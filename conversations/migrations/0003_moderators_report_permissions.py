from django.contrib.auth.management import create_permissions
from django.db import migrations

# What the Reports page asks for: seeing the reports, and marking one handled
REPORT_PERMISSIONS = ('view_report', 'change_report')


def report_permissions(apps):
    # Django creates permissions after migrate has finished, so on a fresh
    # database they don't exist yet. Create them now.
    app_config = apps.get_app_config('conversations')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Permission = apps.get_model('auth', 'Permission')
    return Permission.objects.filter(
        content_type__app_label='conversations', codename__in=REPORT_PERMISSIONS
    )


def add_to_moderators(apps, schema_editor):
    """Moderators handle the reported messages, next to what they could do before."""
    Group = apps.get_model('auth', 'Group')
    group, _ = Group.objects.get_or_create(name='Moderators')
    group.permissions.add(*report_permissions(apps))


def remove_from_moderators(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    group = Group.objects.filter(name='Moderators').first()
    if group:
        group.permissions.remove(*report_permissions(apps))


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0002_report'),
        ('forums', '0016_moderators_group'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(add_to_moderators, remove_from_moderators),
    ]

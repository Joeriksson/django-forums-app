from django.contrib.auth.management import create_permissions
from django.db import migrations

# The only permissions the views and templates check for moderation.
MODERATOR_PERMISSIONS = ('change_thread', 'delete_thread', 'delete_post')


def create_moderators_group(apps, schema_editor):
    """
    Create the Moderators group with just the moderation permissions.
    If the group already exists, its permissions are replaced.
    """
    # Django creates permissions after migrate has finished, so on a fresh
    # database they don't exist yet. Create them now.
    app_config = apps.get_app_config('forums')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    group, _ = Group.objects.get_or_create(name='Moderators')
    group.permissions.set(
        Permission.objects.filter(
            content_type__app_label='forums',
            codename__in=MODERATOR_PERMISSIONS,
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('forums', '0015_unique_upvote_and_notification'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        # Reversing leaves the group in place, since people may belong to it.
        migrations.RunPython(create_moderators_group, migrations.RunPython.noop),
    ]

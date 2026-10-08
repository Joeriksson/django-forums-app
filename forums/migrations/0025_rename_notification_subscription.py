from django.db import migrations, models


def rename_permissions(apps, schema_editor):
    """
    Django renames the content type with the model but leaves its permissions, and
    would add a second set: rename them, so whoever holds one keeps it.
    """
    Permission = apps.get_model('auth', 'Permission')
    for permission in Permission.objects.filter(
        content_type__app_label='forums',
        content_type__model__in=('notification', 'subscription'),
        codename__endswith='_notification',
    ):
        permission.codename = permission.codename.replace('_notification', '_subscription')
        permission.name = permission.name.replace('notification', 'subscription')
        permission.save()


def restore_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    for permission in Permission.objects.filter(
        content_type__app_label='forums',
        content_type__model__in=('notification', 'subscription'),
        codename__endswith='_subscription',
    ):
        permission.codename = permission.codename.replace('_subscription', '_notification')
        permission.name = permission.name.replace('subscription', 'notification')
        permission.save()


class Migration(migrations.Migration):
    """
    A row here is a member following a thread, so the model is Subscription; the name
    Notification is for what the notification center shows.
    """

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('forums', '0024_field_names'),
    ]

    operations = [
        migrations.RenameModel(old_name='Notification', new_name='Subscription'),
        migrations.RunPython(rename_permissions, restore_permissions),
        migrations.RemoveConstraint(
            model_name='subscription', name='unique_notification_per_user'
        ),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.UniqueConstraint(
                fields=('thread', 'user'), name='unique_subscription_per_user'
            ),
        ),
    ]

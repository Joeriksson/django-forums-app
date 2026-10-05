from datetime import timedelta

from django.db import migrations, models
from django.db.models import F


def clear_unedited(apps, schema_editor):
    # "edited" was set at every save, the first one included: a time within a second of
    # "added" is the creation, not an edit
    for name in ('Thread', 'Post'):
        apps.get_model('forums', name).objects.filter(
            edited__lt=F('added') + timedelta(seconds=1)
        ).update(edited=None)


def fill_unedited(apps, schema_editor):
    for name in ('Thread', 'Post'):
        apps.get_model('forums', name).objects.filter(edited=None).update(edited=F('added'))


class Migration(migrations.Migration):

    dependencies = [
        ('forums', '0021_forum_posting'),
    ]

    operations = [
        migrations.AlterField(
            model_name='thread',
            name='edited',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name='post',
            name='edited',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(clear_unedited, fill_unedited),
    ]

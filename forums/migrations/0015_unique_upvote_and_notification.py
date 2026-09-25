from django.db import migrations, models
from django.db.models import Min


def remove_duplicates(apps, schema_editor):
    """
    Keep the oldest row for each (post, user) upvote and (thread, user)
    subscription, so the unique constraints below can be added.
    """
    for model_name, fields in (
        ('UpVote', ('post', 'user')),
        ('Notification', ('thread', 'user')),
    ):
        model = apps.get_model('forums', model_name)
        keep_ids = (
            model.objects.order_by()
            .values(*fields)
            .annotate(keep_id=Min('id'))
            .values('keep_id')
        )
        model.objects.exclude(id__in=keep_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('forums', '0014_auto_20200324_1234'),
    ]

    operations = [
        # Deleted duplicates can't be restored, so the reverse is a no-op
        migrations.RunPython(remove_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='upvote',
            constraint=models.UniqueConstraint(
                fields=('post', 'user'), name='unique_upvote_per_user'
            ),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(
                fields=('thread', 'user'), name='unique_notification_per_user'
            ),
        ),
    ]

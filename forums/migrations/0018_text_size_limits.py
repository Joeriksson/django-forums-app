from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Maximum lengths for thread text, post text and the signature. Only the forms and the
    API check them: the columns don't change, and longer texts already saved stay as they are.
    """

    dependencies = [
        ('forums', '0017_plain_text_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='post',
            name='text',
            field=models.TextField(help_text='You can use Markdown: **bold**, *italic*, `code`, > quote, lists, links and tables.', max_length=20000),
        ),
        migrations.AlterField(
            model_name='thread',
            name='text',
            field=models.TextField(help_text='You can use Markdown: **bold**, *italic*, `code`, > quote, lists, links and tables.', max_length=20000),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='signature',
            field=models.TextField(blank=True, max_length=500),
        ),
    ]

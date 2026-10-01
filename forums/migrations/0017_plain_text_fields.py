from django.db import migrations, models

MARKDOWN_HELP = 'You can use Markdown: **bold**, *italic*, `code`, > quote, lists, links and tables.'


class Migration(migrations.Migration):
    # No database change: the columns were text already (MartorField is a TextField subclass)

    dependencies = [
        ('forums', '0016_moderators_group'),
    ]

    operations = [
        migrations.AlterField(
            model_name='post',
            name='text',
            field=models.TextField(help_text=MARKDOWN_HELP),
        ),
        migrations.AlterField(
            model_name='thread',
            name='text',
            field=models.TextField(help_text=MARKDOWN_HELP),
        ),
    ]

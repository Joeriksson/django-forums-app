from celery import shared_task
from django.conf import settings
from django.utils.translation import gettext

from project.utils import send_mail, site_language


@shared_task
def my_scheduled_task():
    print('A scheduled task just ran')


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_notifications_task(
    thread_id, thread_title, user_name, full_url, email_addresses
):
    # TODO: Look into how to send multiple mails via header instead of BCC

    # Compose message to subscribers
    with site_language():
        subject = gettext('New post added by %(name)s') % {'name': user_name}
        added = gettext('A new post was added to thread "%(title)s"') % {'title': thread_title}
        url = gettext('Url: %(url)s') % {'url': full_url}
    from_email = settings.DEFAULT_FROM_EMAIL

    bcc = email_addresses

    text_content = f'{added} \n\n{url} \n\n'

    send_mail(subject, from_email, bcc, text_content)

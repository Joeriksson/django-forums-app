from celery import shared_task

from project.utils import send_mail

@shared_task
def my_scheduled_task():
    print('A scheduled task just ran')


@shared_task
def send_notifications_task(thread_id, thread_title, user_name, full_url, email_addresses):
    # TODO: Look into how to send multiple mails via header instead of BCC

    # Compose message to subscribers
    subject, from_email = f'New post added by {user_name}', 'info@wildvasa.com'

    bcc = email_addresses

    text_content = f'A new post was added to thread "{thread_title}" \n\nUrl: {full_url} \n\n'

    send_mail(subject, from_email, bcc, text_content)








from django.core.mail import EmailMultiAlternatives


def send_mail(subject, from_email, bcc, text_content):

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, bcc=bcc
    )

    msg.send()

    print('email sent ####################')

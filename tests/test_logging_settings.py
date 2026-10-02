import logging

from django.core import mail
from django.utils.log import AdminEmailHandler

from project.utils import send_mail


def console_handlers(logger):
    # pytest adds handlers of its own to the root logger: they are subclasses
    return [handler for handler in logger.handlers if type(handler) is logging.StreamHandler]


def test_info_messages_go_to_stdout_with_a_timestamp(settings):
    root = logging.getLogger()

    handlers = console_handlers(root)

    assert len(handlers) == 1
    assert '{asctime}' in handlers[0].formatter._fmt
    # Not the handler's stream: pytest replaces sys.stdout
    assert settings.LOGGING['handlers']['console']['stream'] == 'ext://sys.stdout'
    assert logging.getLogger('security').isEnabledFor(logging.INFO)
    assert logging.getLogger('django.request').isEnabledFor(logging.INFO)


def test_django_messages_are_printed_once():
    django_logger = logging.getLogger('django')

    # They reach the root handler; a console handler here would print them twice
    assert django_logger.propagate
    assert not [h for h in django_logger.handlers if isinstance(h, logging.StreamHandler)]


def test_errors_are_still_mailed_to_admins():
    handlers = [h for h in logging.getLogger('django').handlers if isinstance(h, AdminEmailHandler)]

    assert len(handlers) == 1
    assert handlers[0].level == logging.ERROR


def test_send_mail_logs_the_number_of_recipients_only(caplog, capsys):
    with caplog.at_level(logging.INFO, logger='project.utils'):
        send_mail('Subject', 'forum@example.com', ['a@example.com', 'b@example.com'], 'Text')

    assert len(mail.outbox) == 1
    assert [record.getMessage() for record in caplog.records] == ['Mail sent to 2 recipients']
    assert 'email sent' not in capsys.readouterr().out

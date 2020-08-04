import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings.development')

app = Celery('project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


# @app.task(bind=True, retry_limit=4, default_retry_delay=10)
# def debug_task(self):
#     print('Request: {0!r}'.format(self.request))

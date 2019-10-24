from django.apps import AppConfig


class ForumsConfig(AppConfig):
    name = 'forums'

    def ready(self):
        from . import signals

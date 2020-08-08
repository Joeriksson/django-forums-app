# from celery import app as celery_app
import os

if not os.environ.get('CI'):
    from .celery import app as celery_app
    __all__ = ['celery_app']
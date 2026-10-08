from django.urls import path

from .views import MarkAllRead, NotificationList

urlpatterns = [
    path('', NotificationList.as_view(), name='notifications'),
    path('read/', MarkAllRead.as_view(), name='notifications_read'),
]

from django.urls import path

from .views import MarkAllRead, NotificationList, UnreadCount

urlpatterns = [
    path('', NotificationList.as_view(), name='notifications'),
    path('read/', MarkAllRead.as_view(), name='notifications_read'),
    path('count/', UnreadCount.as_view(), name='notifications_count'),
]

from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    search_fields = ('user__username',)
    list_display = ('user', 'kind', 'thread', 'count', 'read', 'updated')
    list_filter = ('kind', 'read')
    raw_id_fields = ('user', 'thread', 'post')

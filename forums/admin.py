from django.contrib import admin

from .models import Forum, Thread, Post, UserProfile, UpVote, Notification


class PostAdmin(admin.ModelAdmin):
    search_fields = ('user__username',)
    list_display = ('thread', 'added', 'edited', 'user', 'upvotes')
    list_filter = (
        ('added', admin.DateFieldListFilter),
        ('edited', admin.DateFieldListFilter),
        ('upvotes', admin.BooleanFieldListFilter),
    )


class NotificationAdmin(admin.ModelAdmin):
    search_fields = ('user__username',)
    list_filter = (
        ('added', admin.DateFieldListFilter),
    )
    list_display = ('thread', 'user')


class ThreadAdmin(admin.ModelAdmin):
    search_fields = ('user__username',)
    list_display = ('title', 'forum', 'added', 'edited', 'user')
    list_filter = (
        ('forum', admin.RelatedFieldListFilter),
        ('added', admin.DateFieldListFilter),
        ('edited', admin.DateFieldListFilter),
    )


class UserProfileAdmin(admin.ModelAdmin):
    search_fields = ('first_name', 'last_name', 'user__username')
    list_display = ('user', 'first_name', 'last_name', 'gender', 'location')
    list_filter = (
        'location',
        'gender',
    )


admin.site.register(Forum)
admin.site.register(Thread, ThreadAdmin)
admin.site.register(Post, PostAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(UpVote)
admin.site.register(Notification, NotificationAdmin)

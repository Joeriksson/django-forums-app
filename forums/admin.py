from django.contrib import admin

from .models import Forum, Thread, Post, UserProfile, UpVote, Notification


class PostAdmin(admin.ModelAdmin):
    list_display = ('thread', 'added', 'edited', 'user', 'upvotes')
    list_filter = (
        ('added', admin.DateFieldListFilter),
        ('edited', admin.DateFieldListFilter),
    )


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('thread', 'user')


class ThreadAdmin(admin.ModelAdmin):
    list_display = ('title', 'forum', 'added', 'edited', 'user')
    list_filter = (
        ('forum', admin.RelatedFieldListFilter),
        ('added', admin.DateFieldListFilter),
        ('edited', admin.DateFieldListFilter),
    )

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user','first_name', 'last_name', 'gender', 'location')
    list_filter = (
        ('location', )
    )

admin.site.register(Forum)
admin.site.register(Thread, ThreadAdmin)
admin.site.register(Post, PostAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(UpVote)
admin.site.register(Notification, NotificationAdmin)

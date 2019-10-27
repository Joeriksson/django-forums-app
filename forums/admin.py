from django.contrib import admin

from .models import Forum, Thread, Post, UpVote, Notification

admin.site.register(Forum)
admin.site.register(Thread)
admin.site.register(Post)
admin.site.register(UpVote)
admin.site.register(Notification)

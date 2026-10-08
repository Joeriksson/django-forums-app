from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import redirect
from django.views.generic import TemplateView, View

from forums.models import Post
from forums.views import thread_page_url
from pages.models import SiteSettings

from .models import Notification

# The page has no paging: older rows than these are left out
MAX_ROWS = 50


def load(user, posts_per_page):
    """
    The member's notifications, unread first, each with `url`: the first reply not yet
    seen, on its page of the thread, or the thread's last page if that reply is gone.
    One query.
    """
    # The replies up to and including that one, in the thread page's order
    position = (
        Post.objects.filter(thread=OuterRef('thread'))
        .filter(
            Q(added__lt=OuterRef('post__added'))
            | Q(added=OuterRef('post__added'), id__lte=OuterRef('post'))
        )
        .order_by()
        .values('thread')
        .annotate(count=Count('id'))
        .values('count')
    )
    notifications = list(
        Notification.objects.filter(user=user, thread__isnull=False)
        .select_related('thread__forum')
        .annotate(position=Subquery(position))[:MAX_ROWS]
    )
    for notification in notifications:
        if notification.position:
            page = (notification.position - 1) // posts_per_page + 1
            url = thread_page_url(notification.thread_id, page)
            notification.url = f'{url}#post-{notification.post_id}'
        else:
            notification.url = thread_page_url(notification.thread_id, 'last')
    return notifications


class NotificationList(LoginRequiredMixin, TemplateView):
    """What is new for the member; following a row opens the thread, which marks it read."""

    template_name = 'notifications/notification_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        notifications = load(
            self.request.user, SiteSettings.for_request(self.request).posts_per_page
        )
        context['notifications'] = notifications
        context['unread'] = any(not notification.read for notification in notifications)
        return context


class MarkAllRead(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return redirect('notifications')

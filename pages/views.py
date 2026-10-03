from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from forums.activity import add_last_repliers, with_activity
from forums.models import Thread
from forums.views import ForumsList


class HomePageView(TemplateView):
    """Members get the forum list; visitors only a way in."""

    template_name = 'home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return ForumsList.as_view()(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)


class LatestView(LoginRequiredMixin, TemplateView):
    """The conversations with the newest activity, across all forums."""

    template_name = 'forums/latest.html'
    thread_count = 15

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # A thread without replies counts from when it was started (last_activity)
        threads = with_activity(Thread.objects.select_related('forum', 'user__profile'))
        context['threads'] = add_last_repliers(
            threads.order_by('-last_activity', '-id')[: self.thread_count]
        )
        return context

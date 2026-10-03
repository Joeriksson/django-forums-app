from django.views.generic import TemplateView

from forums.activity import add_last_repliers, with_activity
from forums.models import Thread


class HomePageView(TemplateView):
    """Members see the latest conversations; visitors only a way in."""

    template_name = 'home.html'
    thread_count = 15

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            # A thread without replies counts from when it was started (last_activity)
            threads = with_activity(Thread.objects.select_related('forum', 'user__profile'))
            context['threads'] = add_last_repliers(
                threads.order_by('-last_activity', '-id')[: self.thread_count]
            )
        return context

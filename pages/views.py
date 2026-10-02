from django.db.models import Count, Max
from django.db.models.functions import Coalesce
from django.views.generic import TemplateView

from forums.models import Thread


class HomePageView(TemplateView):
    """Members see the latest conversations; visitors only a way in."""

    template_name = 'home.html'
    thread_count = 15

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['threads'] = (
                Thread.objects.select_related('forum', 'user__profile')
                .annotate(post_count=Count('posts'), last_post=Max('posts__added'))
                # A thread without replies counts from when it was started
                .annotate(last_activity=Coalesce('last_post', 'added'))
                .order_by('-last_activity', '-id')[: self.thread_count]
            )
        return context

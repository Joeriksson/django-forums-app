from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.views.generic import FormView

from forums.throttling import MESSAGE_THROTTLES, allowed
from notifications.events import conversation_opened
from pages.models import SiteSettings

from .forms import MessageForm
from .models import Conversation, Message, send


class ConversationDetail(LoginRequiredMixin, FormView):
    """
    The member's messages with one other member, oldest first, and the form for the
    next one. The address names the other member, so it can only show the reader's own
    conversation, and one that hasn't started yet is an empty page: nothing is saved
    before the first message.
    """

    template_name = 'conversations/conversation_detail.html'
    form_class = MessageForm

    @cached_property
    def other(self):
        other = get_object_or_404(
            get_user_model().objects.select_related('profile'),
            pk=self.kwargs['pk'],
            is_active=True,
        )
        if other == self.request.user:
            raise Http404
        return other

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if self.conversation:
            conversation_opened(request.user, self.conversation)
        return response

    @cached_property
    def conversation(self):
        return Conversation.find(self.request.user, self.other)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['other'] = self.other
        # One page of messages with each sender and profile in the same query
        messages = Message.objects.filter(conversation=self.conversation).select_related(
            'sender__profile'
        )
        paginator = Paginator(messages, SiteSettings.for_request(self.request).posts_per_page)
        # The newest messages unless a page is asked for; get_page() shows the first or
        # last page for a page number that doesn't exist
        page = self.request.GET.get('page', 'last')
        context['messages_page'] = paginator.get_page(
            paginator.num_pages if page == 'last' else page
        )
        return context

    def form_valid(self, form):
        # Checked here, so a form with errors doesn't count
        if not allowed(self.request, *MESSAGE_THROTTLES):
            form.add_error(
                None, gettext('You are sending messages too fast. Wait a while and try again.')
            )
            # The form comes back with the text, to send again later
            return self.render_to_response(self.get_context_data(form=form), status=429)
        message = send(self.request.user, self.other, form.cleaned_data['text'])
        url = reverse('conversation', kwargs={'pk': self.other.pk})
        return redirect(f'{url}#message-{message.pk}')

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.views.generic import FormView, TemplateView, View

from forums.throttling import MESSAGE_THROTTLES, allowed
from notifications.events import conversation_opened
from notifications.models import Notification
from pages.models import SiteSettings
from users.audit import log_event

from .forms import MessageForm, ReportForm
from .models import Block, Blocked, Conversation, Message, Report, send


def other_member(request, pk):
    """The member a conversation's address names: someone else, with an active account."""
    other = get_object_or_404(
        get_user_model().objects.select_related('profile'), pk=pk, is_active=True
    )
    if other == request.user:
        raise Http404
    return other


class ConversationList(LoginRequiredMixin, TemplateView):
    """The member's conversations, the one with the newest message first."""

    template_name = 'conversations/conversation_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        conversations = Conversation.objects.filter(
            Q(user_low=user) | Q(user_high=user)
        ).select_related('user_low__profile', 'user_high__profile')
        paginator = Paginator(
            conversations, SiteSettings.for_request(self.request).threads_per_page
        )
        page = paginator.get_page(self.request.GET.get('page'))
        # The messages the member hasn't seen, from the notification center's rows
        unread = dict(
            Notification.objects.filter(
                user=user, read=False, conversation__in=[c.pk for c in page]
            ).values_list('conversation_id', 'count')
        )
        for conversation in page:
            low = conversation.user_low
            conversation.other = conversation.user_high if low == user else low
            conversation.unread = unread.get(conversation.pk, 0)
        context['conversations'] = page
        return context


class MemberList(LoginRequiredMixin, TemplateView):
    """Who to write to: every member with an active account, by name."""

    template_name = 'conversations/member_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        members = (
            get_user_model()
            .objects.filter(is_active=True)
            .exclude(pk=self.request.user.pk)
            .select_related('profile')
        )
        # The name is the profile's or "Member <id>": sorted here, not by the database
        context['members'] = sorted(
            members, key=lambda member: (member.display_name.casefold(), member.pk)
        )
        return context


class ConversationDetail(LoginRequiredMixin, FormView):
    """
    The member's messages with one other member, oldest first, and the form for the
    next one, unless one of them has blocked the other. The address names the other member, so it can only show the reader's own
    conversation, and one that hasn't started yet is an empty page: nothing is saved
    before the first message.
    """

    template_name = 'conversations/conversation_detail.html'
    form_class = MessageForm

    @cached_property
    def other(self):
        return other_member(self.request, self.kwargs['pk'])

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if self.conversation:
            conversation_opened(request.user, self.conversation)
        return response

    @cached_property
    def conversation(self):
        return Conversation.find(self.request.user, self.other)

    @cached_property
    def blockers(self):
        return Block.between(self.request.user, self.other)

    def post(self, request, *args, **kwargs):
        # Before the form, so a refused message doesn't count against the sending limit
        if self.blockers:
            raise PermissionDenied
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['other'] = self.other
        # Either one's block stops the messages; only one's own is told and can be undone
        context['blocked'] = bool(self.blockers)
        context['blocked_by_me'] = self.request.user.pk in self.blockers
        # One page of messages with each sender and profile in the same query
        # and whether it was reported
        texts = Message.objects.filter(conversation=self.conversation).select_related(
            'sender__profile', 'report'
        )
        paginator = Paginator(texts, SiteSettings.for_request(self.request).posts_per_page)
        # The newest messages unless a page is asked for; get_page() shows the first or
        # last page for a page number that doesn't exist
        page = self.request.GET.get('page', 'last')
        context['messages_page'] = paginator.get_page(
            paginator.num_pages if page == 'last' else page
        )
        for message in context['messages_page']:
            # Loaded with the message: no query
            message.reported = hasattr(message, 'report')
        return context

    def form_valid(self, form):
        # Checked here, so a form with errors doesn't count
        if not allowed(self.request, *MESSAGE_THROTTLES):
            form.add_error(
                None, gettext('You are sending messages too fast. Wait a while and try again.')
            )
            # The form comes back with the text, to send again later
            return self.render_to_response(self.get_context_data(form=form), status=429)
        try:
            message = send(self.request.user, self.other, form.cleaned_data['text'])
        except Blocked:
            # Blocked since this request began
            raise PermissionDenied
        url = reverse('conversation', kwargs={'pk': self.other.pk})
        return redirect(f'{url}#message-{message.pk}')


class BlockMember(LoginRequiredMixin, View):
    """The member no longer wants messages from the one in the address."""

    def post(self, request, pk):
        other = other_member(request, pk)
        _block, created = Block.objects.get_or_create(blocker=request.user, blocked=other)
        if created:
            log_event('block', request, user=request.user.pk, blocked=other.pk)
        return redirect('conversation', pk=other.pk)


class UnblockMember(LoginRequiredMixin, View):
    def post(self, request, pk):
        other = other_member(request, pk)
        deleted, _per_model = Block.objects.filter(blocker=request.user, blocked=other).delete()
        if deleted:
            log_event('unblock', request, user=request.user.pk, blocked=other.pk)
        return redirect('conversation', pk=other.pk)


class ReportMessage(LoginRequiredMixin, FormView):
    """
    Show one received message to the moderators: a page to confirm it, with a note.
    Only the member the message was sent to can, and once.
    """

    template_name = 'conversations/report_form.html'
    form_class = ReportForm

    @cached_property
    def message(self):
        other = other_member(self.request, self.kwargs['pk'])
        conversation = Conversation.find(self.request.user, other)
        if conversation is None:
            raise Http404
        # From the other member in the address, so never one's own
        return get_object_or_404(
            Message.objects.select_related('sender__profile', 'report'),
            pk=self.kwargs['message_pk'],
            conversation=conversation,
            sender=other,
        )

    def back(self):
        url = reverse('conversation', kwargs={'pk': self.kwargs['pk']})
        return redirect(f'{url}#message-{self.message.pk}')

    def dispatch(self, request, *args, **kwargs):
        # After LoginRequiredMixin has sent a visitor to the login page
        if request.user.is_authenticated and hasattr(self.message, 'report'):
            return self.back()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['message'] = self.message
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                report = Report.of(self.message, self.request.user, form.cleaned_data['note'])
        except IntegrityError:
            # Reported in another tab since this page was loaded
            return self.back()
        log_event(
            'report',
            self.request,
            user=self.request.user.pk,
            sender=self.message.sender_id,
            report=report.pk,
        )
        messages.success(self.request, gettext('The message was reported to the moderators.'))
        return self.back()

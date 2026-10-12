from collections import Counter

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.views.generic import FormView, ListView, TemplateView, View

from forums.throttling import MESSAGE_THROTTLES, SearchThrottle, allowed
from notifications.events import conversation_opened
from notifications.models import Notification
from pages.models import SiteSettings
from users.audit import log_event

from .forms import MemberSearchForm, MessageForm, ReportForm
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


# The members a search shows; with more than these, the page asks for more of the name
MAX_MEMBERS = 20


def find_members(user, text):
    """
    The members with an active account that the words fit, by name, one more than
    MAX_MEMBERS at most. Every word must be in the first or the last name, ignoring
    case; a number also fits the member with that number, which is how a member
    without a name ("Member 11") is found. One query.
    """
    members = (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(pk=user.pk)
        .select_related('profile')
    )
    # "member 11" as the pages write it, in the reader's language
    label = (gettext('Member %(id)s') % {'id': ''}).strip().casefold()
    words = [word for word in text.split() if word.casefold() != label]
    if not words:
        return []
    for word in words:
        fits = Q(profile__first_name__icontains=word) | Q(profile__last_name__icontains=word)
        # Not longer than a member number can be
        if word.isdecimal() and len(word) <= 9:
            fits |= Q(pk=int(word))
        members = members.filter(fits)
    return list(
        members.order_by(
            Lower('profile__first_name'), Lower('profile__last_name'), 'pk'
        )[: MAX_MEMBERS + 1]
    )


class MemberList(LoginRequiredMixin, TemplateView):
    """
    Who to write to: a search among the members by name or number. Until something is
    searched for, the members the reader already has conversations with.
    """

    template_name = 'conversations/member_list.html'

    def get(self, request, *args, **kwargs):
        form = MemberSearchForm(request.GET or None)
        text = form.cleaned_data['q'].strip() if form.is_valid() else ''
        members, more, throttled = None, False, False
        if text:
            # Counted with the searches of the search page, so the members can't be
            # listed quickly a few letters at a time
            throttled = not allowed(request, SearchThrottle)
            if not throttled:
                members = find_members(request.user, text)
                more = len(members) > MAX_MEMBERS
                members = members[:MAX_MEMBERS]
                # Members with the same name are told apart by their number
                names = Counter(member.display_name for member in members)
                for member in members:
                    member.show_number = names[member.display_name] > 1
        context = self.get_context_data(
            form=form,
            members=members,
            more=more,
            throttled=throttled,
            known=None if text else self.known(),
        )
        return self.render_to_response(context, status=429 if throttled else 200)

    def known(self):
        """The members of the reader's latest conversations, if still active. One query."""
        user = self.request.user
        conversations = Conversation.objects.filter(
            Q(user_low=user) | Q(user_high=user)
        ).select_related('user_low__profile', 'user_high__profile')[:MAX_MEMBERS]
        others = (c.user_high if c.user_low == user else c.user_low for c in conversations)
        return [other for other in others if other.is_active]


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


class ReportList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    The reported messages, for the moderators: those not yet handled first. A report
    shows the one message and who it is between, nothing else of the conversation.
    A member without the permission gets a 403.
    """

    permission_required = 'conversations.view_report'
    template_name = 'conversations/report_list.html'
    context_object_name = 'reports'
    queryset = Report.objects.select_related(
        'reporter__profile', 'sender__profile', 'handled_by__profile'
    )

    def get_paginate_by(self, queryset):
        return SiteSettings.for_request(self.request).threads_per_page


class ReportHandled(LoginRequiredMixin, PermissionRequiredMixin, View):
    """A moderator has dealt with a report: it says who and when, and can't be reopened."""

    permission_required = 'conversations.change_report'

    def post(self, request, pk):
        get_object_or_404(Report, pk=pk)
        # Only the first one to press the button is recorded
        handled = Report.objects.filter(pk=pk, handled__isnull=True).update(
            handled=timezone.now(), handled_by=request.user
        )
        if handled:
            log_event('report_handled', request, user=request.user.pk, report=pk)
        return redirect('reports')

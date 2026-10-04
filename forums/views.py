from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    UserPassesTestMixin,
    PermissionRequiredMixin,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.forms import modelform_factory
from django.db.models import F, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
    View,
)

from .activity import add_last_repliers, add_top_threads, latest_threads, with_activity, with_counts
from .forms import SearchForm
from .search import load, matches, search_query
from .markdown import render as render_markdown
from .models import MAX_TEXT_LENGTH, Forum, Thread, Post, UpVote, Notification
from .throttling import PreviewThrottle, SearchThrottle, allowed, posting_allowed
from pages.models import SiteSettings
from users.audit import log_moderation


class ForumsList(LoginRequiredMixin, ListView):
    model = Forum
    context_object_name = 'forum_list'
    # Django skips Meta.ordering on GROUP BY queries, so order explicitly
    queryset = with_counts(Forum.objects.all()).order_by('title', 'id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['forum_list'] = add_top_threads(context['forum_list'])
        # Above the forums: the newest activity anywhere (all of it under Latest)
        count = SiteSettings.for_request(self.request).recent_threads
        context['recent_threads'] = latest_threads(count)
        return context


class ForumDetail(LoginRequiredMixin, DetailView):
    model = Forum
    context_object_name = 'forum'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Threads with each author, profile and reply count in the same query
        threads = with_activity(
            Thread.objects.filter(forum=self.object).select_related('user__profile')
        )
        # Announcements on every page, above the threads and outside their pages.
        # Django skips Meta.ordering on GROUP BY queries, so order explicitly.
        announcements = list(threads.filter(announcement=True).order_by('-added', '-id'))
        regular = threads.filter(announcement=False).order_by('-added', '-id')
        # get_page() shows the first or last page for a page number that doesn't exist
        per_page = SiteSettings.for_request(self.request).threads_per_page
        page = Paginator(regular, per_page).get_page(self.request.GET.get('page'))
        page.object_list = list(page.object_list)
        # One query for the last repliers of both lists
        add_last_repliers(announcements + page.object_list)
        context['announcements'] = announcements
        context['threads'] = page
        context['can_start_thread'] = self.object.can_start_thread(self.request.user)
        return context


class ForumCreate(PermissionRequiredMixin, CreateView):
    model = Forum
    fields = '__all__'
    permission_required = 'forums.add_forum'
    success_url = reverse_lazy('home')


class ForumUpdate(PermissionRequiredMixin, UpdateView):
    model = Forum
    fields = '__all__'
    permission_required = 'forums.change_forum'
    template_name_suffix = '_update_form'

    def get_success_url(self):
        return reverse_lazy('forum_detail', kwargs={'pk': self.kwargs['pk']})


def thread_page_url(thread_id, page=None):
    """A thread's page; `page` is a page number or 'last', anything else gives the first page."""
    url = reverse('thread_detail', kwargs={'pk': thread_id})
    page = str(page or '')
    if page == 'last' or page.isdecimal():
        return f'{url}?page={page}'
    return url


class ThreadDetail(LoginRequiredMixin, DetailView):
    model = Thread
    context_object_name = 'thread'

    def get_queryset(self):
        return super().get_queryset().select_related('forum', 'user__profile')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # One page of posts, oldest first, with each author and profile in the same query
        posts = (
            Post.objects.filter(thread=self.object)
            .select_related('user__profile')
            .order_by('added', 'id')
        )
        paginator = Paginator(posts, SiteSettings.for_request(self.request).posts_per_page)
        page = self.request.GET.get('page')
        # get_page() shows the first or last page for a page number that doesn't exist
        context['posts'] = paginator.get_page(paginator.num_pages if page == 'last' else page)
        context['can_reply'] = self.object.forum.can_reply(self.request.user)

        if self.request.user.is_authenticated:
            # The posts on this page that the reader upvoted
            context['voted'] = set(
                UpVote.objects.filter(
                    user=self.request.user, post__in=[post.id for post in context['posts']]
                ).values_list('post_id', flat=True)
            )
            context['subscribed'] = Notification.objects.filter(
                thread=self.kwargs['pk'], user=self.request.user
            )
        return context


class AnnouncementFieldMixin:
    """The thread form, with the announcement checkbox for moderators only."""

    def get_form_class(self):
        fields = list(self.fields)
        if self.request.user.has_perm('forums.change_thread'):
            fields.append('announcement')
        return modelform_factory(self.model, fields=fields)


class ThreadUpdate(LoginRequiredMixin, UserPassesTestMixin, AnnouncementFieldMixin, UpdateView):
    model = Thread
    fields = ('title', 'text')
    template_name_suffix = '_update_form'

    def test_func(self):
        """
        User must be author to update
        """
        if self.request.user.has_perm('forums.change_thread'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)
        log_moderation(self.request, 'change', self.object)
        return response

    def get_success_url(self):
        return reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['pk']})


class PostingLimitMixin:
    """Refuse a new thread or post over the user's posting limit, shared with the API."""

    def form_valid(self, form):
        # Checked here, so a form with errors doesn't count
        if not posting_allowed(self.request):
            form.add_error(None, 'You are posting too fast. Wait a while and try again.')
            # The form comes back with the text, to send again later
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().form_valid(form)


class ClosedForumMixin:
    """Refuse a new thread or post that the forum's posting setting doesn't allow."""

    def may_post(self):
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        # After LoginRequiredMixin, so a visitor is sent to the login page. Before the
        # form, so a refused post doesn't count against the posting limit.
        if not self.may_post():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ThreadCreate(
    LoginRequiredMixin,
    ClosedForumMixin,
    PostingLimitMixin,
    AnnouncementFieldMixin,
    SuccessMessageMixin,
    CreateView,
):
    model = Thread
    context_object_name = 'thread'
    fields = ['title', 'text']
    success_message = "Thread was created successfullty"

    def may_post(self):
        forum = get_object_or_404(Forum, pk=self.kwargs['pk'])
        return forum.can_start_thread(self.request.user)

    def get_context_data(self, **kwargs):
        # Call the base implementation
        context = super(ThreadCreate, self).get_context_data(**kwargs)
        # Get the forum and add it to the context
        context['forum'] = get_object_or_404(Forum, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        # Add logged-in user as author of thread
        form.instance.user = self.request.user
        # Associate thread with forum based on passed id
        form.instance.forum = get_object_or_404(Forum, pk=self.kwargs['pk'])
        # Call super-class form validation behaviour
        return super(ThreadCreate, self).form_valid(form)

    def get_success_url(self):
        return reverse_lazy('forum_detail', kwargs={'pk': self.kwargs['pk']})


class ThreadDelete(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Thread
    template_name_suffix = '_delete_form'

    # permission_required = 'forums.delete_thread'

    def test_func(self):
        """
        User must be author to delete
        """
        if self.request.user.has_perm('forums.delete_thread'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user

    def form_valid(self, form):
        # The id is gone from the object once it is deleted
        pk = self.object.pk
        response = super().form_valid(form)
        self.object.pk = pk
        log_moderation(self.request, 'delete', self.object)
        return response

    def get_success_url(self):
        return reverse_lazy('forum_detail', kwargs={'pk': self.kwargs['fpk']})


class PostCreate(
    LoginRequiredMixin, ClosedForumMixin, PostingLimitMixin, SuccessMessageMixin, CreateView
):
    model = Post
    fields = ['text']
    success_message = "Post was created successfully!"

    def may_post(self):
        thread = get_object_or_404(Thread.objects.select_related('forum'), pk=self.kwargs['pk'])
        return thread.forum.can_reply(self.request.user)

    def get_context_data(self, **kwargs):
        # Call the base implementation
        context = super(PostCreate, self).get_context_data(**kwargs)
        # Get the forum and add it to the context
        context['thread'] = get_object_or_404(Thread, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        # Add logged-in user as author of thread
        form.instance.user = self.request.user
        # Associate post with thread based on passed id
        form.instance.thread = get_object_or_404(Thread, pk=self.kwargs['pk'])
        # Call super-class form validation behaviour
        return super(PostCreate, self).form_valid(form)

    def get_success_url(self):
        # The new post is the last one of the thread
        return thread_page_url(self.kwargs['pk'], 'last')


class PostDelete(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    template_name_suffix = '_delete_form'

    # permission_required = 'forums.delete_post'

    def test_func(self):
        """
        User must be author to delete
        """
        if self.request.user.has_perm('forums.delete_post'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user

    def form_valid(self, form):
        # The id is gone from the object once it is deleted
        pk = self.object.pk
        response = super().form_valid(form)
        self.object.pk = pk
        log_moderation(self.request, 'delete', self.object)
        return response

    def get_success_url(self):
        return reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['tpk']})


class PostUpvote(LoginRequiredMixin, View):
    model = Post

    def post(self, request, **kwargs):
        post = get_object_or_404(Post, id=self.kwargs['pk'])
        if post.user == request.user:
            raise PermissionDenied
        _, created = UpVote.objects.get_or_create(post=post, user=request.user)
        if created:
            Post.objects.filter(id=post.id).update(upvotes=F('upvotes') + 1)
        # Back to the page of the thread the vote came from
        return HttpResponseRedirect(thread_page_url(self.kwargs['tpk'], request.POST.get('page')))


class ThreadNotification(LoginRequiredMixin, View):
    model = Thread

    def post(self, request, **kwargs):
        thread = get_object_or_404(Thread, id=self.kwargs['pk'])
        deleted, _ = Notification.objects.filter(
            thread=thread, user=request.user
        ).delete()
        if not deleted:
            Notification.objects.create(thread=thread, user=request.user)
        return HttpResponseRedirect(thread_page_url(thread.pk, request.POST.get('page')))


class SearchView(LoginRequiredMixin, TemplateView):
    """
    Words and filters in, every match out, 20 to a page (forums/search.py). The page
    without a search shows only the form. A search counts against the search limit.
    """

    template_name = 'forums/search.html'
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        # Submitted once any of the form's fields is in the address
        submitted = any(name in request.GET for name in SearchForm.base_fields)
        form = SearchForm(request.GET if submitted else None)
        results = page = None
        throttled = False
        if submitted and form.is_valid():
            # Counted only when a search would run
            throttled = not allowed(request, SearchThrottle)
            if not throttled:
                page = Paginator(matches(form.cleaned_data), self.paginate_by).get_page(
                    request.GET.get('page')
                )
                results = load(
                    page.object_list,
                    SiteSettings.for_request(request).posts_per_page,
                    search_query(form.cleaned_data),
                )
        # The filters in use, shown on the toggle that folds them away on small screens
        filter_count = sum(1 for name in ('forum', 'author', 'since', 'until') if request.GET.get(name))
        filter_count += request.GET.get('kind') in ('threads', 'replies')
        context = self.get_context_data(
            form=form, results=results, page=page, throttled=throttled, filter_count=filter_count
        )
        return self.render_to_response(context, status=429 if throttled else 200)

    # ## SearchRank ##
    # def get_queryset(self):
    #     query = self.request.GET.get('q')
    #     object_list = Post.objects.annotate(
    #         search=SearchVector('text'),
    #     ).filter(search=SearchQuery(query))
    #     return object_list


class MarkdownPreview(LoginRequiredMixin, View):
    """What the editor's preview button shows: the text rendered as it will be on the thread page."""

    http_method_names = ['post']

    def post(self, request):
        if not allowed(request, PreviewThrottle):
            # The editor shows "The preview could not be loaded."
            return HttpResponse('Too many previews. Wait a moment and try again.', status=429)
        text = request.POST.get('text', '')
        # Longer than a thread or post may be: it couldn't be saved either
        if len(text) > MAX_TEXT_LENGTH:
            return HttpResponseBadRequest('The text is too long.')
        return HttpResponse(render_markdown(text))

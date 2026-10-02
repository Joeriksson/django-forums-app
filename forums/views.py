from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    UserPassesTestMixin,
    PermissionRequiredMixin,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    View,
    FormView,
)

from .forms import SearchForm
from .markdown import render as render_markdown
from .models import MAX_TEXT_LENGTH, Forum, Thread, Post, UpVote, Notification
from .throttling import posting_allowed
from users.audit import log_moderation


class ForumsList(ListView, FormView):
    model = Forum
    context_object_name = 'forum_list'
    form_class = SearchForm


class ForumDetail(DetailView):
    model = Forum
    context_object_name = 'forum'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # One page of threads, with each author, profile and post count in the same query
        threads = (
            Thread.objects.filter(forum=self.object)
            .select_related('user__profile')
            .annotate(post_count=Count('posts'))
            # Django skips Meta.ordering on GROUP BY queries, so order explicitly
            .order_by('-added', '-id')
        )
        # get_page() shows the first or last page for a page number that doesn't exist
        context['threads'] = Paginator(threads, self.paginate_by).get_page(
            self.request.GET.get('page')
        )
        return context


class ForumCreate(PermissionRequiredMixin, CreateView):
    model = Forum
    fields = '__all__'
    permission_required = 'forums.add_forum'
    success_url = reverse_lazy('forum_list')


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


class ThreadDetail(DetailView):
    model = Thread
    context_object_name = 'thread'
    paginate_by = 25

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
        paginator = Paginator(posts, self.paginate_by)
        page = self.request.GET.get('page')
        # get_page() shows the first or last page for a page number that doesn't exist
        context['posts'] = paginator.get_page(paginator.num_pages if page == 'last' else page)

        # Check if current user upvoted
        if self.request.user.is_authenticated:
            context['voted'] = UpVote.objects.filter(user=self.request.user)
            context['subscribed'] = Notification.objects.filter(
                thread=self.kwargs['pk'], user=self.request.user
            )
        return context


class ThreadUpdate(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
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


class ThreadCreate(LoginRequiredMixin, PostingLimitMixin, SuccessMessageMixin, CreateView):
    model = Thread
    context_object_name = 'thread'
    fields = ['title', 'text']
    success_message = "Thread was created successfullty"

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


class PostCreate(LoginRequiredMixin, PostingLimitMixin, SuccessMessageMixin, CreateView):
    model = Post
    fields = ['text']
    success_message = "Post was created successfully!"

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


class SearchResultsView(ListView):
    model = Post
    # template_name_suffix = '_search_results_form'
    template_name = 'forums/post_search_results_form.html'

    # Search scans every thread and post, so keep it from being used to load the server:
    # no scan for very short words, and only the newest results of each kind.
    min_query_length = 3
    max_query_length = 200
    max_results = 50

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()[: self.max_query_length]
        self.too_short = len(query) < self.min_query_length
        self.limited = False
        if self.too_short:
            return []

        posts = Post.objects.filter(text__icontains=query).select_related('thread', 'user')
        threads = Thread.objects.filter(
            Q(title__icontains=query) | Q(text__icontains=query)
        ).select_related('forum', 'user')
        return self.newest(posts) + self.newest(threads)

    def newest(self, queryset):
        # One more than the limit, to know whether something was left out
        results = list(queryset.order_by('-added')[: self.max_results + 1])
        if len(results) > self.max_results:
            self.limited = True
        return results[: self.max_results]

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            too_short=self.too_short,
            limited=self.limited,
            min_query_length=self.min_query_length,
            **kwargs,
        )

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
        text = request.POST.get('text', '')
        # Longer than a thread or post may be: it couldn't be saved either
        if len(text) > MAX_TEXT_LENGTH:
            return HttpResponseBadRequest('The text is too long.')
        return HttpResponse(render_markdown(text))

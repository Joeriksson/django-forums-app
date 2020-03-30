from itertools import chain

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, FormView

from .forms import SearchForm
from .models import Forum, Thread, Post, UpVote, Notification


class ForumsList(ListView, FormView):
    model = Forum
    context_object_name = 'forum_list'
    form_class = SearchForm


class ForumDetail(DetailView):
    model = Forum
    context_object_name = 'forum'

    # def get_context_data(self, **kwargs):
    #     # Call the base implementation
    #     context = super(ForumDetail, self).get_context_data(**kwargs)
    #     context['threads'] = Thread.objects.filter(forum=self.kwargs['pk'])


class ForumCreate(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Forum
    fields = '__all__'
    permission_required = 'forums.add_forum'
    success_url = reverse_lazy('forum_list')
    login_url = 'home'

    def get_login_url(self):
        """
        Override this method to override the login_url attribute.
        """
        login_url = self.login_url
        if not login_url:
            raise NotImplementedError(
                '{0} is missing the login_url attribute. Define {0}.login_url, settings.LOGIN_URL, or override '
                '{0}.get_login_url().'.format(self.__class__.__name__)
            )
        return str(login_url)


class ForumUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Forum
    fields = '__all__'
    permission_required = 'forums.change_forum'
    template_name_suffix = '_update_form'

    def get_success_url(self):
        return reverse_lazy('forum_detail', kwargs={'pk': self.kwargs['pk']})


class ThreadDetail(DetailView):
    model = Thread
    context_object_name = 'thread'

    def get_context_data(self, **kwargs):
        # Call the base implementation
        context = super(ThreadDetail, self).get_context_data(**kwargs)
        context['posts'] = Post.objects.filter(thread=self.kwargs['pk']).select_related('thread').select_related(
            'user').prefetch_related(
            'user__profile')

        # Check if current user upvoted
        if self.request.user.is_authenticated:
            context['voted'] = UpVote.objects.filter(user=self.request.user)
            context['subscribed'] = Notification.objects.filter(thread=self.kwargs['pk'], user=self.request.user)
        return context


class ThreadUpdate(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Thread
    fields = ('title', 'text')
    # permission_required = 'forums.change_thread'
    template_name_suffix = '_update_form'

    def test_func(self):
        if self.request.user.has_perm('forums.update_thread'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user

    def get_success_url(self):
        return reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['pk']})


class ThreadCreate(LoginRequiredMixin, CreateView):
    model = Thread
    context_object_name = 'thread'
    fields = ['title', 'text']

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
        if self.request.user.has_perm('forums.delete_thread'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user

    def get_success_url(self):
        return reverse_lazy('forum_detail', kwargs={'pk': self.kwargs['fpk']})


class PostCreate(LoginRequiredMixin, CreateView):
    model = Post
    fields = ['text']

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
        return reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['pk']})


class PostDelete(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    template_name_suffix = '_delete_form'

    # permission_required = 'forums.delete_post'

    def test_func(self):
        if self.request.user.has_perm('forums.delete_post'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user

    def get_success_url(self):
        return reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['tpk']})


class PostUpvote(LoginRequiredMixin, View):
    model = Post

    def get(self, request, **kwargs):
        post = Post.objects.get(id=self.kwargs['pk'])
        post.upvotes += 1
        post.save()
        upvote = UpVote.objects.create(post=post, user=self.request.user)
        upvote.save()
        return HttpResponseRedirect(reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['tpk']}))


class ThreadNotification(LoginRequiredMixin, View):
    model = Thread

    def get(self, request, **kwargs):
        thread = Thread.objects.get(id=self.kwargs['pk'])
        existing_notification = Notification.objects.filter(thread=thread, user=self.request.user)
        if not existing_notification:
            notification = Notification.objects.create(thread=thread, user=self.request.user)
            notification.save()
        else:
            existing_notification.delete()

        return HttpResponseRedirect(reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['pk']}))


class SearchResultsView(ListView):
    model = Post
    # template_name_suffix = '_search_results_form'
    template_name = 'forums/post_search_results_form.html'

    def get_queryset(self):  # new
        query = self.request.GET.get('q')

        post = Post.objects.filter(Q(text__icontains=query))
        thread = Thread.objects.filter(Q(title__icontains=query) | Q(text__icontains=query))

        return chain(post, thread)

    # ## SearchRank ##
    # def get_queryset(self):
    #     query = self.request.GET.get('q')
    #     object_list = Post.objects.annotate(
    #         search=SearchVector('text'),
    #     ).filter(search=SearchQuery(query))
    #     return object_list

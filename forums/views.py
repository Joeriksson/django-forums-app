from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import get_object_or_404
from .models import Forum, Thread, Post
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin


class ForumsList(ListView):
    model = Forum
    context_object_name = 'forum_list'


class ForumDetail(DetailView):
    model = Forum
    context_object_name = 'forum'


class ForumCreate(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Forum
    fields = '__all__'
    permission_required = "auth.change_user"
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


class ForumUpdate(LoginRequiredMixin, UpdateView):
    model = Forum
    fields = '__all__'
    template_name_suffix = '_update_form'

    def get_success_url(self):
        return reverse_lazy('forum_detail', kwargs={'pk': self.kwargs['pk']})


class ThreadDetail(DetailView):
    model = Thread
    context_object_name = 'thread'


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

    def test_func(self):
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

    def test_func(self):
        obj = self.get_object()
        return obj.user == self.request.user

    def get_success_url(self):
        return reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['tpk']})

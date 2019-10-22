from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, HttpResponseRedirect
from .models import Forum, Thread, Post, UpVote, Notification
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save


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

    def get_context_data(self, **kwargs):
        # Call the base implementation
        context = super(ThreadDetail, self).get_context_data(**kwargs)
        # Check if current user upvoted
        context['voted'] = UpVote.objects.filter(user=self.request.user)
        context['subscribed'] = Notification.objects.filter(thread=self.kwargs['pk'], user=self.request.user)
        return context


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


def send_notification(sender, created, **kwargs):
    if created:
        obj = kwargs['instance']

        # Check which users has subscribed to the thread which was posted to
        notification_users = Notification.objects.filter(thread=obj.thread)

        # Compose message to subscribers
        subject, from_email = f'New post added by {obj.user.username}', 'info@email.com'

        bcc = []

        for notification_user in notification_users:
            bcc.append(notification_user.user.email)

        text_content = f'A new post was added to thread "{obj.thread.title}" \n'
        # text_content += f'{[email for email in bcc]}'

        msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, bcc=bcc)

        msg.send()


post_save.connect(send_notification, sender=Post)

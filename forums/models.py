from django.contrib.auth import get_user_model
from django.db import models
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse_lazy
from django.contrib.sites.models import Site
from django_lifecycle import LifecycleModelMixin, hook


class Forum(models.Model):
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=500)

    def __str__(self):
        return f'Forum: {self.title}'

    class Meta:
        ordering = ['title']


class Thread(models.Model):
    title = models.CharField(max_length=300)
    text = models.TextField()
    added = models.DateTimeField(auto_now_add=True)
    edited = models.DateTimeField(auto_now=True)
    forum = models.ForeignKey(Forum, related_name='threads', on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, )

    def __str__(self):
        return f'Thread: {self.title} - (started by {self.user})'

    class Meta:
        ordering = ['-added']


class Post(LifecycleModelMixin, models.Model):
    text = models.TextField()
    upvotes = models.IntegerField(default=0)
    added = models.DateTimeField(auto_now_add=True)
    edited = models.DateTimeField(auto_now=True)
    thread = models.ForeignKey(Thread, related_name='posts', on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, )

    def __str__(self):
        return f'Post: {self.text} - (submitted by {self.user})'

    class Meta:
        ordering = ['added']

    @hook('after_create')
    def notify_subscribers(self):
        # TODO: Look into how to send multiple mails via header instead of BCC

        # Check which users has subscribed to the thread which was posted to
        notification_users = Notification.objects.filter(thread=self.thread)

        # Compose message to subscribers
        subject, from_email = f'New post added by {self.user.username}', 'info@wildvasa.com'

        url = reverse_lazy('thread_detail', args=(self.thread_id,))
        full_url = ''.join(['http://', str(Site.objects.get_current().domain), str(url)])

        bcc = [notification_user.user.email for notification_user in notification_users if
               notification_user != self.user]
        text_content = f'A new post was added to thread "{self.thread.title}" \n\nUrl: {full_url} \n\n'

        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email, bcc=bcc)

        msg.send()


class Gender(models.TextChoices):
    NOTPROVIDED = 'N', 'NotProvided'
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    OTHER = 'O', 'Other'


class UserProfile(models.Model):
    # NOTPROVIDED = 'N'
    # MALE = 'M'
    # FEMALE = 'F'
    # OTHER = 'O'
    # GENDER_CHOICES = (
    #     (NOTPROVIDED, 'NotProvided'),
    #     (MALE, 'Male'),
    #     (FEMALE, 'Female'),
    #     (OTHER, 'Other'),
    # )
    user = models.OneToOneField(get_user_model(), related_name='profile', on_delete=models.CASCADE, )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    bio = models.TextField(max_length=1000, blank=True)
    location = models.CharField(max_length=50, blank=True)
    gender = models.TextField(max_length=1, choices=Gender.choices, default=Gender.NOTPROVIDED)
    web_site = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    signature = models.TextField(blank=True)


class UpVote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, )
    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Upvote: {self.post} - (upvoted by {self.user})'

    class Meta:
        ordering = ['added']


class Notification(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Notification: {self.thread} - (subscribed by {self.user})'

    class Meta:
        ordering = ['added']

import os

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.urls import reverse
from django_lifecycle import LifecycleModelMixin, hook, AFTER_CREATE

from forums.tasks import send_notifications_task
from project.utils import queue_task

MARKDOWN_HELP = 'You can use Markdown: **bold**, *italic*, `code`, > quote, lists, links and tables.'
# Checked by the forms and the API, not by the database: texts are rendered on every page view
MAX_TEXT_LENGTH = 20_000
MAX_SIGNATURE_LENGTH = 500

# Full-text search in English word forms (forums/search.py). The indexes below are built on
# the same expressions, so a search must use these to be fast. A title weighs more than text.
SEARCH_CONFIG = 'english'
THREAD_SEARCH_VECTOR = SearchVector('title', weight='A', config=SEARCH_CONFIG) + SearchVector(
    'text', weight='B', config=SEARCH_CONFIG
)
POST_SEARCH_VECTOR = SearchVector('text', weight='B', config=SEARCH_CONFIG)


class Posting(models.TextChoices):
    """Who may add to a forum. A moderator is anyone with forums.change_thread."""

    OPEN = 'open', 'Open: every member can start threads and reply'
    MODERATORS_START = 'moderators_start', 'Moderators start threads; members can reply'
    MODERATORS_ONLY = 'moderators_only', 'Moderators only: members can read'


class Forum(models.Model):
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=500)
    posting = models.CharField(
        'Who can post',
        max_length=20,
        choices=Posting.choices,
        default=Posting.OPEN,
        help_text='Closing a forum stops new threads or replies. What is already there stays.',
    )

    def __str__(self):
        return f'Forum: {self.title}'

    @property
    def is_closed(self):
        return self.posting != Posting.OPEN

    @property
    def posting_note(self):
        """What a closed forum tells its readers."""
        return {
            Posting.MODERATORS_START: 'Only moderators can start threads here. Everyone can reply.',
            Posting.MODERATORS_ONLY: 'Only moderators can post here.',
        }.get(self.posting, '')

    def can_start_thread(self, user):
        return self.posting == Posting.OPEN or user.has_perm('forums.change_thread')

    def can_reply(self, user):
        return self.posting != Posting.MODERATORS_ONLY or user.has_perm('forums.change_thread')

    class Meta:
        ordering = ['title']


class Thread(models.Model):
    title = models.CharField(max_length=300)
    text = models.TextField(max_length=MAX_TEXT_LENGTH, help_text=MARKDOWN_HELP)
    added = models.DateTimeField(auto_now_add=True)
    edited = models.DateTimeField(auto_now=True)
    forum = models.ForeignKey(Forum, related_name='threads', on_delete=models.CASCADE)
    # Set by moderators (forums.change_thread)
    announcement = models.BooleanField(
        default=False, help_text='Keep this thread at the top of its forum, above the others.'
    )
    # user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f'Thread: {self.title} - (started by {self.user})'

    class Meta:
        ordering = ['-added']
        indexes = [GinIndex(THREAD_SEARCH_VECTOR, name='thread_search')]


class Post(LifecycleModelMixin, models.Model):
    text = models.TextField(max_length=MAX_TEXT_LENGTH, help_text=MARKDOWN_HELP)
    upvotes = models.IntegerField(default=0)
    added = models.DateTimeField(auto_now_add=True)
    edited = models.DateTimeField(auto_now=True)
    thread = models.ForeignKey(Thread, related_name='posts', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f'Post: {self.text} - (submitted by {self.user})'

    class Meta:
        ordering = ['added']
        indexes = [GinIndex(POST_SEARCH_VECTOR, name='post_search')]

    @hook(AFTER_CREATE, on_commit=True)
    def notify_subscribers(self):
        # Runs only once the post is committed, so a rollback sends nothing
        if not os.environ.get('CI'):
            full_url = settings.SITE_URL + reverse('thread_detail', args=(self.thread_id,))

            # Only to active accounts, and only to an address its owner has confirmed
            email_addresses = list(
                Notification.objects.filter(
                    thread_id=self.thread_id,
                    user__is_active=True,
                    user__emailaddress__verified=True,
                    user__emailaddress__email__iexact=models.F('user__email'),
                )
                .exclude(user_id=self.user_id)
                .order_by('pk')
                .values_list('user__email', flat=True)
                .distinct()
            )
            if not email_addresses:
                return

            queue_task(
                send_notifications_task,
                self.thread_id,
                self.thread.title,
                self.user.display_name,
                full_url,
                email_addresses,
            )


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
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name='profile',
        on_delete=models.CASCADE,
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    bio = models.TextField(max_length=1000, blank=True)
    location = models.CharField(max_length=50, blank=True)
    gender = models.TextField(
        max_length=1, choices=Gender.choices, default=Gender.NOTPROVIDED
    )
    web_site = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    signature = models.TextField(max_length=MAX_SIGNATURE_LENGTH, blank=True)


class UpVote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Upvote: {self.post} - (upvoted by {self.user})'

    class Meta:
        ordering = ['added']
        constraints = [
            models.UniqueConstraint(
                fields=['post', 'user'], name='unique_upvote_per_user'
            ),
        ]


class Notification(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Notification: {self.thread} - (subscribed by {self.user})'

    class Meta:
        ordering = ['added']
        constraints = [
            models.UniqueConstraint(
                fields=['thread', 'user'], name='unique_notification_per_user'
            ),
        ]

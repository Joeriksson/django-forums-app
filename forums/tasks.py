from celery import shared_task
from django.conf import settings
from django.db.models import F, Q
from django.urls import reverse
from django.utils.translation import gettext

from project.utils import send_mail, site_language


@shared_task
def my_scheduled_task():
    print('A scheduled task just ran')


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_notifications_task(post_id):
    """
    The mail about a reply, queued to run some minutes after it (Site settings). It goes
    to the subscribers whose notification for the thread still starts at this reply and
    is unread: who has opened the thread gets none, and the replies that follow send
    none either, until the member has been there. One mail, BCC.
    """
    # The models import this module
    from forums.models import Post, Subscription
    from pages.models import SiteSettings

    post = Post.objects.select_related('thread', 'user__profile').filter(pk=post_id).first()
    # Deleted while the mail waited
    if post is None:
        return

    # Only to active accounts, and only to an address its owner has confirmed
    email_addresses = list(
        Subscription.objects.filter(
            thread_id=post.thread_id,
            user__is_active=True,
            user__emailaddress__verified=True,
            user__emailaddress__email__iexact=F('user__email'),
            # One filter() call, so both are about the same notification
            user__notifications__post=post,
            user__notifications__read=False,
        )
        .order_by('pk')
        .values_list('user__email', flat=True)
        .distinct()
    )
    if not email_addresses:
        return

    # The reply on its page of the thread: the replies up to it, plus the opening post
    position = Post.objects.filter(thread_id=post.thread_id).filter(
        Q(added__lt=post.added) | Q(added=post.added, id__lte=post.id)
    ).count()
    page = (position - 1) // SiteSettings.load().posts_per_page + 1
    thread_url = reverse('thread_detail', args=(post.thread_id,))
    full_url = f'{settings.SITE_URL}{thread_url}?page={page}#post-{post.id}'

    # The mail is for all subscribers: the site's language, also for "Member <id>"
    with site_language():
        subject = gettext('New post added by %(name)s') % {'name': post.user.display_name}
        added = gettext('A new post was added to thread "%(title)s"') % {'title': post.thread.title}
        url = gettext('Url: %(url)s') % {'url': full_url}

    text_content = f'{added} \n\n{url} \n\n'

    send_mail(subject, settings.DEFAULT_FROM_EMAIL, email_addresses, text_content)

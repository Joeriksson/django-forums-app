from django.conf import settings
from django.contrib.sites.models import Site
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class SiteSettings(models.Model):
    """
    The site's name and the visitors' texts: one record, edited in the admin. Read it
    with load(); pages get it as site_settings (pages.context_processors).
    """

    PK = 1

    title = models.CharField(
        max_length=60, default='Wildvasa', help_text='The site\'s name: header, tab, emails and authenticator apps.'
    )
    tagline = models.CharField(
        max_length=200,
        default='A private forum. Sign in to read and write.',
        help_text='Under the name on the visitors\' home page.',
    )
    invitation_note = models.CharField(
        max_length=300,
        default='Membership is by invitation. Got an invitation? Use the link in the email.',
        help_text='On the visitors\' home page while signup is closed.',
    )
    recent_threads = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text='Threads under Recent activity, above the forum list (1 to 10).',
    )
    latest_threads = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(50)],
        help_text='Threads on the Latest page (5 to 50).',
    )
    threads_per_page = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(100)],
        help_text='Threads per page of a forum (5 to 100). Old links to a page may then lead elsewhere.',
    )
    posts_per_page = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(5), MaxValueValidator(100)],
        help_text='Posts per page of a thread (5 to 100). Old links to a page may then lead elsewhere.',
    )

    notification_mail_delay = models.PositiveSmallIntegerField(
        default=5,
        validators=[MaxValueValidator(30)],
        help_text='Minutes a reply waits before it is mailed to the thread\'s subscribers. Those who '
        'open the thread in that time get no mail (0 to 30; 0 mails at once).',
    )

    class Meta:
        verbose_name = 'site settings'
        verbose_name_plural = 'site settings'

    def __str__(self):
        return 'Site settings'

    @classmethod
    def load(cls):
        """The record, or the defaults if it is missing. One query, no cache: every
        process sees a change at once."""
        return cls.objects.filter(pk=cls.PK).first() or cls(pk=cls.PK)

    @classmethod
    def for_request(cls, request):
        """load(), once per request: the view and its templates share it."""
        if not hasattr(request, '_site_settings'):
            request._site_settings = cls.load()
        return request._site_settings

    def save(self, *args, **kwargs):
        self.pk = self.PK
        super().save(*args, **kwargs)
        # allauth and Django name the site from Sites: keep its display name the same
        Site.objects.filter(pk=settings.SITE_ID).update(name=self.title)
        Site.objects.clear_cache()

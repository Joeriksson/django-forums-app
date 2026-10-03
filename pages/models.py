from django.conf import settings
from django.contrib.sites.models import Site
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

    def save(self, *args, **kwargs):
        self.pk = self.PK
        super().save(*args, **kwargs)
        # allauth and Django name the site from Sites: keep its display name the same
        Site.objects.filter(pk=settings.SITE_ID).update(name=self.title)
        Site.objects.clear_cache()

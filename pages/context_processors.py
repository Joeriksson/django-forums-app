from django.utils.functional import SimpleLazyObject

from .models import SiteSettings


def site_settings(request):
    """site_settings in every template: loaded once, and only when a template uses it."""
    return {'site_settings': SimpleLazyObject(lambda: SiteSettings.for_request(request))}

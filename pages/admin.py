from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """One record: the list opens it, and it can't be added twice or deleted."""

    def changelist_view(self, request, extra_context=None):
        site_settings = SiteSettings.load()
        if site_settings._state.adding:
            # The migration creates it; recreate it with the defaults if it is gone
            site_settings.save()
        return redirect(reverse('admin:pages_sitesettings_change', args=[site_settings.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

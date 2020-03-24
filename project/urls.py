from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from . import views

urlpatterns = [
                  # django admin
                  path('nimda/', admin.site.urls),
                  path('admin/', include('admin_honeypot.urls', namespace='admin_honeypot')),
                  # user management
                  path('accounts/', include('allauth.urls')),
                  path('user_profile/<int:pk>', views.UserProfileUpdate.as_view(), name='user_profile_edit'),
                  # local apps
                  path('', include('pages.urls')),
                  path('forums/', include('forums.urls')),
                  path('api/', include('api.urls')),
                  path('martor/', include('martor.urls')),
              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
                      path('__debug__/', include(debug_toolbar.urls)),
                  ] + urlpatterns

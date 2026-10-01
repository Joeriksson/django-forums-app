import os

from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from users import views as user_views

from . import views

ADMIN_URL = os.getenv('ADMIN_URL', 'nimda')

# The admin logs in through allauth's login page, so it gets the two-factor step
admin.site.login = secure_admin_login(admin.site.login)

urlpatterns = [
    # django admin
    path(f'{ADMIN_URL}/', admin.site.urls),
    # path('admin/', include('admin_honeypot.urls', namespace='admin_honeypot')),
    # user management
    path(
        'accounts/invite/<str:key>/',
        user_views.accept_invitation,
        name='accept_invitation',
    ),
    path('accounts/', include('allauth.urls')),
    path(
        'user_profile/<int:pk>',
        views.UserProfileUpdate.as_view(),
        name='user_profile_edit',
    ),
    # local apps
    path('', include('pages.urls')),
    path('forums/', include('forums.urls')),
    path('api/', include('api.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

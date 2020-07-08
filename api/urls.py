from django.urls import path, include
from rest_framework import routers
from rest_framework.documentation import include_docs_urls
from rest_framework.schemas import get_schema_view

from .views import ForumViewSet, ThreadViewSet, PostViewSet, UserViewSet

router = routers.DefaultRouter()
router.register(r'forums', ForumViewSet)
router.register(r'threads', ThreadViewSet)
router.register(r'posts', PostViewSet)
router.register(r'users', UserViewSet)

API_TITLE = 'Forums API'
API_DESCRIPTION = 'A Web API for creating and editing forums, threads, and posts'
schema_view = get_schema_view(title=API_TITLE)

urlpatterns = [
    path('', include(router.urls)),
    path('api-auth', include('rest_framework.urls')),
    path('rest_auth/', include('rest_auth.urls')),
    # path('rest-auth/registration/', include('rest_auth.registration.urls')),
    path('docs/', include_docs_urls(title=API_TITLE, description=API_DESCRIPTION)),
    path('schema/', schema_view),
]

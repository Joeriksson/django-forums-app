from django.urls import path, include
from rest_framework import routers

from .views import ForumViewSet, ThreadViewSet, PostViewSet, UserViewSet

router = routers.DefaultRouter()
router.register(r'forums', ForumViewSet)
router.register(r'threads', ThreadViewSet)
router.register(r'posts', PostViewSet)
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('api-auth', include('rest_framework.urls')),
]

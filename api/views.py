from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticatedOrReadOnly

from forums.models import Forum, Thread, Post
from users.models import CustomUser
from .permissions import IsOwnerOrModeratorOrReadOnly
from .serializers import (
    ForumSerializer,
    ThreadSerializer,
    PostSerializer,
    UserSerializer,
)


class ForumViewSet(viewsets.ModelViewSet):
    queryset = Forum.objects.all().order_by('title')
    serializer_class = ForumSerializer


class ThreadViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrModeratorOrReadOnly & IsAuthenticatedOrReadOnly,)
    queryset = Thread.objects.all().order_by('-added')
    serializer_class = ThreadSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PostViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrModeratorOrReadOnly & IsAuthenticatedOrReadOnly,)
    queryset = Post.objects.all().order_by('-added')
    serializer_class = PostSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAdminUser,)
    queryset = CustomUser.objects.all().order_by('username')
    serializer_class = UserSerializer

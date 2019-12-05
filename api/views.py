from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from forums.models import Forum, Thread, Post
from users.models import CustomUser
from .permissions import IsOwnerOrReadOnly
from .serializers import ForumSerializer, ThreadSerializer, PostSerializer, UserSerializer


class ForumViewSet(viewsets.ModelViewSet):
    queryset = Forum.objects.all().order_by('title')
    serializer_class = ForumSerializer


class ThreadViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrReadOnly,)
    queryset = Thread.objects.all().order_by('-added')
    serializer_class = ThreadSerializer


class PostViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrReadOnly,)
    queryset = Post.objects.all().order_by('-added')
    serializer_class = PostSerializer


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    queryset = CustomUser.objects.all().order_by('username')
    serializer_class = UserSerializer

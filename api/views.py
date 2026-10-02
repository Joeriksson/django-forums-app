from django.db.models import Count
from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import (
    DjangoModelPermissionsOrAnonReadOnly,
    IsAdminUser,
    IsAuthenticatedOrReadOnly,
)

from forums.models import Forum, Thread, Post
from users.audit import log_moderation
from users.models import CustomUser
from .permissions import IsOwnerOrModeratorOrReadOnly
from .serializers import (
    ForumSerializer,
    ThreadSerializer,
    PostSerializer,
    UserSerializer,
)


def filter_by_id(queryset, request, param):
    """Filter `queryset` on the `param` query parameter, if given."""
    value = request.query_params.get(param)
    if value is None:
        return queryset
    # Primary keys are AutoFields (32-bit), so bigger values would crash the query
    id_field = serializers.IntegerField(min_value=1, max_value=2**31 - 1)
    try:
        pk = id_field.run_validation(value)
    except ValidationError as exc:
        raise ValidationError({param: exc.detail})
    return queryset.filter(**{f'{param}_id': pk})


class ModerationLogMixin:
    """Record edits and deletions of other users' threads and posts in the security log."""

    def perform_update(self, serializer):
        super().perform_update(serializer)
        log_moderation(self.request, 'change', serializer.instance)

    def perform_destroy(self, instance):
        # The id is gone from the object once it is deleted
        pk = instance.pk
        super().perform_destroy(instance)
        instance.pk = pk
        log_moderation(self.request, 'delete', instance)


class ForumViewSet(viewsets.ModelViewSet):
    # Anyone can read; writing needs forums.add/change/delete_forum
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)
    # Django skips Meta.ordering on GROUP BY queries, so order explicitly
    queryset = Forum.objects.annotate(thread_count=Count('threads')).order_by('title')
    serializer_class = ForumSerializer

    def perform_create(self, serializer):
        forum = serializer.save()
        # Not loaded through the annotated queryset, and has no threads yet
        forum.thread_count = 0


class ThreadViewSet(ModerationLogMixin, viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrModeratorOrReadOnly & IsAuthenticatedOrReadOnly,)
    # Django skips Meta.ordering on GROUP BY queries, so order explicitly
    queryset = Thread.objects.annotate(post_count=Count('posts')).order_by('-added')
    serializer_class = ThreadSerializer

    def get_queryset(self):
        return filter_by_id(super().get_queryset(), self.request, 'forum')

    def perform_create(self, serializer):
        thread = serializer.save(user=self.request.user)
        # Not loaded through the annotated queryset, and has no posts yet
        thread.post_count = 0


class PostViewSet(ModerationLogMixin, viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrModeratorOrReadOnly & IsAuthenticatedOrReadOnly,)
    queryset = Post.objects.all()
    serializer_class = PostSerializer

    def get_queryset(self):
        return filter_by_id(super().get_queryset(), self.request, 'thread')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAdminUser,)
    queryset = CustomUser.objects.all().order_by('username')
    serializer_class = UserSerializer

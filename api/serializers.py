from rest_framework import serializers

from forums.models import Forum, Thread, Post
from users.models import CustomUser


class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
        read_only_fields = ('user', 'upvotes', 'added', 'edited')

    def validate_thread(self, value):
        # The thread is set on create; moving an existing post isn't allowed.
        if self.instance is not None and value != self.instance.thread:
            raise serializers.ValidationError(
                'A post cannot be moved to another thread.'
            )
        return value


class ThreadSerializer(serializers.ModelSerializer):
    # Posts are listed through /api/posts/?thread=<id>, not nested here
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Thread
        fields = (
            'id', 'title', 'text', 'forum', 'user', 'announcement', 'post_count', 'added', 'edited'
        )
        read_only_fields = ('user', 'added', 'edited')

    def validate_announcement(self, value):
        # Only moderators mark announcements; others may send the value unchanged
        current = self.instance.announcement if self.instance is not None else False
        if value != current and not self.context['request'].user.has_perm('forums.change_thread'):
            raise serializers.ValidationError('Only moderators can mark announcements.')
        return value

    def validate_forum(self, value):
        # The forum is set on create; moving an existing thread isn't allowed.
        if self.instance is not None and value != self.instance.forum:
            raise serializers.ValidationError(
                'A thread cannot be moved to another forum.'
            )
        return value


class ForumSerializer(serializers.ModelSerializer):
    # Threads are listed through /api/threads/?forum=<id>, not nested here
    thread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Forum
        fields = ('id', 'title', 'description', 'thread_count')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'date_joined',
            'last_login',
        )

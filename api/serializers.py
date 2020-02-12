from rest_framework import serializers

from forums.models import Forum, Thread, Post
from users.models import CustomUser


class PostSerializer(serializers.ModelSerializer):

    class Meta:
        model = Post
        # fields = ('url', 'id', 'text', 'thread', 'upvotes', 'user')
        fields = ('id', 'text', 'thread', 'upvotes', 'user')


class ThreadSerializer(serializers.ModelSerializer):
    posts = PostSerializer(many=True, read_only=True)

    class Meta:
        model = Thread
        # fields = ('url', 'id', 'title', 'text', 'forum', 'user', 'posts')
        fields = ('id', 'title', 'text', 'forum', 'user', 'posts')


class ForumSerializer(serializers.ModelSerializer):
    threads = ThreadSerializer(many=True, read_only=True)

    class Meta:
        model = Forum
        # fields = ('url', 'id', 'title', 'description', 'threads')
        fields = ('id', 'title', 'description', 'threads')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        # fields = (
        #     'url',
        #     'id',
        #     'username',
        #     'first_name',
        #     'last_name',
        #     'email',
        #     'date_joined',
        #     'last_login',
        # )
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'date_joined',
            'last_login',
        )

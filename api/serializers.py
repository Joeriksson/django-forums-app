from rest_framework import serializers

from forums.models import Forum, Thread, Post


class ForumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Forum
        fields = ('id', 'title', 'description')


class ThreadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thread
        fields = ('id', 'title', 'text', 'forum', 'user')


class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('id', 'text', 'thread', 'upvotes', 'user')

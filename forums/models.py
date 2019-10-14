from django.db import models

from django.contrib.auth import get_user_model


class Forum(models.Model):
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=500)

    def __str__(self):
        return f'Forum: {self.title}'

    class Meta:
        ordering = ['title']


class Thread(models.Model):
    title = models.CharField(max_length=300)
    text = models.TextField(default='<empy>')
    added = models.DateTimeField(auto_now_add=True)
    edited = models.DateTimeField(auto_now=True)
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, )

    def __str__(self):
        return f'Thread: {self.title} - (started by {self.user})'

    class Meta:
        ordering = ['-added']


class Post(models.Model):
    text = models.TextField()
    added = models.DateTimeField(auto_now_add=True)
    edited = models.DateTimeField(auto_now=True)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, )

    def __str__(self):
        return f'Post: {self.text} - (submitted by {self.user})'

    class Meta:
        ordering = ['added']

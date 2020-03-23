from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import CustomUser
from .models import UserProfile


@receiver(post_save, sender=CustomUser, dispatch_uid="create_user_profile")
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=get_user_model(), dispatch_uid="save_user_profile")
def save_user_profile(sender, instance, **kwargs):
    user_profile = UserProfile.objects.filter(user=instance)
    if not user_profile:
        UserProfile.objects.create(user=instance)
    instance.profile.save()

from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView

from forums.forms import UserProfileForm
from forums.models import UserProfile


class UserProfileUpdate(UpdateView):
    model = UserProfile
    success_url = reverse_lazy('home')
    form_class = UserProfileForm

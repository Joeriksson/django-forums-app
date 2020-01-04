from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from forums.forms import UserProfileForm
from forums.models import UserProfile


class UserProfileUpdate(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = UserProfile
    success_url = reverse_lazy('home')
    form_class = UserProfileForm

    def test_func(self):
        obj = self.get_object()
        return obj.user == self.request.user

from django.views.generic.edit import UpdateView
from django.urls import reverse_lazy

from django.contrib.auth import get_user_model


class UserUpdate(UpdateView):
    model = get_user_model()
    fields = ['first_name', 'last_name']
    success_url = reverse_lazy('home')

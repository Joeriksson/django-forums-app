from django.urls import path

from .views import HomePageView, LatestView

urlpatterns = [
    path('', HomePageView.as_view(), name='home'),
    path('latest/', LatestView.as_view(), name='latest'),
]

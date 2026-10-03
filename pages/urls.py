from django.urls import path

from forums.views import SearchView

from .views import HomePageView, LatestView

urlpatterns = [
    path('', HomePageView.as_view(), name='home'),
    path('latest/', LatestView.as_view(), name='latest'),
    path('search/', SearchView.as_view(), name='search_results'),
]

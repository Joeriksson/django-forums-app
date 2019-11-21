from django.urls import path

from .views import ForumsList, \
    ForumDetail, \
    ForumCreate, \
    ForumUpdate, \
    ThreadDetail, \
    ThreadCreate, \
    ThreadDelete, \
    ThreadNotification, \
    PostCreate, \
    PostDelete, \
    PostUpvote, \
    SearchResultsView


urlpatterns = [
    path('', ForumsList.as_view(), name='forum_list'),
    path('add/', ForumCreate.as_view(), name='forum_add'),
    path('<int:pk>/', ForumDetail.as_view(), name='forum_detail'),
    path('<int:pk>/update', ForumUpdate.as_view(), name='forum_update'),
    path('thread/<int:pk>', ThreadDetail.as_view(), name='thread_detail'),
    path('thread/<int:pk>/notify', ThreadNotification.as_view(), name='thread_notification'),
    path('<int:pk>/add/', ThreadCreate.as_view(), name='thread_add'),
    path('<int:fpk>/delete/<int:pk>', ThreadDelete.as_view(), name='thread_delete'),
    path('thread/<int:pk>/post', PostCreate.as_view(), name='post_add'),
    path('thread/<int:tpk>/post/<int:pk>/delete', PostDelete.as_view(), name='post_delete'),
    path('thread/<int:tpk>/post/<int:pk>/upvote', PostUpvote.as_view(), name='post_upvote'),
    path('search/', SearchResultsView.as_view(), name='search_results'),
]

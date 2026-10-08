from django.urls import path
from django.views.generic import RedirectView

from .views import (
    ForumDetail,
    ForumCreate,
    ForumUpdate,
    ThreadDetail,
    ThreadCreate,
    ThreadDelete,
    ThreadUpdate,
    ThreadSubscription,
    PostCreate,
    PostUpdate,
    PostDelete,
    PostUpvote,
    MarkdownPreview,
)


urlpatterns = [
    # The forum list is the home page now; old links still lead there
    path('', RedirectView.as_view(pattern_name='home')),
    path('add/', ForumCreate.as_view(), name='forum_add'),
    path('<int:pk>/', ForumDetail.as_view(), name='forum_detail'),
    path('<int:pk>/update/', ForumUpdate.as_view(), name='forum_update'),
    path('thread/<int:pk>', ThreadDetail.as_view(), name='thread_detail'),
    path('thread/<int:pk>/update/', ThreadUpdate.as_view(), name='thread_update'),
    path(
        'thread/<int:pk>/notify',
        ThreadSubscription.as_view(),
        name='thread_subscription',
    ),
    path('<int:pk>/add/', ThreadCreate.as_view(), name='thread_add'),
    path('<int:fpk>/delete/<int:pk>', ThreadDelete.as_view(), name='thread_delete'),
    path('thread/<int:pk>/post', PostCreate.as_view(), name='post_add'),
    path(
        'thread/<int:tpk>/post/<int:pk>/update/',
        PostUpdate.as_view(),
        name='post_update',
    ),
    path(
        'thread/<int:tpk>/post/<int:pk>/delete',
        PostDelete.as_view(),
        name='post_delete',
    ),
    path(
        'thread/<int:tpk>/post/<int:pk>/upvote',
        PostUpvote.as_view(),
        name='post_upvote',
    ),
    # The search page moved to /search/; old links keep their words and filters
    path('search/', RedirectView.as_view(pattern_name='search_results', query_string=True)),
    path('preview/', MarkdownPreview.as_view(), name='markdown_preview'),
]

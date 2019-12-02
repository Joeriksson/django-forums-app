from django.urls import path, include

from .views import ForumList, ForumDetail, ThreadList, ThreadDetail, PostList, PostDetail

urlpatterns = [
    path('', ForumList.as_view(), name='forums'),
    path('<int:pk>', ForumDetail.as_view(), name='forum_detail'),
    path('threads/', ThreadList.as_view(), name='threads'),
    path('threads/<int:pk>', ThreadDetail.as_view(), name='thread_detail'),
    path('posts/', PostList.as_view(), name='posts'),
    path('posts/<int:pk>', PostDetail.as_view(), name='post_detail'),
    path('api-auth', include('rest_framework.urls')),
]

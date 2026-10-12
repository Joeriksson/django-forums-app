from django.urls import path

from .views import ConversationDetail, ConversationList, MemberList

urlpatterns = [
    path('', ConversationList.as_view(), name='conversations'),
    path('new/', MemberList.as_view(), name='conversation_new'),
    # The number is the other member's, not the conversation's
    path('<int:pk>/', ConversationDetail.as_view(), name='conversation'),
]

from django.urls import path

from .views import BlockMember, ConversationDetail, ConversationList, MemberList, UnblockMember

urlpatterns = [
    path('', ConversationList.as_view(), name='conversations'),
    path('new/', MemberList.as_view(), name='conversation_new'),
    # The number is the other member's, not the conversation's
    path('<int:pk>/', ConversationDetail.as_view(), name='conversation'),
    path('<int:pk>/block/', BlockMember.as_view(), name='conversation_block'),
    path('<int:pk>/unblock/', UnblockMember.as_view(), name='conversation_unblock'),
]

from django.urls import path

from .views import (
    BlockMember,
    ConversationDetail,
    ConversationList,
    MemberList,
    ReportHandled,
    ReportList,
    ReportMessage,
    UnblockMember,
)

urlpatterns = [
    path('', ConversationList.as_view(), name='conversations'),
    path('new/', MemberList.as_view(), name='conversation_new'),
    # For the moderators: the messages that members have reported
    path('reports/', ReportList.as_view(), name='reports'),
    path('reports/<int:pk>/handled/', ReportHandled.as_view(), name='report_handled'),
    # The number is the other member's, not the conversation's
    path('<int:pk>/', ConversationDetail.as_view(), name='conversation'),
    path('<int:pk>/block/', BlockMember.as_view(), name='conversation_block'),
    path('<int:pk>/unblock/', UnblockMember.as_view(), name='conversation_unblock'),
    path('<int:pk>/report/<int:message_pk>/', ReportMessage.as_view(), name='message_report'),
]

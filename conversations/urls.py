from django.urls import path

from .views import ConversationDetail

urlpatterns = [
    # The number is the other member's, not the conversation's
    path('<int:pk>/', ConversationDetail.as_view(), name='conversation'),
]

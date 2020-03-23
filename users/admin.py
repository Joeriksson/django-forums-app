from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from forums.models import UserProfile

CustomUser = get_user_model()

class UserProfileInline(admin.StackedInline):
    model = UserProfile

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'is_staff', 'is_active','date_joined']
    # list_filter = ('date_joined',)

    list_filter = (
        ('is_staff', admin.BooleanFieldListFilter),
        ('is_superuser', admin.BooleanFieldListFilter),
        ('is_active', admin.BooleanFieldListFilter),
        ('date_joined', admin.DateFieldListFilter),
    )



admin.site.register(CustomUser, CustomUserAdmin)

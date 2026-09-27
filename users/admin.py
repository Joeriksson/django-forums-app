from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from forums.models import UserProfile

CustomUser = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    # The post_save signal creates the profile, so the admin mustn't delete it.
    can_delete = False


class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'is_staff', 'is_active', 'date_joined']
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )
    # list_filter = ('date_joined',)

    list_filter = (
        ('is_staff', admin.BooleanFieldListFilter),
        ('is_superuser', admin.BooleanFieldListFilter),
        ('is_active', admin.BooleanFieldListFilter),
        ('date_joined', admin.DateFieldListFilter),
    )

    def get_inline_instances(self, request, obj=None):
        # No profile inline on "add": the signal creates the profile when the
        # user is saved, and a second one from the inline would clash with it.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)


admin.site.register(CustomUser, CustomUserAdmin)

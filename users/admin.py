from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.sites.models import Site
from django.urls import reverse

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import Invitation
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


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ['email', 'status', 'invited_by', 'created', 'accepted_by']
    list_select_related = ['invited_by', 'accepted_by']
    search_fields = ['email']
    fields = ['email', 'link', 'invited_by', 'created', 'accepted_at', 'accepted_by']

    def get_fields(self, request, obj=None):
        # Adding asks only for the address; the rest is filled in
        return ['email'] if obj is None else self.fields

    def get_readonly_fields(self, request, obj=None):
        # The link belongs to the address it was made for
        return [] if obj is None else self.fields

    def save_model(self, request, obj, form, change):
        if not change:
            obj.invited_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='Status')
    def status(self, obj):
        if obj.accepted_at:
            return 'Used'
        return 'Pending' if obj.is_valid() else 'Expired'

    @admin.display(description='Invitation link')
    def link(self, obj):
        # Same domain as the links in notification emails (Sites)
        path = reverse('accept_invitation', args=[obj.key])
        return f'https://{Site.objects.get_current().domain}{path}'

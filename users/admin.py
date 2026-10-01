from functools import partial

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.db import transaction

from .forms import CustomUserCreationForm, CustomUserChangeForm, InvitationAdminForm
from .models import Invitation
from .tasks import send_invitation_email_task
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
    form = InvitationAdminForm
    list_display = ['email', 'status', 'sent_at', 'invited_by', 'created', 'accepted_by']
    list_select_related = ['invited_by', 'accepted_by']
    search_fields = ['email']
    fields = ['email', 'link', 'invited_by', 'created', 'sent_at', 'accepted_at', 'accepted_by']
    actions = ['resend_invitations']

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
        if not change:
            self.send_email(obj)

    def send_email(self, invitation):
        # Only once the save has committed, so a rollback sends nothing
        transaction.on_commit(partial(send_invitation_email_task.delay, invitation.pk))

    @admin.action(
        description='Resend invitation (new link, old one stops working)', permissions=['add']
    )
    def resend_invitations(self, request, queryset):
        sent = skipped = 0
        for invitation in queryset:
            registered = CustomUser.objects.filter(email__iexact=invitation.email).exists()
            if invitation.accepted_at or registered:
                skipped += 1
                continue
            invitation.renew()
            self.send_email(invitation)
            sent += 1
        if sent:
            self.message_user(request, f'Sent {sent} new invitation link(s).', messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f'Skipped {skipped}: already used, or the address has an account.',
                messages.WARNING,
            )

    @admin.display(description='Status')
    def status(self, obj):
        if obj.accepted_at:
            return 'Used'
        return 'Pending' if obj.is_valid() else 'Expired'

    @admin.display(description='Invitation link')
    def link(self, obj):
        return obj.get_link()

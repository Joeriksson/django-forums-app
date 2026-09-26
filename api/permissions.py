from rest_framework import permissions


class IsOwnerOrModeratorOrReadOnly(permissions.BasePermission):
    """
    Object-level permission: anyone can read, the object's `user` can edit
    and delete it, and so can users with the matching model permission
    (e.g. forums.delete_post), like the moderation checks in the web views.
    """

    actions = {'PUT': 'change', 'PATCH': 'change', 'DELETE': 'delete'}

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Instance must have an attribute named `user`.
        if obj.user == request.user:
            return True

        action = self.actions.get(request.method)
        opts = obj._meta
        return action is not None and request.user.has_perm(
            f'{opts.app_label}.{action}_{opts.model_name}'
        )

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile

ADMIN_GROUP_NAME = "admin"


def sync_user_admin_group(user) -> None:
    """Añade o quita el grupo `admin` según superusuario o rol ADMIN en perfil."""
    group, _ = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
    try:
        profile = user.profile
        is_admin = user.is_superuser or profile.role == UserProfile.Role.ADMIN
    except UserProfile.DoesNotExist:
        is_admin = user.is_superuser
    if is_admin:
        user.groups.add(group)
    else:
        user.groups.remove(group)


@receiver(post_save, sender=UserProfile)
def user_profile_admin_group(sender, instance: UserProfile, **kwargs):
    sync_user_admin_group(instance.user)


@receiver(post_save, sender=get_user_model())
def user_superuser_admin_group(sender, instance, **kwargs):
    sync_user_admin_group(instance)

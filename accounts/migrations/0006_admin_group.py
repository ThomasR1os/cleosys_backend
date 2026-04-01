# Grupo auth "admin" y asignación a superusuarios y perfiles con rol ADMIN

from django.db import migrations


def create_admin_group_and_assign(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")

    group, _ = Group.objects.get_or_create(name="admin")
    for user in User.objects.filter(is_superuser=True):
        user.groups.add(group)
    for profile in UserProfile.objects.filter(role="ADMIN"):
        u = User.objects.get(pk=profile.user_id)
        u.groups.add(group)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_userprofile_role"),
    ]

    operations = [
        migrations.RunPython(create_admin_group_and_assign, noop_reverse),
    ]

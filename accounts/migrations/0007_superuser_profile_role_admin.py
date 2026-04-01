# Superusuarios: rol ADMIN y perfil con compañía por defecto si falta

from django.db import migrations


def assign_admin_role_to_superusers(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")
    Company = apps.get_model("accounts", "Company")

    company = Company.objects.order_by("id").first()
    if company is None:
        return

    for user in User.objects.filter(is_superuser=True):
        profile = UserProfile.objects.filter(user_id=user.pk).first()
        if profile:
            if profile.role != "ADMIN":
                UserProfile.objects.filter(pk=profile.pk).update(role="ADMIN")
        else:
            UserProfile.objects.create(
                user_id=user.pk,
                company_id=company.pk,
                role="ADMIN",
                quotation_prefix="",
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_admin_group"),
    ]

    operations = [
        migrations.RunPython(assign_admin_role_to_superusers, noop_reverse),
    ]

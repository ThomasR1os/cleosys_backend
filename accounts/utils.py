"""Utilidades de cuentas compartidas entre views y serializers."""

from django.http import Http404

from .models import Company, UserProfile


def get_or_create_profile_for_user(user):
    """Perfil del usuario (crea uno mínimo si no existe)."""
    profile = UserProfile.objects.filter(user=user).select_related("company").first()
    if profile is not None:
        return profile
    company = Company.objects.order_by("id").first()
    if company is None:
        raise Http404("No hay compañía configurada; cree una en /api/companies/ antes del perfil.")
    role = UserProfile.Role.ADMIN if user.is_superuser else UserProfile.Role.VENTAS
    return UserProfile.objects.create(user=user, company=company, role=role)

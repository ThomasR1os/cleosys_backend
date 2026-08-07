"""
Roles: ALMACEN, VENTAS, LOGISTICA, ADMIN (perfil).
Superusuarios Django se tratan como acceso total (equivalente a ADMIN).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import permissions

from accounts.models import UserProfile

User = get_user_model()


def user_profile(user) -> UserProfile | None:
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "profile", None) or UserProfile.objects.filter(user=user).first()


def company_id_for_user(user) -> int | None:
    """Empresa del perfil del usuario; None si no hay perfil."""
    p = user_profile(user)
    return p.company_id if p else None


def user_in_company(user_id: int, company_id: int) -> bool:
    """True si el usuario tiene perfil en la empresa indicada."""
    return UserProfile.objects.filter(user_id=user_id, company_id=company_id).exists()


def is_admin_access(user) -> bool:
    """Admin de app o superusuario: ve y modifica todo."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    p = user_profile(user)
    return p is not None and p.role == UserProfile.Role.ADMIN


def resolve_contact_owner_user(request, requested_user=None):
    """
    Vendedor del contacto al crear o reasignar.
    - Sin `requested_user`: quien crea la operación.
    - Admin: cualquier usuario indicado.
    - Ventas (u otro no admin): puede derivar a otro usuario de la misma empresa
      (misma regla que assignable-users en solicitudes de proforma).
    """
    actor = request.user
    if requested_user is None:
        return actor
    target_id = requested_user.pk if hasattr(requested_user, "pk") else int(requested_user)
    if is_admin_access(actor):
        if hasattr(requested_user, "pk"):
            return requested_user
        return User.objects.get(pk=target_id)
    company_id = company_id_for_user(actor)
    if (
        company_id is not None
        and target_id != actor.pk
        and user_in_company(target_id, company_id)
    ):
        if hasattr(requested_user, "pk"):
            return requested_user
        return User.objects.get(pk=target_id)
    return actor


def can_edit_sensitive_profile_fields(user) -> bool:
    """
    company_id y role del perfil solo editables por staff Django, superusuario
    o perfil con rol ADMIN (misma noción que gestión admin en la app).
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return is_admin_access(user)


class AdminAccessPermission(permissions.BasePermission):
    """Solo superusuarios o perfiles con rol ADMIN (gestión de usuarios/perfiles)."""

    message = "Solo administradores pueden acceder a este recurso."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin_access(request.user))


class AdminUserOrSelfPermission(permissions.BasePermission):
    """
    Lista y alta: solo administradores.
    Detalle / PATCH / PUT: el propio usuario (datos básicos) o administrador.
    DELETE: solo administrador. set-password: propio usuario o administrador.
    """

    message = "No tiene permiso para acceder a este usuario."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        action = getattr(view, "action", None)
        if action in ("list", "create"):
            return is_admin_access(request.user)
        return True

    def has_object_permission(self, request, view, obj):
        if is_admin_access(request.user):
            return True
        if request.user.pk != obj.pk:
            return False
        action = getattr(view, "action", None)
        if action == "destroy":
            return False
        if action in ("retrieve", "update", "partial_update", "set_password"):
            return True
        return False


class AlmacenWritePermission(permissions.BasePermission):
    """
    GET/HEAD/OPTIONS: cualquier usuario autenticado.
    POST/PUT/PATCH/DELETE: solo ALMACEN, ADMIN o superusuario.
    """

    message = "Solo personal de almacén o administradores pueden modificar este recurso."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_superuser:
            return True
        p = user_profile(request.user)
        if not p:
            return False
        return p.role in (UserProfile.Role.ALMACEN, UserProfile.Role.ADMIN)


class ProductWritePermission(permissions.BasePermission):
    """
    GET/HEAD/OPTIONS: cualquier usuario autenticado.
    POST/PUT/PATCH/DELETE: ALMACEN, LOGISTICA, ADMIN o superusuario.
    """

    message = "Solo almacén, logística o administradores pueden modificar productos."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_superuser:
            return True
        p = user_profile(request.user)
        if not p:
            return False
        return p.role in (
            UserProfile.Role.ALMACEN,
            UserProfile.Role.LOGISTICA,
            UserProfile.Role.ADMIN,
        )


class LogisticaWritePermission(permissions.BasePermission):
    """
    Lectura: autenticados. Escritura: LOGISTICA, ADMIN o superusuario.
    """

    message = "Solo logística o administradores pueden modificar este recurso."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_superuser:
            return True
        p = user_profile(request.user)
        if not p:
            return False
        return p.role in (UserProfile.Role.LOGISTICA, UserProfile.Role.ADMIN)

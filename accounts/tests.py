from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.branding_defaults import DEFAULT_BRANDING_COLORS
from accounts.models import Company, CompanyBranding, UserProfile

User = get_user_model()


class CompanyBrandingModelTests(TestCase):
    def test_one_to_one_company_branding(self) -> None:
        company = Company.objects.create(name="Branding Co")
        with self.assertRaises(CompanyBranding.DoesNotExist):
            getattr(company, "branding")
        branding = CompanyBranding.objects.create(company=company)
        company.refresh_from_db()
        self.assertEqual(company.branding.pk, company.pk)
        self.assertEqual(branding.primary, DEFAULT_BRANDING_COLORS["primary"])


class CompanyBrandingAPITests(APITestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="API Co")
        self.admin = User.objects.create_user(username="admin_brand", password="pass12345")
        UserProfile.objects.create(
            user=self.admin,
            company=self.company,
            role=UserProfile.Role.ADMIN,
        )
        self.user_ventas = User.objects.create_user(username="ventas_brand", password="pass12345")
        UserProfile.objects.create(
            user=self.user_ventas,
            company=self.company,
            role=UserProfile.Role.VENTAS,
        )

    def test_retrieve_company_includes_default_branding_without_row(self) -> None:
        self.client.force_authenticate(self.admin)
        url = f"/api/companies/{self.company.pk}/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("branding", res.data)
        for key, hex_val in DEFAULT_BRANDING_COLORS.items():
            self.assertEqual(res.data["branding"][key], hex_val, msg=key)
        self.assertEqual(res.data["branding"]["extensions"], {})

    def test_patch_branding_creates_row_and_normalizes_hex(self) -> None:
        self.client.force_authenticate(self.admin)
        url = f"/api/companies/{self.company.pk}/branding/"
        self.assertFalse(CompanyBranding.objects.filter(company=self.company).exists())
        res = self.client.patch(url, {"primary": "aabbcc"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(CompanyBranding.objects.filter(company=self.company).exists())
        self.assertEqual(res.data["branding"]["primary"], "#AABBCC")
        branding = CompanyBranding.objects.get(company=self.company)
        self.assertEqual(branding.primary, "#AABBCC")

    def test_patch_branding_rejects_invalid_hex(self) -> None:
        CompanyBranding.objects.create(company=self.company)
        self.client.force_authenticate(self.admin)
        url = f"/api/companies/{self.company.pk}/branding/"
        res = self.client.patch(url, {"primary": "GGGGGG"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_branding_forbidden_for_non_admin(self) -> None:
        self.client.force_authenticate(self.user_ventas)
        url = f"/api/companies/{self.company.pk}/branding/"
        res = self.client.patch(url, {"primary": "#222222"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

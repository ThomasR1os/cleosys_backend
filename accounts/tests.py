from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.branding_defaults import DEFAULT_BRANDING_COLORS
from accounts.email_crypto import decrypt_secret, encrypt_secret
from accounts.models import Company, CompanyBranding, CompanyEmailSettings, UserProfile

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


class CompanyEmailSettingsAPITests(APITestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="Email Co")
        self.other = Company.objects.create(name="Other Co")
        self.admin = User.objects.create_user(username="admin_email", password="pass12345")
        UserProfile.objects.create(
            user=self.admin,
            company=self.company,
            role=UserProfile.Role.ADMIN,
        )
        self.ventas = User.objects.create_user(username="ventas_email", password="pass12345")
        UserProfile.objects.create(
            user=self.ventas,
            company=self.company,
            role=UserProfile.Role.VENTAS,
        )
        self.admin_other = User.objects.create_user(username="admin_other", password="pass12345")
        UserProfile.objects.create(
            user=self.admin_other,
            company=self.other,
            role=UserProfile.Role.ADMIN,
        )

    def test_encrypt_roundtrip(self) -> None:
        token = encrypt_secret("secret-pass")
        self.assertNotEqual(token, "secret-pass")
        self.assertEqual(decrypt_secret(token), "secret-pass")

    def test_admin_can_patch_settings_password_masked(self) -> None:
        self.client.force_authenticate(self.admin)
        url = f"/api/companies/{self.company.pk}/email-settings/"
        res = self.client.patch(
            url,
            {
                "host": "smtp.example.com",
                "port": 587,
                "use_tls": True,
                "username": "noreply@example.com",
                "password": "plain-secret",
                "from_email": "noreply@example.com",
                "from_name": "Cotizaciones",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertTrue(res.data["password_configured"])
        self.assertNotIn("password", res.data)
        self.assertNotIn("password_encrypted", res.data)
        self.assertEqual(res.data["host"], "smtp.example.com")

        settings_obj = CompanyEmailSettings.objects.get(company=self.company)
        self.assertEqual(settings_obj.get_password(), "plain-secret")

        get_res = self.client.get(url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertTrue(get_res.data["password_configured"])
        self.assertNotIn("password", get_res.data)

    def test_ventas_forbidden(self) -> None:
        self.client.force_authenticate(self.ventas)
        url = f"/api/companies/{self.company.pk}/email-settings/"
        res = self.client.patch(url, {"host": "x"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_manage_other_company(self) -> None:
        self.client.force_authenticate(self.admin)
        url = f"/api/companies/{self.other.pk}/email-settings/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_me_exposes_reply_fields(self) -> None:
        self.client.force_authenticate(self.ventas)
        res = self.client.patch(
            "/api/auth/me/",
            {
                "profile": {
                    "reply_to_email": "maria@empresa.com",
                    "email_display_name": "María Ventas",
                }
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["profile"]["reply_to_email"], "maria@empresa.com")
        self.assertEqual(res.data["profile"]["email_display_name"], "María Ventas")


class EmailInlineMimeTests(TestCase):
    def test_related_inline_and_pdf_attachment(self) -> None:
        from accounts.email_inline import InlineImage
        from accounts.email_sending import EmailMultiRelated

        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        msg = EmailMultiRelated(
            subject="Cotización",
            body="Hola",
            from_email="noreply@empresa.com",
            to=["ana@cliente.com"],
        )
        msg.attach_alternative('<img src="cid:logo_empresa" alt="Logo" />', "text/html")
        msg.attach_related_image(
            InlineImage(
                cid="logo_empresa",
                content=png,
                mimetype="image/png",
                filename="logo_empresa.png",
            )
        )
        msg.attach("cotizacion-GER-000293.pdf", b"%PDF-1.4 fake", "application/pdf")
        mime = msg.message()
        self.assertEqual(mime.get_content_type(), "multipart/mixed")
        mixed_children = list(mime.iter_parts())
        related = next(p for p in mixed_children if p.get_content_type() == "multipart/related")
        pdf = next(p for p in mixed_children if p.get_content_type() == "application/pdf")
        self.assertIn("attachment", (pdf.get("Content-Disposition") or "").lower())
        image_part = next(
            p for p in related.iter_parts() if p.get_content_maintype() == "image"
        )
        cid = image_part.get("Content-ID") or ""
        self.assertIn("logo_empresa", cid)
        self.assertIn("inline", (image_part.get("Content-Disposition") or "").lower())
        html_blob = mime.as_string()
        self.assertIn("cid:logo_empresa", html_blob)


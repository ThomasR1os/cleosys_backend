from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from core.models import Client
from ventas.models import ClientContact

User = get_user_model()


class ClientLookupByRucTests(APITestCase):
    """GET /api/clients/lookup-by-ruc/"""

    def setUp(self) -> None:
        self.company_a = Company.objects.get(pk=1)
        self.company_b = Company.objects.get(pk=2)
        self.ruc_digits = "20510886977"
        self.cli = Client.objects.create(ruc=self.ruc_digits, name="JEGR INGENIEROS SAC TEST")

        self.seller_a = User.objects.create_user(username="lk_seller_a", password="pass12345")
        UserProfile.objects.create(
            user=self.seller_a,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="LKA",
        )
        self.seller_b = User.objects.create_user(username="lk_seller_b", password="pass12345")
        UserProfile.objects.create(
            user=self.seller_b,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="LKB",
        )

        ClientContact.objects.create(
            contact_first_name="Ana",
            contact_last_name="Uno",
            email="a@example.com",
            phone="111",
            client=self.cli,
            user=self.seller_a,
            company=self.company_a,
        )
        ClientContact.objects.create(
            contact_first_name="Bob",
            contact_last_name="Dos",
            email="b@example.com",
            phone="222",
            client=self.cli,
            user=self.seller_b,
            company=self.company_a,
        )

    def test_company_scope_success(self) -> None:
        self.client.force_authenticate(self.seller_a)
        res = self.client.get("/api/clients/lookup-by-ruc/", {"ruc": self.ruc_digits})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["exists"])
        self.assertEqual(res.data["client"]["id"], self.cli.pk)
        self.assertEqual(res.data["sales_summary"]["contacts_count"], 2)
        self.assertEqual(len(res.data["contacts"]), 2)
        msg = res.data["sales_summary"]["message_for_ui"]
        self.assertIn("cada uno", msg)
        self.assertIsNone(res.data["sales_summary"]["primary_sales_user"])
        self.assertEqual(len(res.data["sales_summary"]["sales_users"]), 2)
        by_user = {row["encargado"]["id"]: row for row in res.data["contacts"]}
        self.assertEqual(set(by_user.keys()), {self.seller_a.pk, self.seller_b.pk})
        self.assertEqual(by_user[self.seller_a.pk]["nombre"], "Ana Uno")
        self.assertEqual(by_user[self.seller_b.pk]["nombre"], "Bob Dos")
        self.assertFalse(by_user[self.seller_a.pk]["is_primary_advisor"])
        self.assertFalse(by_user[self.seller_b.pk]["is_primary_advisor"])
        self.assertEqual(by_user[self.seller_a.pk]["user"], self.seller_a.pk)
        self.assertEqual(by_user[self.seller_b.pk]["user"], self.seller_b.pk)

    def test_one_advisor_many_contacts_has_primary(self) -> None:
        ClientContact.objects.create(
            contact_first_name="Extra",
            contact_last_name="Contact",
            client=self.cli,
            user=self.seller_a,
            company=self.company_a,
        )
        self.client.force_authenticate(self.seller_a)
        res = self.client.get("/api/clients/lookup-by-ruc/", {"ruc": self.ruc_digits})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(res.data["sales_summary"]["primary_sales_user"])
        self.assertEqual(
            res.data["sales_summary"]["primary_sales_user"]["id"],
            self.seller_a.pk,
        )
        primary_rows = [r for r in res.data["contacts"] if r["is_primary_advisor"]]
        self.assertEqual(len(primary_rows), 2)

    def test_ruc_query_accepts_formatting(self) -> None:
        self.client.force_authenticate(self.seller_a)
        res = self.client.get("/api/clients/lookup-by-ruc/", {"ruc": "20510886977 "})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["exists"])

    def test_unknown_client(self) -> None:
        self.client.force_authenticate(self.seller_a)
        res = self.client.get("/api/clients/lookup-by-ruc/", {"ruc": "20999999999"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["exists"])
        self.assertEqual(res.data["contacts"], [])

    def test_client_only_other_company(self) -> None:
        cli_b_only = Client.objects.create(ruc="20987654321", name="Solo empresa B")
        stranger = User.objects.create_user(username="lk_other_co", password="pass12345")
        UserProfile.objects.create(
            user=stranger,
            company=self.company_b,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="LOB",
        )
        ClientContact.objects.create(
            contact_first_name="Z",
            contact_last_name="Z",
            client=cli_b_only,
            user=stranger,
            company=self.company_b,
        )
        self.client.force_authenticate(self.seller_a)
        res = self.client.get("/api/clients/lookup-by-ruc/", {"ruc": "20987654321"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["exists"])

    def test_scope_mine_requires_own_contact(self) -> None:
        lonely = User.objects.create_user(username="lk_lonely", password="pass12345")
        UserProfile.objects.create(
            user=lonely,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="LOL",
        )
        self.client.force_authenticate(lonely)
        res = self.client.get(
            "/api/clients/lookup-by-ruc/",
            {"ruc": self.ruc_digits, "scope": "mine"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["exists"])

        self.client.force_authenticate(self.seller_a)
        res2 = self.client.get(
            "/api/clients/lookup-by-ruc/",
            {"ruc": self.ruc_digits, "scope": "mine"},
        )
        self.assertTrue(res2.data["exists"])
        self.assertEqual(len(res2.data["contacts"]), 2)

    def test_invalid_ruc_digits(self) -> None:
        self.client.force_authenticate(self.seller_a)
        res = self.client.get("/api/clients/lookup-by-ruc/", {"ruc": "123"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from core.models import Client, PaymentMethods
from ventas.models import ClientContact, Quotation

User = get_user_model()


class QuotationUserDetailSerializerTests(TestCase):
    def test_user_detail_shape(self) -> None:
        from ventas.serializers import QuotationSerializer

        seller = User.objects.create_user(
            username="asesor_q",
            password="x",
            first_name="Luis",
            last_name="Pérez",
        )
        company = Company.objects.create(name="Co Q")
        UserProfile.objects.create(
            user=seller,
            company=company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="QQQ",
        )
        client = Client.objects.create(ruc="201", name="Cli")
        pm = PaymentMethods.objects.create(name="Transferencia")
        q = Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=client,
            user=seller,
            discount=0,
            final_price=50,
            delivery_time=3,
            payment_methods=pm,
            see_sku=False,
        )
        data = QuotationSerializer(q).data
        self.assertEqual(data["user"], seller.pk)
        self.assertEqual(
            data["user_detail"],
            {
                "id": seller.pk,
                "username": "asesor_q",
                "first_name": "Luis",
                "last_name": "Pérez",
                "nombre": "Luis Pérez",
                "email": "",
                "cellphone": "",
            },
        )


class QuotationUserDetailAPITests(APITestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="Ventas Test Co")
        self.client_obj = Client.objects.create(ruc="999", name="Cliente API")
        self.pm = PaymentMethods.objects.create(name="Contado")
        self.seller = User.objects.create_user(
            username="vendedor_api",
            password="pass12345",
            first_name="María",
            last_name="López",
        )
        UserProfile.objects.create(
            user=self.seller,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="API",
        )
        self.admin = User.objects.create_user(username="admin_api", password="pass12345")
        UserProfile.objects.create(
            user=self.admin,
            company=self.company,
            role=UserProfile.Role.ADMIN,
            quotation_prefix="ADM",
        )

    def _create_quotation(self) -> Quotation:
        return Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=self.client_obj,
            user=self.seller,
            discount=0,
            final_price=200,
            delivery_time=5,
            payment_methods=self.pm,
            see_sku=True,
        )

    def test_list_and_detail_include_user_detail(self) -> None:
        q = self._create_quotation()
        self.client.force_authenticate(self.admin)
        list_res = self.client.get("/api/ventas/quotations/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        row = next(r for r in list_res.data if r["id"] == q.pk)
        self.assertEqual(row["user"], self.seller.pk)
        self.assertEqual(
            row["user_detail"]["nombre"],
            "María López",
        )
        self.assertEqual(row["user_detail"]["username"], "vendedor_api")

        detail_res = self.client.get(f"/api/ventas/quotations/{q.pk}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data["user_detail"]["id"], self.seller.pk)
        self.assertEqual(detail_res.data["user_detail"]["first_name"], "María")

    def test_user_detail_includes_email_and_cellphone_in_detail(self) -> None:
        self.seller.email = "maria@example.com"
        self.seller.save(update_fields=["email"])
        prof = self.seller.profile
        prof.cellphone = "999888777"
        prof.save(update_fields=["cellphone"])
        q = self._create_quotation()
        self.client.force_authenticate(self.admin)
        detail_res = self.client.get(f"/api/ventas/quotations/{q.pk}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        ud = detail_res.data["user_detail"]
        self.assertEqual(ud["email"], "maria@example.com")
        self.assertEqual(ud["cellphone"], "999888777")

    def test_ventas_peer_sees_company_quotations_and_owner_fields(self) -> None:
        self.seller.email = "maria@example.com"
        self.seller.save(update_fields=["email"])
        prof = self.seller.profile
        prof.cellphone = "111222333"
        prof.save(update_fields=["cellphone"])
        other = User.objects.create_user(
            username="otro_vendedor",
            password="pass12345",
            first_name="Otro",
            last_name="User",
        )
        UserProfile.objects.create(
            user=other,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="OTR",
        )
        q = self._create_quotation()
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"/api/ventas/quotations/{q.pk}/").status_code, status.HTTP_200_OK)
        detail = self.client.get(f"/api/ventas/quotations/{q.pk}/").data
        self.assertEqual(detail["user"], self.seller.pk)
        self.assertEqual(detail["user_detail"]["nombre"], "María López")
        self.assertEqual(detail["user_detail"]["email"], "maria@example.com")
        self.assertEqual(detail["user_detail"]["cellphone"], "111222333")
        list_res = self.client.get("/api/ventas/quotations/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertIn(q.pk, [r["id"] for r in list_res.data])

    def test_client_contact_detail_name_visible_email_phone_hidden_for_peers(self) -> None:
        contact = ClientContact.objects.create(
            contact_first_name="Ana",
            contact_last_name="Ruiz",
            email="ana@cliente.com",
            phone="555111222",
            client=self.client_obj,
            user=self.seller,
            company=self.company,
        )
        q = self._create_quotation()
        q.client_contact = contact
        q.save(update_fields=["client_contact"])
        peer = User.objects.create_user(
            username="peer_cc",
            password="pass12345",
            first_name="Peer",
            last_name="User",
        )
        UserProfile.objects.create(
            user=peer,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="PEE",
        )
        self.client.force_authenticate(peer)
        detail = self.client.get(f"/api/ventas/quotations/{q.pk}/").data
        d = detail["client_contact_detail"]
        self.assertEqual(d["id"], contact.pk)
        self.assertEqual(d["nombre"], "Ana Ruiz")
        self.assertEqual(d["contact_first_name"], "Ana")
        self.assertIsNone(d["email"])
        self.assertIsNone(d["phone"])

    def test_client_contact_detail_email_phone_for_admin_and_encargado(self) -> None:
        contact = ClientContact.objects.create(
            contact_first_name="Ana",
            contact_last_name="Ruiz",
            email="ana@cliente.com",
            phone="555111222",
            client=self.client_obj,
            user=self.seller,
            company=self.company,
        )
        q = self._create_quotation()
        q.client_contact = contact
        q.save(update_fields=["client_contact"])
        self.client.force_authenticate(self.admin)
        d = self.client.get(f"/api/ventas/quotations/{q.pk}/").data["client_contact_detail"]
        self.assertEqual(d["email"], "ana@cliente.com")
        self.assertEqual(d["phone"], "555111222")

        self.client.force_authenticate(self.seller)
        d2 = self.client.get(f"/api/ventas/quotations/{q.pk}/").data["client_contact_detail"]
        self.assertEqual(d2["email"], "ana@cliente.com")
        self.assertEqual(d2["phone"], "555111222")

    def test_ventas_peer_cannot_patch_others_quotation(self) -> None:
        other = User.objects.create_user(
            username="otro_vendedor2",
            password="pass12345",
            first_name="Otro",
            last_name="Dos",
        )
        UserProfile.objects.create(
            user=other,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="OT2",
        )
        q = self._create_quotation()
        self.client.force_authenticate(other)
        res = self.client.patch(
            f"/api/ventas/quotations/{q.pk}/",
            {"discount": "1.00"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_does_not_n_plus_one_on_user(self) -> None:
        for _ in range(5):
            self._create_quotation()
        self.client.force_authenticate(self.admin)
        qs = Quotation.objects.filter(client=self.client_obj).select_related(
            "client", "user", "user__profile", "payment_methods"
        )
        with CaptureQueriesContext(connection) as ctx:
            from ventas.serializers import QuotationSerializer

            list(QuotationSerializer(qs, many=True).data)
        user_table_hits = sum(1 for q in ctx.captured_queries if "auth_user" in q["sql"].lower())
        self.assertLessEqual(
            user_table_hits,
            1,
            msg="Se esperaba una sola lectura de auth_user al serializar varias cotizaciones con user precargado.",
        )

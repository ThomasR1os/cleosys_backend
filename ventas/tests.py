from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from core.models import Client, PaymentMethods
from ventas.models import Quotation

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

    def test_list_does_not_n_plus_one_on_user(self) -> None:
        for _ in range(5):
            self._create_quotation()
        self.client.force_authenticate(self.admin)
        qs = Quotation.objects.filter(client=self.client_obj).select_related("client", "user", "payment_methods")
        with CaptureQueriesContext(connection) as ctx:
            from ventas.serializers import QuotationSerializer

            list(QuotationSerializer(qs, many=True).data)
        user_table_hits = sum(1 for q in ctx.captured_queries if "auth_user" in q["sql"].lower())
        self.assertLessEqual(
            user_table_hits,
            1,
            msg="Se esperaba una sola lectura de auth_user al serializar varias cotizaciones con user precargado.",
        )

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from almacen.models import Product
from core.models import Client, PaymentMethods
from ventas.models import ClientContact, ProformaRequest, Quotation, QuotationProduct

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
            delivery_time="3 días",
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
            delivery_time="5 días",
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


class ProformaRequestAPITests(APITestCase):
    def setUp(self) -> None:
        # Usar compañías del seed (0002_seed_companies); evita colisión de PK con secuencias en PostgreSQL.
        self.company_a = Company.objects.get(pk=1)
        self.company_b = Company.objects.get(pk=2)
        self.client_a = Client.objects.create(ruc="55511122211", name="Cliente Proforma")
        self.client_b_only = Client.objects.create(ruc="99988877701", name="Cliente solo B")
        self.pm = PaymentMethods.objects.create(name="Efectivo")

        self.creator = User.objects.create_user(username="prof_creator", password="pass12345")
        UserProfile.objects.create(
            user=self.creator,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="PFC",
        )
        self.advisor = User.objects.create_user(username="prof_advisor", password="pass12345")
        UserProfile.objects.create(
            user=self.advisor,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="PFA",
        )
        self.admin_a = User.objects.create_user(username="prof_admin_a", password="pass12345")
        UserProfile.objects.create(
            user=self.admin_a,
            company=self.company_a,
            role=UserProfile.Role.ADMIN,
            quotation_prefix="PAM",
        )
        self.peer_a = User.objects.create_user(username="prof_peer_a", password="pass12345")
        UserProfile.objects.create(
            user=self.peer_a,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="PPA",
        )
        self.user_b = User.objects.create_user(username="prof_user_b", password="pass12345")
        UserProfile.objects.create(
            user=self.user_b,
            company=self.company_b,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="PFB",
        )

        ClientContact.objects.create(
            contact_first_name="Lead",
            contact_last_name="Uno",
            client=self.client_a,
            user=self.creator,
            company=self.company_a,
        )
        ClientContact.objects.create(
            contact_first_name="Lead",
            contact_last_name="B",
            client=self.client_b_only,
            user=self.user_b,
            company=self.company_b,
        )

    def _payload(self, **kwargs):
        base = {
            "client": self.client_a.pk,
            "assigned_user": self.advisor.pk,
            "entry_channel": ProformaRequest.EntryChannel.WHATSAPP,
            "proforma_type": ProformaRequest.ProformaType.MAQUINARIA,
            "description": "Requiere cotización excavadora",
        }
        base.update(kwargs)
        return base

    def test_create_success(self) -> None:
        self.client.force_authenticate(self.creator)
        res = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["company"], self.company_a.pk)
        self.assertEqual(res.data["assigned_user"], self.advisor.pk)
        self.assertIsNone(res.data["quotation"])
        self.assertIsNone(res.data["quotation_correlativo"])
        self.assertIsNotNone(res.data["entered_at"])
        self.assertIsNone(res.data["quoted_at"])
        self.assertEqual(res.data["status"], ProformaRequest.Status.PENDIENTE)

    def test_patch_status_by_assigned_advisor(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        pr_id = cre.data["id"]
        self.client.force_authenticate(self.advisor)
        res = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"status": ProformaRequest.Status.APROBADA},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], ProformaRequest.Status.APROBADA)

    def test_create_rejects_client_without_company_contact(self) -> None:
        orphan = Client.objects.create(ruc="00000000000", name="Sin contacto empresa")
        self.client.force_authenticate(self.creator)
        res = self.client.post(
            "/api/ventas/proforma-requests/",
            self._payload(client=orphan.pk),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("client", res.data)

    def test_create_rejects_assigned_user_other_company(self) -> None:
        self.client.force_authenticate(self.creator)
        res = self.client.post(
            "/api/ventas/proforma-requests/",
            self._payload(assigned_user=self.user_b.pk),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assigned_user", res.data)

    def test_list_scoped_other_company_empty(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        self.assertEqual(cre.status_code, status.HTTP_201_CREATED)
        pr_id = cre.data["id"]

        self.client.force_authenticate(self.user_b)
        res = self.client.get("/api/ventas/proforma-requests/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, [])

        detail = self.client.get(f"/api/ventas/proforma-requests/{pr_id}/")
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_peer_in_same_company_can_list_but_not_patch(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        pr_id = cre.data["id"]

        self.client.force_authenticate(self.peer_a)
        res = self.client.get("/api/ventas/proforma-requests/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(pr_id, [row["id"] for row in res.data])

        patch_res = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"description": "Cambio prohibido"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_assignable_users_same_company(self) -> None:
        self.client.force_authenticate(self.peer_a)
        res = self.client.get("/api/ventas/proforma-requests/assignable-users/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in res.data}
        self.assertGreaterEqual(ids, {self.creator.pk, self.advisor.pk, self.peer_a.pk})

    def test_patch_link_quotation_by_advisor(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        pr_id = cre.data["id"]

        q = Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=self.client_a,
            user=self.advisor,
            discount=0,
            final_price=100,
            delivery_time="1 día",
            payment_methods=self.pm,
            see_sku=False,
        )

        self.client.force_authenticate(self.advisor)
        patch_res = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"quotation": q.pk},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["quotation"], q.pk)
        self.assertEqual(patch_res.data["quotation_correlativo"], q.correlativo)
        self.assertIsNotNone(patch_res.data["quoted_at"])

    def test_patch_unlink_quotation_clears_quoted_at(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        pr_id = cre.data["id"]

        q = Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=self.client_a,
            user=self.advisor,
            discount=0,
            final_price=100,
            delivery_time="1 día",
            payment_methods=self.pm,
            see_sku=False,
        )

        self.client.force_authenticate(self.advisor)
        link = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"quotation": q.pk},
            format="json",
        )
        self.assertEqual(link.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(link.data["quoted_at"])

        unlink = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"quotation": None},
            format="json",
        )
        self.assertEqual(unlink.status_code, status.HTTP_200_OK)
        self.assertIsNone(unlink.data["quotation"])
        self.assertIsNone(unlink.data["quoted_at"])

    def test_patch_quotation_rejects_mismatched_client(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        pr_id = cre.data["id"]

        other_client = Client.objects.create(ruc="77777777701", name="Otro cliente")
        ClientContact.objects.create(
            contact_first_name="x",
            contact_last_name="y",
            client=other_client,
            user=self.advisor,
            company=self.company_a,
        )
        q = Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=other_client,
            user=self.advisor,
            discount=0,
            final_price=10,
            delivery_time="1 día",
            payment_methods=self.pm,
            see_sku=False,
        )

        self.client.force_authenticate(self.advisor)
        patch_res = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"quotation": q.pk},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quotation", patch_res.data)

    def test_admin_can_patch_without_being_assignee(self) -> None:
        self.client.force_authenticate(self.creator)
        cre = self.client.post("/api/ventas/proforma-requests/", self._payload(), format="json")
        pr_id = cre.data["id"]

        self.client.force_authenticate(self.admin_a)
        patch_res = self.client.patch(
            f"/api/ventas/proforma-requests/{pr_id}/",
            {"description": "Nota administrador"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["description"], "Nota administrador")

    def test_creator_can_assign_proforma_to_peer_advisor(self) -> None:
        self.client.force_authenticate(self.creator)
        res = self.client.post(
            "/api/ventas/proforma-requests/",
            self._payload(assigned_user=self.advisor.pk),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["assigned_user"], self.advisor.pk)
        self.assertEqual(res.data["assigned_user_detail"]["id"], self.advisor.pk)


class ClientContactDuplicateInsensitiveTests(APITestCase):
    """Nombre/apellido y email duplicados no deben pasar por diferencias solo de mayúsculas."""

    def setUp(self) -> None:
        self.company = Company.objects.get(pk=1)
        self.client_obj = Client.objects.create(ruc="88877766655", name="Cliente Dup Test")
        self.user = User.objects.create_user(username="cc_dup_user", password="pass12345")
        UserProfile.objects.create(
            user=self.user,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="CCD",
        )
        self.peer = User.objects.create_user(username="cc_peer_adv", password="pass12345")
        UserProfile.objects.create(
            user=self.peer,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="CCP",
        )

    def test_ventas_can_create_contact_for_peer_in_same_company(self) -> None:
        self.client.force_authenticate(self.user)
        res = self.client.post(
            "/api/ventas/client-contacts/",
            {
                "contact_first_name": "Lead",
                "contact_last_name": "Peer",
                "email": "",
                "phone": "",
                "client": self.client_obj.pk,
                "user": self.peer.pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"], self.peer.pk)

    def test_rejects_same_name_different_case(self) -> None:
        self.client.force_authenticate(self.user)
        base = {
            "contact_first_name": "Oscar",
            "contact_last_name": "Jara",
            "email": "",
            "phone": "",
            "client": self.client_obj.pk,
        }
        first = self.client.post("/api/ventas/client-contacts/", base, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        dup = self.client.post(
            "/api/ventas/client-contacts/",
            {**base, "contact_first_name": "oscar", "contact_last_name": "jara"},
            format="json",
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_same_email_different_case(self) -> None:
        self.client.force_authenticate(self.user)
        base = {
            "contact_first_name": "Ana",
            "contact_last_name": "Pérez",
            "email": "Logistica@Servimine.pe",
            "phone": "",
            "client": self.client_obj.pk,
        }
        first = self.client.post("/api/ventas/client-contacts/", base, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        dup = self.client.post(
            "/api/ventas/client-contacts/",
            {
                **base,
                "contact_first_name": "Ana",
                "contact_last_name": "Gomez",
                "email": "logistica@servimine.pe",
            },
            format="json",
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)


class QuotationProductDeliveryTimeTests(APITestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="Delivery Time Co")
        self.client_obj = Client.objects.create(ruc="20100000001", name="Cliente DT")
        self.pm = PaymentMethods.objects.create(name="Transferencia DT")
        self.seller = User.objects.create_user(username="seller_dt", password="pass12345")
        UserProfile.objects.create(
            user=self.seller,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="DTT",
        )
        self.product_a = Product.objects.create(
            type_id=1,
            subcategory_id=1,
            brand_id=1,
            sku="SKU-DT-A",
            description="Producto A",
            price=100,
            warranty="6 meses",
            unit_measurement_id=1,
            status=Product.ProductStatus.ACTIVE,
        )
        self.product_b = Product.objects.create(
            type_id=1,
            subcategory_id=1,
            brand_id=1,
            sku="SKU-DT-B",
            description="Producto B",
            price=200,
            unit_measurement_id=1,
            status=Product.ProductStatus.ACTIVE,
        )

    def _create_quotation(self, quotation_type: str, delivery_time: str = "10 días") -> Quotation:
        return Quotation.objects.create(
            quotation_type=quotation_type,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=self.client_obj,
            user=self.seller,
            discount=0,
            final_price=300,
            delivery_time=delivery_time,
            payment_methods=self.pm,
            see_sku=True,
        )

    def test_venta_lines_expose_distinct_delivery_time(self) -> None:
        q = self._create_quotation(Quotation.QuotationType.VENTA, delivery_time="10 días")
        self.client.force_authenticate(self.seller)

        res_a = self.client.post(
            "/api/ventas/quotation-products/",
            {
                "quotation": q.pk,
                "product": self.product_a.pk,
                "cant": 1,
                "product_price": "100.00",
                "delivery_time": "5 días",
            },
            format="json",
        )
        self.assertEqual(res_a.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_a.data["delivery_time"], "5 días")
        self.assertEqual(res_a.data["line_warranty"], "6 meses")

        res_b = self.client.post(
            "/api/ventas/quotation-products/",
            {
                "quotation": q.pk,
                "product": self.product_b.pk,
                "cant": 1,
                "product_price": "200.00",
                "delivery_time": "15 días hábiles",
            },
            format="json",
        )
        self.assertEqual(res_b.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_b.data["delivery_time"], "15 días hábiles")

        list_res = self.client.get(f"/api/ventas/quotation-products/?quotation={q.pk}")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        by_product = {row["product"]: row["delivery_time"] for row in list_res.data}
        self.assertEqual(by_product[self.product_a.pk], "5 días")
        self.assertEqual(by_product[self.product_b.pk], "15 días hábiles")

    def test_venta_line_requires_delivery_time(self) -> None:
        q = self._create_quotation(Quotation.QuotationType.VENTA)
        self.client.force_authenticate(self.seller)
        res = self.client.post(
            "/api/ventas/quotation-products/",
            {
                "quotation": q.pk,
                "product": self.product_a.pk,
                "cant": 1,
                "product_price": "100.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_time", res.data)

    def test_servicio_line_allows_missing_delivery_time(self) -> None:
        q = self._create_quotation(Quotation.QuotationType.SERVICIO, delivery_time="30 días")
        self.client.force_authenticate(self.seller)
        res = self.client.post(
            "/api/ventas/quotation-products/",
            {
                "quotation": q.pk,
                "product": self.product_a.pk,
                "cant": 1,
                "product_price": "100.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["delivery_time"], "30 días")

        detail_res = self.client.get(f"/api/ventas/quotations/{q.pk}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data["delivery_time"], "30 días")

    def test_line_warranty_can_be_updated(self) -> None:
        q = self._create_quotation(Quotation.QuotationType.VENTA)
        self.client.force_authenticate(self.seller)
        create_res = self.client.post(
            "/api/ventas/quotation-products/",
            {
                "quotation": q.pk,
                "product": self.product_a.pk,
                "cant": 1,
                "product_price": "100.00",
                "delivery_time": "Inmediato",
                "line_warranty": "18 meses",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_res.data["line_warranty"], "18 meses")

        patch_res = self.client.patch(
            f"/api/ventas/quotation-products/{create_res.data['id']}/",
            {"line_warranty": "24 meses"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["line_warranty"], "24 meses")


class QuotationProductDeliveryTimeModelTests(TestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="Delivery Model Co")
        self.client_obj = Client.objects.create(ruc="20100000002", name="Cliente Model")
        self.pm = PaymentMethods.objects.create(name="Contado Model")
        self.seller = User.objects.create_user(username="seller_model", password="pass12345")
        UserProfile.objects.create(
            user=self.seller,
            company=self.company,
            role=UserProfile.Role.VENTAS,
            quotation_prefix="MDL",
        )
        self.product = Product.objects.create(
            type_id=1,
            subcategory_id=1,
            brand_id=1,
            sku="SKU-MODEL",
            description="Producto model",
            price=50,
            unit_measurement_id=1,
            status=Product.ProductStatus.ACTIVE,
        )

    def test_save_defaults_delivery_time_from_quotation(self) -> None:
        q = Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=self.client_obj,
            user=self.seller,
            discount=0,
            final_price=50,
            delivery_time="7 días",
            payment_methods=self.pm,
            see_sku=False,
        )
        line = QuotationProduct.objects.create(
            quotation=q,
            product=self.product,
            cant=1,
            product_price=50,
        )
        self.assertEqual(line.delivery_time, "7 días")

    def test_save_defaults_line_warranty_from_product(self) -> None:
        self.product.warranty = "12 meses"
        self.product.save(update_fields=["warranty"])
        q = Quotation.objects.create(
            quotation_type=Quotation.QuotationType.VENTA,
            money=Quotation.QuotationMoney.PEN,
            status=Quotation.QuotationStatus.PENDIENTE,
            client=self.client_obj,
            user=self.seller,
            discount=0,
            final_price=50,
            delivery_time="7 días",
            payment_methods=self.pm,
            see_sku=False,
        )
        line = QuotationProduct.objects.create(
            quotation=q,
            product=self.product,
            cant=1,
            product_price=50,
        )
        self.assertEqual(line.line_warranty, "12 meses")

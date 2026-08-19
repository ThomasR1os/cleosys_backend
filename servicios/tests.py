from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from core.models import Brand, Client
from ventas.models import ClientContact

from .models import Machine

User = get_user_model()


class MachineAPITests(APITestCase):
    def setUp(self) -> None:
        self.company_a = Company.objects.create(name="Servicios Co A")
        self.company_b = Company.objects.create(name="Servicios Co B")
        self.client_a = Client.objects.create(ruc="20100000001", name="Cliente A")
        self.client_b = Client.objects.create(ruc="20100000002", name="Cliente B")
        # Catálogo sembrado por core.0002_seed_catalog (mismo patrón que almacen.tests)
        self.brand = Brand.objects.get(pk=1)

        self.user_servicios = User.objects.create_user(
            username="servicios_a",
            password="pass12345",
            first_name="Tec",
            last_name="Uno",
        )
        UserProfile.objects.create(
            user=self.user_servicios,
            company=self.company_a,
            role=UserProfile.Role.SERVICIOS,
        )

        self.user_other = User.objects.create_user(
            username="servicios_b",
            password="pass12345",
        )
        UserProfile.objects.create(
            user=self.user_other,
            company=self.company_b,
            role=UserProfile.Role.SERVICIOS,
        )

        self.user_ventas = User.objects.create_user(
            username="ventas_a",
            password="pass12345",
        )
        UserProfile.objects.create(
            user=self.user_ventas,
            company=self.company_a,
            role=UserProfile.Role.VENTAS,
        )

        ClientContact.objects.create(
            contact_first_name="Ana",
            contact_last_name="Contacto",
            email="ana@a.com",
            client=self.client_a,
            user=self.user_servicios,
            company=self.company_a,
        )
        ClientContact.objects.create(
            contact_first_name="Bob",
            contact_last_name="Contacto",
            email="bob@b.com",
            client=self.client_b,
            user=self.user_other,
            company=self.company_b,
        )

        self.url = "/api/servicios/machines/"

    def _payload(self, **overrides):
        data = {
            "client": self.client_a.pk,
            "brand": self.brand.pk,
            "model": "SRPQ-20",
            "serial_number": "SN-001",
            "plate_image_url": "https://cdn.example.com/plate.jpg",
            "daily_working_hours": 8,
            "current_hour_meter": 1200,
            "location": "Planta 1",
            "status": Machine.Status.ACTIVE,
        }
        data.update(overrides)
        return data

    def test_servicios_user_creates_and_lists_own_company_only(self) -> None:
        self.client.force_authenticate(self.user_servicios)
        create_resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        self.assertEqual(create_resp.data["company"], self.company_a.pk)
        self.assertEqual(create_resp.data["brand_name"], self.brand.name)
        self.assertEqual(create_resp.data["client_name"], "Cliente A")

        Machine.objects.create(
            company=self.company_b,
            client=self.client_b,
            brand=self.brand,
            model="Other",
            serial_number="SN-OTHER",
            daily_working_hours=4,
            location="Planta B",
        )

        list_resp = self.client.get(self.url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in list_resp.data]
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0], create_resp.data["id"])

    def test_other_company_cannot_see_or_edit(self) -> None:
        machine = Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-LOCK",
            daily_working_hours=8,
            location="Planta 1",
        )
        detail = f"{self.url}{machine.pk}/"

        self.client.force_authenticate(self.user_other)
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
        patch_resp = self.client.patch(detail, {"location": "Hack"}, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_duplicate_serial_same_company_rejected(self) -> None:
        Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-DUP",
            daily_working_hours=8,
            location="Planta 1",
        )
        self.client.force_authenticate(self.user_servicios)
        resp = self.client.post(
            self.url,
            self._payload(serial_number="SN-DUP"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("serial_number", resp.data)

    def test_ventas_can_get_but_not_post(self) -> None:
        Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-READ",
            daily_working_hours=8,
            location="Planta 1",
        )
        self.client.force_authenticate(self.user_ventas)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        post_resp = self.client.post(self.url, self._payload(serial_number="SN-V"), format="json")
        self.assertEqual(post_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_without_contact_in_company_rejected(self) -> None:
        orphan = Client.objects.create(ruc="20999999999", name="Sin vínculo")
        self.client.force_authenticate(self.user_servicios)
        resp = self.client.post(
            self.url,
            self._payload(client=orphan.pk, serial_number="SN-ORPHAN"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("client", resp.data)

    def test_filter_by_status_and_client(self) -> None:
        m1 = Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="A",
            serial_number="SN-F1",
            daily_working_hours=8,
            location="L1",
            status=Machine.Status.ACTIVE,
        )
        Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="B",
            serial_number="SN-F2",
            daily_working_hours=8,
            location="L2",
            status=Machine.Status.OUT_OF_SERVICE,
        )
        self.client.force_authenticate(self.user_servicios)
        resp = self.client.get(self.url, {"status": "ACTIVE", "client_id": self.client_a.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["id"], m1.pk)

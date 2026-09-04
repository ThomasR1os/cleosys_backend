from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from core.models import Brand, CategoryProduct, Client, SubcategoryProduct, SubcategoryRecommendedPart
from ventas.models import ClientContact

from .models import Machine, MachineElectricalEvaluation, MachineReport, MachineReportPartCheck

User = get_user_model()


def _sync_pk_sequence(table: str) -> None:
    """Avoid PK collisions with seeded rows when using --keepdb on Postgres."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "GREATEST(COALESCE((SELECT MAX(id) FROM " + table + "), 1), 1))",
            [table],
        )


class MachineAPITests(APITestCase):
    def setUp(self) -> None:
        _sync_pk_sequence("company")
        _sync_pk_sequence("client")
        _sync_pk_sequence("auth_user")

        self.company_a = Company.objects.create(name="Servicios Co A")
        self.company_b = Company.objects.create(name="Servicios Co B")
        self.client_a = Client.objects.create(ruc="20100000001", name="Cliente A")
        self.client_b = Client.objects.create(ruc="20100000002", name="Cliente B")
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

    def _electrical_payload(self, **overrides):
        data = {
            "nominal_voltage": "380V",
            "actual_voltage": {"l1_l2": "379.50", "l2_l3": "381.00", "l3_l1": "380.20"},
            "main_motor_current": {"l1": "12.40", "l2": "12.10", "l3": "12.60"},
            "fan_motor_current": {"l1": "2.10", "l2": "2.00", "l3": "2.20"},
            "starter_type": "VSD",
            "starter_brand": "ABB",
            "control_voltage": "24_VDC",
            "grounding": "OK",
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
        self.assertIsNone(create_resp.data["electrical_evaluation"])
        self.assertNotIn("voltage", create_resp.data)

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

    def test_create_with_nested_electrical_evaluation(self) -> None:
        self.client.force_authenticate(self.user_servicios)
        resp = self.client.post(
            self.url,
            self._payload(
                serial_number="SN-ELEC",
                electrical_evaluation=self._electrical_payload(),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        ev = resp.data["electrical_evaluation"]
        self.assertIsNotNone(ev)
        from decimal import Decimal

        self.assertEqual(ev["nominal_voltage"], "380V")
        self.assertEqual(ev["starter_type"], "VSD")
        self.assertEqual(Decimal(ev["actual_voltage"]["l1_l2"]), Decimal("379.50"))
        self.assertEqual(Decimal(ev["main_motor_current"]["l1"]), Decimal("12.40"))
        self.assertTrue(
            MachineElectricalEvaluation.objects.filter(machine_id=resp.data["id"]).exists()
        )

    def test_electrical_evaluation_endpoint_upsert(self) -> None:
        machine = Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-EP",
            daily_working_hours=8,
            location="Planta 1",
        )
        url = f"{self.url}{machine.pk}/electrical-evaluation/"
        self.client.force_authenticate(self.user_servicios)

        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
        self.assertIsNone(self.client.get(url).data)

        put_resp = self.client.put(url, self._electrical_payload(), format="json")
        self.assertEqual(put_resp.status_code, status.HTTP_200_OK, put_resp.data)
        self.assertEqual(put_resp.data["control_voltage"], "24_VDC")

        patch_resp = self.client.patch(url, {"grounding": "Revisar"}, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["grounding"], "Revisar")
        self.assertEqual(patch_resp.data["nominal_voltage"], "380V")

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

    def test_upload_plate_requires_file(self) -> None:
        machine = Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-PLATE",
            daily_working_hours=8,
            location="Planta 1",
        )
        self.client.force_authenticate(self.user_servicios)
        resp = self.client.post(f"{self.url}{machine.pk}/upload_plate/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", resp.data)

    def test_upload_plate_updates_url(self) -> None:
        from unittest.mock import patch

        machine = Machine.objects.create(
            company=self.company_a,
            client=self.client_a,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-PLATE2",
            daily_working_hours=8,
            location="Planta 1",
        )
        self.client.force_authenticate(self.user_servicios)
        with patch(
            "servicios.views.upload_product_image",
            return_value={"secure_url": "https://cdn.example.com/plates/new.jpg"},
        ):
            from django.core.files.uploadedfile import SimpleUploadedFile

            upload = SimpleUploadedFile("plate.jpg", b"fake-image", content_type="image/jpeg")
            resp = self.client.post(
                f"{self.url}{machine.pk}/upload_plate/",
                {"file": upload},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["plate_image_url"], "https://cdn.example.com/plates/new.jpg")
        machine.refresh_from_db()
        self.assertEqual(machine.plate_image_url, "https://cdn.example.com/plates/new.jpg")

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


class MachineReportAPITests(APITestCase):
    def setUp(self) -> None:
        _sync_pk_sequence("company")
        _sync_pk_sequence("client")
        _sync_pk_sequence("auth_user")

        self.company = Company.objects.create(name="Reports Co")
        self.client_obj = Client.objects.create(ruc="20111111111", name="Cliente Reports")
        self.brand = Brand.objects.get(pk=1)
        self.user = User.objects.create_user(
            username="servicios_reports",
            password="pass12345",
            first_name="Ana",
            last_name="Tec",
        )
        UserProfile.objects.create(
            user=self.user,
            company=self.company,
            role=UserProfile.Role.SERVICIOS,
        )
        ClientContact.objects.create(
            contact_first_name="Contact",
            contact_last_name="One",
            email="c@r.com",
            client=self.client_obj,
            user=self.user,
            company=self.company,
        )
        self.machine = Machine.objects.create(
            company=self.company,
            client=self.client_obj,
            brand=self.brand,
            model="SRPQ-20",
            serial_number="SN-REP-1",
            daily_working_hours=8,
            current_hour_meter=1000,
            location="Planta 1",
        )
        self.url = "/api/servicios/reports/"

    def _eval_payload(self, **overrides):
        data = {
            "type": MachineReport.ReportType.EVALUATION,
            "machine": self.machine.pk,
            "intervention_date": "2026-08-30",
            "hour_meter": 4520,
            "current_condition": MachineReport.CurrentCondition.OPERATIONAL,
            "background": "Ruido en compresor.",
            "conclusions": "Fuga menor.",
            "recommendations": "Programar servicio.",
        }
        data.update(overrides)
        return data

    def test_create_evaluation_syncs_hour_meter_to_machine(self) -> None:
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.url, self._eval_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["type"], "EVALUATION")
        self.assertIsNone(resp.data["origin_report"])
        self.assertEqual(resp.data["created_by"], self.user.pk)
        self.assertEqual(resp.data["created_by_name"], "Ana Tec")
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.current_hour_meter, 4520)

    def test_create_service_from_evaluation(self) -> None:
        self.client.force_authenticate(self.user)
        eval_resp = self.client.post(self.url, self._eval_payload(hour_meter=4100), format="json")
        self.assertEqual(eval_resp.status_code, status.HTTP_201_CREATED, eval_resp.data)

        service_resp = self.client.post(
            self.url,
            {
                "type": MachineReport.ReportType.SERVICE,
                "machine": self.machine.pk,
                "origin_report": eval_resp.data["id"],
                "intervention_date": "2026-09-05",
                "hour_meter": 4680,
                "current_condition": MachineReport.CurrentCondition.OPERATIONAL,
                "background": "Seguimiento.",
                "conclusions": "Reparación OK.",
                "recommendations": "Revisión en 500 h.",
            },
            format="json",
        )
        self.assertEqual(service_resp.status_code, status.HTTP_201_CREATED, service_resp.data)
        self.assertEqual(service_resp.data["origin_report"], eval_resp.data["id"])
        self.assertEqual(service_resp.data["origin_report_type"], "EVALUATION")
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.current_hour_meter, 4680)

    def test_evaluation_cannot_have_origin(self) -> None:
        self.client.force_authenticate(self.user)
        origin = MachineReport.objects.create(
            type=MachineReport.ReportType.EVALUATION,
            machine=self.machine,
            intervention_date="2026-08-01",
            current_condition=MachineReport.CurrentCondition.OPERATIONAL,
            created_by=self.user,
        )
        resp = self.client.post(
            self.url,
            self._eval_payload(origin_report=origin.pk),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("origin_report", resp.data)

    def test_origin_must_be_same_machine_and_evaluation(self) -> None:
        other = Machine.objects.create(
            company=self.company,
            client=self.client_obj,
            brand=self.brand,
            model="Other",
            serial_number="SN-REP-2",
            daily_working_hours=8,
            location="Planta 2",
        )
        foreign_eval = MachineReport.objects.create(
            type=MachineReport.ReportType.EVALUATION,
            machine=other,
            intervention_date="2026-08-01",
            current_condition=MachineReport.CurrentCondition.OPERATIONAL,
            created_by=self.user,
        )
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            self.url,
            {
                "type": MachineReport.ReportType.SERVICE,
                "machine": self.machine.pk,
                "origin_report": foreign_eval.pk,
                "intervention_date": "2026-09-05",
                "current_condition": MachineReport.CurrentCondition.OPERATIONAL,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("origin_report", resp.data)

    def test_list_filter_and_machine_nested_reports(self) -> None:
        self.client.force_authenticate(self.user)
        self.client.post(self.url, self._eval_payload(), format="json")
        list_resp = self.client.get(self.url, {"machine_id": self.machine.pk, "type": "EVALUATION"})
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data), 1)

        nested = self.client.get(f"/api/servicios/machines/{self.machine.pk}/reports/")
        self.assertEqual(nested.status_code, status.HTTP_200_OK)
        self.assertEqual(len(nested.data), 1)

    def test_patch_hour_meter_updates_machine(self) -> None:
        self.client.force_authenticate(self.user)
        create = self.client.post(self.url, self._eval_payload(hour_meter=2000), format="json")
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.data)
        patch = self.client.patch(
            f"{self.url}{create.data['id']}/",
            {"hour_meter": 2100},
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK, patch.data)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.current_hour_meter, 2100)

    def test_hour_meter_cannot_be_less_than_machine(self) -> None:
        self.machine.current_hour_meter = 5000
        self.machine.save(update_fields=["current_hour_meter"])
        self.client.force_authenticate(self.user)

        too_low = self.client.post(
            self.url,
            self._eval_payload(hour_meter=4999),
            format="json",
        )
        self.assertEqual(too_low.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hour_meter", too_low.data)

        equal_ok = self.client.post(
            self.url,
            self._eval_payload(hour_meter=5000),
            format="json",
        )
        self.assertEqual(equal_ok.status_code, status.HTTP_201_CREATED, equal_ok.data)

    def test_part_checks_notes_null_is_accepted(self) -> None:
        category = CategoryProduct.objects.get(pk=1)
        subcategory = SubcategoryProduct.objects.filter(category=category).first()
        self.assertIsNotNone(subcategory)
        self.machine.category = category
        self.machine.subcategory = subcategory
        self.machine.save(update_fields=["category", "subcategory"])

        self.client.force_authenticate(self.user)
        part = SubcategoryRecommendedPart.objects.create(
            subcategory=subcategory,
            name="Filtro aceite",
            sort_order=1,
        )
        resp = self.client.post(
            self.url,
            self._eval_payload(
                hour_meter=5150,
                part_checks=[
                    {
                        "recommended_part": part.pk,
                        "condition": MachineReportPartCheck.Condition.OK,
                        "part_number": None,
                        "notes": None,
                    }
                ],
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        row = resp.data["part_checks"][0]
        self.assertEqual(row["notes"], "")
        self.assertEqual(row["part_number"], "")

    def test_evaluation_part_checks_replace_requires_part_number(self) -> None:
        category = CategoryProduct.objects.get(pk=1)
        subcategory = SubcategoryProduct.objects.filter(category=category).first()
        self.assertIsNotNone(subcategory)
        self.machine.category = category
        self.machine.subcategory = subcategory
        self.machine.save(update_fields=["category", "subcategory"])

        part = SubcategoryRecommendedPart.objects.create(
            subcategory=subcategory,
            name="Sello eje",
            sort_order=1,
        )
        self.client.force_authenticate(self.user)

        bad = self.client.post(
            self.url,
            self._eval_payload(
                hour_meter=5100,
                work_performed="Inspección checklist",
                part_checks=[
                    {
                        "recommended_part": part.pk,
                        "condition": MachineReportPartCheck.Condition.REPLACE,
                        "part_number": "",
                    }
                ],
            ),
            format="json",
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

        part2 = SubcategoryRecommendedPart.objects.create(
            subcategory=subcategory,
            name="Filtro",
            sort_order=2,
        )
        ok = self.client.post(
            self.url,
            self._eval_payload(
                hour_meter=5200,
                work_performed="Inspección checklist",
                part_checks=[
                    {
                        "recommended_part": part.pk,
                        "condition": MachineReportPartCheck.Condition.REPLACE,
                        "part_number": "PN-12345",
                        "notes": "Desgaste",
                    },
                    {
                        "recommended_part": part2.pk,
                        "condition": MachineReportPartCheck.Condition.OK,
                    },
                ],
            ),
            format="json",
        )
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.data)
        self.assertEqual(len(ok.data["part_checks"]), 2)
        replace_row = next(
            r for r in ok.data["part_checks"] if r["condition"] == "REPLACE"
        )
        self.assertEqual(replace_row["part_number"], "PN-12345")

    def test_optional_photos_on_report(self) -> None:
        from .models import MachineReportPhoto

        self.client.force_authenticate(self.user)
        resp = self.client.post(
            self.url,
            self._eval_payload(
                hour_meter=5300,
                photos=[
                    {
                        "photo_url": "https://cdn.example.com/before.jpg",
                        "label": MachineReportPhoto.Label.BEFORE,
                        "note": "Estado inicial",
                        "sort_order": 0,
                    },
                    {
                        "photo_url": "https://cdn.example.com/after.jpg",
                        "label": MachineReportPhoto.Label.AFTER,
                        "note": "",
                        "sort_order": 1,
                    },
                ],
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(len(resp.data["photos"]), 2)
        self.assertEqual(resp.data["photos"][0]["label"], "BEFORE")

        list_photos = self.client.get(f"{self.url}{resp.data['id']}/photos/")
        self.assertEqual(list_photos.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_photos.data), 2)

    def test_correlativo_and_electrical_sync_to_machine(self) -> None:
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            self.url,
            self._eval_payload(
                hour_meter=5400,
                electrical_evaluation={
                    "nominal_voltage": "380V",
                    "actual_voltage": {"l1_l2": "379.50", "l2_l3": "381.00", "l3_l1": "380.20"},
                    "starter_type": "VSD",
                    "starter_brand": "ABB",
                    "control_voltage": "24_VDC",
                    "grounding": "OK",
                },
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(resp.data["correlativo"].startswith(f"{self.company.pk}-EVA-"))
        self.assertIsNotNone(resp.data["electrical_evaluation"])
        self.assertEqual(resp.data["electrical_evaluation"]["nominal_voltage"], "380V")

        from .models import MachineElectricalEvaluation

        machine_ev = MachineElectricalEvaluation.objects.get(machine=self.machine)
        self.assertEqual(machine_ev.nominal_voltage, "380V")
        self.assertEqual(machine_ev.starter_type, "VSD")

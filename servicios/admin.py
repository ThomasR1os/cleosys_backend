from django.contrib import admin

from .models import (
    Machine,
    MachineElectricalEvaluation,
    MachineReport,
    MachineReportPartCheck,
    MachineReportPhoto,
    ReportElectricalEvaluation,
)


class MachineElectricalEvaluationInline(admin.StackedInline):
    model = MachineElectricalEvaluation
    extra = 0
    max_num = 1


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "client",
        "brand",
        "category",
        "subcategory",
        "model",
        "serial_number",
        "status",
        "location",
    )
    list_filter = ("status", "company", "brand", "category")
    search_fields = ("serial_number", "model", "location")
    raw_id_fields = ("company", "client", "brand", "category", "subcategory")
    inlines = [MachineElectricalEvaluationInline]


@admin.register(MachineElectricalEvaluation)
class MachineElectricalEvaluationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "machine",
        "nominal_voltage",
        "starter_type",
        "control_voltage",
    )
    list_filter = ("nominal_voltage", "starter_type", "control_voltage")
    raw_id_fields = ("machine",)


class MachineReportPartCheckInline(admin.TabularInline):
    model = MachineReportPartCheck
    extra = 0
    raw_id_fields = ("recommended_part",)


class MachineReportPhotoInline(admin.TabularInline):
    model = MachineReportPhoto
    extra = 0


class ReportElectricalEvaluationInline(admin.StackedInline):
    model = ReportElectricalEvaluation
    extra = 0
    max_num = 1


@admin.register(MachineReport)
class MachineReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "correlativo",
        "type",
        "machine",
        "intervention_date",
        "current_condition",
        "hour_meter",
        "created_by",
    )
    list_filter = ("type", "current_condition", "intervention_date")
    search_fields = (
        "correlativo",
        "background",
        "conclusions",
        "recommendations",
        "work_performed",
    )
    raw_id_fields = ("machine", "origin_report", "created_by")
    inlines = [
        ReportElectricalEvaluationInline,
        MachineReportPartCheckInline,
        MachineReportPhotoInline,
    ]

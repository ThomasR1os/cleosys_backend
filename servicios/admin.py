from django.contrib import admin

from .models import Machine


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "client",
        "brand",
        "model",
        "serial_number",
        "status",
        "location",
    )
    list_filter = ("status", "company", "brand")
    search_fields = ("serial_number", "model", "location")
    raw_id_fields = ("company", "client", "brand")

from django.contrib import admin

from .models import Company, CompanyBranding


class CompanyBrandingInline(admin.StackedInline):
    model = CompanyBranding
    extra = 0
    max_num = 1
    can_delete = True


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    inlines = (CompanyBrandingInline,)


@admin.register(CompanyBranding)
class CompanyBrandingAdmin(admin.ModelAdmin):
    list_display = ("company", "primary", "emphasis_bar")
    raw_id_fields = ("company",)

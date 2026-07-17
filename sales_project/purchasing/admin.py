from django.contrib import admin
from .models import Purchase, PurchaseDetail


class PurchaseDetailInline(admin.TabularInline):
    model = PurchaseDetail
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'supplier', 'document_number', 'purchase_date', 'total']
    inlines = [PurchaseDetailInline]

    def get_readonly_fields(self, request, obj=None):
        """Segunda capa de protección (la primera es Purchase.save(), ver
        modelo) — mismo criterio que InvoiceAdmin (billing/admin.py)."""
        if obj is not None and obj.estado == 'PAGADA':
            return [f.name for f in self.model._meta.fields if f.name != 'id']
        return super().get_readonly_fields(request, obj)

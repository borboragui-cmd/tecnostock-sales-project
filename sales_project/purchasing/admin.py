from django.contrib import admin
from .models import Purchase, PurchaseDetail


class PurchaseDetailInline(admin.TabularInline):
    model = PurchaseDetail
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'supplier', 'document_number', 'purchase_date', 'total']
    inlines = [PurchaseDetailInline]

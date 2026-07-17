# Register your models here.
from django.contrib import admin
from .models import *

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    search_fields = ['name']
    list_filter = ['is_active']

@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_name', 'email', 'is_active']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'group', 'unit_price', 'stock']
    list_filter = ['brand', 'group']
    filter_horizontal = ['suppliers']

class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    extra = 0; can_delete = False

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['dni', 'last_name', 'first_name', 'email']
    inlines = [CustomerProfileInline]

class InvoiceDetailInline(admin.TabularInline):
    model = InvoiceDetail; extra = 1

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'invoice_date', 'total']
    inlines = [InvoiceDetailInline]

    def get_readonly_fields(self, request, obj=None):
        """Segunda capa de protección (la primera es Invoice.save(), ver
        modelo) — auditoría 2026-07-17: una factura PAGADA no debe poder
        editarse tampoco desde el admin. Todos los campos quedan de solo
        lectura, no solo los inmutables, para que el admin funcione como
        vista de consulta y no de edición sobre facturas cerradas."""
        if obj is not None and obj.estado == 'PAGADA':
            return [f.name for f in self.model._meta.fields if f.name != 'id']
        return super().get_readonly_fields(request, obj)

 
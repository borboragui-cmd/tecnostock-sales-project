from django.contrib import admin
from .models import CuotaVenta, PagoCuotaVenta


class PagoCuotaVentaInline(admin.TabularInline):
    model = PagoCuotaVenta
    extra = 0
    readonly_fields = ['fecha', 'valor', 'observacion']
    can_delete = False


@admin.register(CuotaVenta)
class CuotaVentaAdmin(admin.ModelAdmin):
    list_display = ['factura', 'numero', 'fecha_vencimiento', 'valor', 'saldo', 'estado']
    list_filter = ['estado', 'fecha_vencimiento']
    search_fields = ['factura__numero', 'factura__customer__last_name']
    inlines = [PagoCuotaVentaInline]


@admin.register(PagoCuotaVenta)
class PagoCuotaVentaAdmin(admin.ModelAdmin):
    list_display = ['cuota', 'fecha', 'valor']
    list_filter = ['fecha']

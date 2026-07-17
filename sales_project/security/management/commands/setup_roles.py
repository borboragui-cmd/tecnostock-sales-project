from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

ROLES = {
    # El Administrador recibe TODOS los permisos del sistema
    'Administrador': '__all__',

    # Vendedor: gestiona clientes, facturas, y el cobro de ventas a crédito.
    # NO puede tocar catálogo (brand/product/supplier) ni compras.
    'Vendedor': [
        'view_customer', 'add_customer', 'change_customer',
        'view_customerprofile', 'add_customerprofile', 'change_customerprofile',
        'view_invoice', 'add_invoice', 'change_invoice',
        'view_invoicedetail', 'add_invoicedetail', 'change_invoicedetail',
        'view_product',
        # Crédito de ventas: puede ver y cobrar cuotas, no las crea a mano
        # (se generan automáticamente vía generar_cuotas al facturar a crédito).
        'view_cuotaventa', 'change_cuotaventa',
        'view_pagocuotaventa', 'add_pagocuotaventa',
    ],

    # Analista de Compras: gestiona catálogo completo, proveedores, y el
    # ciclo de compras a crédito. NO toca clientes ni facturas de venta.
    'Analista de Compras': [
        'view_brand', 'add_brand', 'change_brand', 'delete_brand',
        'view_productgroup', 'add_productgroup', 'change_productgroup', 'delete_productgroup',
        'view_supplier', 'add_supplier', 'change_supplier', 'delete_supplier',
        'view_product', 'add_product', 'change_product', 'delete_product',
        'view_purchase', 'add_purchase', 'change_purchase', 'delete_purchase',
        'view_purchasedetail', 'add_purchasedetail', 'change_purchasedetail',
        # Crédito de compras: mismo criterio que Vendedor con creditos_ventas.
        'view_cuotacompra', 'change_cuotacompra',
        'view_pagocuotacompra', 'add_pagocuotacompra',
    ],
}


class Command(BaseCommand):
    help = 'Crea los 3 roles del sistema (Administrador, Vendedor, Analista de Compras) con sus permisos'

    def handle(self, *args, **kwargs):
        for role_name, codenames in ROLES.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if codenames == '__all__':
                perms = Permission.objects.all()
            else:
                perms = Permission.objects.filter(codename__in=codenames)
            group.permissions.set(perms)
            status = 'creado' if created else 'actualizado'
            self.stdout.write(self.style.SUCCESS(
                f'Rol "{role_name}" {status} con {perms.count()} permisos'
            ))

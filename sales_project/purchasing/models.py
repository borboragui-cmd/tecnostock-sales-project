from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from billing.models import Supplier, Product


class Purchase(models.Model):
    """Cabecera de compra. Documenta una adquisición a un proveedor."""
    numero = models.CharField(max_length=20, unique=True, blank=True, null=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchases'
    )
    document_number = models.CharField(
        max_length=20, verbose_name='N° Factura Proveedor'
    )
    purchase_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    tipo_pago = models.CharField(
        max_length=10, choices=[('CONTADO', 'CONTADO'), ('CREDITO', 'CREDITO')], default='CONTADO'
    )
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(
        max_length=15, choices=[('PENDIENTE', 'PENDIENTE'), ('PAGADA', 'PAGADA')], default='PENDIENTE'
    )

    class Meta:
        verbose_name = 'Purchase'
        verbose_name_plural = 'Purchases'
        ordering = ['-purchase_date']
        constraints = [
            models.UniqueConstraint(
                fields=['supplier', 'document_number'],
                name='unique_supplier_document'
            )
        ]

    def __str__(self):
        return f'Purchase #{self.numero or self.id} - {self.supplier}'

    # Campos financieros/identificatorios que ya no pueden cambiar una vez
    # que la compra quedó PAGADA — auditoría 2026-07-17, hallazgo crítico,
    # mismo criterio que Invoice.CAMPOS_INMUTABLES_SI_PAGADA (billing/models.py).
    CAMPOS_INMUTABLES_SI_PAGADA = ['numero', 'supplier_id', 'subtotal', 'tax', 'total', 'tipo_pago']

    def save(self, *args, **kwargs):
        """
        Guarda en dos fases: primero para obtener el pk (necesario para
        construir el número interno), luego actualiza solo ese campo.
        Mismo patrón que Invoice.numero (billing/models.py), con prefijo ORD-.

        Mismo chequeo de inmutabilidad que Invoice: si la compra YA existía
        en BD con estado=='PAGADA' (valor ANTES de este save), rechaza si
        algún campo de CAMPOS_INMUTABLES_SI_PAGADA cambió. La transición
        PENDIENTE->PAGADA (creditos_compras.services) no se ve afectada.
        """
        if self.pk:
            anterior = Purchase.objects.filter(pk=self.pk).values(
                'estado', *self.CAMPOS_INMUTABLES_SI_PAGADA
            ).first()
            if anterior and anterior['estado'] == 'PAGADA':
                for campo in self.CAMPOS_INMUTABLES_SI_PAGADA:
                    if getattr(self, campo) != anterior[campo]:
                        raise ValidationError(
                            'No se puede modificar una compra ya pagada.'
                        )

        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f'ORD-{self.pk:06d}'
            super().save(update_fields=['numero'])


class PurchaseDetail(models.Model):
    """Líneas de compra. Cada fila es un producto adquirido."""
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='details'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='purchase_details'
    )
    quantity = models.PositiveIntegerField(default=1)
    # unit_cost: precio que pagamos al proveedor por este producto (costo de compra).
    # NO confundir con Product.unit_price, que es el precio de venta al cliente.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Purchase Detail'
        verbose_name_plural = 'Purchase Details'
        ordering = ['id']

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    def save(self, *args, **kwargs):
        if self.unit_cost <= 0:
            raise ValidationError("El costo de compra debe ser mayor a 0")
        self.subtotal = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

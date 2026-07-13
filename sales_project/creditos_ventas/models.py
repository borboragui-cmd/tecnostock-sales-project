from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from billing.models import Invoice


class CuotaVenta(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'PENDIENTE'),
        ('PAGADA', 'PAGADA'),
    ]

    factura = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')

    class Meta:
        verbose_name = 'Cuota de Venta'
        verbose_name_plural = 'Cuotas de Venta'
        ordering = ['factura', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['factura', 'numero'], name='unique_cuota_numero_por_factura'),
            models.CheckConstraint(
                condition=models.Q(saldo__gte=0) & models.Q(saldo__lte=models.F('valor')),
                name='cuotaventa_saldo_valido',
            ),
        ]

    def __str__(self):
        return f'Cuota {self.numero} - Factura {self.factura.numero}'

    @property
    def esta_pagada(self):
        return self.estado == 'PAGADA'

    @property
    def esta_vencida(self):
        """True si la cuota sigue pendiente y ya pasó su fecha de vencimiento.
        No es un campo de BD nuevo, solo una bandera calculada para
        resaltar en pantalla y en reportes — no altera el schema pedido
        por el enunciado (que solo define PENDIENTE/PAGADA)."""
        return self.estado == 'PENDIENTE' and self.fecha_vencimiento < timezone.now().date()

    def interes_mora_actual(self, fecha=None):
        """Interés si se liquidara HOY (o en `fecha`). 0 si no está vencida.
        Prorratea TASA_MORA_DESCUENTO_MENSUAL linealmente por días de mora
        (mes = 30 días) sobre el saldo pendiente."""
        fecha = fecha or timezone.now().date()
        vencida = self.estado == 'PENDIENTE' and self.fecha_vencimiento < fecha
        if not vencida:
            return Decimal('0.00')
        dias_mora = (fecha - self.fecha_vencimiento).days
        meses_mora = Decimal(dias_mora) / Decimal(30)
        interes = self.saldo * settings.TASA_MORA_DESCUENTO_MENSUAL * meses_mora
        return interes.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def descuento_pronto_pago_actual(self, fecha=None):
        """Descuento si se liquidara HOY (o en `fecha`), antes del vencimiento.
        0 si ya está vencida o si fecha >= fecha_vencimiento. Prorratea
        TASA_MORA_DESCUENTO_MENSUAL linealmente por días de anticipo
        (mes = 30 días) sobre el valor nominal de la cuota."""
        fecha = fecha or timezone.now().date()
        if self.estado != 'PENDIENTE' or fecha >= self.fecha_vencimiento:
            return Decimal('0.00')
        dias_anticipo = (self.fecha_vencimiento - fecha).days
        meses_anticipo = Decimal(dias_anticipo) / Decimal(30)
        descuento = self.valor * settings.TASA_MORA_DESCUENTO_MENSUAL * meses_anticipo
        return descuento.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def monto_para_liquidar_hoy(self, fecha=None):
        """saldo + interes_mora_actual - descuento_pronto_pago_actual, nunca negativo."""
        monto = (
            self.saldo
            + self.interes_mora_actual(fecha)
            - self.descuento_pronto_pago_actual(fecha)
        )
        return max(monto, Decimal('0.00'))


class PagoCuotaVenta(models.Model):
    cuota = models.ForeignKey(CuotaVenta, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message='El pago debe ser mayor a cero.')]
    )
    interes_mora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_pronto_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observacion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Pago de Cuota'
        verbose_name_plural = 'Pagos de Cuotas'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota.numero} (Factura {self.cuota.factura.numero})'

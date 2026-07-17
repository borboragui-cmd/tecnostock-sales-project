from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class CuotaCompra(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'PENDIENTE'),
        ('PAGADA', 'PAGADA'),
    ]

    compra = models.ForeignKey('purchasing.Purchase', on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')

    class Meta:
        verbose_name = 'Cuota de Compra'
        verbose_name_plural = 'Cuotas de Compra'
        ordering = ['compra', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['compra', 'numero'], name='uq_cuotacompra_compra_numero'),
            models.CheckConstraint(
                condition=models.Q(saldo__gte=0) & models.Q(saldo__lte=models.F('valor')),
                name='ck_cuotacompra_saldo_rango',
            ),
        ]

    def __str__(self):
        return f'Cuota {self.numero} - Compra {self.compra.numero}'

    @property
    def esta_pagada(self):
        return self.estado == 'PAGADA'

    @property
    def esta_vencida(self):
        """True si la cuota sigue pendiente y ya pasó su fecha de vencimiento.
        No es un campo de BD nuevo, solo una bandera calculada — mismo
        criterio que CuotaVenta.esta_vencida en creditos_ventas."""
        return self.estado == 'PENDIENTE' and self.fecha_vencimiento < timezone.localdate()

    def interes_mora_actual(self, fecha=None):
        """Interés si se liquidara HOY (o en `fecha`). 0 si no está vencida.
        Prorratea TASA_MORA_DESCUENTO_MENSUAL linealmente por días de mora
        (mes = 30 días) sobre el saldo pendiente."""
        fecha = fecha or timezone.localdate()
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
        fecha = fecha or timezone.localdate()
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


class PagoCuotaCompra(models.Model):
    METODO_PAGO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('PAYPAL', 'PayPal'),
    ]

    cuota = models.ForeignKey(CuotaCompra, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message='El pago debe ser mayor a cero.')]
    )
    interes_mora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_pronto_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observacion = models.TextField(blank=True)
    metodo_pago = models.CharField(max_length=15, choices=METODO_PAGO_CHOICES, default='EFECTIVO')
    paypal_transaction_id = models.CharField(max_length=40, blank=True)

    class Meta:
        verbose_name = 'Pago de Cuota de Compra'
        verbose_name_plural = 'Pagos de Cuotas de Compra'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota.numero} (Compra {self.cuota.compra.numero})'

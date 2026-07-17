from django.db import models


class ComprobanteElectronico(models.Model):
    """Simulación de un comprobante electrónico SRI (factura o liquidación
    de compra). Sirve tanto a billing.Invoice como a purchasing.Purchase
    con un solo modelo — la lógica de clave de acceso/estados es idéntica
    para ambos, a diferencia de creditos_ventas/creditos_compras donde sí
    hay reglas de negocio distintas que justifican duplicar.

    NO implementa firma electrónica real (XAdES-BES) ni se conecta contra
    el SRI real ni sandbox — xml_firmado y firma_hash son una simulación,
    ver facturacion_electronica/services.py.
    """

    TIPO_COMPROBANTE_CHOICES = [
        ('01', 'Factura'),
        ('03', 'Liquidación de compra'),
    ]
    ESTADO_CHOICES = [
        ('BORRADOR', 'Borrador'),
        ('FIRMADO', 'Firmado'),
        ('ENVIADO', 'Enviado'),
        ('EN_PROCESAMIENTO', 'En procesamiento'),
        ('AUTORIZADO', 'Autorizado'),
        ('RECHAZADO', 'Rechazado'),
        ('DEVUELTO', 'Devuelto'),
    ]

    factura = models.ForeignKey(
        'billing.Invoice', null=True, blank=True,
        on_delete=models.PROTECT, related_name='comprobantes',
    )
    compra = models.ForeignKey(
        'purchasing.Purchase', null=True, blank=True,
        on_delete=models.PROTECT, related_name='comprobantes',
    )

    # Los 9 campos de la clave de acceso, guardados por separado para
    # trazabilidad/debug (además de la clave ya concatenada abajo).
    fecha_emision = models.DateField()
    tipo_comprobante = models.CharField(max_length=2, choices=TIPO_COMPROBANTE_CHOICES)
    ruc_emisor = models.CharField(max_length=13)
    tipo_ambiente = models.CharField(max_length=1, default='1')  # SIEMPRE 1 (pruebas) en este proyecto
    establecimiento = models.CharField(max_length=3, default='001')
    punto_emision = models.CharField(max_length=3, default='001')
    secuencial = models.CharField(max_length=9)  # correlativo por establecimiento+punto_emision+tipo, nunca se reutiliza
    codigo_numerico = models.CharField(max_length=8)  # aleatorio por comprobante
    tipo_emision = models.CharField(max_length=1, default='1')  # SIEMPRE 1 (normal) en este proyecto
    digito_verificador = models.CharField(max_length=1)

    clave_acceso = models.CharField(max_length=49, unique=True)

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='BORRADOR')

    # Simulación de firma electrónica — NO es una firma XAdES-BES real.
    xml_firmado = models.TextField(blank=True)
    firma_hash = models.CharField(max_length=64, blank=True)

    motivo_rechazo = models.TextField(blank=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_firmado = models.DateTimeField(null=True, blank=True)
    fecha_enviado = models.DateTimeField(null=True, blank=True)
    fecha_respuesta_sri = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Comprobante Electrónico'
        verbose_name_plural = 'Comprobantes Electrónicos'
        ordering = ['-fecha_creacion']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(factura__isnull=False, compra__isnull=True) |
                    models.Q(factura__isnull=True, compra__isnull=False)
                ),
                name='comprobante_exactamente_una_referencia',
            ),
        ]

    def __str__(self):
        origen = self.factura or self.compra
        return f'Comprobante {self.get_tipo_comprobante_display()} — {origen} ({self.estado})'

    @property
    def origen(self):
        """El Invoice o Purchase que dio origen a este comprobante."""
        return self.factura or self.compra

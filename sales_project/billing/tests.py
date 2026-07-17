from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.test import override_settings

from creditos_ventas import services
from .models import Customer, Invoice


class InvoiceInmutablePagadaTests(TestCase):
    """Auditoría 2026-07-17, hallazgo crítico: una Invoice ya PAGADA no
    debía poder cambiar de contenido financiero (total/subtotal/tax/
    tipo_pago/customer/numero), ni por ORM directo ni por Django Admin.
    Verificado que hoy (antes del fix) NO hay ninguna validación —
    reproducido acá con un test que debe fallar en rojo antes del fix y
    pasar en verde después, mismo patrón que el hallazgo de cédula."""

    def setUp(self):
        self.customer = Customer.objects.create(
            dni='0953187142', first_name='Inmutable', last_name='Test',
        )
        self.otro_customer = Customer.objects.create(
            dni='0953187143', first_name='Otro', last_name='Cliente',
        )

    def _crear_factura_pagada(self, total='100.00'):
        factura = Invoice.objects.create(customer=self.customer, total=Decimal(total))
        services.procesar_tipo_pago(factura, 'CONTADO')
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PAGADA')
        return factura

    # a) Reproduce el hallazgo exacto de la auditoría: modificar el total
    # de una factura PAGADA por ORM directo debe rechazarse.
    def test_no_se_puede_modificar_total_de_factura_pagada_por_orm(self):
        factura = self._crear_factura_pagada()
        factura.total = Decimal('9999.00')
        with self.assertRaises(ValidationError):
            factura.save()
        factura.refresh_from_db()
        self.assertEqual(factura.total, Decimal('100.00'))  # no se modificó

    # a-bis) Lo mismo para cada uno de los otros campos inmutables.
    def test_no_se_puede_modificar_subtotal_tax_tipo_pago_customer_numero(self):
        factura = self._crear_factura_pagada()
        numero_original = factura.numero

        factura.subtotal = Decimal('1.00')
        with self.assertRaises(ValidationError):
            factura.save()
        factura.refresh_from_db()

        factura.tax = Decimal('1.00')
        with self.assertRaises(ValidationError):
            factura.save()
        factura.refresh_from_db()

        factura.tipo_pago = 'CREDITO'
        with self.assertRaises(ValidationError):
            factura.save()
        factura.refresh_from_db()

        factura.customer = self.otro_customer
        with self.assertRaises(ValidationError):
            factura.save()
        factura.refresh_from_db()

        factura.numero = 'FAC-999999'
        with self.assertRaises(ValidationError):
            factura.save()
        factura.refresh_from_db()
        self.assertEqual(factura.numero, numero_original)

    # b) Una factura PENDIENTE (no pagada) se sigue pudiendo editar sin problema.
    def test_se_puede_modificar_una_factura_pendiente_sin_problema(self):
        factura = Invoice.objects.create(customer=self.customer, total=Decimal('50.00'))
        self.assertEqual(factura.estado, 'PENDIENTE')
        factura.total = Decimal('75.00')
        factura.save()  # no debe lanzar nada
        factura.refresh_from_db()
        self.assertEqual(factura.total, Decimal('75.00'))

    # c) La transición legítima PENDIENTE->PAGADA hecha por services.py
    # sigue funcionando sin excepción (CONTADO y vía pago de cuotas CREDITO).
    def test_transicion_pendiente_a_pagada_via_contado_sigue_funcionando(self):
        factura = Invoice.objects.create(customer=self.customer, total=Decimal('60.00'))
        services.procesar_tipo_pago(factura, 'CONTADO')  # no debe lanzar nada
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PAGADA')

    def test_transicion_pendiente_a_pagada_via_pago_de_cuotas_sigue_funcionando(self):
        factura = Invoice.objects.create(customer=self.customer, total=Decimal('100.00'))
        services.procesar_tipo_pago(factura, 'CREDITO', num_cuotas=1)
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PENDIENTE')

        cuota = factura.cuotas.first()
        from django.utils import timezone
        cuota.fecha_vencimiento = timezone.localdate()
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()

        services.registrar_pago(cuota.id, cuota.saldo)  # no debe lanzar nada
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PAGADA')

    # d) El admin de Django tampoco permite editar una factura pagada —
    # doble capa de protección, no solo el save() del modelo.
    def test_admin_no_permite_editar_factura_pagada(self):
        factura = self._crear_factura_pagada()
        admin_user = User.objects.create_superuser(
            username='admin_inmutable', password='x', email='admin_inmutable@test.com',
        )
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(admin_user)
            r = client.get(f'/admin/billing/invoice/{factura.pk}/change/')
            self.assertEqual(r.status_code, 200)
            # Los campos inmutables deben aparecer como texto plano
            # (readonly), no como <input>/<select> editable.
            html = r.content.decode()
            self.assertNotIn('name="total"', html)
            self.assertNotIn('name="tipo_pago"', html)

            r = client.post(f'/admin/billing/invoice/{factura.pk}/change/', {
                'total': '9999.00',
                'subtotal': '9999.00',
                'tax': '0.00',
                'customer': self.otro_customer.pk,
                'numero': 'FAC-999999',
                'is_active': 'on',
                'invoicedetail_set-TOTAL_FORMS': '0',
                'invoicedetail_set-INITIAL_FORMS': '0',
                'invoicedetail_set-MIN_NUM_FORMS': '0',
                'invoicedetail_set-MAX_NUM_FORMS': '1000',
            })
        factura.refresh_from_db()
        self.assertEqual(factura.total, Decimal('100.00'))  # no se modificó
        self.assertEqual(factura.customer_id, self.customer.pk)

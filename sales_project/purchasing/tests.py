from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.test import override_settings

from billing.models import Supplier
from creditos_compras import services
from .models import Purchase


class PurchaseInmutablePagadaTests(TestCase):
    """Auditoría 2026-07-17, hallazgo crítico: mismo criterio que
    billing.tests.InvoiceInmutablePagadaTests, espejado para Purchase
    (compras a proveedores). Ver Purchase.CAMPOS_INMUTABLES_SI_PAGADA en
    purchasing/models.py."""

    def setUp(self):
        self.supplier = Supplier.objects.create(name='Proveedor Inmutable Test')
        self.otro_supplier = Supplier.objects.create(name='Otro Proveedor')
        self._doc_counter = 0

    def _crear_compra_pagada(self, total='100.00'):
        self._doc_counter += 1
        compra = Purchase.objects.create(
            supplier=self.supplier,
            document_number=f'DOC-INM-{self._doc_counter:03d}',
            total=Decimal(total),
        )
        services.procesar_tipo_pago(compra, 'CONTADO')
        compra.refresh_from_db()
        self.assertEqual(compra.estado, 'PAGADA')
        return compra

    # a) Reproduce el hallazgo exacto de la auditoría, espejo de Invoice.
    def test_no_se_puede_modificar_total_de_compra_pagada_por_orm(self):
        compra = self._crear_compra_pagada()
        compra.total = Decimal('9999.00')
        with self.assertRaises(ValidationError):
            compra.save()
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('100.00'))

    # a-bis) Resto de campos inmutables.
    def test_no_se_puede_modificar_subtotal_tax_tipo_pago_supplier_numero(self):
        compra = self._crear_compra_pagada()
        numero_original = compra.numero

        compra.subtotal = Decimal('1.00')
        with self.assertRaises(ValidationError):
            compra.save()
        compra.refresh_from_db()

        compra.tax = Decimal('1.00')
        with self.assertRaises(ValidationError):
            compra.save()
        compra.refresh_from_db()

        compra.tipo_pago = 'CREDITO'
        with self.assertRaises(ValidationError):
            compra.save()
        compra.refresh_from_db()

        compra.supplier = self.otro_supplier
        with self.assertRaises(ValidationError):
            compra.save()
        compra.refresh_from_db()

        compra.numero = 'ORD-999999'
        with self.assertRaises(ValidationError):
            compra.save()
        compra.refresh_from_db()
        self.assertEqual(compra.numero, numero_original)

    # b) Una compra PENDIENTE se sigue pudiendo editar sin problema.
    def test_se_puede_modificar_una_compra_pendiente_sin_problema(self):
        compra = Purchase.objects.create(
            supplier=self.supplier, document_number='DOC-PEND-001', total=Decimal('50.00'),
        )
        self.assertEqual(compra.estado, 'PENDIENTE')
        compra.total = Decimal('75.00')
        compra.save()
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('75.00'))

    # c) Transiciones legítimas PENDIENTE->PAGADA siguen funcionando.
    def test_transicion_pendiente_a_pagada_via_contado_sigue_funcionando(self):
        compra = Purchase.objects.create(
            supplier=self.supplier, document_number='DOC-CONTADO-001', total=Decimal('60.00'),
        )
        services.procesar_tipo_pago(compra, 'CONTADO')
        compra.refresh_from_db()
        self.assertEqual(compra.estado, 'PAGADA')

    def test_transicion_pendiente_a_pagada_via_pago_de_cuotas_sigue_funcionando(self):
        compra = Purchase.objects.create(
            supplier=self.supplier, document_number='DOC-CREDITO-001', total=Decimal('100.00'),
        )
        services.procesar_tipo_pago(compra, 'CREDITO', num_cuotas=1)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, 'PENDIENTE')

        cuota = compra.cuotas.first()
        from django.utils import timezone
        cuota.fecha_vencimiento = timezone.localdate()
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()

        services.registrar_pago(cuota.id, cuota.saldo)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, 'PAGADA')

    # d) El admin de Django tampoco permite editar una compra pagada.
    def test_admin_no_permite_editar_compra_pagada(self):
        compra = self._crear_compra_pagada()
        admin_user = User.objects.create_superuser(
            username='admin_inmutable_compras', password='x', email='admin_inm_c@test.com',
        )
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(admin_user)
            r = client.get(f'/admin/purchasing/purchase/{compra.pk}/change/')
            self.assertEqual(r.status_code, 200)
            html = r.content.decode()
            self.assertNotIn('name="total"', html)
            self.assertNotIn('name="tipo_pago"', html)

            r = client.post(f'/admin/purchasing/purchase/{compra.pk}/change/', {
                'total': '9999.00',
                'subtotal': '9999.00',
                'tax': '0.00',
                'supplier': self.otro_supplier.pk,
                'document_number': compra.document_number,
                'numero': 'ORD-999999',
                'is_active': 'on',
                'purchasedetail_set-TOTAL_FORMS': '0',
                'purchasedetail_set-INITIAL_FORMS': '0',
                'purchasedetail_set-MIN_NUM_FORMS': '0',
                'purchasedetail_set-MAX_NUM_FORMS': '1000',
            })
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('100.00'))
        self.assertEqual(compra.supplier_id, self.supplier.pk)

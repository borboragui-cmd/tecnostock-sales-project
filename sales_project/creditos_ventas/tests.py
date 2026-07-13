import re
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.test import override_settings
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from billing.models import Customer
from billing.models import Invoice
from creditos_ventas.models import CuotaVenta, PagoCuotaVenta
from creditos_ventas import services


class CreditosVentasServicesTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            dni='0953187135', first_name='Juan', last_name='Perez',
        )

    def _crear_factura(self, total, tipo_pago='CREDITO'):
        factura = Invoice.objects.create(
            customer=self.customer,
            total=Decimal(total),
        )
        factura.tipo_pago = tipo_pago
        if tipo_pago == 'CREDITO':
            # Mismo efecto que procesar_tipo_pago() para CREDITO: sin esto,
            # factura.saldo queda en el default (0) y cualquier pago la
            # marcaría PAGADA de inmediato (criterio saldo<=0 en ventas).
            factura.estado = 'PENDIENTE'
            factura.saldo = factura.total
        factura.save(update_fields=['tipo_pago', 'estado', 'saldo'])
        return factura

    # 1. procesar_tipo_pago CONTADO -> saldo=0, estado=PAGADA inmediato.
    def test_procesar_tipo_pago_contado_cancela_de_inmediato(self):
        factura = self._crear_factura('150.00')
        services.procesar_tipo_pago(factura, 'CONTADO')
        factura.refresh_from_db()
        self.assertEqual(factura.tipo_pago, 'CONTADO')
        self.assertEqual(factura.saldo, Decimal('0.00'))
        self.assertEqual(factura.estado, 'PAGADA')

    # 2. generar_cuotas con total no divisible exacto -> suma exacta, última absorbe residuo.
    def test_generar_cuotas_residuo_en_ultima_cuota(self):
        factura = self._crear_factura('100.00')
        cuotas = services.generar_cuotas(factura, 3)
        self.assertEqual(len(cuotas), 3)
        self.assertEqual(cuotas[0].valor, Decimal('33.33'))
        self.assertEqual(cuotas[1].valor, Decimal('33.33'))
        self.assertEqual(cuotas[2].valor, Decimal('33.34'))
        suma = sum(c.valor for c in cuotas)
        self.assertEqual(suma, Decimal('100.00'))

    # 3. generar_cuotas rechaza num_cuotas=0 y negativos.
    def test_generar_cuotas_rechaza_num_cuotas_invalido(self):
        factura = self._crear_factura('100.00')
        with self.assertRaises(ValidationError):
            services.generar_cuotas(factura, 0)
        with self.assertRaises(ValidationError):
            services.generar_cuotas(factura, -1)

    # 4. generar_cuotas rechaza generar cuotas dos veces sobre la misma factura.
    def test_generar_cuotas_rechaza_duplicado(self):
        factura = self._crear_factura('100.00')
        services.generar_cuotas(factura, 2)
        with self.assertRaises(ValidationError):
            services.generar_cuotas(factura, 2)

    # 5. registrar_pago rechaza valor <= 0.
    def test_registrar_pago_rechaza_valor_no_positivo(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]
        with self.assertRaises(ValidationError):
            services.registrar_pago(cuota.id, Decimal('0'))
        with self.assertRaises(ValidationError):
            services.registrar_pago(cuota.id, Decimal('-10'))

    # 6. registrar_pago rechaza valor > monto de liquidación (sin mora, == saldo).
    def test_registrar_pago_rechaza_valor_mayor_a_liquidacion(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]
        with self.assertRaises(ValidationError):
            services.registrar_pago(cuota.id, cuota.saldo + Decimal('1'))

    # 7. registrar_pago rechaza pagos sobre una factura ya PAGADA.
    def test_registrar_pago_rechaza_factura_ya_pagada(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]
        services.registrar_pago(cuota.id, cuota.monto_para_liquidar_hoy())  # liquidación total
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PAGADA')

        otra_cuota = CuotaVenta.objects.create(
            factura=factura, numero=2, fecha_vencimiento=timezone.now().date(),
            valor=Decimal('10.00'), saldo=Decimal('10.00'),
        )
        with self.assertRaises(ValidationError):
            services.registrar_pago(otra_cuota.id, Decimal('5.00'))

    # 8. registrar_pago exige el pago mínimo en pagos parciales.
    @override_settings(PAGO_MINIMO_CUOTA=Decimal('5.00'))
    def test_registrar_pago_parcial_exige_minimo(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]  # saldo = 100.00
        with self.assertRaises(ValidationError):
            services.registrar_pago(cuota.id, Decimal('2.00'))  # < mínimo y < saldo

    # 9. registrar_pago: un pago parcial no puede superar el saldo de capital
    #    aunque el monto de liquidación sea mayor por mora (evita saldo negativo).
    def test_registrar_pago_parcial_no_supera_saldo_aunque_haya_mora(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]
        cuota.fecha_vencimiento = timezone.now().date() - timedelta(days=30)
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()

        monto_liquidacion = cuota.monto_para_liquidar_hoy()
        self.assertGreater(monto_liquidacion, cuota.saldo)  # hay mora

        pago_intermedio = cuota.saldo + Decimal('1.00')
        self.assertLessEqual(pago_intermedio, monto_liquidacion)
        with self.assertRaises(ValidationError):
            services.registrar_pago(cuota.id, pago_intermedio)

        pago = services.registrar_pago(cuota.id, monto_liquidacion)
        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, 'PAGADA')
        self.assertEqual(cuota.saldo, Decimal('0.00'))
        self.assertGreater(pago.interes_mora, Decimal('0.00'))

    # 10. registrar_pago: la fecha del pago siempre es hoy.
    def test_registrar_pago_fecha_siempre_es_hoy(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]
        pago = services.registrar_pago(cuota.id, cuota.monto_para_liquidar_hoy(), observacion='test')
        self.assertEqual(pago.fecha, timezone.localdate())

    # 11. registrar_pago sobre la última cuota pendiente deja la factura en PAGADA.
    def test_registrar_pago_ultima_cuota_marca_factura_pagada(self):
        factura = self._crear_factura('100.00')
        factura.estado = 'PENDIENTE'
        factura.saldo = factura.total
        factura.save(update_fields=['estado', 'saldo'])
        cuota1, cuota2 = services.generar_cuotas(factura, 2)

        services.registrar_pago(cuota1.id, cuota1.monto_para_liquidar_hoy())
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PENDIENTE')

        services.registrar_pago(cuota2.id, cuota2.monto_para_liquidar_hoy())
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'PAGADA')
        self.assertEqual(factura.saldo, Decimal('0.00'))

    # 12. registrar_pagos_multiples: si un pago del lote falla, ninguno se aplica.
    def test_registrar_pagos_multiples_todo_o_nada(self):
        factura = self._crear_factura('100.00')
        factura.estado = 'PENDIENTE'
        factura.saldo = factura.total
        factura.save(update_fields=['estado', 'saldo'])
        cuota1, cuota2 = services.generar_cuotas(factura, 2)

        pagos_data = [
            {'cuota_id': cuota1.id, 'valor': cuota1.monto_para_liquidar_hoy()},
            {'cuota_id': cuota2.id, 'valor': cuota2.saldo + Decimal('999')},  # inválido
        ]
        with self.assertRaises(ValidationError):
            services.registrar_pagos_multiples(pagos_data)

        cuota1.refresh_from_db()
        cuota2.refresh_from_db()
        factura.refresh_from_db()
        self.assertEqual(cuota1.saldo, cuota1.valor)  # sin cambios, se revirtió
        self.assertEqual(cuota2.saldo, cuota2.valor)
        self.assertEqual(factura.saldo, factura.total)
        self.assertFalse(PagoCuotaVenta.objects.filter(cuota=cuota1).exists())

    # 13. Eliminar una CuotaVenta con pagos registrados levanta ProtectedError.
    def test_eliminar_cuota_con_pagos_levanta_protected_error(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]
        services.registrar_pago(cuota.id, Decimal('10.00'))
        with self.assertRaises(ProtectedError):
            cuota.delete()

    # 14. Eliminar una Invoice con cuotas asociadas levanta ProtectedError.
    def test_eliminar_factura_con_cuotas_levanta_protected_error(self):
        factura = self._crear_factura('100.00')
        services.generar_cuotas(factura, 1)
        with self.assertRaises(ProtectedError):
            factura.delete()

    # 15. Cuota vencida hace 15 días, liquidada completa -> interés de mora
    #     exacto: saldo * 0.02 * (15/30).
    def test_liquidacion_total_cuota_vencida_15_dias_calcula_interes_exacto(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]  # saldo = 100.00
        cuota.fecha_vencimiento = timezone.localdate() - timedelta(days=15)
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()

        interes_esperado = (Decimal('100.00') * Decimal('0.02') * (Decimal(15) / Decimal(30))).quantize(Decimal('0.01'))
        self.assertEqual(interes_esperado, Decimal('1.00'))
        self.assertEqual(cuota.interes_mora_actual(), interes_esperado)

        monto_liquidacion = cuota.monto_para_liquidar_hoy()
        pago = services.registrar_pago(cuota.id, monto_liquidacion)
        self.assertEqual(pago.interes_mora, interes_esperado)
        self.assertEqual(pago.descuento_pronto_pago, Decimal('0.00'))
        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, 'PAGADA')

    # 16. Cuota con vencimiento en 20 días, liquidada hoy (pago anticipado)
    #     -> descuento por pronto pago exacto: valor * 0.02 * (20/30).
    def test_liquidacion_total_anticipada_20_dias_calcula_descuento_exacto(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]  # valor = saldo = 100.00
        cuota.fecha_vencimiento = timezone.localdate() + timedelta(days=20)
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()

        descuento_esperado = (Decimal('100.00') * Decimal('0.02') * (Decimal(20) / Decimal(30))).quantize(Decimal('0.01'))
        self.assertEqual(descuento_esperado, Decimal('1.33'))
        self.assertEqual(cuota.descuento_pronto_pago_actual(), descuento_esperado)

        monto_liquidacion = cuota.monto_para_liquidar_hoy()
        pago = services.registrar_pago(cuota.id, monto_liquidacion)
        self.assertEqual(pago.descuento_pronto_pago, descuento_esperado)
        self.assertEqual(pago.interes_mora, Decimal('0.00'))
        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, 'PAGADA')

    # 17. Pago parcial de una cuota vencida -> NO se aplica interés (1:1 sobre saldo).
    def test_pago_parcial_de_cuota_vencida_no_aplica_interes(self):
        factura = self._crear_factura('100.00')
        cuota = services.generar_cuotas(factura, 1)[0]  # saldo = 100.00
        cuota.fecha_vencimiento = timezone.localdate() - timedelta(days=10)
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()
        self.assertTrue(cuota.esta_vencida)

        pago = services.registrar_pago(cuota.id, Decimal('20.00'))  # parcial, < saldo
        self.assertEqual(pago.interes_mora, Decimal('0.00'))
        self.assertEqual(pago.descuento_pronto_pago, Decimal('0.00'))
        cuota.refresh_from_db()
        self.assertEqual(cuota.saldo, Decimal('80.00'))  # 1:1, sin interés
        self.assertEqual(cuota.estado, 'PENDIENTE')

    # 18. Pago parcial exactamente igual al saldo restante, cuando ese saldo
    #     es menor a PAGO_MINIMO_CUOTA -> se acepta igual.
    @override_settings(PAGO_MINIMO_CUOTA=Decimal('5.00'))
    def test_pago_parcial_igual_al_resto_bajo_minimo_se_acepta(self):
        factura = self._crear_factura('12.00')
        factura.estado = 'PENDIENTE'
        factura.saldo = factura.total
        factura.save(update_fields=['estado', 'saldo'])
        cuota = services.generar_cuotas(factura, 1)[0]  # saldo = 12.00
        cuota.fecha_vencimiento = timezone.localdate()  # vence hoy: sin mora/descuento
        cuota.save(update_fields=['fecha_vencimiento'])
        cuota.refresh_from_db()

        services.registrar_pago(cuota.id, Decimal('10.00'))  # parcial válido
        cuota.refresh_from_db()
        self.assertEqual(cuota.saldo, Decimal('2.00'))  # resto < PAGO_MINIMO_CUOTA (5.00)

        services.registrar_pago(cuota.id, Decimal('2.00'))
        cuota.refresh_from_db()
        self.assertEqual(cuota.saldo, Decimal('0.00'))
        self.assertEqual(cuota.estado, 'PAGADA')

    # 19. Un usuario autenticado NO-staff puede registrar pagos exitosamente.
    def test_usuario_no_staff_puede_registrar_pagos(self):
        no_staff = User.objects.create_user(username='no_staff_ventas', password='x', is_staff=False)
        factura = self._crear_factura('100.00')
        factura.estado = 'PENDIENTE'
        factura.saldo = factura.total
        factura.save(update_fields=['estado', 'saldo'])
        cuota = services.generar_cuotas(factura, 1)[0]
        cuota.fecha_vencimiento = timezone.localdate()
        cuota.save(update_fields=['fecha_vencimiento'])

        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(no_staff)

            r = client.get(f'/creditos/facturas/{factura.pk}/pagar/')
            html = r.content.decode()
            ids = re.findall(r'name="form-(\d+)-cuota_id" value="(\d+)"', html)
            self.assertTrue(ids)

            data = {
                'form-TOTAL_FORMS': str(len(ids)), 'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            }
            for idx, cuota_id in ids:
                data[f'form-{idx}-cuota_id'] = cuota_id
                data[f'form-{idx}-pagar'] = 'on'
                data[f'form-{idx}-valor'] = str(cuota.saldo)

            r = client.post(f'/creditos/facturas/{factura.pk}/pagar/', data, follow=True)
            self.assertEqual(r.status_code, 200)
            msgs = [str(m) for m in r.context['messages']]
            self.assertTrue(any('registrado' in m.lower() for m in msgs))
            self.assertFalse(any('staff' in m.lower() for m in msgs))

        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, 'PAGADA')

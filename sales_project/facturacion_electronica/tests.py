from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, Client
from django.test import override_settings

from billing.models import Customer, Invoice
from purchasing.models import Purchase, Supplier
from shared.validators import calcular_digito_verificador_clave_acceso
from . import services
from .models import ComprobanteElectronico


class CalcularDigitoVerificadorClaveAccesoTests(TestCase):
    """Módulo 11 de pesos cíclicos 2,3,4,5,6,7 sobre 48 dígitos (clave de
    acceso SRI) — algoritmo distinto al de validate_cedula_ec. Casos
    conocidos calculados a mano y confirmados antes de usar la función
    en el resto del flujo."""

    # 1. Único dígito significativo, el más a la derecha (peso=2):
    # total=1*2=2; residuo=2; resultado=11-2=9.
    def test_un_solo_digito_significativo(self):
        digits = '0' * 47 + '1'
        self.assertEqual(calcular_digito_verificador_clave_acceso(digits), 9)

    # 2. Los 48 dígitos en 1: cada ciclo completo de 6 pesos suma
    # 2+3+4+5+6+7=27, hay 8 ciclos exactos (48/6) -> total=216;
    # 216%11=7; resultado=11-7=4.
    def test_48_unos(self):
        digits = '1' * 48
        self.assertEqual(calcular_digito_verificador_clave_acceso(digits), 4)

    # 3. Todos ceros -> total=0, residuo=0, resultado=11-0=11 -> regla
    # especial: 11 se convierte en 0.
    def test_todos_ceros_da_verificador_cero_por_regla_especial(self):
        digits = '0' * 48
        self.assertEqual(calcular_digito_verificador_clave_acceso(digits), 0)

    # 4. Dígito significativo en una posición intermedia del ciclo (6ta
    # desde la derecha, peso=7): total=1*7=7; residuo=7; resultado=4.
    # Confirma que el offset del ciclo de pesos es el correcto, no solo
    # el caso trivial de la posición más a la derecha.
    def test_peso_del_ciclo_en_una_posicion_intermedia(self):
        digits = '0' * 42 + '100000'
        self.assertEqual(calcular_digito_verificador_clave_acceso(digits), 4)

    # 5. Rechaza una clave que no tiene exactamente 48 dígitos.
    def test_rechaza_longitud_invalida(self):
        with self.assertRaises(ValidationError):
            calcular_digito_verificador_clave_acceso('123')

    # 6. Rechaza caracteres no numéricos.
    def test_rechaza_caracteres_no_numericos(self):
        with self.assertRaises(ValidationError):
            calcular_digito_verificador_clave_acceso('a' * 48)


class ComprobanteElectronicoServiciosTests(TestCase):
    """Cobertura de facturacion_electronica/services.py: creación,
    unicidad de clave de acceso, transiciones de estado completas,
    secuencial que nunca se reutiliza, y forzar= restringido a
    Administrador/superuser."""

    def setUp(self):
        call_command('setup_roles', stdout=__import__('io').StringIO())
        self.customer = Customer.objects.create(
            dni='0953187138', first_name='Fact', last_name='Electronica',
        )
        self.supplier = Supplier.objects.create(name='Proveedor Facturación')
        self.admin = User.objects.create_user(username='admin_fe', password='x')
        self.admin.groups.add(Group.objects.get(name='Administrador'))
        self.vendedor = User.objects.create_user(username='vendedor_fe', password='x')
        self.vendedor.groups.add(Group.objects.get(name='Vendedor'))

    def _crear_factura(self):
        return Invoice.objects.create(customer=self.customer, total=100)

    def _crear_compra(self, doc='DOC-FE-001'):
        return Purchase.objects.create(supplier=self.supplier, document_number=doc, total=50)

    # 1. crear_comprobante(factura=...) genera una clave de 49 dígitos,
    # única, con tipo_comprobante='01'.
    def test_crear_comprobante_factura_genera_clave_valida(self):
        factura = self._crear_factura()
        comprobante = services.crear_comprobante(factura=factura)
        self.assertEqual(len(comprobante.clave_acceso), 49)
        self.assertTrue(comprobante.clave_acceso.isdigit())
        self.assertEqual(comprobante.tipo_comprobante, '01')
        self.assertEqual(comprobante.estado, 'BORRADOR')
        self.assertEqual(comprobante.ruc_emisor, '0992345675001')

    # 2. crear_comprobante(compra=...) usa tipo_comprobante='03'
    # (Liquidación de compra).
    def test_crear_comprobante_compra_usa_tipo_03(self):
        compra = self._crear_compra()
        comprobante = services.crear_comprobante(compra=compra)
        self.assertEqual(comprobante.tipo_comprobante, '03')

    # 3. Dos comprobantes (de facturas distintas) nunca comparten clave
    # de acceso — el campo unique=True de la BD lo respalda, pero acá se
    # confirma a nivel de negocio (código_numerico/secuencial distintos).
    def test_dos_comprobantes_tienen_claves_de_acceso_distintas(self):
        factura1 = self._crear_factura()
        factura2 = self._crear_factura()
        c1 = services.crear_comprobante(factura=factura1)
        c2 = services.crear_comprobante(factura=factura2)
        self.assertNotEqual(c1.clave_acceso, c2.clave_acceso)
        self.assertEqual(ComprobanteElectronico.objects.count(), 2)

    # 4. crear_comprobante rechaza generar un segundo comprobante activo
    # para la misma factura (mientras el primero no esté RECHAZADO/DEVUELTO).
    def test_crear_comprobante_rechaza_si_ya_hay_uno_activo(self):
        factura = self._crear_factura()
        services.crear_comprobante(factura=factura)
        with self.assertRaises(ValidationError):
            services.crear_comprobante(factura=factura)

    # 5. Flujo completo hasta AUTORIZADO (forzado por Administrador):
    # BORRADOR -> FIRMADO -> EN_PROCESAMIENTO -> AUTORIZADO, con
    # xml_firmado/firma_hash generados y timestamps en cada paso.
    def test_flujo_completo_hasta_autorizado(self):
        factura = self._crear_factura()
        comprobante = services.crear_comprobante(factura=factura)

        services.firmar(comprobante)
        self.assertEqual(comprobante.estado, 'FIRMADO')
        self.assertTrue(comprobante.xml_firmado)
        self.assertTrue(comprobante.firma_hash)
        self.assertIsNotNone(comprobante.fecha_firmado)

        services.enviar(comprobante)
        self.assertEqual(comprobante.estado, 'EN_PROCESAMIENTO')
        self.assertIsNotNone(comprobante.fecha_enviado)

        services.consultar_respuesta_sri(comprobante, forzar='AUTORIZADO', usuario=self.admin)
        self.assertEqual(comprobante.estado, 'AUTORIZADO')
        self.assertIsNotNone(comprobante.fecha_respuesta_sri)
        self.assertEqual(comprobante.motivo_rechazo, '')

    # 6. Flujo hasta RECHAZADO (forzado): motivo_rechazo se llena con un
    # mensaje real del catálogo de services.MOTIVOS_RECHAZO.
    def test_flujo_completo_hasta_rechazado_llena_motivo(self):
        factura = self._crear_factura()
        comprobante = services.crear_comprobante(factura=factura)
        services.firmar(comprobante)
        services.enviar(comprobante)
        services.consultar_respuesta_sri(comprobante, forzar='RECHAZADO', usuario=self.admin)

        self.assertEqual(comprobante.estado, 'RECHAZADO')
        self.assertIn(comprobante.motivo_rechazo, services.MOTIVOS_RECHAZO)

    # 7. Transiciones fuera de orden se rechazan (ej. firmar algo que ya
    # está FIRMADO, o enviar algo que sigue en BORRADOR).
    def test_transiciones_fuera_de_orden_se_rechazan(self):
        factura = self._crear_factura()
        comprobante = services.crear_comprobante(factura=factura)

        with self.assertRaises(ValidationError):
            services.enviar(comprobante)  # todavía en BORRADOR

        services.firmar(comprobante)
        with self.assertRaises(ValidationError):
            services.firmar(comprobante)  # ya no está en BORRADOR

    # 8. El secuencial NUNCA se reutiliza: si un comprobante es RECHAZADO,
    # el siguiente comprobante generado para el mismo origen (o cualquier
    # otro del mismo tipo) recibe un secuencial nuevo, consecutivo.
    def test_secuencial_no_se_reutiliza_tras_rechazo(self):
        factura = self._crear_factura()
        c1 = services.crear_comprobante(factura=factura)
        secuencial_1 = c1.secuencial

        services.firmar(c1)
        services.enviar(c1)
        services.consultar_respuesta_sri(c1, forzar='RECHAZADO', usuario=self.admin)
        self.assertEqual(c1.estado, 'RECHAZADO')

        # Ahora sí se puede generar uno nuevo para la misma factura,
        # porque el anterior ya no cuenta como "activo".
        c2 = services.crear_comprobante(factura=factura)
        self.assertNotEqual(c2.secuencial, secuencial_1)
        self.assertEqual(int(c2.secuencial), int(secuencial_1) + 1)
        self.assertNotEqual(c1.clave_acceso, c2.clave_acceso)

    # 9. forzar= está bloqueado para cualquier usuario que no sea
    # Administrador ni superusuario.
    def test_forzar_bloqueado_para_no_admin(self):
        factura = self._crear_factura()
        comprobante = services.crear_comprobante(factura=factura)
        services.firmar(comprobante)
        services.enviar(comprobante)

        with self.assertRaises(ValidationError):
            services.consultar_respuesta_sri(comprobante, forzar='AUTORIZADO', usuario=self.vendedor)

        comprobante.refresh_from_db()
        self.assertEqual(comprobante.estado, 'EN_PROCESAMIENTO')  # no cambió

    # 10. forzar= también está bloqueado sin usuario (None) — ej. si se
    # llamara el servicio sin pasar quién lo pide.
    def test_forzar_bloqueado_sin_usuario(self):
        factura = self._crear_factura()
        comprobante = services.crear_comprobante(factura=factura)
        services.firmar(comprobante)
        services.enviar(comprobante)

        with self.assertRaises(ValidationError):
            services.consultar_respuesta_sri(comprobante, forzar='AUTORIZADO', usuario=None)


class ComprobanteElectronicoVistasTests(TestCase):
    """Flujo completo por HTTP real: generar -> firmar -> enviar ->
    consultar, más el botón nuevo en invoice_detail.html."""

    def setUp(self):
        call_command('setup_roles', stdout=__import__('io').StringIO())
        self.customer = Customer.objects.create(
            dni='0953187139', first_name='Http', last_name='Test',
        )
        self.user = User.objects.create_user(username='fe_http_user', password='x')
        self.admin = User.objects.create_user(username='fe_http_admin', password='x')
        self.admin.groups.add(Group.objects.get(name='Administrador'))

    def test_flujo_completo_via_http_hasta_autorizado(self):
        factura = Invoice.objects.create(customer=self.customer, total=80)

        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.admin)

            r = client.post(f'/facturacion/facturas/{factura.pk}/generar/', follow=True)
            self.assertEqual(r.status_code, 200)
            comprobante = ComprobanteElectronico.objects.get(factura=factura)
            self.assertEqual(comprobante.estado, 'BORRADOR')

            r = client.post(f'/facturacion/comprobantes/{comprobante.pk}/firmar/', follow=True)
            self.assertEqual(r.status_code, 200)
            comprobante.refresh_from_db()
            self.assertEqual(comprobante.estado, 'FIRMADO')

            r = client.post(f'/facturacion/comprobantes/{comprobante.pk}/enviar/', follow=True)
            self.assertEqual(r.status_code, 200)
            comprobante.refresh_from_db()
            self.assertEqual(comprobante.estado, 'EN_PROCESAMIENTO')

            r = client.post(
                f'/facturacion/comprobantes/{comprobante.pk}/consultar/',
                {'forzar': 'AUTORIZADO'}, follow=True,
            )
            self.assertEqual(r.status_code, 200)
            comprobante.refresh_from_db()
            self.assertEqual(comprobante.estado, 'AUTORIZADO')

    # El botón "Generar comprobante electrónico" en invoice_detail.html
    # aparece cuando no hay comprobante, y el link "Ver comprobante"
    # cuando ya existe uno.
    def test_boton_generar_aparece_en_invoice_detail_sin_comprobante(self):
        factura = Invoice.objects.create(customer=self.customer, total=80)
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.user)
            r = client.get(f'/invoices/{factura.pk}/')
            self.assertContains(r, 'Generar comprobante electrónico')

    # Un usuario sin rol Administrador no puede forzar el resultado desde
    # la vista tampoco (bloqueado en services, la vista lo propaga como error).
    def test_vista_consultar_bloquea_forzar_para_no_admin(self):
        factura = Invoice.objects.create(customer=self.customer, total=80)
        comprobante = services.crear_comprobante(factura=factura)
        services.firmar(comprobante)
        services.enviar(comprobante)

        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.user)
            r = client.post(
                f'/facturacion/comprobantes/{comprobante.pk}/consultar/',
                {'forzar': 'AUTORIZADO'}, follow=True,
            )
            self.assertEqual(r.status_code, 200)
            msgs = [str(m) for m in r.context['messages']]
            self.assertTrue(any('administrador' in m.lower() for m in msgs))

        comprobante.refresh_from_db()
        self.assertEqual(comprobante.estado, 'EN_PROCESAMIENTO')

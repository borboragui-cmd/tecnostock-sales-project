import hashlib
import random
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from shared.validators import calcular_digito_verificador_clave_acceso
from .models import ComprobanteElectronico

ESTABLECIMIENTO = '001'
PUNTO_EMISION = '001'

MOTIVOS_RECHAZO = [
    'Clave de acceso ya registrada',
    'RUC del emisor no autorizado para este comprobante',
    'Firma electrónica inválida',
    'Secuencial ya fue registrado con anterioridad',
]
MOTIVOS_DEVOLUCION = [
    'XML no cumple esquema XSD del SRI',
    'Comprobante recibido fuera de la ventana de tiempo permitida',
]


def generar_clave_acceso(fecha_emision, tipo_comprobante, ruc_emisor, establecimiento, punto_emision, secuencial):
    """Arma los 9 campos de la clave de acceso SRI (48 dígitos) + el
    dígito verificador (módulo 11 de pesos cíclicos, ver
    shared.validators.calcular_digito_verificador_clave_acceso).
    tipo_ambiente y tipo_emision son SIEMPRE '1' en este proyecto
    (pruebas / normal) — nunca producción ni contingencia."""
    tipo_ambiente = '1'
    tipo_emision = '1'
    codigo_numerico = f'{secrets.randbelow(10 ** 8):08d}'

    campos_48 = (
        fecha_emision.strftime('%d%m%Y')
        + tipo_comprobante
        + ruc_emisor
        + tipo_ambiente
        + establecimiento
        + punto_emision
        + secuencial
        + codigo_numerico
        + tipo_emision
    )
    if len(campos_48) != 48:
        raise ValidationError(
            f'La clave de acceso quedó con {len(campos_48)} dígitos, se esperaban 48.'
        )

    digito_verificador = calcular_digito_verificador_clave_acceso(campos_48)
    clave_acceso = campos_48 + str(digito_verificador)

    return {
        'fecha_emision': fecha_emision,
        'tipo_comprobante': tipo_comprobante,
        'ruc_emisor': ruc_emisor,
        'tipo_ambiente': tipo_ambiente,
        'establecimiento': establecimiento,
        'punto_emision': punto_emision,
        'secuencial': secuencial,
        'codigo_numerico': codigo_numerico,
        'tipo_emision': tipo_emision,
        'digito_verificador': str(digito_verificador),
        'clave_acceso': clave_acceso,
    }


def _siguiente_secuencial(establecimiento, punto_emision, tipo_comprobante):
    """Correlativo por establecimiento+punto_emision+tipo_comprobante.
    Nunca se reutiliza: siempre es max(existente)+1, incluso si el último
    comprobante emitido con ese secuencial terminó RECHAZADO/DEVUELTO —
    para reintentar se emite un secuencial nuevo, no se reusa el viejo.
    select_for_update() evita que dos altas simultáneas generen el mismo
    secuencial (debe llamarse dentro de una transacción)."""
    ultimo = (
        ComprobanteElectronico.objects
        .select_for_update()
        .filter(
            establecimiento=establecimiento,
            punto_emision=punto_emision,
            tipo_comprobante=tipo_comprobante,
        )
        .order_by('-secuencial')
        .values_list('secuencial', flat=True)
        .first()
    )
    siguiente = int(ultimo) + 1 if ultimo else 1
    return f'{siguiente:09d}'


@transaction.atomic
def crear_comprobante(factura=None, compra=None):
    """Crea un ComprobanteElectronico en BORRADOR a partir de una Invoice
    (tipo 01, Factura) o una Purchase (tipo 03, Liquidación de compra).
    Exactamente uno de los dos debe venir. Rechaza si ya existe un
    comprobante activo (no RECHAZADO/DEVUELTO) para ese origen."""
    if (factura is None) == (compra is None):
        raise ValidationError('Debe indicarse exactamente uno: factura o compra.')

    tipo_comprobante = '01' if factura else '03'
    filtro_origen = {'factura': factura} if factura else {'compra': compra}

    ya_activo = ComprobanteElectronico.objects.filter(**filtro_origen).exclude(
        estado__in=['RECHAZADO', 'DEVUELTO']
    ).exists()
    if ya_activo:
        raise ValidationError(
            'Ya existe un comprobante electrónico activo para este comprobante de origen.'
        )

    secuencial = _siguiente_secuencial(ESTABLECIMIENTO, PUNTO_EMISION, tipo_comprobante)
    datos = generar_clave_acceso(
        fecha_emision=timezone.localdate(),
        tipo_comprobante=tipo_comprobante,
        ruc_emisor=settings.EMPRESA_RUC,
        establecimiento=ESTABLECIMIENTO,
        punto_emision=PUNTO_EMISION,
        secuencial=secuencial,
    )

    return ComprobanteElectronico.objects.create(
        factura=factura,
        compra=compra,
        estado='BORRADOR',
        **datos,
    )


def firmar(comprobante):
    """BORRADOR -> FIRMADO. Genera un XML simplificado (NO el esquema
    completo del SRI) y un hash simulado de firma — NO es una firma
    XAdES-BES real, no hay criptografía de certificado involucrada."""
    if comprobante.estado != 'BORRADOR':
        raise ValidationError(
            f'Solo se puede firmar un comprobante en BORRADOR (actual: {comprobante.estado}).'
        )

    xml_firmado = (
        '<comprobante>\n'
        f'  <claveAcceso>{comprobante.clave_acceso}</claveAcceso>\n'
        f'  <ruc>{comprobante.ruc_emisor}</ruc>\n'
        f'  <tipoComprobante>{comprobante.tipo_comprobante}</tipoComprobante>\n'
        f'  <fechaEmision>{comprobante.fecha_emision.strftime("%d/%m/%Y")}</fechaEmision>\n'
        '  <!-- Firma simulada — NO es XAdES-BES real, no hay certificado de firma electrónica -->\n'
        '</comprobante>'
    )
    firma_hash = hashlib.sha256(
        f'{xml_firmado}{timezone.now().isoformat()}'.encode()
    ).hexdigest()

    comprobante.xml_firmado = xml_firmado
    comprobante.firma_hash = firma_hash
    comprobante.estado = 'FIRMADO'
    comprobante.fecha_firmado = timezone.now()
    comprobante.save(update_fields=['xml_firmado', 'firma_hash', 'estado', 'fecha_firmado'])
    return comprobante


def enviar(comprobante):
    """FIRMADO -> ENVIADO -> EN_PROCESAMIENTO. Ambas transiciones en el
    mismo llamado — no hay nada async real que esperar en la simulación."""
    if comprobante.estado != 'FIRMADO':
        raise ValidationError(
            f'Solo se puede enviar un comprobante FIRMADO (actual: {comprobante.estado}).'
        )
    comprobante.estado = 'EN_PROCESAMIENTO'
    comprobante.fecha_enviado = timezone.now()
    comprobante.save(update_fields=['estado', 'fecha_enviado'])
    return comprobante


def consultar_respuesta_sri(comprobante, forzar=None, usuario=None):
    """EN_PROCESAMIENTO -> AUTORIZADO/RECHAZADO/DEVUELTO.
    Sin `forzar`: sortea el resultado según settings.SRI_SIMULACION_PROBABILIDADES.
    Con `forzar`: usa ese resultado exacto, pero solo si `usuario` es
    Administrador o superusuario (mismo criterio de bypass que
    shared.mixins.GroupRequiredMixin) — cualquier otro usuario que intente
    forzar un resultado recibe ValidationError."""
    if comprobante.estado != 'EN_PROCESAMIENTO':
        raise ValidationError(
            f'Solo se puede consultar un comprobante EN_PROCESAMIENTO (actual: {comprobante.estado}).'
        )

    if forzar is not None:
        es_admin = usuario is not None and (
            usuario.is_superuser or usuario.groups.filter(name='Administrador').exists()
        )
        if not es_admin:
            raise ValidationError('Solo un Administrador puede forzar el resultado de la simulación.')
        if forzar not in ('AUTORIZADO', 'RECHAZADO', 'DEVUELTO'):
            raise ValidationError(f'Resultado forzado no válido: {forzar}')
        resultado = forzar
    else:
        probabilidades = settings.SRI_SIMULACION_PROBABILIDADES
        resultado = random.choices(
            population=list(probabilidades.keys()),
            weights=list(probabilidades.values()),
            k=1,
        )[0]

    comprobante.estado = resultado
    comprobante.fecha_respuesta_sri = timezone.now()
    if resultado == 'RECHAZADO':
        comprobante.motivo_rechazo = random.choice(MOTIVOS_RECHAZO)
    elif resultado == 'DEVUELTO':
        comprobante.motivo_rechazo = random.choice(MOTIVOS_DEVOLUCION)

    comprobante.save(update_fields=['estado', 'fecha_respuesta_sri', 'motivo_rechazo'])
    return comprobante

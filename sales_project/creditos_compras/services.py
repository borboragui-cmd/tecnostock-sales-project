from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import CuotaCompra, PagoCuotaCompra


def procesar_tipo_pago(compra, tipo_pago, num_cuotas=None):
    """
    Aplica el tipo de pago elegido a una compra recién creada.
    CONTADO -> queda cancelada de inmediato.
    CREDITO -> queda pendiente y se generan las cuotas mensuales.
    """
    compra.tipo_pago = tipo_pago

    if tipo_pago == 'CONTADO':
        compra.saldo = Decimal('0.00')
        compra.estado = 'PAGADA'
        compra.save(update_fields=['tipo_pago', 'saldo', 'estado'])
        return

    if tipo_pago == 'CREDITO':
        if not num_cuotas or num_cuotas < 1:
            raise ValidationError('El número de cuotas debe ser al menos 1.')
        compra.saldo = compra.total
        compra.estado = 'PENDIENTE'
        compra.save(update_fields=['tipo_pago', 'saldo', 'estado'])
        generar_cuotas(compra, num_cuotas)
        return

    raise ValidationError(f'Tipo de pago no reconocido: {tipo_pago}')


@transaction.atomic
def generar_cuotas(compra, num_cuotas):
    """
    Divide el total en partes iguales; la ÚLTIMA cuota absorbe el residuo
    de redondeo para que la suma cuadre exacto con el total. Vencimientos
    mensuales a partir de la fecha de la compra.
    """
    if num_cuotas < 1:
        raise ValidationError('El número de cuotas debe ser al menos 1.')
    if compra.cuotas.exists():
        raise ValidationError('Esta compra ya tiene cuotas generadas.')

    valor_base = (compra.total / num_cuotas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    acumulado = Decimal('0.00')
    cuotas_creadas = []

    for i in range(1, num_cuotas + 1):
        if i < num_cuotas:
            valor_cuota = valor_base
            acumulado += valor_cuota
        else:
            valor_cuota = compra.total - acumulado  # última cuota absorbe el residuo

        cuota = CuotaCompra.objects.create(
            compra=compra,
            numero=i,
            fecha_vencimiento=compra.purchase_date.date() + relativedelta(months=i),
            valor=valor_cuota,
            saldo=valor_cuota,
        )
        cuotas_creadas.append(cuota)

    return cuotas_creadas


@transaction.atomic
def registrar_pago(cuota_id, valor, observacion=''):
    """
    Registra un pago sobre UNA cuota. La fecha de pago es SIEMPRE hoy
    (timezone.localdate()) — ya no se acepta como parámetro externo, ni
    siquiera fechas pasadas dentro del rango de la compra. select_for_update
    evita condiciones de carrera si dos pagos llegan casi simultáneos sobre
    la misma cuota.

    Dos modalidades de pago:
    - Liquidación total (valor == monto_para_liquidar_hoy): cancela la cuota
      por completo, aplicando el interés de mora o descuento por pronto
      pago que corresponda a la fecha de hoy.
    - Pago parcial (cualquier otro valor entre el mínimo y el saldo): abona
      1:1 sobre el saldo de capital, SIN interés ni descuento — por eso no
      puede superar `cuota.saldo`, aunque `monto_para_liquidar_hoy` sea
      mayor por mora (si no, el saldo quedaría negativo).
    """
    cuota = CuotaCompra.objects.select_for_update().select_related('compra').get(pk=cuota_id)

    if cuota.compra.estado == 'PAGADA':
        raise ValidationError('La compra ya está completamente pagada.')

    fecha_hoy = timezone.localdate()
    monto_liquidacion = cuota.monto_para_liquidar_hoy(fecha_hoy)
    interes = cuota.interes_mora_actual(fecha_hoy)
    descuento = cuota.descuento_pronto_pago_actual(fecha_hoy)

    if valor <= 0:
        raise ValidationError('El pago debe ser mayor a cero.')
    if valor > monto_liquidacion:
        raise ValidationError(
            f'El pago (${valor}) no puede superar el monto de liquidación '
            f'(${monto_liquidacion}), que incluye intereses de mora si aplica.'
        )

    es_liquidacion_total = (valor == monto_liquidacion)

    if not es_liquidacion_total:
        # Pago parcial: 1:1 sobre saldo, sin interés ni descuento. No puede
        # superar el saldo de capital aunque monto_liquidacion sea mayor
        # por mora (superarlo solo es válido como liquidación total exacta).
        if valor > cuota.saldo:
            raise ValidationError(
                f'Un pago parcial no puede superar el saldo de capital de la cuota '
                f'(${cuota.saldo}). Para pagar más que eso (incluye interés de mora), '
                f'debe ser exactamente el monto de liquidación total (${monto_liquidacion}).'
            )
        minimo_exigido = min(settings.PAGO_MINIMO_CUOTA, cuota.saldo)
        if valor < minimo_exigido:
            raise ValidationError(f'El pago mínimo permitido es ${minimo_exigido}.')
        capital_reducido = valor
        cuota.saldo = F('saldo') - valor
        interes_a_guardar = Decimal('0.00')
        descuento_a_guardar = Decimal('0.00')
    else:
        # Liquidación total: aplica interés/descuento calculados a hoy.
        capital_reducido = cuota.saldo
        cuota.saldo = 0
        cuota.estado = 'PAGADA'
        interes_a_guardar = interes
        descuento_a_guardar = descuento

    cuota.save()
    cuota.refresh_from_db()

    pago = PagoCuotaCompra.objects.create(
        cuota=cuota,
        fecha=fecha_hoy,
        valor=valor,
        observacion=observacion,
        interes_mora=interes_a_guardar,
        descuento_pronto_pago=descuento_a_guardar,
    )

    compra = cuota.compra
    compra.saldo = F('saldo') - capital_reducido
    compra.save(update_fields=['saldo'])
    compra.refresh_from_db()
    if not compra.cuotas.exclude(estado='PAGADA').exists():
        compra.estado = 'PAGADA'
        compra.save(update_fields=['estado'])

    return pago


@transaction.atomic
def registrar_pagos_multiples(pagos_data):
    """
    pagos_data: [{'cuota_id':.., 'valor':.., 'observacion':..}, ...]
    Todo o nada: si un pago del lote falla, se revierte el lote completo.
    La fecha de cada pago siempre es hoy (ver registrar_pago).
    """
    resultados = []
    for dato in pagos_data:
        pago = registrar_pago(
            cuota_id=dato['cuota_id'],
            valor=dato['valor'],
            observacion=dato.get('observacion', ''),
        )
        resultados.append(pago)
    return resultados
